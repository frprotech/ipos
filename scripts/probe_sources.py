#!/usr/bin/env python3
"""Diagnostic round 14: does the CSE bulletin page BODY (not just the title)
contain the old name/ticker for name/symbol-change bulletins? Temporary tool
-- not part of the site."""

import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0",
    "Accept": "text/html,application/xhtml+xml",
}

def get(url, **kw):
    return requests.get(url, headers=HEADERS, timeout=30, **kw)

def clean(html):
    body = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    body = re.sub(r"<style.*?</style>", " ", body, flags=re.S | re.I)
    body = re.sub(r"<[^>]+>", " ", body)
    return re.sub(r"\s+", " ", body).strip()

urls = [
    "https://thecse.com/bulletin/2026-0716-name-and-symbol-change-arctic-fox-lithium-corp-afx/",
    "https://thecse.com/bulletin/2026-0615-symbol-change-inactive-designation-egf-theramed-health-corp-tmed/",
    "https://thecse.com/bulletin/2026-0523-symbol-change-copper-one-resources-corp-bfg/",
]

for u in urls:
    print("=" * 100, "\n", u)
    try:
        r = get(u)
        text = clean(r.text)
        # print a big chunk starting right after "Bulletin" heading area, to see
        # the actual body paragraph text (not nav)
        idx = text.find("Bulletin")
        print("  FULL AREA:", text[idx:idx+2500])
    except Exception as exc:
        print("  ERROR:", exc)
