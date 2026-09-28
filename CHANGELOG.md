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

- CARTO basemap key support (`WEPDASH_CARTO_KEY`), so the map tiles are not watermarked in production.
- `data/curated/fire_centre_codes.csv` populated (BC fire-centre code -> name), so the dashboard
  shows real fire-centre names instead of "Fire centre <code>". There is no reliable API that maps
  these codes to names (see `docs/sources.md`), so the six rows were hand-verified by cross-checking
  each code's live fire locations against BC Wildfire Service's published fire-centre boundaries.
  `pipeline.verify_fire_centre_codes` re-checks this against each new snapshot.

The live endpoints have been confirmed working against the real government servers (daily refresh
runs green in GitHub Actions).

- Fires are coloured by their real status (out of control / being held / under control) instead of
  a binary "out-of-control vs. everything else" grey bucket, on the map, the legend, and its CSS.
- Fixed the map sometimes going blank after toggling a "Map layers" checkbox off and back on. The
  map used to be torn down and rebuilt from scratch (a brand-new `ipyleaflet.Map`) on every filter
  or layer change; Leaflet can fail to reinitialize a new map into a browser element that still
  holds a previous one, especially across two rebuilds in quick succession, leaving frozen tiles
  and no overlay layers. The map is now built once per session and its layers are updated in place
  (`mapview.new_map` / `mapview.update_layers`) - this also means the map no longer resets to the
  province view on every filter change, since the underlying Leaflet map is never recreated.
