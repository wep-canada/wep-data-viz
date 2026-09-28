# wep-data-viz

Open-data dashboards for WEP Canada, built with Python and Shiny. The first one is **BC wildfire
resilience**: current fires, evacuation orders and alerts, satellite detections, and the equity and
governance indicators from the *Building Inclusive Wildfire Resilience in British Columbia* paper.

Design goals: public and transparent, cheap to run alone, and honest about how old its data is.

> For awareness and analysis only. This is not an emergency alert service. For evacuation orders and
> safety information use EmergencyInfoBC, the BC Wildfire Service and your local authority.

## How the data stays fresh

| Tier | What | How | Refresh |
|---|---|---|---|
| **Live** | Fire locations, perimeters, evacuation orders and alerts, satellite hotspots | The app fetches the feeds itself when opened, cached 15 minutes. If a feed fails it uses the last daily snapshot and says so. | Every visit |
| **Daily** | Snapshots of the live feeds, `data/freshness.json`, one row per day in `data/history/daily_summary.parquet` | GitHub Action `daily-refresh` runs `python -m pipeline.run` and commits. The commit redeploys the app. | Daily |
| **Slow** | Season totals, cultural fire, FireSmart, ISC evacuees, and other figures published as text | You edit `data/curated/indicators.csv`. A weekly GitHub Action fingerprints the source pages and opens an issue when one changes. | Yearly, prompted weekly |

Every panel shows an "as of" time and flags itself Fresh, Degraded, Stale, or No data. If a source
changes shape or goes down, the dashboard keeps the last good data, says so, and the daily job fails
loudly so you get an email.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt

# 1. Fetch real data once and check it (see docs/sources.md, "Things to check on the first real run")
cd src && python -m pipeline.run && cd ..

# 2. Run the app
python -m shiny run --reload src/app.py                          # http://127.0.0.1:8000

# 3. Tests
python -m pytest                                       # unit tests (fast, no network)
python -m playwright install chromium && python -m pytest -m e2e   # browser tests
```

To work offline, set `WEPDASH_LIVE_FETCH=0` to use only saved snapshots.

**Base map key.** CARTO now asks for a free key on its map tiles; without one the map shows an
"API KEY REQUIRED" watermark. Request one at <https://carto.com/basemaps/apikey>, copy `.env.example`
to `.env` (or `.env.local`), and set `WEPDASH_CARTO_KEY=your-key` (both files are git-ignored). On Posit
Connect Cloud, add the same name and value as an environment variable in the app's settings. Browsers
can see the key in the tile URLs, so restrict it to your website addresses in CARTO's key settings.
CARTO has said the raster tiles it serves are being phased out, so expect to switch this map to vector
tiles or another provider eventually.

**Important:** the live endpoints were written from the providers' documentation and sample
responses and have not yet been run from this repo against the real servers. Step 1 above is the
first thing to do, and `docs/sources.md` lists what to look for.

## Repository layout

The layout follows the reference repo you shared: one module per concern, a test file to match each,
`.env.example`, and a changelog. Additions for this project are the `pipeline/` and `core/` packages
and the `data/` tiers.

```
wep-data-viz/
├── .github/workflows/     tests.yml, daily-refresh.yml, weekly-watch.yml
├── data/
│   ├── live/              latest snapshot of each live feed (written by the pipeline)
│   ├── history/           daily_summary.parquet, one row per day (written by the pipeline)
│   ├── curated/           indicators.csv, data_gaps.csv, fire_centre_codes.csv (edited by hand)
│   ├── watch/             page fingerprints for the weekly check
│   └── freshness.json     when each source last succeeded (written by the pipeline)
├── docs/sources.md        source catalogue: endpoints, fields, licences, what is untested
├── notebooks/             exploration
├── src/
│   ├── app.py             entry point: assembles the dashboards into one app
│   ├── core/              shared: config, http, freshness, frames (GeoJSON to tables), theme
│   ├── pipeline/          sources.py (registry), fetchers.py, run.py, history.py, watch.py
│   ├── dashboards/
│   │   ├── sources.py     "Data and sources" page (shared by every dashboard)
│   │   └── wildfire/      data.py, filters.py, kpis.py, charts.py, mapview.py, page.py
│   └── www/styles.css
├── tests/                 mirrors src/, plus e2e/ (browser) and fixtures/ (synthetic data)
├── requirements.txt       what Connect Cloud installs (pinned to the tested versions)
└── requirements-dev.txt   adds pytest and playwright
```

`ai_tab.py` and `prompts/` from the reference repo are left out on purpose. A public app with an
LLM key behind it invites cost and abuse; add one later only with rate limits.

## Deploying to Posit Connect Cloud

1. Push this repo to GitHub (public keeps GitHub Actions free).
2. In Connect Cloud, publish from the GitHub repo: pick the branch, set the primary file to
   `src/app.py`, and let it install `requirements.txt`. Check Connect Cloud's current docs for the
   exact wording, since I have not deployed this yet.
3. The daily job's commit to that branch should trigger a redeploy. Confirm this after the first run.
4. Add a `LICENSE` before making the repo public (MIT is typical for code). The data stays under the
   providers' open government licences; the app's Data and sources page carries the attribution.

## Adding another dashboard

1. Copy `src/dashboards/wildfire/` to `src/dashboards/<name>/` and change `data.py` and `page.py`.
2. Register the module in `src/app.py`: one `ui.nav_panel(...)` and one `..._server(...)` call.
3. New data sources go in `src/pipeline/sources.py` (live feeds) or `src/pipeline/watch.py` (pages).
4. Add `tests/` files that mirror the new modules.

Connect Cloud's free plan allows 5 apps; one app with several dashboards uses just one slot.

## Maintaining the curated indicators

`data/curated/indicators.csv` is long-format: one row per indicator per period, with the
definition, source link, and an `origin` column saying either "source page (checked <date>)" or
"webinar paper (Sept 2026); not re-checked". When the weekly job opens an issue, open the page, update
the value, and change `origin` to the date you checked. A test fails if a row lacks a source link,
definition or origin, or if one indicator has two values for the same period.

Some measures are defined differently from year to year (for example First Nations involvement in
cultural fire). Those rows carry a note and are deliberately not charted.

## Known limitations

- **Live endpoints unverified.** See above.
- **Fire centres show as codes** until `fire_centre_codes.csv` is filled.
- **Map tiles need internet.** They come from CARTO; if blocked the map shows fires on a blank background.
- **The map redraws when a filter changes**, so it resets to the province view. Updating layers in place is a later improvement.
- **Console message.** Switching tabs while a chart is still starting can log `[anywidget] Failed to initialize model` in the browser console. It has no visible effect; the browser tests ignore it.
- **Repository size.** Daily snapshots of the perimeter layer add up. If the repo grows past a few hundred MB, move snapshots to GitHub release assets or drop the perimeter snapshot (the live fetch does not need it).
- **Scheduled workflows can be paused** by GitHub after 60 days without repo activity (from memory; check GitHub's docs). Watch for it in the off-season.
- **No gender-disaggregated or community-level outcome data.** This is a finding, shown on the Data gaps tab, not something to fill with proxies.
