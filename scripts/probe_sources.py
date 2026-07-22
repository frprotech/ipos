#!/usr/bin/env python3
"""Diagnostic round 17: thecse.com's listed-companies webapi has a
"recent_change" field per company -- dump it for a company we know recently
changed name/symbol (Arctic Fox Lithium Corp, AFX) to see if it holds the
old name/ticker. Temporary tool -- not part of the site."""

import json
import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0",
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
}

def get(url, **kw):
    return requests.get(url, headers=HEADERS, timeout=30, **kw)

r = get("https://thecse.com/api/webapi/listed-companies/")
data = r.json()

def largest_list(obj, depth=0):
    best = []
    if isinstance(obj, list):
        dicts = [x for x in obj if isinstance(x, dict)]
        if dicts and any(re.search(r"symbol|ticker", str(k), re.I) for k in dicts[0]):
            best = dicts
    elif isinstance(obj, dict) and depth < 6:
        for v in obj.values():
            cand = largest_list(v, depth + 1)
            if len(cand) > len(best):
                best = cand
    return best

items = largest_list(data)
print("total items:", len(items))

targets = ["AFX", "TMED", "CMT", "APPT"]
for it in items:
    sym = str(it.get("symbol", "")).upper()
    if sym in targets:
        print("=" * 100, "\n", sym, "-", it.get("security_name"))
        print("  recent_change:", json.dumps(it.get("recent_change"), indent=2))
        print("  sedar_filings (truncated):", json.dumps(it.get("sedar_filings"), indent=2)[:800])
        print("  status:", it.get("status"))

# Also print a couple of full records raw, in case recent_change is buried
# under a differently-named key we haven't spotted
print("=" * 100, "\nFull raw record for AFX")
for it in items:
    if str(it.get("symbol", "")).upper() == "AFX":
        print(json.dumps(it, indent=2)[:3000])
