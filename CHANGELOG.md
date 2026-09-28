# Changelog

All notable changes to this project. Newest first.

## 0.1.0 (unreleased)

First working scaffold.

- Shiny for Python app with a BC wildfire dashboard: headline numbers, map (fires, perimeters,
  evacuation orders and alerts, satellite hotspots), charts, table views, equity and governance
  indicators, a data-gaps page, and a data and sources page. Light and dark mode.
- Live tier: the app fetches BC fire locations, perimeters, evacuation orders and alerts, and
  satellite hotspots, cached for 15 minutes, falling back to the last daily snapshot.
- Pipeline (`python -m pipeline.run`): daily snapshots, freshness manifest, append-only daily history.
- Page watcher (`python -m pipeline.watch`): flags changes to pages that publish numbers as text.
- GitHub Actions: tests, daily refresh, weekly page watch.
- Curated indicators from the BC Wildfire webinar paper, each with its source and whether it was re-checked.

Known gaps: the live endpoints have not yet been run from this repo against the real servers, and
`data/curated/fire_centre_codes.csv` is empty (fire centres show as "Fire centre <code>").
