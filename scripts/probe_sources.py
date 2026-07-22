#!/usr/bin/env python3
"""Diagnostic round 20: figure out why the US (NASDAQ/NYSE) RTO fetcher is
producing false "Symbol Change" entries for companies like JPMorgan, Morgan
Stanley, Royal Bank of Canada, Citigroup, Barclays -- their preferred-stock
suffixes (JPM-PC, MS-PK) and OTC/foreign-listing symbols (RYLBF, BWVTF) are
NOT a prior ticker that was renamed, they're just OTHER securities of the
same CIK (different share class or different market). Dump the raw
submissions.json for a handful of these CIKs to see the full tickers[] /
exchanges[] / formerNames[] shape, so we can find a reliable way to exclude
these. Temporary tool -- not part of the site."""

import json
import requests

HEADERS = {
    "User-Agent": "ipos.com RTO tracker (contact: admin@ipos.com)",
    "Accept": "application/json",
}

def get(cik_padded):
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()

# CIKs for the companies the user flagged as wrong, plus one genuine
# small-cap RTO shell (if we still remember one) for contrast.
targets = {
    "JPMorgan Chase": "0000019617",
    "Morgan Stanley": "0000895421",
    "Royal Bank of Canada": "0001000275",
    "Citigroup": "0000831001",
    "Barclays": "0000312069",
}

for name, cik in targets.items():
    print("=" * 100)
    print(name, cik)
    try:
        data = get(cik)
    except Exception as exc:
        print("FETCH FAILED:", exc)
        continue
    print("name:", data.get("name"))
    print("tickers:", data.get("tickers"))
    print("exchanges:", data.get("exchanges"))
    print("category:", data.get("category"))
    print("sicDescription:", data.get("sicDescription"))
    fn = data.get("formerNames") or []
    print(f"formerNames ({len(fn)}):")
    for f in fn[-5:]:
        print(" ", f)
