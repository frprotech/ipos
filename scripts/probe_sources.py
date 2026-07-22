#!/usr/bin/env python3
"""Diagnostic round 15: CSE bulletin page body has no old-name/ticker text at
all (confirmed round 14) -- check for a linked PDF notice document, or a
hidden API backing the page, that might carry the full details. Temporary
tool -- not part of the site."""

import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0",
    "Accept": "text/html,application/xhtml+xml",
}

def get(url, **kw):
    return requests.get(url, headers=HEADERS, timeout=30, **kw)

url = "https://thecse.com/bulletin/2026-0716-name-and-symbol-change-arctic-fox-lithium-corp-afx/"
r = get(url)
body = r.text

print("=" * 100, "\nPDF / document links on the bulletin page")
pdfs = sorted(set(re.findall(r'href="([^"]+\.pdf[^"]*)"', body, re.I)))
print("  pdf links:", pdfs)

print("=" * 100, "\nAny data-* / API / json hints in the raw HTML")
apis = sorted(set(re.findall(r'"(/wp-json/[^"]+|/api/[^"]+)"', body)))
print("  api-ish paths:", apis[:20])

print("=" * 100, "\nWordPress REST API guess (thecse.com looks WP-based)")
for path in [
    "wp-json/wp/v2/bulletin?slug=2026-0716-name-and-symbol-change-arctic-fox-lithium-corp-afx",
    "wp-json/wp/v2/posts?slug=2026-0716-name-and-symbol-change-arctic-fox-lithium-corp-afx",
    "wp-json/",
]:
    try:
        rr = get(f"https://thecse.com/{path}")
        print(f"  {path} -> {rr.status_code} type={rr.headers.get('content-type')} len={len(rr.content)}")
        if rr.status_code == 200 and "json" in (rr.headers.get("content-type") or ""):
            print("  SAMPLE:", rr.text[:1500])
    except Exception as exc:
        print(f"  {path} ERROR:", exc)
