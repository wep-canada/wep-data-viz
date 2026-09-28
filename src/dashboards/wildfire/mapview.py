"""The Leaflet map.

Layers, drawn bottom to top: fire perimeters, evacuation areas, satellite hotspots, fires.
Fires use the "emphasis" form: out-of-control fires in the accent colour, everything else in
grey. Evacuation orders and alerts use the reserved status colours and differ by line style
(solid for orders, dashed for alerts), so colour is never the only cue.
"""

from __future__ import annotations

from typing import Callable

import pandas as pd
from ipyleaflet import GeoJSON, Map, TileLayer
from ipywidgets import Layout

from core import config
from core.frames import evac_frame
from core.normalize import normalize_evac_status
from core.theme import tokens

BC_CENTER = (54.5, -125.5)
BC_ZOOM = 5

# (minimum hectares, marker radius in px): marker size grows with fire size.
RADIUS_BUCKETS = [(0.0, 3), (1.0, 5), (100.0, 8), (1000.0, 11), (10000.0, 14)]

LAYER_CHOICES = {
    "perimeters": "Fire perimeters",
    "fires": "Fires",
    "evacuations": "Evacuation orders and alerts",
    "hotspots": "Satellite hotspots (24 h)",
}
DEFAULT_LAYERS = ["perimeters", "fires", "evacuations"]

TILES = {
    "light": "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
    "dark": "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
}
ATTRIBUTION = "&copy; OpenStreetMap contributors &copy; CARTO"


def tile_url(mode: str) -> str:
    """Tile URL for "light" or "dark", with the CARTO key attached when one is configured."""
    url = TILES["dark" if mode == "dark" else "light"]
    key = config.CARTO_KEY
    return f"{url}?key={key}" if key else url


def radius_for(size_ha) -> int:
    """Marker radius in px for a fire of ``size_ha`` hectares (unknown size gets the smallest)."""
    try:
        size = float(size_ha)
    except (TypeError, ValueError):
        return RADIUS_BUCKETS[0][1]
    if size != size:  # NaN
        return RADIUS_BUCKETS[0][1]
    radius = RADIUS_BUCKETS[0][1]
    for minimum, r in RADIUS_BUCKETS:
        if size >= minimum:
            radius = r
    return radius


def safe_https_url(url) -> str | None:
    """Only ever link to https URLs."""
    text = str(url or "")
    return text if text.startswith("https://") else None


def fire_detail_items(row) -> list[tuple[str, str]]:
    """Label/value pairs describing one fire, ready for display."""
    size = row["size_ha"]
    ignited = row["ignition_date"]
    return [
        ("Status", str(row["status"])),
        ("Size", "unknown" if pd.isna(size) else f"{size:,.1f} ha"),
        ("Cause", str(row["cause"])),
        ("Ignited", "unknown" if pd.isna(ignited) else pd.Timestamp(ignited).strftime("%Y-%m-%d")),
        ("Near", str(row["description"]) or "unknown"),
    ]


def fires_feature_collection(frame: pd.DataFrame) -> dict:
    """Minimal GeoJSON for the fire markers (the map only needs the fire number)."""
    features = []
    for row in frame.itertuples():
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [row.lon, row.lat]},
            "properties": {"fire_number": row.fire_number},
        })
    return {"type": "FeatureCollection", "features": features}


def filter_perimeters(fc: dict, fire_numbers: set[str]) -> dict:
    """Keep perimeters of the fires currently shown. Perimeters without a fire number stay."""
    kept = []
    for feature in fc.get("features", []):
        number = (feature.get("properties") or {}).get("FIRE_NUMBER")
        if number is None or str(number) in fire_numbers:
            kept.append(feature)
    return {"type": "FeatureCollection", "features": kept}


