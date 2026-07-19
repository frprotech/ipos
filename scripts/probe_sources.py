#!/usr/bin/env python3
"""Diagnostic: probe candidate data-source URLs from a GitHub runner and print
what they return, so the real fetchers can be pointed at working endpoints.
Temporary tool — not part of the site."""

import re
import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

URLS = [
    # CSE — hunt for the current stock-list file / data API
    "https://thecse.com/listing/listed-companies/",
    "https://thecse.com/market-activity/market-overview/",
    "https://market-reports.thecse.com/Deprecated/CSE%20Stock%20List%20Changes.xlsx",
    "https://market-reports.thecse.com/CSE%20Stock%20List.xlsx",
    "https://market-reports.thecse.com/CSE_Stock_List.xlsx",
    "https://listings.thecse.com/sites/default/files/CSE_Stock_List.xlsx",
]

for url in URLS:
    print("=" * 100)
    print("URL:", url)
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        ct = r.headers.get("content-type", "")
        print("STATUS:", r.status_code, "| TYPE:", ct, "| LEN:", len(r.content),
              "| FINAL-URL:", r.url)
        if r.status_code != 200 or "html" not in ct:
            continue
        body = r.text

        for label, pattern in [
            ("XLSX", r"[^\"'\s<>]*\.xlsx?[^\"'\s<>]*"),
            ("CSV", r"[^\"'\s<>]*\.csv[^\"'\s<>]*"),
            ("REL-API", r"[\"'](/[^\"']*api[^\"']*)[\"']"),
            ("ABS-API", r"https?://[^\"'\s<>\\]+(?:api|json|graphql)[^\"'\s<>\\]*"),
        ]:
            for m in sorted(set(re.findall(pattern, body, re.I)))[:15]:
                print(f"  {label}:", m)

        # Next.js hints
        if "__NEXT_DATA__" in body:
            print("  HAS __NEXT_DATA__")
        for m in sorted(set(re.findall(r'"buildId"\s*:\s*"([^"]+)"', body)))[:3]:
            print("  NEXT-BUILD-ID:", m)
        # Context around 'stock list' mentions
        for m in re.finditer(r"stock[\s_-]*list", body, re.I):
            start = max(0, m.start() - 150)
            print("  CTX:", re.sub(r"\s+", " ", body[start:m.end() + 150]))
    except Exception as exc:
        print("ERROR:", exc)
