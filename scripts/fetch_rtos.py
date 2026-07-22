#!/usr/bin/env python3
"""Fetch name/symbol-change (RTO) events from public exchange sources and
write data/rtos.json.

Covered exchanges:
  - ASX   via the official asx.com.au code-changes page (full history table)
  - CSE   via thecse.com's bulletins sitemap (bulletin type is in the slug),
    enriched with old name/ticker from the listed-companies webapi's
    per-company recent_change field where it's available
  - NASDAQ + NYSE (+ NYSE American) via SEC EDGAR's bulk submissions.zip:
    every US-listed CIK's filing history includes formerNames (old name +
    the date the change took effect) and its ticker history -- the CIK is a
    stable ID that never changes, so old and new ticker link up properly
    even when the ticker itself changes (not just the company name).
  - TSXV  via infoventure.tsx.com's bulletin system: each bulletin's
    NOTICE_ID is a global sequential counter, and the bulletin text itself
    (e.g. "NEW NAME (\"TICK\") [formerly Old Name (\"OLD\")] BULLETIN TYPE:
    Name Change") carries everything needed, so a plain incremental scan
    (persisted last-seen NOTICE_ID) finds every one -- no per-company lookup
    needed.
  - TSX   (senior board) has no equivalent free feed (TMX's Datalinx "TSX
    Bulletins" covering it is paid); reported as a standing failure so the
    gap stays visible rather than silently empty.

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

from fetch_ipos import ROOT, TIMEOUT, TODAY, KEEP_AFTER, HEADERS, http_get, parse_date, _largest_dict_list

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
# CSE — the bulletins sitemap URL slug encodes the date and bulletin type
# (new-listing, name-change, symbol-change, name-and-symbol-change,
# resumption-and-symbol-change, ...), which is enough to find and filter the
# relevant bulletins cheaply. But the slug is lowercase, so it can't recover
# a company's real capitalization (e.g. "EGF Theramed Health Corp" becomes
# "egf-theramed-health-corp" in the URL, indistinguishable from a name that
# was never capitalized that way) -- so once we know which bulletins matter,
# we fetch each one's actual page title for the correctly-cased name/ticker.
#
# Neither the sitemap nor the bulletin page itself says what the company was
# CALLED/TICKED before the change (confirmed directly: a bulletin page's raw
# HTML is just a client-rendered-JS stub with generic site boilerplate, no
# former-name text anywhere; there's no per-company history endpoint either)
# -- but thecse.com's own listed-companies webapi carries a per-company
# recent_change field (name_was/symbol_was) for whichever change was most
# recent for that company AT THE MOMENT WE CHECK. It only ever holds that one
# latest hop, and CSE companies turn out to rename/re-ticker again within
# days of a prior change often enough (observed directly: FFF, WMC and APPT
# all had a further, undisclosed-by-bulletin change days after the one we'd
# already captured for them) that the live snapshot alone usually doesn't
# line up with whichever of our own bulletins it's compared against.
#
# So instead of relying on a single live snapshot, every run appends any
# not-yet-seen (ticker, effective_on) pairs to a persisted history file
# (CSE_RECENT_CHANGES_STATE_FILE) -- since thecse.com only ever exposes the
# CURRENT hop, checking every 6 hours and remembering what we saw is the only
# way to accumulate genuine multi-hop history for free. A bulletin only gets
# enriched when some hop in that accumulated history has an effective_on
# exactly equal to the bulletin's own date -- anything looser risks pinning
# an unrelated rename's old name onto the wrong bulletin.
# ---------------------------------------------------------------------------

CSE_BULLETINS_SITEMAP = "https://thecse.com/sitemaps/bulletins.xml"
CSE_LISTED_COMPANIES_URL = "https://thecse.com/api/webapi/listed-companies/"
CSE_RECENT_CHANGES_STATE_FILE = ROOT / "data" / "snapshots" / "cse_recent_changes.json"

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

# Bulletin page <title> looks like:
#   "2026-0615 - Symbol Change - Inactive Designation - EGF Theramed Health
#    Corp. (TMED) | The Canadian Securities Exchange (CSE)"
# The type portion can itself contain " - ", so the company name is
# whichever segment comes after the LAST " - " before ". (TICKER)".
CSE_TITLE_PREFIX_RE = re.compile(r"^\d{4}-\d{4}\s*[-–]\s*(.+)$")
CSE_TITLE_TICKER_RE = re.compile(r"\(([^)]{1,15})\)\s*$")


def _parse_cse_bulletin_title(title: str) -> tuple[str, str] | None:
    normalized = title.replace("–", "-").split(" | ")[0].strip()
    prefix_m = CSE_TITLE_PREFIX_RE.match(normalized)
    if not prefix_m:
        return None
    rest = prefix_m.group(1)
    ticker_m = CSE_TITLE_TICKER_RE.search(rest)
    if not ticker_m:
        return None
    ticker = ticker_m.group(1).strip()
    before_ticker = rest[:ticker_m.start()].rstrip()
    if before_ticker.endswith("."):
        before_ticker = before_ticker[:-1].rstrip()
    idx = before_ticker.rfind(" - ")
    company = before_ticker[idx + 3:].strip() if idx != -1 else before_ticker.strip()
    return (company, ticker) if company and ticker else None


def _cse_recent_changes() -> dict[str, dict]:
    """Current ticker -> {name_was, symbol_was, effective_on} sourced from
    thecse.com's listed-companies webapi, for companies whose most recent
    bulletin was a name/symbol (or CUSIP-only) change. Best-effort: returns
    {} if the endpoint is unreachable, since this is only an enrichment on
    top of the sitemap-derived records, not their sole source."""
    try:
        payload = http_get(CSE_LISTED_COMPANIES_URL).json()
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for item in _largest_dict_list(payload):
        rc = item.get("recent_change")
        ticker = str(item.get("symbol") or "").strip().upper()
        if not rc or not ticker:
            continue
        name_was = re.sub(r"\s+", " ", str(rc.get("name_was") or "")).strip()
        symbol_was = str(rc.get("symbol_was") or "").strip().upper()
        if not name_was and not symbol_was:
            continue  # e.g. a CUSIP-only change -- nothing we can show
        out[ticker] = {
            "name_was": name_was,
            "symbol_was": symbol_was,
            "effective_on": str(rc.get("effective_on") or "")[:10],
        }
    return out


def _load_cse_recent_change_history() -> dict[str, list[dict]]:
    if CSE_RECENT_CHANGES_STATE_FILE.exists():
        try:
            return json.loads(CSE_RECENT_CHANGES_STATE_FILE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def _save_cse_recent_change_history(history: dict[str, list[dict]]) -> None:
    CSE_RECENT_CHANGES_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CSE_RECENT_CHANGES_STATE_FILE.write_text(json.dumps(history, indent=2) + "\n")


def fetch_cse_rtos() -> list[dict]:
    body = http_get(CSE_BULLETINS_SITEMAP).text
    locs = re.findall(r"<loc>(https://thecse\.com/bulletin/([^<]+?))/?</loc>", body)
    candidates: list[tuple[str, str, str]] = []  # (url, date, change_type)
    for full_url, slug in locs:
        m = re.match(r"^(\d{4})-(\d{2})(\d{2})-(.+)$", slug)
        if not m:
            continue
        year, month, day, tail = m.groups()
        type_m = CSE_CHANGE_TYPE_RE.match(tail)
        if not type_m:
            continue
        try:
            listing_date = dt.date(int(year), int(month), int(day)).isoformat()
        except ValueError:
            continue
        if listing_date < KEEP_AFTER.isoformat():
            continue
        change_type = CSE_CHANGE_LABELS.get(type_m.group("type"), "Name/Symbol Change")
        candidates.append((full_url, listing_date, change_type))

    history = _load_cse_recent_change_history()
    for ticker, rc in _cse_recent_changes().items():
        seen = history.setdefault(ticker, [])
        if not any(e.get("effective_on") == rc["effective_on"] for e in seen):
            seen.append(rc)
    _save_cse_recent_change_history(history)

    out: list[dict] = []
    session = requests.Session()
    session.headers.update(HEADERS)
    for full_url, listing_date, change_type in candidates:
        try:
            page = session.get(full_url, timeout=TIMEOUT).text
        except Exception:
            continue
        title_m = re.search(r"<title>(.*?)</title>", page, re.S | re.I)
        if not title_m:
            continue
        parsed = _parse_cse_bulletin_title(title_m.group(1))
        if not parsed:
            continue
        company, ticker = parsed
        old_name, old_ticker = "", ""
        for rc in history.get(ticker.upper(), []):
            if rc.get("effective_on") == listing_date:
                old_name = rc.get("name_was", "")
                old_ticker = rc.get("symbol_was", "")
                break
        rec = rto_record(
            exchange="CSE",
            old_name=old_name, old_ticker=old_ticker,
            new_name=company, new_ticker=ticker,
            change_type=change_type,
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
                exchanges_arr = data.get("exchanges") or []
                new_name = data.get("name", "")
                new_ticker = tickers[0]
                # tickers[1:] are NOT a rename history -- they're the CIK's
                # other securities (preferred share series, OTC/foreign
                # cross-listings, ETNs the company sponsors, ...), which just
                # happen to share the same CIK. Only trust a candidate old
                # ticker if it looks like plain common stock (no class/series
                # suffix) and its own listed exchange is one we actually
                # track (guards against e.g. an OTC cross-listing like
                # RYLBF being read as "the old ticker before a rename").
                old_ticker = ""
                if len(tickers) > 1 and "-" not in tickers[1] and "." not in tickers[1]:
                    cand_exchange = exchanges_arr[1] if len(exchanges_arr) > 1 else ""
                    if _map_us_exchange(cand_exchange):
                        old_ticker = tickers[1]

                for former in data.get("formerNames") or []:
                    to_date = (former.get("to") or "")[:10]
                    if not to_date or to_date < start_date:
                        continue
                    former_name = re.sub(r"\s+", " ", former.get("name", "")).strip()
                    if former_name.lower() == new_name.lower():
                        continue  # this is the CURRENT identity's own row (SEC keeps its "to" rolling to today), not a real change
                    name_changed = True
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
# TSXV (TSX Venture) — infoventure.tsx.com's bulletin system. Each bulletin's
# NOTICE_ID is a global sequential counter (independent of the company/PO_ID
# it's tied to), and the bulletin body itself contains the company name,
# ticker, bulletin type and date regardless of PO_ID -- so a plain sequential
# scan finds every bulletin, including "[formerly Old Name ("OLD")]" for
# Name/Symbol Change ones, without needing to already know which company to
# look up. We only ever scan forward from the last NOTICE_ID checked
# (persisted in the repo) so a run only makes a small, polite number of
# requests once caught up to the present.
#
# Senior TSX (non-Venture) has no equivalent free source -- TMX's "TSX
# Bulletins" product covering it is paid (Datalinx) -- so that board is
# reported as a standing gap separately from TSXV.
# ---------------------------------------------------------------------------

TSXV_STATE_FILE = ROOT / "data" / "snapshots" / "tsxv_last_notice_id.json"
TSXV_BASE = "http://infoventure.tsx.com/TSXVenture/TSXVentureHttpController"
TSXV_BACKFILL_START = 298000  # calibrated 2026-07: a little before our 365-day KEEP_AFTER cutoff
TSXV_BATCH_SIZE = 4000  # requests per run -- backfills a year of history over a handful of runs
TSXV_STOP_AFTER_EMPTY_STREAK = 300  # long run of empty IDs means we've caught up to the live edge

TSXV_NOTICE_RE = re.compile(
    r'BULLETIN\s+V[\w-]+\s+(?P<new_name>.+?)\s*\("(?P<new_ticker>[^"]{1,15})"\)'
    r'(?:\s*\[formerly\s+(?P<old_name>.+?)\s*\("(?P<old_ticker>[^"]{1,15})"\)\])?'
    r'\s*BULLETIN TYPE:\s*(?P<type>.+?)\s*BULLETIN DATE:\s*(?P<date>[A-Za-z]+ \d{1,2},? \d{4})',
    re.S,
)


def _tsxv_notice_url(nid: int) -> str:
    return f"{TSXV_BASE}?GetPage=NoticesContents&PO_ID=0&NOTICE_ID={nid}&CORRECTION_FLG=N&HC_FLAG1=checked"


def fetch_tsxv_rtos() -> list[dict]:
    state: dict = {}
    if TSXV_STATE_FILE.exists():
        try:
            state = json.loads(TSXV_STATE_FILE.read_text())
        except json.JSONDecodeError:
            state = {}
    nid = state.get("last_notice_id", TSXV_BACKFILL_START)

    out: list[dict] = []
    empty_streak = 0
    for _ in range(TSXV_BATCH_SIZE):
        if empty_streak >= TSXV_STOP_AFTER_EMPTY_STREAK:
            break
        nid += 1
        try:
            body = http_get(_tsxv_notice_url(nid)).text
        except Exception:
            empty_streak += 1
            continue

        text = re.sub(r"<script.*?</script>", " ", body, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"\s+", " ", text)
        m = TSXV_NOTICE_RE.search(text)
        if not m:
            empty_streak += 1
            continue
        empty_streak = 0

        btype = m.group("type").strip()
        if not re.search(r"name change|symbol change", btype, re.I):
            continue
        date_str = parse_date(m.group("date"))
        if not date_str:
            continue
        new_name = re.sub(r"\s+", " ", m.group("new_name")).strip()
        new_ticker = m.group("new_ticker").strip()
        old_name = re.sub(r"\s+", " ", m.group("old_name") or "").strip()
        old_ticker = (m.group("old_ticker") or "").strip()
        name_changed = bool(old_name) and old_name.lower() != new_name.lower()
        ticker_changed = bool(old_ticker) and old_ticker != new_ticker
        if name_changed and ticker_changed:
            change_type = "Name & Symbol Change"
        elif ticker_changed:
            change_type = "Symbol Change"
        else:
            change_type = "Name Change"  # the bulletin itself is typed as one, even if brackets are sparse
        rec = rto_record(
            exchange="TSXV",
            old_name=old_name, old_ticker=old_ticker,
            new_name=new_name, new_ticker=new_ticker,
            change_type=change_type,
            date=date_str,
            source=_tsxv_notice_url(nid),
        )
        if rec:
            out.append(rec)

    TSXV_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    TSXV_STATE_FILE.write_text(json.dumps({"last_notice_id": nid}, indent=2) + "\n")
    return out


def fetch_tsx_rtos() -> list[dict]:
    raise RuntimeError(
        "No free structured feed for senior TSX (non-Venture) name/symbol "
        "changes: TMX's official corporate-actions data (Datalinx / TSX "
        "Bulletins) covering the senior board is a paid product."
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
    "TSXV": (fetch_tsxv_rtos, {"TSXV"}, True),
    "TSX": (fetch_tsx_rtos, {"TSX"}, False),
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