def wildfire_evac_features(fc: dict) -> dict:
    """Only wildfire orders and alerts that are in effect (not All Clear, not floods or slides)."""
    kept = []
    for feature in fc.get("features", []):
        props = feature.get("properties") or {}
        is_fire = "fire" in str(props.get("EVENT_TYPE", "")).lower()
        status = normalize_evac_status(props.get("ORDER_ALERT_STATUS"))
        if is_fire and status in {"Order", "Alert"}:
            kept.append(feature)
    return {"type": "FeatureCollection", "features": kept}


def evac_style(feature: dict, mode: str) -> dict:
    t = tokens(mode)
    status = normalize_evac_status((feature.get("properties") or {}).get("ORDER_ALERT_STATUS"))
    colour = t["critical"] if status == "Order" else t["warning"]
    style = {"color": colour, "weight": 2, "fillColor": colour, "fillOpacity": 0.3}
    if status == "Alert":
        style["dashArray"] = "6 4"
    return style


def build_map(*, points: pd.DataFrame, perimeters_fc: dict, evac_fc: dict, hotspots_fc: dict,
              layers: set[str], mode: str,
              on_select: Callable[[str], None] | None = None) -> Map:
    """Build the map. ``on_select(fire_number)`` is called when a fire marker is clicked."""
    t = tokens(mode)
    tile = TileLayer(url=tile_url(mode), attribution=ATTRIBUTION,
                     max_zoom=18)
    fmap = Map(center=BC_CENTER, zoom=BC_ZOOM, basemap=tile, scroll_wheel_zoom=True,
               layout=Layout(height="560px", width="100%"))

    if "perimeters" in layers:
        shown = filter_perimeters(perimeters_fc, set(points["fire_number"].astype(str)))
        if shown["features"]:
            fmap.add(GeoJSON(
                data=shown, name="Fire perimeters",
                style={"color": t["orange"], "weight": 1.5, "fillColor": t["orange"], "fillOpacity": 0.2},
                hover_style={"weight": 3, "fillOpacity": 0.4}))

    if "evacuations" in layers:
        shown = wildfire_evac_features(evac_fc)
        if shown["features"]:
            fmap.add(GeoJSON(data=shown, name="Evacuation orders and alerts",
                             style_callback=lambda feature: evac_style(feature, mode),
                             hover_style={"weight": 3, "fillOpacity": 0.45}))

    if "hotspots" in layers and hotspots_fc.get("features"):
        fmap.add(GeoJSON(
            data=hotspots_fc, name="Satellite hotspots (24 h)",
            point_style={"radius": 3, "color": t["violet"], "fillColor": t["violet"],
                         "fillOpacity": 0.7, "weight": 0}))

    if "fires" in layers and not points.empty:
        frame = points.dropna(subset=["lat", "lon"])
        radii = frame["size_ha"].map(radius_for)
        # Grey context first, then out-of-control fires on top (the emphasis form).
        for is_ooc in (False, True):
            in_group = frame["status"].eq("Out of Control") == is_ooc
            for radius in sorted(set(radii[in_group])):
                subset = frame[in_group & (radii == radius)]
                layer = GeoJSON(
                    data=fires_feature_collection(subset),
                    name="Out-of-control fires" if is_ooc else "Other fires",
                    point_style={
                        "radius": radius + (1 if is_ooc else 0),
                        "color": t["surface"], "weight": 2 if is_ooc else 1,
                        "fillColor": t["orange"] if is_ooc else t["context"],
                        "fillOpacity": 0.9 if is_ooc else 0.75,
                    },
                    hover_style={"weight": 3, "fillOpacity": 1.0},
                )
                if on_select is not None:
                    def handler(feature=None, _cb=on_select, **_kwargs):
                        number = ((feature or {}).get("properties") or {}).get("fire_number")
                        if number:
                            _cb(str(number))
                    layer.on_click(handler)
                fmap.add(layer)
    return fmap


def evac_summary(evac_fc: dict) -> pd.DataFrame:
    """Wildfire orders and alerts in effect, as a table (used for the accessible table view)."""
    frame = evac_frame(wildfire_evac_features(evac_fc))
    return frame[["name", "status", "agency", "homes", "population", "start_date"]]
