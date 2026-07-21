#!/usr/bin/env python3
"""Diagnostic round 10: is TSXV's NOTICE_ID a global sequential counter we
can scan (like CSE's bulletin slugs), or is it scoped per-company (PO_ID)?
Also inspect one real notice's content/structure. Temporary tool -- not
part of the site."""

import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0",
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
}

def get(url, **kw):
    return requests.get(url, headers=HEADERS, timeout=30, **kw)

BASE = "http://infoventure.tsx.com/TSXVenture/TSXVentureHttpController"

# ---------------------------------------------------------------------------
# 1) Fetch one known notice directly (with its real PO_ID) and inspect it
# ---------------------------------------------------------------------------
print("=" * 100, "\nOne known notice, full content")
try:
    r = get(f"{BASE}?GetPage=NoticesContents&PO_ID=1044821&NOTICE_ID=319314&CORRECTION_FLG=N&HC_FLAG1=checked")
    print("  status:", r.status_code, "len:", len(r.text))
    body = re.sub(r"<[^>]+>", " ", r.text)
    body = re.sub(r"\s+", " ", body).strip()
    print("  TEXT:", body[:1500])
except Exception as exc:
    print("  ERROR:", exc)

# ---------------------------------------------------------------------------
# 2) Try that same NOTICE_ID with a WRONG/blank PO_ID -- does it still work?
#    (tests whether NOTICE_ID alone is globally sufficient)
# ---------------------------------------------------------------------------
print("=" * 100, "\nSame NOTICE_ID, no PO_ID / wrong PO_ID")
for po in ["", "0", "1"]:
    try:
        r = get(f"{BASE}?GetPage=NoticesContents&PO_ID={po}&NOTICE_ID=319314&CORRECTION_FLG=N&HC_FLAG1=checked")
        body = re.sub(r"<[^>]+>", " ", r.text)
        body = re.sub(r"\s+", " ", body).strip()
        print(f"  PO_ID={po!r} -> {r.status_code} len={len(r.text)} text[:200]={body[:200]!r}")
    except Exception as exc:
        print(f"  PO_ID={po!r} ERROR:", exc)

# ---------------------------------------------------------------------------
# 3) Try nearby/different NOTICE_IDs with the SAME PO_ID -- and with a
#    DIFFERENT PO_ID than the notice was originally tied to, to see if
#    NOTICE_ID collisions/lookups cross companies
# ---------------------------------------------------------------------------
print("=" * 100, "\nAdjacent NOTICE_IDs under the same PO_ID")
for nid in [319313, 319315, 319320, 300000, 250000]:
    try:
        r = get(f"{BASE}?GetPage=NoticesContents&PO_ID=1044821&NOTICE_ID={nid}&CORRECTION_FLG=N&HC_FLAG1=checked")
        body = re.sub(r"<[^>]+>", " ", r.text)
        body = re.sub(r"\s+", " ", body).strip()
        print(f"  NOTICE_ID={nid} -> {r.status_code} len={len(r.text)} text[:150]={body[:150]!r}")
    except Exception as exc:
        print(f"  NOTICE_ID={nid} ERROR:", exc)

# ---------------------------------------------------------------------------
# 4) What does LcdbSearch actually do -- a company/symbol lookup form, or
#    something broader?
# ---------------------------------------------------------------------------
print("=" * 100, "\nLcdbSearch page")
try:
    r = get(f"{BASE}?GetPage=LcdbSearch")
    print("  status:", r.status_code, "len:", len(r.text))
    body = re.sub(r"\s+", " ", r.text)
    print("  SAMPLE:", body[:800])
except Exception as exc:
    print("  ERROR:", exc)
