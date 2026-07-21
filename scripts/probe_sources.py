#!/usr/bin/env python3
"""Diagnostic round 2: fix NASDAQ Daily List URL, find NYSE's underlying API,
find CSE's bulletins API, and extract TSX press-release search results.
Temporary tool — not part of the site."""

import datetime as dt
import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0",
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
}
today = dt.date.today()

def get(url, **kw):
    return requests.get(url, headers=HEADERS, timeout=30, **kw)

# ---------------------------------------------------------------------------
# 1) NASDAQ Daily List — inspect the product-description page for the real
#    download link/form, and try the FTP host over HTTPS mirror.
# ---------------------------------------------------------------------------
print("=" * 100, "\nNASDAQ Daily List — page internals")
try:
    r = get("https://www.nasdaqtrader.com/Trader.aspx?id=dailylistpd")
    body = r.text
    for pat in [r'href="([^"]*DailyList[^"]*)"', r'href="([^"]*\.txt[^"]*)"',
                r"action=\"([^\"]+)\"", r'ftp[^"\'\s]+']:
        hits = sorted(set(re.findall(pat, body, re.I)))
        print(f"  pattern {pat!r}: {len(hits)} hits")
        for h in hits[:10]:
            print("    ", h)
except Exception as exc:
    print("  ERROR:", exc)

for url in [
    "https://ftp.nasdaqtrader.com/Trader.aspx?id=DailyListFile",
    f"https://www.nasdaqtrader.com/dynamic/DailyList/nq{today.month:02d}{today.day:02d}{today.year}.txt",
    "https://www.nasdaqtrader.com/RemoveNASD.aspx",
]:
    try:
        r = get(url)
        print(f"  TRY {url} -> {r.status_code} type={r.headers.get('content-type')} len={len(r.content)}")
        if r.status_code == 200 and "html" not in (r.headers.get("content-type") or ""):
            print("  SAMPLE:", r.text[:400])
    except Exception as exc:
        print(f"  TRY {url} -> ERROR {exc}")

# ---------------------------------------------------------------------------
# 2) NYSE — dump actual table rows from /markets/notices, and hunt for API
#    endpoints in the listing-notices SPA's JS bundles.
# ---------------------------------------------------------------------------
print("=" * 100, "\nNYSE notices — table content + API hints")
try:
    r = get("https://www.nyse.com/markets/notices")
    tables = re.findall(r"<table.*?</table>", r.text, re.S | re.I)
    for i, t in enumerate(tables):
        print(f"  TABLE {i} HEAD:", re.sub(r"\s+", " ", t)[:1200])
except Exception as exc:
    print("  ERROR:", exc)

try:
    r = get("https://www.nyse.com/market-data/corporate-actions/nyse-and-nyse-american-listing-notices")
    body = r.text
    apis = sorted(set(re.findall(r'https?://[^"\'\s]+(?:api|json|graphql)[^"\'\s]*', body, re.I)))
    for a in apis[:20]:
        print("    api-hint:", a)
    scripts = re.findall(r'src="(/[^"]+\.js[^"]*)"', body)
    print("  script count:", len(scripts))
    for s in scripts[:15]:
        print("    script:", s)
except Exception as exc:
    print("  ERROR:", exc)

# ---------------------------------------------------------------------------
# 3) CSE — try the webapi pattern that worked for listed-companies, and
#    the sitemap as a fallback way to enumerate bulletin URLs.
# ---------------------------------------------------------------------------
print("=" * 100, "\nCSE bulletins API / sitemap")
for url in [
    "https://thecse.com/api/webapi/bulletins/",
    "https://thecse.com/api/bulletins/",
    "https://thecse.com/api/webapi/news/",
    "https://thecse.com/sitemap.xml",
    "https://thecse.com/bulletin-sitemap.xml",
    "https://thecse.com/sitemaps/bulletins.xml",
]:
    try:
        r = get(url)
        print(f"  {url} -> {r.status_code} type={r.headers.get('content-type')} len={len(r.content)}")
        if r.status_code == 200:
            print("  SAMPLE:", r.text[:500])
    except Exception as exc:
        print(f"  {url} -> ERROR {exc}")

# ---------------------------------------------------------------------------
# 4) TSX via Newsfile Corp — extract actual result links from the search page
# ---------------------------------------------------------------------------
print("=" * 100, "\nNewsfile Corp search — result extraction")
try:
    r = get("https://www.newsfilecorp.com/search?q=%22name+and+symbol+change%22+TSX")
    body = r.text
    links = re.findall(r'href="(/release/[^"]+)"[^>]*>([^<]{5,120})<', body)
    print("  release links found:", len(links))
    for href, title in links[:15]:
        print("   ", href, "|", title.strip())
    # Also check if there's a JSON API backing the search (XHR)
    apis = sorted(set(re.findall(r'https?://[^"\'\s]+search[^"\'\s]*', body, re.I)))
    for a in apis[:10]:
        print("    api-hint:", a)
except Exception as exc:
    print("  ERROR:", exc)
