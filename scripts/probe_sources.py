#!/usr/bin/env python3
"""Diagnostic round 9: how to discover CURRENT TSXV daily bulletins (not just
one hardcoded old example) -- via newswire.ca link structure, RSS, or the
infoventure.tsx.com bulletin database's own search/filter parameters.
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
# 1) Dump ALL hrefs on the newswire.ca org page to see the real link pattern
# ---------------------------------------------------------------------------
print("=" * 100, "\nnewswire.ca/news/tsx-venture-exchange/ -- all links")
try:
    r = get("https://www.newswire.ca/news/tsx-venture-exchange/")
    print("  status:", r.status_code, "len:", len(r.text))
    hrefs = re.findall(r'href="([^"]+)"', r.text)
    rel = [h for h in hrefs if "news-releases" in h or "daily-bulletin" in h.lower()]
    print("  news-release-ish hrefs:", len(rel))
    for h in sorted(set(rel))[:20]:
        print("   ", h)
except Exception as exc:
    print("  ERROR:", exc)

# ---------------------------------------------------------------------------
# 2) Try RSS feed patterns for this organization
# ---------------------------------------------------------------------------
print("=" * 100, "\nnewswire.ca RSS feed candidates")
for url in [
    "https://www.newswire.ca/rss/news/tsx-venture-exchange.rss",
    "https://rss.newswire.ca/news-releases-list.rss?keyword=tsx+venture+exchange+daily+bulletins",
    "https://www.newswire.ca/news/tsx-venture-exchange/rss/",
]:
    try:
        r = get(url)
        print(f"  {url} -> {r.status_code} type={r.headers.get('content-type')} len={len(r.content)}")
        if r.status_code == 200 and "xml" in (r.headers.get("content-type") or "").lower():
            print("  SAMPLE:", r.text[:500])
    except Exception as exc:
        print(f"  {url} -> ERROR {exc}")

# ---------------------------------------------------------------------------
# 3) infoventure.tsx.com over plain HTTP -- dump its search form / links for
#    a way to filter by date or bulletin type instead of one hardcoded PO_ID
# ---------------------------------------------------------------------------
print("=" * 100, "\ninfoventure.tsx.com -- links and form fields on the bulletins page")
try:
    r = get("http://infoventure.tsx.com/TSXVenture/TSXVentureHttpController?GetPage=CompanyDocuments&PO_ID=1044821&HC_FLAG1=Y&NewsReleases=on&BulletinsMode=on")
    body = r.text
    print("  status:", r.status_code, "len:", len(body))
    forms = re.findall(r"<form[^>]*>(.*?)</form>", body, re.S | re.I)
    print("  form count:", len(forms))
    inputs = re.findall(r'<input[^>]*name="([^"]+)"[^>]*>', body, re.I)
    print("  input names:", sorted(set(inputs))[:30])
    hrefs = re.findall(r'href="([^"]+)"', body)
    ventures = [h for h in hrefs if "GetPage" in h or "Bulletin" in h]
    print("  relevant hrefs:", len(ventures))
    for h in sorted(set(ventures))[:20]:
        print("   ", h)
except Exception as exc:
    print("  ERROR:", exc)

# try a general search page without a specific PO_ID
print("-- try without PO_ID (general search) --")
for url in [
    "http://infoventure.tsx.com/TSXVenture/TSXVentureHttpController?GetPage=Bulletins",
    "http://infoventure.tsx.com/TSXVenture/TSXVentureHttpController?GetPage=DailyBulletins",
    "http://infoventure.tsx.com/TSXVenture/TSXVentureHttpController?GetPage=Search",
]:
    try:
        r = get(url)
        print(f"  {url} -> {r.status_code} len={len(r.content)}")
    except Exception as exc:
        print(f"  {url} -> ERROR {exc}")

# ---------------------------------------------------------------------------
# 4) SEDAR+ -- check if the SPA has a discoverable JSON API backend
# ---------------------------------------------------------------------------
print("=" * 100, "\nSEDAR+ backend API hunt")
try:
    r = get("https://www.sedarplus.ca/landingpage/")
    body = r.text
    apis = sorted(set(re.findall(r'"(/csa-party/[^"]+|/api/[^"]+)"', body)))
    print("  api-ish paths found on landing page:", apis[:20])
except Exception as exc:
    print("  ERROR:", exc)
