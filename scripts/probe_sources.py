#!/usr/bin/env python3
"""Diagnostic: probe candidate RTO / name-change data sources for all 5
exchanges from a GitHub runner. Temporary tool — not part of the site."""

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
# 1) NASDAQ Daily List — find the working file-naming pattern
# ---------------------------------------------------------------------------
print("=" * 100, "\nNASDAQ Daily List")
for days_back in range(0, 6):
    d = today - dt.timedelta(days=days_back)
    fname = f"nq{d.month:02d}{d.day:02d}{d.year}.txt"
    for base in [
        "https://www.nasdaqtrader.com/Trader.aspx?id=DailyListFile&file=",
        "https://www.nasdaqtrader.com/Micro.aspx?id=DailyListFile&file=",
        "https://www.nasdaqtrader.com/dynamic/SymDir/",
    ]:
        url = base + fname
        try:
            r = get(url)
            print(f"  {url} -> {r.status_code} len={len(r.content)}")
            if r.status_code == 200 and len(r.content) > 100:
                print("  SAMPLE:", r.text[:500].replace("\n", " | "))
        except Exception as exc:
            print(f"  {url} -> ERROR {exc}")

# Try FTP-style HTTP mirror and the plain nasdaqtrader.com listing page
for url in [
    "https://www.nasdaqtrader.com/trader.aspx?id=DailyListPD",
    "https://www.nasdaqtrader.com/Trader.aspx?id=dailylistpd",
]:
    try:
        r = get(url)
        print(f"  PAGE {url} -> {r.status_code} len={len(r.content)}")
        links = re.findall(r'href="([^"]+\.txt[^"]*)"', r.text, re.I)
        for l in links[:10]:
            print("    txt link:", l)
    except Exception as exc:
        print(f"  PAGE {url} -> ERROR {exc}")

# ---------------------------------------------------------------------------
# 2) NYSE Market Notices / Listing Notices
# ---------------------------------------------------------------------------
print("=" * 100, "\nNYSE Notices")
for url in [
    "https://www.nyse.com/markets/notices",
    "https://www.nyse.com/market-data/corporate-actions/nyse-and-nyse-american-listing-notices",
]:
    try:
        r = get(url)
        print(f"  {url} -> {r.status_code} len={len(r.content)} type={r.headers.get('content-type')}")
        apis = sorted(set(re.findall(r'https?://[^"\'\s]+api[^"\'\s]*', r.text, re.I)))
        for a in apis[:15]:
            print("    api-hint:", a)
        tables = re.findall(r"<table.*?</table>", r.text, re.S | re.I)
        print("    table-count:", len(tables))
    except Exception as exc:
        print(f"  {url} -> ERROR {exc}")

# ---------------------------------------------------------------------------
# 3) ASX code changes page
# ---------------------------------------------------------------------------
print("=" * 100, "\nASX code changes")
url = "https://www.asx.com.au/markets/market-resources/asx-codes-and-descriptors/asx-code-changes"
try:
    r = get(url)
    print(f"  {url} -> {r.status_code} len={len(r.content)}")
    tables = re.findall(r"<table.*?</table>", r.text, re.S | re.I)
    print("  table-count:", len(tables))
    for t in tables[:2]:
        print("  TABLE-HEAD:", re.sub(r"\s+", " ", t)[:1500])
except Exception as exc:
    print(f"  {url} -> ERROR {exc}")

# ---------------------------------------------------------------------------
# 4) CSE bulletins index — filter for name/symbol change bulletins
# ---------------------------------------------------------------------------
print("=" * 100, "\nCSE bulletins")
for url in [
    "https://thecse.com/news-events/bulletins/",
    "https://listings.thecse.com/en/about/publications/bulletins",
]:
    try:
        r = get(url)
        print(f"  {url} -> {r.status_code} len={len(r.content)}")
        links = re.findall(r'href="(/bulletin/[^"]+)"', r.text, re.I)
        print("  bulletin-links found:", len(links))
        for l in links[:10]:
            print("    ", l)
        m = re.search(r'"buildId"\s*:\s*"([^"]+)"', r.text)
        if m:
            print("  NEXT-BUILD-ID:", m.group(1))
    except Exception as exc:
        print(f"  {url} -> ERROR {exc}")

# ---------------------------------------------------------------------------
# 5) TSX name/symbol changes via free press-release wires
# ---------------------------------------------------------------------------
print("=" * 100, "\nTSX via press release wires")
for url in [
    "https://www.newsfilecorp.com/search?q=%22name+and+symbol+change%22+TSX",
    "https://www.globenewswire.com/search/keyword/TSX%2520name%2520and%2520symbol%2520change",
]:
    try:
        r = get(url)
        print(f"  {url} -> {r.status_code} len={len(r.content)}")
        print("  SAMPLE:", re.sub(r"\s+", " ", r.text)[:800])
    except Exception as exc:
        print(f"  {url} -> ERROR {exc}")
