#!/usr/bin/env python3
"""Diagnostic: map the CSE market-reports bucket and find the thecse.com
data API in its JS bundles. Temporary tool — not part of the site."""

import re
import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0"}
S = requests.Session()
S.headers.update(HEADERS)

# 1) Bucket structure via delimiter listings
for url in [
    "https://market-reports.thecse.com/?list-type=2&delimiter=/",
    "https://market-reports.thecse.com/?list-type=2&delimiter=/&prefix=CSEListed/",
    "https://market-reports.thecse.com/?list-type=2&prefix=CSE%20Stock",
    "https://market-reports.thecse.com/?list-type=2&delimiter=/&prefix=Deprecated/",
]:
    print("=" * 100)
    print("URL:", url)
    try:
        r = S.get(url, timeout=30)
        print("STATUS:", r.status_code)
        for m in re.findall(r"<Prefix>([^<]*)</Prefix>", r.text):
            print("  PREFIX:", m)
        keys = re.findall(r"<Key>([^<]+)</Key>", r.text)
        print("  KEYS:", len(keys))
        for k in keys[:60]:
            print("   ", k)
    except Exception as exc:
        print("ERROR:", exc)

# 2) Find the data API used by thecse.com's listed-companies page
print("=" * 100)
page = "https://thecse.com/listing/listed-companies/"
print("URL:", page, "(scan JS bundles for API endpoints)")
try:
    html = S.get(page, timeout=30).text
    scripts = re.findall(r'src="(/_next/static/[^"]+\.js)"', html)
    print("SCRIPTS:", len(scripts))
    found: set[str] = set()
    for src in scripts[:40]:
        try:
            js = S.get("https://thecse.com" + src, timeout=30).text
        except Exception:
            continue
        for m in re.findall(r'https?://[^"\'\s\\]{8,120}', js):
            if re.search(r"api|graphql|data|feed", m, re.I) and "thecse" in m.lower():
                found.add(m)
        for m in re.findall(r'["\'](/[a-zA-Z0-9_\-/]*api[a-zA-Z0-9_\-/]*)["\']', js):
            found.add("REL " + m)
        if "listingDate" in js:
            for mm in re.finditer(r"listingDate", js):
                start = max(0, mm.start() - 200)
                print("  listingDate CTX in", src.split("/")[-1], ":",
                      js[start:mm.end() + 200].replace("\n", " ")[:420])
                break  # one context per file is enough
    print("API-CANDIDATES:")
    for f in sorted(found)[:40]:
        print("  ", f)
except Exception as exc:
    print("ERROR:", exc)
