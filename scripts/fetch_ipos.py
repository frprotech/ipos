#!/usr/bin/env python3
"""Fetch IPO / new-listing data from public exchange sources and write data/ipos.json.

Covered exchanges:
  - NASDAQ + NYSE (+ NYSE American)  via the Nasdaq IPO calendar API
  - TSX / TSX Venture                via tsx.com "Current listing activity" page
  - ASX                              via asx.com.au upcoming floats & listings
  - CSE                              via the CSE public securities feed

Each exchange fetcher is isolated: if one source fails or changes its markup,
the previous data for that exchange is kept and the rest still update.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "ipos.json"

TIMEOUT = 30
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

TODAY = dt.date.today()
# Keep listings from the past year plus anything upcoming.
KEEP_AFTER = TODAY - dt.timedelta(days=365)


def http_get(url: str, **kwargs) -> requests.Response:
    resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, **kwargs)
    resp.raise_for_status()
    return resp


def parse_date(value) -> str | None:
    """Best-effort parse of a date-ish value to ISO YYYY-MM-DD."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"tba", "tbd", "n/a", "-", "--"}:
        return None
    # Strip common noise: "(expected)" notes, footnote markers ("#"),
    # times ("12.00pm") and timezone tags, as seen on the ASX page.
    text = re.sub(r"\(.*?\)", " ", text)
    text = re.sub(r"#+", " ", text)
    text = re.sub(r"\b\d{1,2}[.:]\d{2}\s*(?:am|pm)?\b", " ", text, flags=re.I)
    text = re.sub(r"\b(?:AEST|AEDT|EST|EDT|ET|noon|midday)\b", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    try:
        return dateparser.parse(text, dayfirst=False, fuzzy=True).date().isoformat()
    except (ValueError, OverflowError):
        try:
            return dateparser.parse(text, dayfirst=True, fuzzy=True).date().isoformat()
        except (ValueError, OverflowError):
            return None


def record(exchange: str, company: str, ticker: str = "", listing_date: str | None = None,
           sector: str = "", status: str = "", source: str = "") -> dict | None:
    company = re.sub(r"\s+", " ", str(company or "")).strip()
    ticker = str(ticker or "").strip().upper()
    if not company:
        return None
    return {
        "company": company,
        "ticker": ticker,
        "exchange": exchange,
        "listing_date": listing_date,
        "sector": re.sub(r"\s+", " ", str(sector or "")).strip(),
        "status": status,
        "source": source,
        "fetched_at": TODAY.isoformat(),
    }


# ---------------------------------------------------------------------------
# NASDAQ + NYSE — Nasdaq's IPO calendar API covers all US listings and tags
# each deal with its proposed exchange.
# ---------------------------------------------------------------------------

def fetch_us() -> list[dict]:
    source = "https://www.nasdaq.com/market-activity/ipos"
    months = []
    cursor = TODAY.replace(day=1) - dt.timedelta(days=1)  # previous month
    cursor = cursor.replace(day=1)
    for _ in range(4):  # previous, current and next two months
        months.append(cursor.strftime("%Y-%m"))
        cursor = (cursor + dt.timedelta(days=32)).replace(day=1)

    def map_exchange(raw: str) -> str | None:
        raw = (raw or "").upper()
        if "NASDAQ" in raw:
            return "NASDAQ"
        if "AMERICAN" in raw or "AMEX" in raw:
            return "NYSE American"
        if "NYSE" in raw:
            return "NYSE"
        return None

    out: list[dict] = []
    for month in months:
        data = http_get(
            f"https://api.nasdaq.com/api/ipo/calendar?date={month}"
        ).json().get("data") or {}

        sections = [
            ("priced", (data.get("priced") or {}).get("rows"), "pricedDate", "Priced"),
            ("upcoming", ((data.get("upcoming") or {}).get("upcomingTable") or {}).get("rows"),
             "expectedPriceDate", "Expected"),
            ("filed", (data.get("filed") or {}).get("rows"), "filedDate", "Filed"),
        ]
        for _name, rows, date_key, status in sections:
            for row in rows or []:
                exchange = map_exchange(row.get("proposedExchange") or row.get("exchange"))
                if not exchange:
                    continue
                rec = record(
                    exchange=exchange,
                    company=row.get("companyName"),
                    ticker=row.get("proposedTickerSymbol") or row.get("symbol"),
                    listing_date=parse_date(row.get(date_key)),
                    status=status,
                    source=source,
                )
                if rec:
                    out.append(rec)
    if not out:
        raise RuntimeError("Nasdaq IPO calendar returned no usable rows")
    return out


# ---------------------------------------------------------------------------
# Generic HTML table extraction — used for exchange pages that publish their
# listing activity as plain HTML tables (TSX, ASX fallback).
# ---------------------------------------------------------------------------

COMPANY_KEYS = ("company", "issuer", "name", "entity")
TICKER_KEYS = ("symbol", "ticker", "code", "stock")
DATE_KEYS = ("date", "listed", "listing", "expected", "anticipated")
SECTOR_KEYS = ("sector", "industry", "category", "type of listing", "activity")


def _match_col(headers: list[str], keys: tuple[str, ...]) -> int | None:
    for i, h in enumerate(headers):
        if any(k in h for k in keys):
            return i
    return None


def extract_table_rows(html: str, exchange: str, source: str, status: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    for table in soup.find_all("table"):
        header_row = table.find("tr")
        if not header_row:
            continue
        headers = [c.get_text(" ", strip=True).lower()
                   for c in header_row.find_all(["th", "td"])]
        ci_company = _match_col(headers, COMPANY_KEYS)
        ci_date = _match_col(headers, DATE_KEYS)
        if ci_company is None or ci_date is None:
            continue
        ci_ticker = _match_col(headers, TICKER_KEYS)
        ci_sector = _match_col(headers, SECTOR_KEYS)

        for tr in header_row.find_next_siblings("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if len(cells) <= max(ci_company, ci_date):
                continue
            rec = record(
                exchange=exchange,
                company=cells[ci_company],
                ticker=cells[ci_ticker] if ci_ticker is not None and ci_ticker < len(cells) else "",
                listing_date=parse_date(cells[ci_date]),
                sector=cells[ci_sector] if ci_sector is not None and ci_sector < len(cells) else "",
                status=status,
                source=source,
            )
            if rec:
                out.append(rec)
    return out


# ---------------------------------------------------------------------------
# TSX / TSX Venture — tsx.com publishes new company listings (TSX and TSXV
# combined) as a server-rendered Date | Company table, where the company cell
# reads "Company Name (TICKER)".
# ---------------------------------------------------------------------------

def fetch_tsx() -> list[dict]:
    url = "https://www.tsx.com/en/news/new-company-listings"
    soup = BeautifulSoup(http_get(url).text, "html.parser")
    out: list[dict] = []
    for table in soup.find_all("table"):
        headers = [c.get_text(" ", strip=True).lower()
                   for c in table.find_all(["th"])]
        if "date" not in headers or "company" not in headers:
            continue
        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) < 2:
                continue
            date = parse_date(cells[0].get_text(" ", strip=True))
            name = cells[1].get_text(" ", strip=True).replace("\xa0", " ")
            m = re.match(r"^(.*?)\s*\(([^()]{1,12})\)\s*$", name)
            company, ticker = (m.group(1), m.group(2)) if m else (name, "")
            rec = record(
                exchange="TSX",
                company=company,
                ticker=ticker,
                listing_date=date,
                status="Listed",
                source=url,
            )
            if rec:
                out.append(rec)
    if not out:
        raise RuntimeError("No new-company-listings table found on tsx.com")
    return out


# ---------------------------------------------------------------------------
# ASX — the upcoming floats page renders one key/value detail table per
# company (Listing date / Security code / Principal activities / ...), with
# the company name in the nearest preceding heading.
# ---------------------------------------------------------------------------

ASX_PAGE = "https://www.asx.com.au/listings/upcoming-floats-and-listings"

ASX_FIELD_LABELS = {"listing date", "contact details", "principal activities",
                    "issue price", "issue type", "security code",
                    "capital to be raised", "expected offer close date",
                    "underwriter"}

ASX_DATE_TAIL = re.compile(
    r"\s*[-–—]\s*(?:(?:mon|tues|wednes|thurs|fri|satur|sun)day\b.*"
    r"|\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+20\d\d.*)$",
    re.I)


def fetch_asx() -> list[dict]:
    soup = BeautifulSoup(http_get(ASX_PAGE).text, "html.parser")
    out: list[dict] = []
    for table in soup.find_all("table"):
        kv: dict[str, str] = {}
        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) >= 2:
                key = cells[0].get_text(" ", strip=True).lower().rstrip(":")
                kv[key] = cells[1].get_text(" ", strip=True)
        if "listing date" not in kv or "security code" not in kv:
            continue  # not a company detail table

        company = ""
        heading = table.find_previous(["h2", "h3", "h4", "h5"])
        if heading:
            text = heading.get_text(" ", strip=True)
            if text and text.lower() not in ASX_FIELD_LABELS and len(text) < 120:
                # Headings read "Company Name - Monday 31 August 2026 ..." —
                # drop the date tail.
                company = ASX_DATE_TAIL.sub("", text).strip()
        rec = record(
            exchange="ASX",
            company=company or kv.get("security code", ""),
            ticker=kv.get("security code", ""),
            listing_date=parse_date(kv.get("listing date")),
            sector=kv.get("principal activities", ""),
            status="Upcoming",
            source=ASX_PAGE,
        )
        if rec:
            out.append(rec)
    if not out:
        raise RuntimeError("No company detail tables found on the ASX floats page")
    return out


# ---------------------------------------------------------------------------
# CSE — thecse.com's own data API (discovered in the site's JS bundles)
# serves the listed-companies dataset including each company's listingDate.
# ---------------------------------------------------------------------------

CSE_API_CANDIDATES = [
    "https://thecse.com/api/webapi/listed-companies/",
    "https://thecse.com/api/companies/all",
    "https://website-data-api-v2.thecse.com/listed-companies/",
    "https://webapi-backup.thecse.com/trading/listed/market/securities.json",
]


def _largest_dict_list(obj, depth: int = 0) -> list[dict]:
    """Find the largest list of dicts that looks like a securities table."""
    best: list[dict] = []
    if isinstance(obj, list):
        dicts = [x for x in obj if isinstance(x, dict)]
        if dicts and any(re.search(r"symbol|ticker", str(k), re.I) for k in dicts[0]):
            best = dicts
    elif isinstance(obj, dict) and depth < 6:
        for v in obj.values():
            cand = _largest_dict_list(v, depth + 1)
            if len(cand) > len(best):
                best = cand
    return best


def fetch_cse() -> list[dict]:
    notes = []
    for url in CSE_API_CANDIDATES:
        try:
            payload = http_get(url).json()
        except Exception as exc:
            notes.append(f"{url} -> {exc}")
            continue
        items = _largest_dict_list(payload)
        out: list[dict] = []
        for item in items:
            low = {re.sub(r"[\s_-]", "", str(k)).lower(): v for k, v in item.items()}

            def pick(*keys):
                for k in keys:
                    for lk, v in low.items():
                        if k in lk and v not in (None, ""):
                            return v
                return ""

            listing_date = parse_date(pick("listingdate", "datelisted", "listeddate",
                                           "listdate", "dateoflisting"))
            if not listing_date or listing_date < KEEP_AFTER.isoformat():
                continue  # only recent listings belong in an IPO table
            rec = record(
                exchange="CSE",
                company=pick("companyname", "company", "name", "title", "security"),
                ticker=pick("symbol", "ticker"),
                listing_date=listing_date,
                sector=pick("industry", "sector"),
                status="Listed",
                source="https://thecse.com/listing/listed-companies/",
            )
            if rec:
                out.append(rec)
        notes.append(f"{url} -> {len(items)} items, {len(out)} recent")
        if out:
            print(f"[CSE] using {url}")
            return out
    raise RuntimeError("No CSE candidate yielded recent listings: " + "; ".join(notes))


# ---------------------------------------------------------------------------
# Sector classification — free, deterministic keyword rules applied to every
# record after fetching. Uses the company name plus whatever raw sector /
# industry / description text the source gave us (if any) as extra signal,
# and reduces it to one short label from a fixed taxonomy. Checked in order;
# first match wins, so more specific buckets (SPAC, Mining) come before
# broader ones (Financial Services).
# ---------------------------------------------------------------------------

SECTOR_RULES: list[tuple[str, "re.Pattern"]] = [
    ("ETF / Fund", re.compile(
        r"\bETF\b|\bCDR\b|\bindex fund\b|\bportfolio\b|\byield maximizer\b", re.I)),
    ("SPAC / Blank Check", re.compile(
        r"\bacquisition\w*\b|\bblank check\b|\bspac\b|"
        # Shell-series naming like "Gores Holdings XI, Inc." or "Cartesian
        # Growth Corp IV" — keyword + a multi-letter roman numeral nearby.
        # Single-letter numerals (I, V, X) are excluded since they collide
        # with ordinary English words.
        r"\b(holdings?|growth|capital|partners|ventures?)\b.{0,30}\b"
        r"(II|III|IV|VI|VII|VIII|IX|XI|XII|XIII)\b", re.I)),
    ("Mining & Materials", re.compile(
        r"\bmin(e|es|ing|eral|erals)\b|\bresources\b|\bgold\b|\blithium\b|\buranium\b|"
        r"\bmetals?\b|\bexploration\b|\bcopper\b|\bnickel\b|\bcobalt\b|\bcoal\b", re.I)),
    ("Clean Energy", re.compile(
        r"\bsolar\b|\bwind\b|\brenewable\b|\bclean energy\b|\bgreen energy\b|\bhydrogen\b|"
        r"\bcarbon\b.{0,25}(technolog|\bcapture\b|\benergy\b)", re.I)),
    ("Energy", re.compile(
        r"\boil\b|\bgas\b|\bpetroleum\b|\benergy\b|\bnuclear\b|\bfission\b|\breactor\w*\b|"
        r"\butilit\w*\b", re.I)),
    ("Healthcare", re.compile(
        r"\bhealth\w*\b|\bmedical\b|\bmedtech\b|\bmedicines?\b|\bpharma\w*\b|\bbiotech\b|"
        r"\btherapeutic\w*\b|\bclinical\b|\blife sciences?\b|\bdiagnostic\w*\b|"
        r"\brx\b|\bcannabis\b", re.I)),
    ("Technology", re.compile(
        r"\btech(nolog(y|ies))?\b|\bsoftware\b|\bcyber\b|\bAI\b|\bdata\b|\bdigital\b|"
        r"\bcloud\b|\bsemiconductor\w*\b|\brobotic\w*\b|\bautonomous\b|\binternet\b|"
        r"\bplatform\b|\bquantum\w*\b|\bmobile\b", re.I)),
    ("Financial Services", re.compile(
        r"\bcapital\b|\bbank\w*\b|\bfinanc\w*\b|\binsurance\b|\bcredit\b|"
        r"\basset management\b|\binvestment\w*\b|\bfund\b", re.I)),
    ("Real Estate", re.compile(
        r"\brealty\b|\breal estate\b|\breit\b|\bproperties\b|\bresidential\b", re.I)),
    ("Industrials", re.compile(
        r"\bindustr\w*\b|\bmanufactur\w*\b|\baerospace\b|\bdefen[cs]e\b|\bengineering\b|"
        r"\blogistics\b|\btransport\w*\b|\baero\b|\bdynamics\b", re.I)),
    ("Consumer Defensive", re.compile(
        r"\bfoods?\b|\bbeverages?\b|\bagri\w*\b|\bgrocery\b|\bstaples\b", re.I)),
    ("Consumer Discretionary", re.compile(
        r"\bretail\w*\b|\bapparel\b|\brestaurants?\b|\btravel\b|\bleisure\b|"
        r"\bhospitality\b", re.I)),
    ("Communication Services", re.compile(
        r"\bmedia\b|\btelecom\w*\b|\bbroadcast\w*\b|\bpublishing\b|\bstreaming\b", re.I)),
]


# Branding like "QumulusAI" fuses "AI" onto the name with no word boundary,
# so it needs its own case-sensitive check (matches capitalized AI only, to
# avoid false positives from ordinary words that happen to contain "ai").
_AI_SUFFIX_RE = re.compile(r"(?<=[a-z])AI\b")


def classify_sector(company: str, hint: str = "") -> str:
    """Best-effort short sector label from company name (+ any raw sector
    text the source provided). Returns "" when nothing matches — an honest
    unknown beats a guessed label."""
    text = f"{company} {hint}"
    for label, pattern in SECTOR_RULES:
        if pattern.search(text):
            return label
    if _AI_SUFFIX_RE.search(text):
        return "Technology"
    return ""


# ---------------------------------------------------------------------------
# Merge / prune / write
# ---------------------------------------------------------------------------

FETCHERS: dict[str, tuple] = {
    # group name -> (fetcher, exchanges the group is authoritative for)
    "US": (fetch_us, {"NASDAQ", "NYSE", "NYSE American"}),
    "TSX": (fetch_tsx, {"TSX", "TSXV"}),
    "ASX": (fetch_asx, {"ASX"}),
    "CSE": (fetch_cse, {"CSE"}),
}


def keep(rec: dict) -> bool:
    date = rec.get("listing_date")
    if date:
        return date >= KEEP_AFTER.isoformat()
    # Undated rows (TBA listings) are kept while their source still reports
    # them; drop them once they go stale.
    fetched = rec.get("fetched_at") or "1970-01-01"
    return fetched >= (TODAY - dt.timedelta(days=60)).isoformat()


def main() -> int:
    existing: list[dict] = []
    if DATA_FILE.exists():
        try:
            existing = json.loads(DATA_FILE.read_text()).get("ipos") or []
        except json.JSONDecodeError:
            print("WARNING: existing data file is invalid JSON; starting fresh")

    merged: list[dict] = []
    failures: list[str] = []
    for name, (fetcher, exchanges) in FETCHERS.items():
        try:
            rows = fetcher()
            print(f"[{name}] fetched {len(rows)} rows")
            merged.extend(rows)
        except Exception as exc:  # keep last good data for this exchange group
            print(f"WARNING: [{name}] fetch failed ({exc}); keeping previous data")
            failures.append(name)
            merged.extend(r for r in existing if r.get("exchange") in exchanges)

    # Reduce whatever raw sector/description text a source gave (or none, for
    # TSX/NASDAQ/NYSE) to one short label, so every exchange shows the same
    # kind of value instead of long descriptions on some and blanks on others.
    for rec in merged:
        rec["sector"] = classify_sector(rec.get("company", ""), rec.get("sector", ""))

    # Dedupe by exchange + ticker (or company when no ticker), newest wins.
    deduped: dict[tuple, dict] = {}
    for rec in merged:
        key = (rec.get("exchange"), rec.get("ticker") or rec.get("company", "").lower())
        prev = deduped.get(key)
        if prev is None or (rec.get("fetched_at") or "") >= (prev.get("fetched_at") or ""):
            deduped[key] = rec

    final = sorted(
        (r for r in deduped.values() if keep(r)),
        key=lambda r: (r.get("listing_date") or "9999-99-99"),
        reverse=True,
    )

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps({
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "sources_failed": failures,
        "ipos": final,
    }, indent=2) + "\n")
    print(f"Wrote {len(final)} records to {DATA_FILE} "
          f"({len(failures)} source(s) failed: {failures or 'none'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
