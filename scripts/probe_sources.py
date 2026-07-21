#!/usr/bin/env python3
"""Diagnostic round 8: deep re-check of TSX/TSXV (real gap), ASX and CSE
(confirm nothing better exists / re-verify current methods are still best).
Temporary tool -- not part of the site."""

import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0",
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
}

def get(url, **kw):
    return requests.get(url, headers=HEADERS, timeout=30, **kw)

# ---------------------------------------------------------------------------
# 1) TSXV's own bulletin database at infoventure.tsx.com
# ---------------------------------------------------------------------------
print("=" * 100, "\ninfoventure.tsx.com TSXV bulletin database")
for url in [
    "http://infoventure.tsx.com/TSXVenture/TSXVentureHttpController?GetPage=CompanyDocuments&PO_ID=1044821&HC_FLAG1=Y&NewsReleases=on&BulletinsMode=on",
    "https://infoventure.tsx.com/TSXVenture/TSXVentureHttpController?GetPage=CompanyDocuments&PO_ID=1044821&HC_FLAG1=Y&NewsReleases=on&BulletinsMode=on",
]:
    try:
        r = get(url)
        print(f"  {url[:80]}... -> {r.status_code} len={len(r.content)}")
        if r.status_code == 200:
            print("  SAMPLE:", re.sub(r"\s+", " ", r.text[:600]))
    except Exception as exc:
        print(f"  -> ERROR {exc}")

# ---------------------------------------------------------------------------
# 2) Canada Newswire (newswire.ca) search for TSXV daily bulletins
# ---------------------------------------------------------------------------
print("=" * 100, "\nnewswire.ca TSXV Daily Bulletins search")
for url in [
    "https://www.newswire.ca/news/tsx-venture-exchange/",
    "https://www.newswire.ca/search/news/?keyword=TSX%20Venture%20Exchange%20Daily%20Bulletins",
]:
    try:
        r = get(url)
        print(f"  {url} -> {r.status_code} len={len(r.content)}")
        links = re.findall(r'href="(/news-releases/[^"]+daily-bulletins[^"]*)"', r.text, re.I)
        print("  daily-bulletin links found:", len(links))
        for l in links[:5]:
            print("   ", l)
    except Exception as exc:
        print(f"  {url} -> ERROR {exc}")

# fetch one actual bulletin page and see its text structure
print("-- sample bulletin content --")
try:
    r = get("https://www.newswire.ca/news-releases/tsx-venture-exchange-daily-bulletins-547056312.html")
    print("  status:", r.status_code, "len:", len(r.text))
    body = re.sub(r"<[^>]+>", " ", r.text)
    body = re.sub(r"\s+", " ", body)
    # find any mention of "name change" or "symbol" in the plain text
    idx = body.lower().find("name change")
    if idx == -1:
        idx = body.lower().find("change")
    print("  SAMPLE around 'change':", body[max(0, idx-200):idx+400])
except Exception as exc:
    print("  ERROR:", exc)

# ---------------------------------------------------------------------------
# 3) SEDAR+ public issuer search -- does it expose former names via a
#    scrapeable/queryable public page?
# ---------------------------------------------------------------------------
print("=" * 100, "\nSEDAR+ public search")
for url in [
    "https://www.sedarplus.ca/csa-party/records/document.html",
    "https://www.sedarplus.ca/landingpage/",
    "https://www.sedarplus.ca/",
]:
    try:
        r = get(url)
        print(f"  {url} -> {r.status_code} len={len(r.content)}")
    except Exception as exc:
        print(f"  {url} -> ERROR {exc}")

# ---------------------------------------------------------------------------
# 4) Re-verify ASX code-changes page still looks complete / check for an
#    even better official ASX source (announcements platform structured feed)
# ---------------------------------------------------------------------------
print("=" * 100, "\nRe-check ASX code-changes page + announcements platform")
try:
    r = get("https://www.asx.com.au/markets/market-resources/asx-codes-and-descriptors/asx-code-changes")
    print("  code-changes page status:", r.status_code, "len:", len(r.content))
except Exception as exc:
    print("  ERROR:", exc)

try:
    r = get("https://www.asx.com.au/markets/trade-our-cash-market/announcements.api")
    print("  announcements.api status:", r.status_code, "type:", r.headers.get("content-type"), "len:", len(r.content))
    if r.status_code == 200:
        print("  SAMPLE:", r.text[:400])
except Exception as exc:
    print("  ERROR:", exc)

# ---------------------------------------------------------------------------
# 5) Re-verify CSE bulletins sitemap is still the best CSE source (check if
#    there's a structured JSON API behind the bulletins page instead of the
#    slug-parsing approach we currently use)
# ---------------------------------------------------------------------------
print("=" * 100, "\nRe-check for a structured CSE bulletins API")
for url in [
    "https://thecse.com/api/webapi/bulletins/",
    "https://thecse.com/api/webapi/bulletin-list/",
    "https://thecse.com/api/webapi/news-bulletins/",
]:
    try:
        r = get(url)
        print(f"  {url} -> {r.status_code} type={r.headers.get('content-type')} len={len(r.content)}")
    except Exception as exc:
        print(f"  {url} -> ERROR {exc}")
