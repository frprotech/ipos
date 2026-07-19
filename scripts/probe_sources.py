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
    # TSX
    "https://www.tsx.com/en/news/new-company-listings",
    "https://www.tsx.com/en/listings/current-market-statistics",
    # ASX
    "https://www.asx.com.au/listings/upcoming-floats-and-listings",
    "https://asx.api.markitdigital.com/asx-research/1.0/companies/upcoming-floats-and-listings",
    "https://www.asx.com.au/asx/1/upcoming-floats",
    # CSE
    "https://listings.thecse.com/en/listings",
    "https://thecse.com/listing/listed-companies/",
    "https://webapi.thecse.ca/trading/listed/market/securities.json",
]

for url in URLS:
    print("=" * 100)
    print("URL:", url)
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        ct = r.headers.get("content-type", "")
        print("STATUS:", r.status_code, "| TYPE:", ct, "| LEN:", len(r.content),
              "| FINAL-URL:", r.url)
        if r.status_code != 200:
            print("BODY-HEAD:", r.text[:500].replace("\n", " "))
            continue
        body = r.text

        # Any embedded API-ish endpoints (for JS-rendered pages).
        apiish = sorted(set(re.findall(
            r"https?://[^\"'\s<>\\]+(?:api|json|graphql)[^\"'\s<>\\]*", body, re.I)))
        for m in apiish[:25]:
            print("  EMBEDDED-API:", m)

        if "json" in ct:
            print("JSON-HEAD:")
            print(body[:4000])
            continue

        tables = re.findall(r"<table.*?</table>", body, re.S | re.I)
        print("  TABLE-COUNT:", len(tables))
        for t in tables[:2]:
            print("  TABLE-HEAD:", re.sub(r"\s+", " ", t)[:2500])

        # Anchors that look like listing items or data files.
        anchors = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', body, re.S | re.I)
        interesting = [(h, re.sub(r"<[^>]+>|\s+", " ", txt).strip()[:80])
                       for h, txt in anchors
                       if re.search(r"new-company-listings\?|\.xlsx|\.csv|\.json|recent|float|listed",
                                    h, re.I)]
        for h, txt in interesting[:30]:
            print("  ANCHOR:", h, "|", txt)

        if not tables and not interesting:
            print("BODY-HEAD:", re.sub(r"\s+", " ", body)[:2500])
    except Exception as exc:
        print("ERROR:", exc)
