#!/usr/bin/env python3
"""Diagnostic round 22: re-check whether a CSE bulletin's full page BODY
(not just <title>) ever mentions the company's former name/ticker -- earlier
research only checked the <title> tag. Also check if there's a distinct
"Name Change" / "Symbol Change" bulletin CATEGORY page or RSS feed with
richer body text, and whether thecse.com exposes any per-company change
HISTORY (not just the single most recent one) anywhere else -- e.g. an
issuer profile page, a filings page, or a "corporate actions" endpoint.
Temporary tool -- not part of the site."""

import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0",
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
}

def get(url, **kw):
    return requests.get(url, headers=HEADERS, timeout=30, **kw)

# A few real, recent name/symbol-change bulletins we already know about.
bulletins = [
    "https://thecse.com/bulletin/2026-0716-name-and-symbol-change-arctic-fox-lithium-corp-afx",
    "https://thecse.com/bulletin/2026-0611-name-and-symbol-change-cullinan-metals-corp-cmt",
    "https://thecse.com/bulletin/2026-0622-name-change-uberdoc-health-technologies-corp-appt",
]

for url in bulletins:
    print("=" * 100)
    print(url)
    try:
        r = get(url)
        html = r.text
    except Exception as exc:
        print("FETCH FAILED:", exc)
        continue
    print("status:", r.status_code, "| length:", len(html))
    # strip tags crudely to get plain text
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    print("plain text length:", len(text))
    # look for any mention of "formerly" / "changed its name" / "previously"
    for kw in ["formerly", "previously", "changed its name", "change its symbol", "was known as"]:
        idx = text.lower().find(kw)
        if idx != -1:
            print(f"  FOUND '{kw}' at {idx}: ...{text[max(0,idx-100):idx+200]}...")
        else:
            print(f"  not found: {kw!r}")
    # dump the full plain text body (bounded) so we can see its real shape
    print("--- first 1500 chars of body text ---")
    print(text[:1500])

# Also probe: does thecse.com have an issuer/company profile page with a
# change-history section? Try a couple of guessed URL shapes for one ticker.
print("=" * 100)
print("Trying possible per-company profile/history endpoints for AFX")
candidates = [
    "https://thecse.com/en/listings/mining/arctic-fox-lithium-corp",
    "https://thecse.com/api/webapi/listed-companies/AFX",
    "https://thecse.com/api/webapi/company-history/AFX",
    "https://thecse.com/api/webapi/symbol-changes/",
    "https://thecse.com/api/webapi/name-changes/",
]
for url in candidates:
    try:
        r = get(url)
        print(url, "->", r.status_code, "len", len(r.text))
        if r.status_code == 200 and len(r.text) < 2000:
            print("   body:", r.text[:500])
    except Exception as exc:
        print(url, "-> FAILED", exc)
