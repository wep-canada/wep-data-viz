"""Readers for the two service types we use (OGC WFS and ArcGIS REST) plus GeoJSON tidy-ups."""

from __future__ import annotations

import copy
from typing import Any, Callable

from core.http import FetchError, get_json

from .sources import SourceSpec

GetJson = Callable[..., Any]

WFS_PAGE = 5000
ARCGIS_PAGE = 1000
MAX_PAGES = 40


def _feature_collection(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def fetch_wfs_geojson(url: str, type_name: str, *, page_size: int = WFS_PAGE,
                      get: GetJson = get_json) -> dict:
    """Read every feature of a WFS 2.0 layer as GeoJSON in lon/lat, paging as needed."""
    features: list[dict] = []
    seen: set[Any] = set()
    start = 0
    for _ in range(MAX_PAGES):
        page = get(url, params={
            "service": "WFS", "version": "2.0.0", "request": "GetFeature",
            "typeNames": type_name, "outputFormat": "application/json",
            "srsName": "EPSG:4326", "count": page_size, "startIndex": start,
        })
        if not isinstance(page, dict) or "features" not in page:
            raise FetchError(f"WFS {type_name}: response is not a GeoJSON FeatureCollection")
        batch = page["features"]
        for feature in batch:
            fid = feature.get("id")
            if fid is not None:
                if fid in seen:
                    continue
                seen.add(fid)
            features.append(feature)
        if len(batch) < page_size:
            return _feature_collection(features)
        start += page_size
    raise FetchError(f"WFS {type_name}: more than {MAX_PAGES} pages, giving up")


def fetch_arcgis_geojson(layer_url: str, *, where: str = "1=1", page_size: int = ARCGIS_PAGE,
                         get: GetJson = get_json) -> dict:
    """Read every feature of an ArcGIS FeatureServer layer as GeoJSON in lon/lat."""
    features: list[dict] = []
    offset = 0
    for _ in range(MAX_PAGES):
        page = get(layer_url.rstrip("/") + "/query", params={
            "where": where, "outFields": "*", "outSR": 4326, "f": "geojson",
            "resultOffset": offset, "resultRecordCount": page_size,
            "orderByFields": "OBJECTID",
        })
        if isinstance(page, dict) and "error" in page:
            raise FetchError(f"ArcGIS error: {page['error']}")
        if not isinstance(page, dict) or "features" not in page:
            raise FetchError("ArcGIS response is not a GeoJSON FeatureCollection")
        batch = page["features"]
        features.extend(batch)
        if len(batch) < page_size:
            return _feature_collection(features)
        offset += len(batch)
    raise FetchError(f"ArcGIS {layer_url}: more than {MAX_PAGES} pages, giving up")


# ---------------------------------------------------------------- tidy-ups

def _is_position(node: Any) -> bool:
    return isinstance(node, (list, tuple)) and len(node) >= 2 and all(
        isinstance(v, (int, float)) for v in node[:2]
    )


def _map_positions(node: Any, fn: Callable[[list], list]) -> Any:
    if _is_position(node):
        return fn(list(node))
    if isinstance(node, (list, tuple)):
        return [_map_positions(child, fn) for child in node]
    return node


def _first_position(fc: dict) -> list | None:
    for feature in fc.get("features", []):
        node = (feature.get("geometry") or {}).get("coordinates")
        while isinstance(node, (list, tuple)) and node and not _is_position(node):
            node = node[0]
        if _is_position(node):
            return list(node)
    return None


def ensure_lonlat(fc: dict) -> dict:
    """Swap coordinates if a server returned (lat, lon) instead of GeoJSON's (lon, lat).

    Canada spans lon -142..-50 and lat 40..84, so a first position that looks like
    (lat, lon) is unambiguous.
    """
    sample = _first_position(fc)
    if sample is None:
        return fc
    x, y = sample[0], sample[1]
    if 40 <= x <= 84 and -142 <= y <= -50:
        swapped = copy.deepcopy(fc)
        for feature in swapped["features"]:
            geom = feature.get("geometry")
            if geom and "coordinates" in geom:
                geom["coordinates"] = _map_positions(
                    geom["coordinates"], lambda p: [p[1], p[0], *p[2:]])
        return swapped
    return fc


def round_coords(fc: dict, digits: int) -> dict:
    """Round coordinates (5 dp is about 1 m) to keep snapshots small."""
    out = copy.deepcopy(fc)
    for feature in out["features"]:
        geom = feature.get("geometry")
        if geom and "coordinates" in geom:
            geom["coordinates"] = _map_positions(
                geom["coordinates"], lambda p: [round(v, digits) for v in p])
    return out


def filter_bbox(fc: dict, bbox: tuple[float, float, float, float]) -> dict:
    """Keep features whose first coordinate lies inside ``bbox`` (min lon, min lat, max lon, max lat)."""
    min_lon, min_lat, max_lon, max_lat = bbox
    kept = []
    for feature in fc["features"]:
        node = (feature.get("geometry") or {}).get("coordinates")
        while isinstance(node, (list, tuple)) and node and not _is_position(node):
            node = node[0]
        if _is_position(node) and min_lon <= node[0] <= max_lon and min_lat <= node[1] <= max_lat:
            kept.append(feature)
    return _feature_collection(kept)


def stable_sort(fc: dict, keys: tuple[str, ...]) -> dict:
    """Order features deterministically so daily snapshots produce small git diffs."""
    def sort_key(feature: dict):
        props = feature.get("properties") or {}
        for key in keys:
            if props.get(key) is not None:
                return (0, str(props[key]))
        return (1, str(feature.get("id", "")))

    return _feature_collection(sorted(fc["features"], key=sort_key))


def fetch_source(spec: SourceSpec, *, get: GetJson = get_json) -> dict:
    """Fetch one source and return a tidy GeoJSON FeatureCollection in lon/lat."""
    if spec.kind == "wfs":
        fc = fetch_wfs_geojson(spec.url, spec.layer, get=get)
    elif spec.kind == "arcgis":
        fc = fetch_arcgis_geojson(spec.url, where=spec.where, get=get)
    else:
        raise FetchError(f"Unknown source kind: {spec.kind}")
    fc = ensure_lonlat(fc)
    if spec.bbox:
        fc = filter_bbox(fc, spec.bbox)
    fc = round_coords(fc, spec.coord_digits)
    if spec.sort_keys:
        fc = stable_sort(fc, spec.sort_keys)
    return fc
