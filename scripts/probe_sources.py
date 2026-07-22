#!/usr/bin/env python3
"""Diagnostic round 19: check why the recent_change enrichment matched only
1 of 7 known CSE bulletins (AFX, FFF, WMC, MJRX, APPT, TMED, CMT), and why
the one match (APPT) looks wrong. Dump the raw listed-companies entry for
each of these tickers verbatim. Temporary tool -- not part of the site."""

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

targets = {"AFX", "FFF", "WMC", "MJRX", "APPT", "TMED", "CMT"}
by_symbol = {}
for it in items:
    sym = str(it.get("symbol") or "").strip().upper()
    by_symbol.setdefault(sym, []).append(it)

for t in sorted(targets):
    matches = by_symbol.get(t, [])
    print("=" * 100)
    print(f"ticker {t!r}: {len(matches)} listed-companies entries with this exact symbol field")
    for it in matches:
        # print full item so we can see ALL fields, not just the ones we guessed matter
        print(json.dumps(it, indent=2, default=str))

# Also: is "symbol" sometimes not the bare ticker? dump a handful of raw
# symbol values to check for suffixes/prefixes.
print("=" * 100, "\nSample of 20 raw symbol fields (to check formatting)")
for it in items[:20]:
    print(repr(it.get("symbol")), "|", it.get("security_name"))
