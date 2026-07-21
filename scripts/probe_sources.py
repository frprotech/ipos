#!/usr/bin/env python3
"""Diagnostic round 5: is SEC EDGAR a viable free source for NASDAQ/NYSE
name & ticker change tracking (a real alternative to paid EODHD)? Temporary
tool -- not part of the site."""

import json
import re
import requests

HEADERS = {
    # SEC requires a descriptive User-Agent with contact info, or it 403s.
    "User-Agent": "ipos.com RTO research contact@ipos.com",
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
}

def get(url, **kw):
    return requests.get(url, headers=HEADERS, timeout=30, **kw)

# ---------------------------------------------------------------------------
# 1) Bulk ticker/CIK/exchange file -- if this updates promptly when a company
#    changes ticker, we could diff it daily keyed by CIK (which never
#    changes) to link old ticker -> new ticker properly, unlike the
#    nasdaqtrader.com snapshot we use now (no stable ID there).
# ---------------------------------------------------------------------------
print("=" * 100, "\nSEC bulk company_tickers_exchange.json")
try:
    r = get("https://www.sec.gov/files/company_tickers_exchange.json")
    print("  status:", r.status_code, "len:", len(r.content))
    if r.status_code == 200:
        data = r.json()
        print("  top-level keys:", list(data.keys())[:5])
        print("  fields:", data.get("fields"))
        print("  sample rows:", data.get("data", [])[:5])
        print("  total rows:", len(data.get("data", [])))
except Exception as exc:
    print("  ERROR:", exc)

# ---------------------------------------------------------------------------
# 2) Find LIXT/NMAD's CIK (the real NMAD example) via SEC full text search,
#    then check its submissions.json for a "formerNames" entry with dates.
# ---------------------------------------------------------------------------
print("=" * 100, "\nFind LIXT/NMAD CIK via full text search")
cik = None
try:
    r = get("https://efts.sec.gov/LATEST/search-index?q=%22NOMAD+Power+Solutions%22&forms=8-K")
    print("  status:", r.status_code)
    if r.status_code == 200:
        data = r.json()
        hits = data.get("hits", {}).get("hits", [])
        print("  hit count:", len(hits))
        for h in hits[:3]:
            src = h.get("_source", {})
            print("   ", src.get("display_names"), src.get("file_date"))
            ciks = src.get("ciks")
            if ciks:
                cik = ciks[0]
        print("  resolved cik:", cik)
except Exception as exc:
    print("  ERROR:", exc)

if not cik:
    # fallback: try the plain company search JSON
    try:
        r = get("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=nomad+power&type=8-K&dateb=&owner=include&count=10&output=atom")
        print("  fallback browse-edgar status:", r.status_code)
        m = re.search(r"CIK=(\d+)", r.text)
        if m:
            cik = m.group(1)
            print("  resolved cik via fallback:", cik)
    except Exception as exc:
        print("  fallback ERROR:", exc)

print("=" * 100, "\nsubmissions.json formerNames check")
if cik:
    try:
        padded = str(int(cik)).zfill(10)
        r = get(f"https://data.sec.gov/submissions/CIK{padded}.json")
        print("  status:", r.status_code)
        if r.status_code == 200:
            data = r.json()
            print("  name:", data.get("name"))
            print("  tickers:", data.get("tickers"))
            print("  exchanges:", data.get("exchanges"))
            print("  formerNames:", json.dumps(data.get("formerNames"), indent=2))
    except Exception as exc:
        print("  ERROR:", exc)
else:
    print("  no CIK resolved, skipping")

# ---------------------------------------------------------------------------
# 3) Full text search for recent 8-Ks announcing name changes generally --
#    a complementary/independent way to catch new events without scanning
#    every CIK's submissions.json.
# ---------------------------------------------------------------------------
print("=" * 100, "\nFull text search for recent name-change 8-Ks")
try:
    r = get('https://efts.sec.gov/LATEST/search-index?q=%22changed+its+name+to%22&forms=8-K&dateRange=custom&startdt=2026-07-01&enddt=2026-07-21')
    print("  status:", r.status_code)
    if r.status_code == 200:
        data = r.json()
        hits = data.get("hits", {}).get("hits", [])
        print("  total hits:", data.get("hits", {}).get("total", {}))
        for h in hits[:10]:
            src = h.get("_source", {})
            print("   ", src.get("file_date"), src.get("display_names"))
except Exception as exc:
    print("  ERROR:", exc)

# ---------------------------------------------------------------------------
# 4) Rate limit / fair-access sanity check -- fire a few quick requests.
# ---------------------------------------------------------------------------
print("=" * 100, "\nRate limit spot check (5 quick requests)")
import time
t0 = time.time()
for i in range(5):
    r = get("https://data.sec.gov/submissions/CIK0000320193.json")
    print(f"  req {i}: {r.status_code}")
print("  elapsed:", round(time.time() - t0, 2), "s")
