#!/usr/bin/env python3
"""Diagnostic round 13: verify CSE bulletin slug parsing against the ACTUAL
bulletin page content -- specifically checking whether "symbol-change" slugs
encode the OLD ticker or the NEW ticker, since two different bulletins
(Copper One Resources Corp, Giant Mining Corp) both parsed to ticker "BFG"
which looks suspicious. Also check acronym-style company names like "Egf
Theramed Health Corp" (should probably be "EGF"). Temporary tool -- not
part of the site."""

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
    "https://thecse.com/bulletin/2026-0523-symbol-change-copper-one-resources-corp-bfg/",
    "https://thecse.com/bulletin/2026-0425-name-change-and-consolidation-giant-mining-corp-bfg/",
    "https://thecse.com/bulletin/2026-0615-symbol-change-inactive-designation-egf-theramed-health-corp-tmed/",
    "https://thecse.com/bulletin/2026-0716-name-and-symbol-change-arctic-fox-lithium-corp-afx/",
]

for u in urls:
    print("=" * 100, "\n", u)
    try:
        r = get(u)
        print("  status:", r.status_code, "len:", len(r.text))
        text = clean(r.text)
        # find the main content area -- look for keywords
        idx = text.lower().find("symbol")
        if idx == -1:
            idx = text.lower().find("name")
        print("  TEXT sample:", text[max(0, idx-300):idx+900])
    except Exception as exc:
        print("  ERROR:", exc)
