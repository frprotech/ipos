#!/usr/bin/env python3
"""Diagnostic round 11: extract the actual bulletin text (past the nav
boilerplate) for several TSXV NOTICE_IDs to confirm the Name/Symbol Change
format is parseable, and get a rough sense of the NOTICE_ID range for our
tracking window. Temporary tool -- not part of the site."""

import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0",
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
}

def get(url, **kw):
    return requests.get(url, headers=HEADERS, timeout=30, **kw)

BASE = "http://infoventure.tsx.com/TSXVenture/TSXVentureHttpController"


def bulletin_text(nid: int) -> str:
    r = get(f"{BASE}?GetPage=NoticesContents&PO_ID=0&NOTICE_ID={nid}&CORRECTION_FLG=N&HC_FLAG1=checked")
    body = re.sub(r"<script.*?</script>", " ", r.text, flags=re.S | re.I)
    body = re.sub(r"<[^>]+>", " ", body)
    body = re.sub(r"&nbsp;", " ", body)
    body = re.sub(r"\s+", " ", body).strip()
    # the real content starts after the nav menu; find "Bulletin" heading
    idx = body.find("Bulletin Type")
    if idx == -1:
        idx = body.find("BULLETIN TYPE")
    return body[idx: idx + 1200] if idx != -1 else body[-1200:]


print("=" * 100, "\nFull bulletin text for several NOTICE_IDs")
for nid in [319314, 319313, 319315, 319320, 300000]:
    print(f"--- NOTICE_ID={nid} ---")
    try:
        print(" ", bulletin_text(nid)[:900])
    except Exception as exc:
        print("  ERROR:", exc)

# ---------------------------------------------------------------------------
# Try to calibrate the ID->date relationship: fetch a handful more and print
# any date string found, to see roughly how many IDs correspond to a year.
# ---------------------------------------------------------------------------
print("=" * 100, "\nDate calibration across a spread of NOTICE_IDs")
for nid in [50000, 100000, 150000, 200000, 250000, 280000, 300000, 310000, 315000, 319000, 319314, 320000, 321000]:
    try:
        r = get(f"{BASE}?GetPage=NoticesContents&PO_ID=0&NOTICE_ID={nid}&CORRECTION_FLG=N&HC_FLAG1=checked")
        body = re.sub(r"<script.*?</script>", " ", r.text, flags=re.S | re.I)
        body = re.sub(r"<[^>]+>", " ", body)
        body = re.sub(r"&nbsp;", " ", body)
        body = re.sub(r"\s+", " ", body)
        m = re.search(r"Bulletin Date:?\s*([A-Za-z]+ \d{1,2},? \d{4})", body, re.I)
        print(f"  NOTICE_ID={nid} -> date: {m.group(1) if m else 'NOT FOUND'} (len={len(body)})")
    except Exception as exc:
        print(f"  NOTICE_ID={nid} ERROR:", exc)
