#!/usr/bin/env python3
"""Fetch name/symbol-change (RTO) events from public exchange sources and
write data/rtos.json.

Covered exchanges:
  - ASX   via the official asx.com.au code-changes page (full history table)
  - CSE   via thecse.com's bulletins sitemap (bulletin type is in the slug)
  - NASDAQ + NYSE (+ NYSE American) via nasdaqtrader.com's anonymous FTP
    symbol directory: there is no free change-log for these, so instead we
    snapshot the current Symbol -> Security Name map each run and diff it
    against the previous run's snapshot; a same-symbol name change is
    reported as a "Name Change" event. This only surfaces changes going
    forward from whenever tracking started, not historical ones.
  - TSX   has no free structured feed (TMX's Datalinx corporate-actions data
    is a paid product); this source is reported as failed every run so the
    gap is visible rather than silently empty.

Each exchange fetcher is isolated: if one fails, previous data for its
exchanges is kept and the rest still update.
"""

from __future__ import annotations

import datetime as dt
import ftplib
import json
import re
import sys

from bs4 import BeautifulSoup

from fetch_ipos import ROOT, TIMEOUT, TODAY, KEEP_AFTER, http_get, parse_date

RTO_DATA_FILE = ROOT / "data" / "rtos.json"
SNAPSHOT_FILE = ROOT / "data" / "snapshots" / "us_symbols.json"


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
# NASDAQ + NYSE (+ NYSE American) — no free change-log exists, so we diff
# today's anonymous-FTP symbol directory snapshot against the previous run's
# snapshot (persisted in the repo). A same-symbol name change is a "Name
# Change" event; this only catches changes from whenever tracking started.
# ---------------------------------------------------------------------------

FTP_HOST = "ftp.nasdaqtrader.com"
US_EXCHANGE_MAP = {"N": "NYSE", "A": "NYSE American"}


def _fetch_ftp_lines(path: str) -> list[str]:
    ftp = ftplib.FTP(FTP_HOST, timeout=TIMEOUT)
    ftp.login()
    lines: list[str] = []
    ftp.retrlines(f"RETR {path}", lines.append)
    ftp.quit()
    return lines


def _parse_symbol_directory() -> dict[str, dict]:
    snapshot: dict[str, dict] = {}

    for line in _fetch_ftp_lines("/Symboldirectory/nasdaqlisted.txt")[1:]:
        cols = line.split("|")
        if len(cols) < 2 or line.startswith("File Creation Time"):
            continue
        symbol, name = cols[0].strip(), cols[1].strip()
        if symbol:
            snapshot[symbol] = {"name": name, "exchange": "NASDAQ"}

    for line in _fetch_ftp_lines("/Symboldirectory/otherlisted.txt")[1:]:
        cols = line.split("|")
        if len(cols) < 3 or line.startswith("File Creation Time"):
            continue
        symbol, name, exch_code = cols[0].strip(), cols[1].strip(), cols[2].strip()
        exchange = US_EXCHANGE_MAP.get(exch_code)
        if symbol and exchange:
            snapshot[symbol] = {"name": name, "exchange": exchange}

    if not snapshot:
        raise RuntimeError("NASDAQ symbol directory FTP returned no rows")
    return snapshot


def fetch_us_rtos() -> list[dict]:
    current = _parse_symbol_directory()

    previous: dict[str, dict] = {}
    if SNAPSHOT_FILE.exists():
        try:
            previous = json.loads(SNAPSHOT_FILE.read_text())
        except json.JSONDecodeError:
            previous = {}

    out: list[dict] = []
    for symbol, info in current.items():
        prev_info = previous.get(symbol)
        if prev_info and prev_info.get("name") and prev_info["name"] != info["name"]:
            rec = rto_record(
                exchange=info["exchange"],
                old_name=prev_info["name"], old_ticker=symbol,
                new_name=info["name"], new_ticker=symbol,
                change_type="Name Change",
                date=TODAY.isoformat(),
                source="https://www.nasdaqtrader.com/Trader.aspx?id=symboldirdefs",
            )
            if rec:
                out.append(rec)

    SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_FILE.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
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
    "US": (fetch_us_rtos, {"NASDAQ", "NYSE", "NYSE American"}, True),
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
