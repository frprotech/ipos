#!/usr/bin/env python3
"""Diagnostic round 3: NASDAQ anonymous FTP daily list, NYSE beta listing-notices
API hunt, ASX official code-changes page. Temporary tool — not part of the site."""

import datetime as dt
import ftplib
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
# 1) NASDAQ — anonymous FTP, list directories to find where Daily List lives.
# ---------------------------------------------------------------------------
print("=" * 100, "\nNASDAQ anonymous FTP exploration")
try:
    ftp = ftplib.FTP("ftp.nasdaqtrader.com", timeout=20)
    ftp.login()  # anonymous
    print("  login OK, welcome:", ftp.getwelcome())
    def walk(path, depth=0):
        if depth > 2:
            return
        try:
            ftp.cwd(path)
        except Exception as exc:
            print(f"  cwd {path} FAILED: {exc}")
            return
        try:
            items = ftp.nlst()
        except Exception as exc:
            print(f"  nlst {path} FAILED: {exc}")
            return
        print(f"  DIR {path}: {items[:30]}")
        for it in items:
            if depth < 1 and ("list" in it.lower() or "daily" in it.lower() or "symbol" in it.lower()):
                walk(f"{path}/{it}" if path != "/" else f"/{it}", depth + 1)
    walk("/")
    ftp.quit()
except Exception as exc:
    print("  FTP ERROR:", exc)

# ---------------------------------------------------------------------------
# 2) NYSE beta listing-notices page — find embedded API / next.js data
# ---------------------------------------------------------------------------
print("=" * 100, "\nNYSE beta listing-notices — API hunt")
for url in [
    "https://beta.nyse.com/market-data/corporate-actions/listing-notices",
    "https://www.nyse.com/data-products/catalog/nyse-and-nyse-american-listing-notices",
]:
    try:
        r = get(url)
        body = r.text
        print(f"  {url} -> {r.status_code} len={len(body)}")
        next_data = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', body, re.S)
        print("  has __NEXT_DATA__:", bool(next_data))
        if next_data:
            print("  NEXT_DATA sample:", next_data.group(1)[:800])
        apis = sorted(set(re.findall(r'"(/api/[^"]+)"', body)))
        print("  /api/ hits:", apis[:20])
        build_id = re.search(r'"buildId":"([^"]+)"', body)
        print("  buildId:", build_id.group(1) if build_id else None)
    except Exception as exc:
        print(f"  {url} -> ERROR {exc}")

# try the Next.js data endpoint pattern if we found a buildId
try:
    r = get("https://beta.nyse.com/market-data/corporate-actions/listing-notices")
    build_id = re.search(r'"buildId":"([^"]+)"', r.text)
    if build_id:
        data_url = f"https://beta.nyse.com/_next/data/{build_id.group(1)}/market-data/corporate-actions/listing-notices.json"
        r2 = get(data_url)
        print(f"  data url {data_url} -> {r2.status_code} len={len(r2.content)}")
        if r2.status_code == 200:
            print("  SAMPLE:", r2.text[:1000])
except Exception as exc:
    print("  next-data-fetch ERROR:", exc)

# ---------------------------------------------------------------------------
# 3) ASX official code-changes page
# ---------------------------------------------------------------------------
print("=" * 100, "\nASX code-changes page")
try:
    r = get("https://www.asx.com.au/markets/market-resources/asx-codes-and-descriptors/asx-code-changes")
    body = r.text
    print(f"  status={r.status_code} len={len(body)}")
    tables = re.findall(r"<table.*?</table>", body, re.S | re.I)
    print("  table count:", len(tables))
    for i, t in enumerate(tables[:2]):
        print(f"  TABLE {i} HEAD:", re.sub(r"\s+", " ", t)[:1000])
    links = sorted(set(re.findall(r'href="([^"]+\.(?:csv|pdf|xlsx?))"', body, re.I)))
    print("  downloadable file links:", links[:10])
    apis = sorted(set(re.findall(r'"(/api/[^"]+|/-/media/[^"]+)"', body)))
    print("  api/media hits:", apis[:10])
except Exception as exc:
    print("  ERROR:", exc)
