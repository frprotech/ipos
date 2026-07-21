#!/usr/bin/env python3
"""Diagnostic round 4: NASDAQ FTP Files/Downloads dirs + api.nasdaq.com corporate
actions endpoints, CSE bulletin slug variety, NYSE proxy endpoint. Temporary
tool — not part of the site."""

import ftplib
import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0",
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
}

def get(url, **kw):
    return requests.get(url, headers=HEADERS, timeout=30, **kw)

# ---------------------------------------------------------------------------
# 1) NASDAQ FTP — look inside Files and Downloads for daily-list archives
# ---------------------------------------------------------------------------
print("=" * 100, "\nNASDAQ FTP — Files / Downloads contents")
try:
    ftp = ftplib.FTP("ftp.nasdaqtrader.com", timeout=20)
    ftp.login()
    for d in ["/Files", "/Downloads"]:
        try:
            ftp.cwd(d)
            items = ftp.nlst()
            print(f"  DIR {d}: {items[:40]}")
        except Exception as exc:
            print(f"  cwd {d} FAILED: {exc}")
    ftp.quit()
except Exception as exc:
    print("  FTP ERROR:", exc)

# ---------------------------------------------------------------------------
# 2) api.nasdaq.com — try corporate-actions / symbol-change style endpoints
#    (same host/pattern as the working IPO calendar API)
# ---------------------------------------------------------------------------
print("=" * 100, "\napi.nasdaq.com corporate-action endpoint hunt")
for url in [
    "https://api.nasdaq.com/api/quote/list-type/nasdaq100",
    "https://api.nasdaq.com/api/company/symbol-change",
    "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=5",
    "https://api.nasdaq.com/api/corporate-actions",
    "https://api.nasdaq.com/api/news/symbolchange",
    "https://www.nasdaq.com/market-activity/stocks/symbol-change-history",
]:
    try:
        r = get(url)
        print(f"  {url} -> {r.status_code} type={r.headers.get('content-type')} len={len(r.content)}")
        if r.status_code == 200 and "json" in (r.headers.get("content-type") or ""):
            print("  SAMPLE:", r.text[:500])
    except Exception as exc:
        print(f"  {url} -> ERROR {exc}")

# ---------------------------------------------------------------------------
# 3) CSE bulletins sitemap — survey the variety of bulletin slug types
# ---------------------------------------------------------------------------
print("=" * 100, "\nCSE bulletins sitemap — slug type survey")
try:
    r = get("https://thecse.com/sitemaps/bulletins.xml")
    locs = re.findall(r"<loc>(https://thecse\.com/bulletin/[^<]+)</loc>", r.text)
    print("  total bulletin urls:", len(locs))
    # bulletin slug pattern: /bulletin/YYYY-MMDD-<type>-...
    types = {}
    for loc in locs:
        m = re.search(r"/bulletin/\d{4}-\d{4}-([a-z0-9-]+?)-[a-z0-9-]*$", loc)
        slug_tail = loc.rsplit("/bulletin/", 1)[-1]
        m2 = re.match(r"\d{4}-\d{4}-(.+)$", slug_tail)
        if m2:
            words = m2.group(1).split("-")
            key = "-".join(words[:3])
            types.setdefault(key, []).append(loc)
    name_change_like = [loc for loc in locs if re.search(r"name-change|symbol-change|trading-symbol|change-of-name|ticker-change", loc, re.I)]
    print("  name/symbol-change-like urls found:", len(name_change_like))
    for u in name_change_like[:15]:
        print("   ", u)
    # print a sample of distinct type prefixes to see the taxonomy
    prefixes = sorted(set("-".join(re.match(r"\d{4}-\d{4}-(.+)$", loc.rsplit('/bulletin/',1)[-1]).group(1).split("-")[:2]) for loc in locs if re.match(r"\d{4}-\d{4}-", loc.rsplit('/bulletin/',1)[-1])))
    print("  distinct 2-word type prefixes (sample):", prefixes[:40])
except Exception as exc:
    print("  ERROR:", exc)

# ---------------------------------------------------------------------------
# 4) NYSE proxy endpoint — try calling it directly
# ---------------------------------------------------------------------------
print("=" * 100, "\nNYSE /api/sites/nyse/proxy hunt")
for url in [
    "https://beta.nyse.com/api/sites/nyse/proxy?path=/market-data/corporate-actions/listing-notices",
    "https://beta.nyse.com/api/sites/nyse/proxy?url=/quotes/filter",
    "https://www.nyse.com/api/quotes/filter",
]:
    try:
        r = get(url)
        print(f"  {url} -> {r.status_code} type={r.headers.get('content-type')} len={len(r.content)}")
        if r.status_code == 200:
            print("  SAMPLE:", r.text[:400])
    except Exception as exc:
        print(f"  {url} -> ERROR {exc}")
