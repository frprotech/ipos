#!/usr/bin/env python3
"""Diagnostic: enumerate the CSE market-reports bucket and inspect the
listed-companies page payload. Temporary tool — not part of the site."""

import re
import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0"}

# 1) S3-style bucket listing
for url in [
    "https://market-reports.thecse.com/?list-type=2",
    "https://market-reports.thecse.com/",
]:
    print("=" * 100)
    print("URL:", url)
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        print("STATUS:", r.status_code, "| TYPE:", r.headers.get("content-type"),
              "| LEN:", len(r.content))
        keys = re.findall(r"<Key>([^<]+)</Key>", r.text)
        if keys:
            print("KEYS:", len(keys))
            for k in keys[:200]:
                print("  ", k)
        else:
            print(r.text[:1000])
    except Exception as exc:
        print("ERROR:", exc)

# 2) The listed-companies page: how much data is embedded server-side?
print("=" * 100)
url = "https://thecse.com/listing/listed-companies/"
print("URL:", url)
try:
    body = requests.get(url, headers=HEADERS, timeout=30).text
    # RSC flight payload chunks often hold the JSON data
    for pat, label in [
        (r'dateListed[^,]{0,60}', "dateListed"),
        (r'listing_?date[^,]{0,60}', "listing_date"),
        (r'"symbol"[^}]{0,120}', "symbol-objects"),
    ]:
        hits = re.findall(pat, body, re.I)
        print(f"  {label}: {len(hits)} hits")
        for h in hits[:5]:
            print("    ", h[:150])
    tables = re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S)
    print("  <tr> rows in HTML:", len(tables))
except Exception as exc:
    print("ERROR:", exc)
