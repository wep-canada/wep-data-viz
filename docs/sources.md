# Data source catalogue

Every source the dashboard uses or plans to use. The live-tier entries are registered in
`src/pipeline/sources.py`; the pages watched for changes are in `src/pipeline/watch.py`.

**Status legend.** *Confirmed* means this has been run from this repo against the live server (see the
`daily-refresh` GitHub Action's run history). *Untested* means the endpoint, layer and field names
still only come from the provider's public documentation and sample responses.

## Live tier (fetched by the app, snapshotted daily)

| Key | Provider and layer | Access | Fields the code relies on | Licence | Status |
|---|---|---|---|---|---|
| `bc_fire_points` | BC Wildfire Service, current fire locations (`WHSE_LAND_AND_NATURAL_RESOURCE.PROT_CURRENT_FIRE_PNTS_SP`) | WFS 2.0 at `openmaps.gov.bc.ca/geo/pub/wfs`, GeoJSON. Provider says it refreshes about every 15 minutes. | `FIRE_NUMBER`, `INCIDENT_NAME`, `FIRE_STATUS`, `FIRE_CAUSE`, `CURRENT_SIZE`, `IGNITION_DATE` (date-only with a trailing Z), `GEOGRAPHIC_DESCRIPTION`, `FIRE_CENTRE` (a numeric code, 2-7 in practice - see below), `ZONE`, `FIRE_URL`, `FIRE_OF_NOTE_IND` | Open Government Licence – British Columbia | Confirmed |
| `bc_fire_perimeters` | BC Wildfire Service, current fire perimeters (`WHSE_LAND_AND_NATURAL_RESOURCE.PROT_CURRENT_FIRE_POLYS_SP`) | WFS 2.0, same server | `FIRE_NUMBER` (used to match perimeters to fires; perimeters without it are always shown) | OGL – BC | Confirmed |
| `bc_evac_orders` | EMCR, Evacuation Orders and Alerts | ArcGIS REST FeatureServer layer 0 (`services6.arcgis.com/ubm4tcTYICKBpist/...`), `f=geojson`, paged | `EVENT_TYPE` (must contain "fire" to count as wildfire), `ORDER_ALERT_STATUS` (Order, Alert, All Clear), `ORDER_ALERT_NAME`, `ISSUING_AGENCY`, `MULTI_SOURCED_HOMES`, `MULTI_SOURCED_POPULATION`, `EVENT_START_DATE` and `DATE_MODIFIED` (epoch milliseconds) | OGL – BC | Confirmed |
| `cwfis_hotspots` | Natural Resources Canada, CWFIS, `public:hotspots_last24hrs` | WFS at `cwfis.cfs.nrcan.gc.ca/geoserver/wfs`; the app keeps points inside a BC bounding box | Geometry only (a count is shown) | OGL – Canada (confirm on the CWFIS metadata page) | Confirmed |

### Fire centre codes: a trap worth documenting

`FIRE_CENTRE` on `bc_fire_points` is a plain integer (2-7 as of 2026) with **no coded-value domain**
anywhere in BC's WFS or ArcGIS schema for this layer - confirmed by inspecting both. BC does publish a
fire-centre name lookup as a separate ArcGIS layer (fire-centre *boundaries*, field
`MOF_FIRE_CENTRE_ID`), but that layer's numbering (141-146) is a **different code space** - they are
not the same codes, even though both layers describe the same six fire centres. Querying that boundary
layer for names and writing its codes into `data/curated/fire_centre_codes.csv` produces a mapping that
silently never matches (the dashboard falls back to "Fire centre 2", etc., with no error).

Because there is no reliable API for this specific mapping, the six rows in
`data/curated/fire_centre_codes.csv` are hand-verified instead: each code's fires were geo-located
(centroid + example place names from a live snapshot) against BC Wildfire Service's own
[fire-centre boundary descriptions](https://www2.gov.bc.ca/gov/content/safety/wildfire-status/about-bcws/fire-centres),
with one independent news-source spot check (code 5's cluster matches a fire reported under "Kamloops
Fire Centre" near Stump Lake). Run `python -m pipeline.verify_fire_centre_codes` after a fresh snapshot
to print each code's current centroid for a human sanity check - BC very rarely renumbers fire centres,
but a mismatch there should be investigated, not silently trusted.

### Other things to keep an eye on

1. **Coordinate order.** The fetcher asks for `EPSG:4326` and swaps coordinates if a server returns
   (lat, lon). This has been confirmed correct against the real feeds; re-check if a provider changes
   its response format.
2. **Evacuation layer contents.** A sample record looked historical (2021 landslide), so the layer may
   hold more than active orders. The dashboard already keeps only wildfire orders and alerts, but check
   `EVENT_TYPE` and `ORDER_ALERT_STATUS` values against the real data if that filter ever looks wrong.
3. **Perimeter size.** If the perimeter layer grows to several MB, the daily snapshot will grow the
   repo. See "Repository size" in the README.
4. **Hotspot filter.** The bounding box is applied after download. Watch for the national layer
   becoming large enough to slow the request.

## Slow tier (curated by hand, watched weekly)

These publish numbers as text, so there is nothing safe to parse automatically. The weekly job
fingerprints each page and opens an issue when it changes.

| Page | What we take from it | Notes |
|---|---|---|
| [ISC evacuation statistics](https://www.sac-isc.gc.ca/eng/1583177459681/1583177553276) | First Nations evacuees in BC (total and over 60 days) | HTML bullets and chart images, no download, "numbers are not final", no community detail |
| [BC season summary](https://www2.gov.bc.ca/gov/content/safety/wildfire-status/about-bcws/wildfire-history/wildfire-season-summary) | Fires and hectares per season | Narrative, updated about once a year. The 2025 page says 1,370 fires and about 886,300 ha; the webinar paper says "more than 1,350" and 886,360 ha. |
| [BC cultural and prescribed fire](https://www2.gov.bc.ca/gov/content/safety/wildfire-status/prevention/prescribed-burning) | Projects, hectares, First Nations involvement per year | Prose quick facts plus annual PDFs. The First Nations measure is defined differently each year. |
| [FireSmart Community Funding and Supports](https://www2.gov.bc.ca/gov/content/safety/wildfire-status/prevention/funding-for-wildfire-prevention/crip/fcfs) | About $71 M to 265 communities since 2019 | No per-community list; ask UBCM (cri-swpi@ubcm.ca) |

## Candidates for later

| Source | Why | Access | Caveat |
|---|---|---|---|
| BC historical orders and alerts | Order-area durations (a partial proxy for displacement time) | Download or WMS on DataCatalogue; updated annually | Order areas, not people |
| BC historical fire perimeters | Long-run exposure and burned area | WFS / download | Large |
| Statistics Canada 2021 Census | Community indicators (age, income, household, housing) to join to fire and evacuation areas | Census Profile downloads; Web Data Service for change detection | 2026 Census releases start later (my understanding is early 2027, not verified) |
| National Burned Area Composite, National Fire Database | National context and long history | CWFIS datamart downloads | Annual |
| CWFIS active fires, fire danger, fire weather index | National view and forecast danger | WFS layers `cwfif_national_activefires` (returns a long time series, needs a filter), `fdr`, `fwi` | Confirm field names first |
| ECCC Air Quality Health Index | Smoke exposure | MSC GeoMet OGC API (`api.weather.gc.ca`) | My fetch tool was blocked by robots.txt; check the terms for programmatic use |
| NASA FIRMS | Satellite hotspots with more detail | REST API, free map key | Key must stay out of git |
| CIFFC situation report | National preparedness level and resource sharing | ciffc.net | Returned 403 to my fetch tool; CWFIS republishes national data, or ask CIFFC |
| BC fire danger rating and weather stations | Hazard layer | DataBC WFS | Layer names not confirmed |

## Attribution

Contains information licensed under the Open Government Licence – British Columbia and the Open
Government Licence – Canada. The dashboard's Data and sources page repeats this.
