#!/usr/bin/env python3
"""Diagnostic round 21: CSE enrichment is at 0/64 with exact-date matching.
Hypothesis: some CSE bulletin types (name+CUSIP, symbol+CUSIP change) aren't
recognized by fetch_cse_rtos()'s CSE_CHANGE_TYPE_RE, so those bulletins never
even become candidates -- meaning a second, later bulletin for the same
ticker (which IS what recent_change reflects) is silently missing from our
list entirely, not just unenriched. Dump every distinct bulletin-type slug
prefix seen in the sitemap in the last ~60 days, and check specifically for
WMC/Wayfinder Metals Corp and FFF/55 North Gold Inc (both showed a SECOND,
more recent rename in probe round 19 that recent_change reflects but that we
never captured as a bulletin candidate). Temporary tool -- not part of the
site."""

import datetime as dt
import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0",
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
}

def get(url, **kw):
    return requests.get(url, headers=HEADERS, timeout=30, **kw)

body = get("https://thecse.com/sitemaps/bulletins.xml").text
locs = re.findall(r"<loc>(https://thecse\.com/bulletin/([^<]+?))/?</loc>", body)
print("total bulletin URLs in sitemap:", len(locs))

CSE_CHANGE_TYPE_RE = re.compile(
    r"^(?P<type>name-and-symbol-change|name-symbol-change(?:-and-consolidation)?|"
    r"name-change(?:-and-consolidation)?|symbol-change(?:-inactive-designation)?|"
    r"resumption-and-symbol-change)-(?P<rest>.+)$"
)

cutoff = (dt.date(2026, 7, 22) - dt.timedelta(days=60)).isoformat()

type_prefixes = {}
unmatched_recent = []
wmc_fff_hits = []
for full_url, slug in locs:
    m = re.match(r"^(\d{4})-(\d{2})(\d{2})-(.+)$", slug)
    if not m:
        continue
    year, month, day, tail = m.groups()
    try:
        d = dt.date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        continue
    if d < cutoff:
        continue
    type_m = CSE_CHANGE_TYPE_RE.match(tail)
    # bucket by first 4 hyphen-tokens of tail, to see slug shapes
    prefix = "-".join(tail.split("-")[:5])
    type_prefixes.setdefault(prefix, 0)
    type_prefixes[prefix] += 1
    if not type_m and re.search(r"name|symbol|cusip", tail, re.I):
        unmatched_recent.append((d, tail))
    if "wmc" in tail.lower() or "wayfinder" in tail.lower() or "55-north" in tail.lower() or tail.lower().endswith("-fff"):
        wmc_fff_hits.append((d, tail, bool(type_m)))

print("=" * 100)
print("Unmatched name/symbol/cusip-ish slugs in the last 60 days (sample up to 40):")
for d, tail in sorted(unmatched_recent)[:40]:
    print(" ", d, tail)
print("total unmatched:", len(unmatched_recent))

print("=" * 100)
print("WMC / Wayfinder / 55 North / FFF bulletins found in sitemap:")
for d, tail, matched in sorted(wmc_fff_hits):
    print(" ", d, tail, "MATCHED" if matched else "NOT MATCHED by current regex")
