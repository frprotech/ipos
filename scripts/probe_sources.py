#!/usr/bin/env python3
"""Diagnostic round 16: find a free source giving CSE's OLD name/ticker too
(like NASDAQ/NYSE/ASX). Check (1) thecse.com's own listed-companies webapi
for a hidden formerNames/previousSymbol-style field, (2) SEDAR+ issuer
profile pages for former-name history, (3) CSE company profile pages.
Temporary tool -- not part of the site."""

import json
import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0",
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
}

def get(url, **kw):
    return requests.get(url, headers=HEADERS, timeout=30, **kw)

print("=" * 100, "\nthecse.com listed-companies webapi -- full schema for one company")
try:
    r = get("https://thecse.com/api/webapi/listed-companies/")
    data = r.json()
    # find the securities list (same helper logic as fetch_ipos.py)
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
    print("  total items:", len(items))
    if items:
        print("  ALL KEYS in one record:", sorted(items[0].keys()))
        # look specifically for a company we know changed name (Arctic Fox Lithium / AFX)
        for it in items:
            low = {str(k).lower(): v for k, v in it.items()}
            if "afx" in str(low.get("symbol", "")).lower() or "arctic fox" in str(low.get("name", "")).lower() or "arctic fox" in str(low.get("companyname", "")).lower():
                print("  MATCHED RECORD:", json.dumps(it, indent=2)[:1500])
except Exception as exc:
    print("  ERROR:", exc)

print("=" * 100, "\nCSE company profile page (not bulletin) for Arctic Fox Lithium")
for url in [
    "https://thecse.com/listed-company/arctic-fox-lithium-corp/",
    "https://thecse.com/listings/afx/",
    "https://thecse.com/company/afx/",
]:
    try:
        r = get(url)
        print(f"  {url} -> {r.status_code} len={len(r.content)}")
    except Exception as exc:
        print(f"  {url} ERROR:", exc)

print("=" * 100, "\nSEDAR+ -- search for Arctic Fox Lithium Corp profile")
try:
    r = get("https://www.sedarplus.ca/csa-party/records/document.html?id=search")
    print("  status:", r.status_code, "len:", len(r.text))
except Exception as exc:
    print("  ERROR:", exc)

# SEDAR+ search likely backed by an API -- try a few guesses
for url in [
    "https://www.sedarplus.ca/csa-party/service/search?keyword=Arctic+Fox+Lithium",
    "https://www.sedarplus.ca/api/search?q=Arctic+Fox+Lithium",
]:
    try:
        r = get(url)
        print(f"  {url} -> {r.status_code} type={r.headers.get('content-type')} len={len(r.content)}")
    except Exception as exc:
        print(f"  {url} ERROR:", exc)
