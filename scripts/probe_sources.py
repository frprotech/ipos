#!/usr/bin/env python3
"""Diagnostic round 6: why doesn't the NMAD/LIXT case show up via our
"changed its name to" full-text search query? Temporary tool -- not part
of the site."""

import requests

HEADERS = {
    "User-Agent": "ipos.com RTO tracker (contact: admin@ipos.com)",
    "Accept": "application/json",
}

def get(url):
    return requests.get(url, headers=HEADERS, timeout=30)

NMAD_CIK = "1335105"

print("=" * 100, "\nDoes our production query find NMAD's CIK?")
url = ("https://efts.sec.gov/LATEST/search-index?q=%22changed+its+name+to%22"
       "&forms=8-K&startdt=2025-07-21&enddt=2026-07-21&from=0")
found = False
for page in range(30):
    frm = page * 10
    u = url.replace("from=0", f"from={frm}")
    try:
        r = get(u)
        data = r.json()
    except Exception as exc:
        print(f"  page {frm} error: {exc}")
        break
    hits = data.get("hits", {}).get("hits", [])
    if not hits:
        print(f"  no more hits at page {frm}")
        break
    for h in hits:
        ciks = h.get("_source", {}).get("ciks") or []
        if NMAD_CIK in ciks:
            found = True
            print(f"  FOUND at page {frm}:", h.get("_source", {}).get("display_names"), h.get("_source", {}).get("file_date"))
    total = data.get("hits", {}).get("total", {}).get("value", 0)
    if frm + 10 >= total:
        print(f"  reached end of results, total={total}")
        break
print("  NMAD found via production query:", found)

# Now check what 8-Ks NMAD actually filed, and what phrases they use
print("=" * 100, "\nNMAD's actual 8-K filings and full text search for its own CIK")
r = get(f"https://data.sec.gov/submissions/CIK{int(NMAD_CIK):010d}.json")
data = r.json()
recent = data.get("filings", {}).get("recent", {})
forms = recent.get("form", [])
dates = recent.get("filingDate", [])
accns = recent.get("accessionNumber", [])
docs = recent.get("primaryDocument", [])
for i, f in enumerate(forms):
    if f == "8-K" and dates[i] >= "2026-06-01":
        print(f"  {dates[i]} {f} accn={accns[i]} doc={docs[i]}")

print("=" * 100, "\nSearch efts.sec.gov filtered to just this CIK, no phrase filter")
r = get(f"https://efts.sec.gov/LATEST/search-index?q=%22name+change%22&forms=8-K&ciks={NMAD_CIK}")
try:
    data = r.json()
    print("  status:", r.status_code, "total:", data.get("hits", {}).get("total"))
    for h in data.get("hits", {}).get("hits", [])[:5]:
        print("   ", h.get("_source", {}).get("file_date"), h.get("_id"))
except Exception as exc:
    print("  ERROR:", exc)

print("=" * 100, "\nTry a few alternate phrase queries restricted to this CIK")
for phrase in ["name+change", "changed+its+name", "will+begin+trading", "new+name", "symbol+change"]:
    r = get(f"https://efts.sec.gov/LATEST/search-index?q=%22{phrase}%22&forms=8-K&ciks={NMAD_CIK}")
    try:
        data = r.json()
        total = data.get("hits", {}).get("total", {}).get("value")
        print(f"  phrase '{phrase.replace('+',' ')}' -> total hits: {total}")
    except Exception as exc:
        print(f"  phrase '{phrase}' ERROR:", exc)
