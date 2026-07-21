#!/usr/bin/env python3
"""Diagnostic round 12: does the TSXV notice body itself contain the company
name/ticker (before "BULLETIN TYPE"), independent of PO_ID? Also specifically
find a real Name Change / Symbol Change bulletin to confirm its exact text
format. Temporary tool -- not part of the site."""

import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0",
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
}

def get(url, **kw):
    return requests.get(url, headers=HEADERS, timeout=30, **kw)

BASE = "http://infoventure.tsx.com/TSXVenture/TSXVentureHttpController"


def clean(html: str) -> str:
    body = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    body = re.sub(r"<style.*?</style>", " ", body, flags=re.S | re.I)
    body = re.sub(r"<[^>]+>", " ", body)
    body = re.sub(r"&nbsp;", " ", body)
    return re.sub(r"\s+", " ", body).strip()


print("=" * 100, "\nFull body (no PO_ID) around 'Bulletin Contents' heading -- look for company name/ticker")
for nid in [319314, 319313, 300000]:
    r = get(f"{BASE}?GetPage=NoticesContents&PO_ID=0&NOTICE_ID={nid}&CORRECTION_FLG=N&HC_FLAG1=checked")
    body = clean(r.text)
    idx = body.find("Bulletin Contents")
    print(f"--- NOTICE_ID={nid} (PO_ID=0) ---")
    print(" ", body[idx:idx+700] if idx != -1 else body[:700])

print("=" * 100, "\nSame notices WITH a correct-ish PO_ID (from the earlier list) to compare")
# 1044821 was the PO_ID tied to notice 319314 in the original probe
for nid, po in [(319314, 1044821)]:
    r = get(f"{BASE}?GetPage=NoticesContents&PO_ID={po}&NOTICE_ID={nid}&CORRECTION_FLG=N&HC_FLAG1=checked")
    body = clean(r.text)
    idx = body.find("Bulletin Contents")
    print(f"--- NOTICE_ID={nid} PO_ID={po} ---")
    print(" ", body[idx:idx+700] if idx != -1 else body[:700])

print("=" * 100, "\nScan a range for an actual Name/Symbol Change bulletin to see its exact text")
found = 0
for nid in range(319300, 319400):
    try:
        r = get(f"{BASE}?GetPage=NoticesContents&PO_ID=0&NOTICE_ID={nid}&CORRECTION_FLG=N&HC_FLAG1=checked")
        body = clean(r.text)
        if re.search(r"BULLETIN TYPE:[^.]*?(Name Change|Symbol Change)", body, re.I):
            idx = body.find("Bulletin Contents")
            print(f"  NOTICE_ID={nid}:", body[idx:idx+900] if idx != -1 else body[:900])
            found += 1
            if found >= 3:
                break
    except Exception:
        continue
print("  total Name/Symbol Change bulletins found in range:", found)
