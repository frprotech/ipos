# IPO Tracker

A self-updating table of recent and upcoming IPOs / new listings on:

- **TSX** (Toronto Stock Exchange, incl. TSX Venture)
- **NASDAQ**
- **NYSE** (incl. NYSE American)
- **ASX** (Australian Securities Exchange)
- **CSE** (Canadian Securities Exchange)

## How it works

```
GitHub Actions (every 6 h) ──► scripts/fetch_ipos.py ──► data/ipos.json ──► index.html
```

1. The **Update IPO data** workflow (`.github/workflows/update-ipos.yml`) runs
   every 6 hours (and on demand from the Actions tab).
2. `scripts/fetch_ipos.py` pulls listing data from each exchange's public
   source, merges it with the previous data, and rewrites `data/ipos.json`.
   Each exchange is fetched independently — if one source is down or changes
   its format, its previous data is kept and the run still succeeds (the
   failure is noted in `sources_failed` and shown on the page).
3. `index.html` renders the table with exchange filter tabs, search, and
   column sorting, and re-fetches the data file every 15 minutes while open.

### Data sources

| Exchange | Source |
| --- | --- |
| NASDAQ / NYSE | Nasdaq IPO calendar API (`api.nasdaq.com/api/ipo/calendar`) — covers all US exchanges and tags each deal with its proposed exchange |
| TSX / TSXV | [tsx.com — Current listing activity](https://www.tsx.com/listings/current-listing-activity) |
| ASX | [asx.com.au — Upcoming floats & listings](https://www.asx.com.au/markets/trade-our-cash-market/upcoming-floats-and-listings) |
| CSE | CSE public securities feed (`webapi.thecse.ca`), filtered to listings from the past 12 months |

Records older than 12 months are pruned automatically.

## Setup (one-time)

1. **Enable the workflow** — merge this branch to `main`; scheduled workflows
   only run from the default branch.
2. **Enable GitHub Pages** — repo *Settings → Pages → Source: GitHub Actions*.
   The workflow then publishes the site automatically after each data update.
3. **First data load** — go to *Actions → Update IPO data → Run workflow* to
   populate the table immediately instead of waiting for the next cron tick.

You can also open `index.html` from any static host (or locally with
`python -m http.server`) — it only needs `data/ipos.json` next to it.

## Notes & maintenance

- The TSX and ASX fetchers parse public web pages; if an exchange redesigns
  its page, that fetcher will start logging a warning in the workflow run
  while the other exchanges keep updating. The parsers live in
  `scripts/fetch_ipos.py` and are small and column-name driven, so they are
  easy to adjust.
- Sector data is shown when the source provides it (the US IPO calendar does
  not include sectors, so US rows show "—").
