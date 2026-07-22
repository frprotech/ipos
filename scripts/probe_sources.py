#!/usr/bin/env python3
"""Diagnostic round 18: survey ALL companies' recent_change field on CSE's
listed-companies webapi to see every "type" value and field name used (is
there a symbol_was for ticker changes? name_symbol for both?). Temporary
tool -- not part of the site."""

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

with_change = [it for it in items if it.get("recent_change")]
print("items with a recent_change field:", len(with_change))

types_seen = {}
for it in with_change:
    rc = it["recent_change"]
    t = rc.get("type")
    types_seen.setdefault(t, []).append((it.get("symbol"), it.get("security_name"), rc))

for t, examples in types_seen.items():
    print("=" * 100, f"\ntype = {t!r} ({len(examples)} examples)")
    for sym, name, rc in examples[:5]:
        print(f"  {sym} | {name} | {json.dumps(rc)}")

print("=" * 100, "\nAll distinct keys seen across every recent_change object")
all_keys = set()
for it in with_change:
    all_keys.update(it["recent_change"].keys())
print("  keys:", sorted(all_keys))
