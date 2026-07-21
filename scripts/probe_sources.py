#!/usr/bin/env python3
"""Diagnostic round 7: full-text search misses real cases (confirmed: NMAD's
own 8-K matches none of our search phrases). Check whether SEC offers a bulk
submissions download so we can scan ALL companies' formerNames directly
instead of relying on fragile phrase search. Temporary tool -- not part of
the site."""

import requests

HEADERS = {
    "User-Agent": "ipos.com RTO tracker (contact: admin@ipos.com)",
    "Accept": "*/*",
}

def get(url, **kw):
    return requests.get(url, headers=HEADERS, timeout=30, **kw)

print("=" * 100, "\nBulk submissions data candidates")
for url in [
    "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip",
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany",
    "https://www.sec.gov/Archives/edgar/full-index/",
    "https://www.sec.gov/os/accessing-edgar-data",
]:
    try:
        r = get(url, stream=True)
        print(f"  {url} -> {r.status_code} type={r.headers.get('content-type')} len={r.headers.get('content-length')}")
    except Exception as exc:
        print(f"  {url} -> ERROR {exc}")

print("=" * 100, "\nSearch sec.gov developer docs page for 'bulk' download links")
try:
    r = get("https://www.sec.gov/search-filings/edgar-application-programming-interfaces")
    body = r.text
    import re
    links = sorted(set(re.findall(r'href="([^"]*(?:bulk|zip|Archives)[^"]*)"', body, re.I)))
    print("  status:", r.status_code, "len:", len(body))
    for l in links[:30]:
        print("   ", l)
except Exception as exc:
    print("  ERROR:", exc)

print("=" * 100, "\nTiming test: how fast can we hit data.sec.gov/submissions in a loop")
import time
t0 = time.time()
session = requests.Session()
session.headers.update(HEADERS)
test_ciks = ["0000320193", "0001045810", "0001652044", "0000789019", "0001018724",
             "0001335105", "0000766704", "0001567925", "0001734005", "0001600222"]
ok = 0
for c in test_ciks:
    try:
        r = session.get(f"https://data.sec.gov/submissions/CIK{c}.json", timeout=15)
        if r.status_code == 200:
            ok += 1
    except Exception:
        pass
elapsed = time.time() - t0
print(f"  {ok}/{len(test_ciks)} ok in {elapsed:.2f}s -> {len(test_ciks)/elapsed:.1f} req/s with a shared Session")

print("=" * 100, "\nBroader (non-phrase) full text search test -- how many total 8-K hits")
for q in ["%22Item+5.03%22", "name+change", "%22certificate+of+amendment%22"]:
    try:
        r = get(f"https://efts.sec.gov/LATEST/search-index?q={q}&forms=8-K&startdt=2025-07-21&enddt=2026-07-21")
        data = r.json()
        print(f"  q={q} -> total: {data.get('hits',{}).get('total')}")
    except Exception as exc:
        print(f"  q={q} ERROR:", exc)
