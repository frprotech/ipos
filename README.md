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
| TSX / TSXV | [tsx.com — New company listings](https://www.tsx.com/en/news/new-company-listings) |
| ASX | [asx.com.au — Upcoming floats & listings](https://www.asx.com.au/listings/upcoming-floats-and-listings) |
| CSE | thecse.com listed-companies data API, filtered to listings from the past 12 months |

Records older than 12 months are pruned automatically.

### Name & Symbol Changes (RTOs)

`rtos.html` is a **separate, standalone page** (its own embed/iframe, not a
tab inside `index.html`) tracking company name/ticker changes — including
reverse takeovers — updated on the same 6-hour cycle by
`scripts/fetch_rtos.py` into `data/rtos.json`:

| Exchange | Source |
| --- | --- |
| ASX | [asx.com.au — ASX code changes](https://www.asx.com.au/markets/market-resources/asx-codes-and-descriptors/asx-code-changes) — full history table, scraped directly |
| CSE | thecse.com's bulletins sitemap — the bulletin type (name change / symbol change / name & symbol change) is encoded in the URL slug itself. Old name/ticker is enriched in from thecse.com's listed-companies webapi, which carries a `recent_change` field (`name_was`/`symbol_was`) for each company's single most recent change — matched to a bulletin by ticker + date proximity, so it only fills in when that bulletin *is* the company's latest change, not for every historical row |
| NASDAQ / NYSE | SEC EDGAR's bulk `submissions.zip` (one filing-history JSON per company, covering every US-listed CIK) — scanned directly for `formerNames` entries within the tracking window, rather than relying on full-text search for filing wording (which turned out to miss real cases, since not every rename 8-K phrases it the same way). The CIK is a stable ID that never changes, so old and new ticker can be linked even when the ticker itself changes (not just the company name) — this properly covers cases like a reverse takeover that renames both the company and its ticker. |
| TSXV | infoventure.tsx.com's bulletin system. Each bulletin's `NOTICE_ID` is a global sequential counter, and the bulletin text itself (`NEW NAME ("TICK") [formerly Old Name ("OLD")] BULLETIN TYPE: Name Change`) carries everything needed — no per-company lookup required. The fetcher only scans forward from the last `NOTICE_ID` it checked (persisted in `data/snapshots/tsxv_last_notice_id.json`), so a run only makes a small number of requests once caught up to the present; a fresh deployment backfills roughly a year of history over its first several runs. |
| TSX (senior board) | **Not automated.** TMX's official corporate-actions feed covering the senior board (Datalinx / TSX Bulletins) is a paid product, and there's no free structured alternative; this is reported as a standing `sources_failed` entry so the gap stays visible instead of silently showing nothing. |

There is also a **Probe data sources** workflow (`.github/workflows/probe.yml`
+ `scripts/probe_sources.py`) — a manual diagnostic that fetches candidate
URLs from a runner and prints what they return. If an exchange fetcher breaks
after a website redesign, edit the probe's URL list, run it from the Actions
tab, and point the fetcher at whatever the logs show is working.

## Setup (one-time)

1. **Enable the workflow** — merge this branch to `main`; scheduled workflows
   only run from the default branch.
2. **Enable GitHub Pages** — repo *Settings → Pages → Source: GitHub Actions*.
   The workflow then publishes the site automatically after each data update.
3. **First data load** — go to *Actions → Update IPO data → Run workflow* to
   populate the table immediately instead of waiting for the next cron tick.

You can also open `index.html` or `rtos.html` from any static host (or
locally with `python -m http.server`) — they only need `data/ipos.json` /
`data/rtos.json` respectively, next to them. Embed each as its own iframe
wherever it's needed on the site; they don't share any UI state.

### Deploying on Vercel instead of GitHub Pages

The repo includes `vercel.json` + `.vercelignore`, which tell Vercel this is a
plain static site (the Python script only runs inside GitHub Actions, not on
the host). Just import the repo in Vercel with default settings — no build
command, no framework. Because the update workflow commits the refreshed
`data/ipos.json` to the branch, every data update automatically triggers a new
Vercel deployment, so the hosted table stays current. The workflow's
`deploy` job (GitHub Pages) is optional and can be deleted from
`.github/workflows/update-ipos.yml` if you only use Vercel.

## Notes & maintenance

- The TSX and ASX fetchers parse public web pages; if an exchange redesigns
  its page, that fetcher will start logging a warning in the workflow run
  while the other exchanges keep updating. The parsers live in
  `scripts/fetch_ipos.py` and are small and column-name driven, so they are
  easy to adjust.
- Sector data is shown when the source provides it (the US IPO calendar does
  not include sectors, so US rows show "—").
