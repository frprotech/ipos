#!/usr/bin/env python3
"""Fetch name/symbol-change (RTO) events from public exchange sources and
write data/rtos.json.

Covered exchanges:
  - ASX   via the official asx.com.au code-changes page (full history table)
  - CSE   via thecse.com's bulletins sitemap (bulletin type is in the slug)
  - NASDAQ + NYSE (+ NYSE American) via SEC EDGAR's bulk submissions.zip:
    every US-listed CIK's filing history includes formerNames (old name +
    the date the change took effect) and its ticker history -- the CIK is a
    stable ID that never changes, so old and new ticker link up properly
    even when the ticker itself changes (not just the company name).
  - TSX   has no free structured feed (TMX's Datalinx corporate-actions data
    is a paid product); this source is reported as failed every run so the
    gap is visible rather than silently empty.

Each exchange fetcher is isolated: if one fails, previous data for its
exchanges is kept and the rest still update.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import tempfile
import zipfile

import requests
from bs4 import BeautifulSoup

from fetch_ipos import ROOT, TIMEOUT, TODAY, KEEP_AFTER, http_get, parse_date

RTO_DATA_FILE = ROOT / "data" / "rtos.json"


def rto_record(exchange: str, new_name: str, new_ticker: str, change_type: str,
                date: str | None, source: str, old_name: str = "", old_ticker: str = "") -> dict | None:
    new_name = re.sub(r"\s+", " ", str(new_name or "")).strip()
    if not new_name or not date:
        return None
    return {
        "exchange": exchange,
        "old_name": re.sub(r"\s+", " ", str(old_name or "")).strip(),
        "old_ticker": str(old_ticker or "").strip().upper(),
        "new_name": new_name,
        "new_ticker": str(new_ticker or "").strip().upper(),
        "change_type": change_type,
        "date": date,
        "source": source,
    }


# ---------------------------------------------------------------------------
# ASX — the official code-changes page lists one table per period, newest
# rows first: As of | Old code | Old name | New code | New name. The page
# doesn't print a year next to each row, so we track the running date and
# roll the assumed year back a year whenever a row's date would otherwise
# jump forward in time (i.e. we've scrolled into the previous year's table).
# ---------------------------------------------------------------------------

ASX_CODE_CHANGES_PAGE = (
    "https://www.asx.com.au/markets/market-resources/asx-codes-and-descriptors/asx-code-changes"
)


def fetch_asx_rtos() -> list[dict]:
    soup = BeautifulSoup(http_get(ASX_CODE_CHANGES_PAGE).text, "html.parser")
    out: list[dict] = []
    year = TODAY.year
    prev_date: str | None = None
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        # Some of these tables split header/data across thead+tbody, others
        # put everything in one tbody — flatten to all <tr>s and use the
        # first as the header, rather than relying on sibling traversal.
        headers = [c.get_text(" ", strip=True).lower() for c in rows[0].find_all("th")]
        if not headers or "as of" not in headers[0]:
            continue
        for tr in rows[1:]:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all("td")]
            if len(cells) < 5:
                continue
            date_str, old_code, old_name, new_code, new_name = cells[:5]
            if not old_code or not new_code:
                continue
            candidate = parse_date(f"{date_str} {year}")
            if candidate and prev_date and candidate > prev_date:
                # Dates run newest-first down the page; a forward jump means
                # we've crossed into a table for the previous calendar year.
                year -= 1
                candidate = parse_date(f"{date_str} {year}")
            if candidate:
                prev_date = candidate
            rec = rto_record(
                exchange="ASX",
                old_name=old_name, old_ticker=old_code,
                new_name=new_name, new_ticker=new_code,
                change_type="Name & Symbol Change",
                date=candidate,
                source=ASX_CODE_CHANGES_PAGE,
            )
            if rec:
                out.append(rec)
    if not out:
        raise RuntimeError("No code-change rows found on the ASX page")
    return out


# ---------------------------------------------------------------------------
# CSE — the bulletins sitemap URL slug already encodes the date, the bulletin
# type (new-listing, name-change, symbol-change, name-and-symbol-change,
# resumption-and-symbol-change, ...) and the company name + ticker, so no
# per-bulletin page fetch is needed.
# ---------------------------------------------------------------------------

CSE_BULLETINS_SITEMAP = "https://thecse.com/sitemaps/bulletins.xml"

CSE_CHANGE_TYPE_RE = re.compile(
    r"^(?P<type>name-and-symbol-change|name-symbol-change(?:-and-consolidation)?|"
    r"name-change(?:-and-consolidation)?|symbol-change(?:-inactive-designation)?|"
    r"resumption-and-symbol-change)-(?P<rest>.+)$"
)

CSE_CHANGE_LABELS = {
    "name-and-symbol-change": "Name & Symbol Change",
    "name-symbol-change": "Name & Symbol Change",
    "name-symbol-change-and-consolidation": "Name & Symbol Change",
    "name-change": "Name Change",
    "name-change-and-consolidation": "Name Change",
    "symbol-change": "Symbol Change",
    "symbol-change-inactive-designation": "Symbol Change",
    "resumption-and-symbol-change": "Symbol Change",
}


def fetch_cse_rtos() -> list[dict]:
    body = http_get(CSE_BULLETINS_SITEMAP).text
    locs = re.findall(r"<loc>(https://thecse\.com/bulletin/([^<]+?))/?</loc>", body)
    out: list[dict] = []
    for full_url, slug in locs:
        m = re.match(r"^(\d{4})-(\d{2})(\d{2})-(.+)$", slug)
        if not m:
            continue
        year, month, day, tail = m.groups()
        type_m = CSE_CHANGE_TYPE_RE.match(tail)
        if not type_m:
            continue
        change_slug, rest = type_m.group("type"), type_m.group("rest")
        try:
            listing_date = dt.date(int(year), int(month), int(day)).isoformat()
        except ValueError:
            continue
        if listing_date < KEEP_AFTER.isoformat():
            continue
        tokens = rest.strip("-").split("-")
        if not tokens:
            continue
        if len(tokens) >= 2 and len(tokens[-1]) <= 2:
            ticker = f"{tokens[-2]}.{tokens[-1]}"
            company_tokens = tokens[:-2]
        else:
            ticker = tokens[-1]
            company_tokens = tokens[:-1]
        company = " ".join(t.capitalize() for t in company_tokens)
        rec = rto_record(
            exchange="CSE",
            new_name=company, new_ticker=ticker,
            change_type=CSE_CHANGE_LABELS.get(change_slug, "Name/Symbol Change"),
            date=listing_date,
            source=full_url,
        )
        if rec:
            out.append(rec)
    if not out:
        raise RuntimeError("No name/symbol-change bulletins found in the CSE sitemap")
    return out


# ---------------------------------------------------------------------------
# NASDAQ + NYSE (+ NYSE American) — via SEC EDGAR. A full-text phrase search
# turned out to be unreliable (real filings, including the exact NASDAQ RTO
# example that prompted this feature, don't contain any of the phrases a
# name-change 8-K "should" use), so instead we scan SEC's own bulk
# submissions.zip -- one filing-history JSON per company -- for every
# NASDAQ/NYSE-listed CIK and read its formerNames directly. This guarantees
# nothing is missed by wording, and is also far more polite to SEC's servers
# than thousands of individual per-CIK requests.
# ---------------------------------------------------------------------------

SEC_HEADERS = {
    # SEC's fair-access policy requires a descriptive User-Agent identifying
    # the application, not a browser string -- unlike the rest of this repo.
    "User-Agent": "ipos.com RTO tracker (contact: admin@ipos.com)",
    "Accept": "application/json",
}

SUBMISSIONS_ZIP_URL = "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip"


def _sec_get(url: str) -> requests.Response:
    resp = requests.get(url, headers=SEC_HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp


def _map_us_exchange(raw: str) -> str | None:
    raw = (raw or "").upper().strip()
    if "NASDAQ" in raw:
        return "NASDAQ"
    if "AMERICAN" in raw or "AMEX" in raw:
        return "NYSE American"
    if raw == "NYSE":
        return "NYSE"  # exact match only -- NYSE Arca/National are different exchanges we don't track
    return None


def _us_listed_ciks() -> dict[str, str]:
    """Zero-padded CIK -> our exchange label, for every NASDAQ/NYSE/NYSE
    American-listed company SEC currently knows about."""
    data = _sec_get("https://www.sec.gov/files/company_tickers_exchange.json").json()
    fields = data.get("fields") or []
    idx = {f: i for i, f in enumerate(fields)}
    wanted: dict[str, str] = {}
    for row in data.get("data") or []:
        exchange = _map_us_exchange(row[idx["exchange"]] if "exchange" in idx else "")
        if exchange:
            wanted[str(row[idx["cik"]]).zfill(10)] = exchange
    return wanted


def _download_submissions_zip() -> str:
    fd, path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    with requests.get(SUBMISSIONS_ZIP_URL, headers=SEC_HEADERS, timeout=600, stream=True) as resp:
        resp.raise_for_status()
        with open(path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
    return path


def fetch_us_rtos() -> list[dict]:
    start_date = KEEP_AFTER.isoformat()
    wanted = _us_listed_ciks()
    if not wanted:
        raise RuntimeError("SEC company_tickers_exchange.json returned no US-listed companies")

    zip_path = _download_submissions_zip()
    out: list[dict] = []
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for padded, exchange in wanted.items():
                try:
                    with zf.open(f"CIK{padded}.json") as fh:
                        data = json.load(fh)
                except KeyError:
                    continue  # not in this dump

                tickers = data.get("tickers") or []
                if not tickers:
                    continue
                new_name = data.get("name", "")
                new_ticker = tickers[0]
                old_ticker = tickers[1] if len(tickers) > 1 else ""

                for former in data.get("formerNames") or []:
                    to_date = (former.get("to") or "")[:10]
                    if not to_date or to_date < start_date:
                        continue
                    former_name = re.sub(r"\s+", " ", former.get("name", "")).strip()
                    name_changed = former_name.lower() != new_name.lower()
                    ticker_changed = bool(old_ticker) and old_ticker != new_ticker
                    if name_changed and ticker_changed:
                        change_type = "Name & Symbol Change"
                    elif ticker_changed:
                        change_type = "Symbol Change"
                    elif name_changed:
                        change_type = "Name Change"
                    else:
                        continue  # formerNames entry logged, but nothing user-visible actually changed
                    rec = rto_record(
                        exchange=exchange,
                        old_name=former_name, old_ticker=old_ticker,
                        new_name=new_name, new_ticker=new_ticker,
                        change_type=change_type,
                        date=to_date,
                        source=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={padded}&type=8-K",
                    )
                    if rec:
                        out.append(rec)
    finally:
        os.remove(zip_path)
    if not out:
        raise RuntimeError("SEC bulk submissions scan returned no US name-change records")
    return out


# ---------------------------------------------------------------------------
# TSX — no free structured feed found; report as a standing gap.
# ---------------------------------------------------------------------------

def fetch_tsx_rtos() -> list[dict]:
    raise RuntimeError(
        "No free structured feed for TSX name/symbol changes: TMX's official "
        "corporate-actions data (Datalinx) is a paid product, and press-release "
        "search engines don't expose a reliable filter for this."
    )


# ---------------------------------------------------------------------------
# Merge / write
# ---------------------------------------------------------------------------

# name -> (fetcher, exchanges it's authoritative for, whether it returns only
# new incremental rows each run instead of the full current history)
RTO_FETCHERS: dict[str, tuple] = {
    "ASX": (fetch_asx_rtos, {"ASX"}, False),
    "CSE": (fetch_cse_rtos, {"CSE"}, False),
    "US": (fetch_us_rtos, {"NASDAQ", "NYSE", "NYSE American"}, False),
    "TSX": (fetch_tsx_rtos, {"TSX", "TSXV"}, False),
}


def main() -> int:
    existing: list[dict] = []
    if RTO_DATA_FILE.exists():
        try:
            existing = json.loads(RTO_DATA_FILE.read_text()).get("rtos") or []
        except json.JSONDecodeError:
            print("WARNING: existing RTO data file is invalid JSON; starting fresh")

    merged: list[dict] = []
    failures: list[str] = []
    for name, (fetcher, exchanges, accumulate) in RTO_FETCHERS.items():
        try:
            rows = fetcher()
            print(f"[{name}] fetched {len(rows)} RTO rows")
            if accumulate:
                merged.extend(r for r in existing if r.get("exchange") in exchanges)
            merged.extend(rows)
        except Exception as exc:  # keep last good data for this exchange group
            print(f"WARNING: [{name}] RTO fetch failed ({exc}); keeping previous data")
            failures.append(name)
            merged.extend(r for r in existing if r.get("exchange") in exchanges)

    # Dedupe by exchange + new ticker + date + change type, newest wins.
    deduped: dict[tuple, dict] = {}
    for rec in merged:
        key = (rec.get("exchange"), rec.get("new_ticker"), rec.get("date"), rec.get("change_type"))
        deduped[key] = rec

    final = sorted(
        (r for r in deduped.values() if (r.get("date") or "") >= KEEP_AFTER.isoformat()),
        key=lambda r: r.get("date") or "",
        reverse=True,
    )

    RTO_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    RTO_DATA_FILE.write_text(json.dumps({
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "sources_failed": failures,
        "rtos": final,
    }, indent=2) + "\n")
    print(f"Wrote {len(final)} RTO records to {RTO_DATA_FILE} "
          f"({len(failures)} source(s) failed: {failures or 'none'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
