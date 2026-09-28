"""Registry of live-tier data sources.

One place describes every feed: where it is, how to read it, its licence and how
old it may get before the dashboard flags it as stale. The pipeline, the app and
the "Data & sources" page all read from this registry, so adding a source is one
entry here.

These endpoints have been run against the live servers (see ``docs/sources.md``
and the ``daily-refresh`` GitHub Action's run history) and are confirmed working.
If you add or change a source, re-run ``python -m pipeline.run`` once and update
``docs/sources.md`` before relying on it.
"""

from __future__ import annotations

from dataclasses import dataclass

# Rough bounding box of British Columbia (min lon, min lat, max lon, max lat).
BC_BBOX = (-139.06, 48.30, -114.03, 60.00)

OGL_BC = "Open Government Licence – British Columbia"
OGL_BC_URL = "https://www2.gov.bc.ca/gov/content/data/open-data/open-government-licence-bc"
OGL_CANADA = "Open Government Licence – Canada"
OGL_CANADA_URL = "https://open.canada.ca/en/open-government-licence-canada"


@dataclass(frozen=True)
class SourceSpec:
    key: str
    label: str
    kind: str                       # "wfs" or "arcgis"
    url: str                        # WFS endpoint, or ArcGIS layer URL (without /query)
    licence: str
    licence_url: str
    landing_page: str
    layer: str = ""                 # WFS typeNames
    where: str = "1=1"              # ArcGIS filter
    sort_keys: tuple[str, ...] = () # properties used to order features (stable diffs)
    bbox: tuple[float, float, float, float] | None = None
    expected_max_age_hours: float = 36.0   # snapshots are refreshed daily
    coord_digits: int = 5


BC_WFS = "https://openmaps.gov.bc.ca/geo/pub/wfs"

SOURCES: dict[str, SourceSpec] = {
    "bc_fire_points": SourceSpec(
        key="bc_fire_points",
        label="BC current fire locations",
        kind="wfs",
        url=BC_WFS,
        layer="pub:WHSE_LAND_AND_NATURAL_RESOURCE.PROT_CURRENT_FIRE_PNTS_SP",
        licence=OGL_BC,
        licence_url=OGL_BC_URL,
        landing_page="https://www2.gov.bc.ca/gov/content/safety/wildfire-status/about-bcws/wildfire-statistics",
        sort_keys=("FIRE_NUMBER", "OBJECTID"),
    ),
    "bc_fire_perimeters": SourceSpec(
        key="bc_fire_perimeters",
        label="BC current fire perimeters",
        kind="wfs",
        url=BC_WFS,
        layer="pub:WHSE_LAND_AND_NATURAL_RESOURCE.PROT_CURRENT_FIRE_POLYS_SP",
        licence=OGL_BC,
        licence_url=OGL_BC_URL,
        landing_page="https://open.canada.ca/data/dataset/cdfc2d7b-c046-4bf0-90ac-4897232619e1",
        sort_keys=("FIRE_NUMBER", "OBJECTID"),
        coord_digits=4,
    ),
    "bc_evac_orders": SourceSpec(
        key="bc_evac_orders",
        label="BC evacuation orders and alerts",
        kind="arcgis",
        url="https://services6.arcgis.com/ubm4tcTYICKBpist/arcgis/rest/services/"
            "Evacuation_Orders_and_Alerts/FeatureServer/0",
        licence=OGL_BC,
        licence_url=OGL_BC_URL,
        landing_page="https://open.canada.ca/data/en/dataset/7efd46d0-b5d3-4dff-af80-d376c42aec33",
        sort_keys=("EMRG_OAA_SYSID", "OBJECTID"),
        coord_digits=4,
    ),
    "cwfis_hotspots": SourceSpec(
        key="cwfis_hotspots",
        label="Satellite hotspots, last 24 h (BC)",
        kind="wfs",
        url="https://cwfis.cfs.nrcan.gc.ca/geoserver/wfs",
        layer="public:hotspots_last24hrs",
        licence=OGL_CANADA,
        licence_url=OGL_CANADA_URL,
        landing_page="https://cwfis.cfs.nrcan.gc.ca/datamart",
        bbox=BC_BBOX,
    ),
}


def get_source(key: str) -> SourceSpec:
    return SOURCES[key]
