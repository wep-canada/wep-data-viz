"""Turn GeoJSON FeatureCollections into tidy pandas frames.

Used by both the pipeline (to compute daily history) and the dashboards, so the
two can never disagree about what "active fire" or "wildfire order" means.
"""

from __future__ import annotations

from typing import Any, Iterable

import pandas as pd

from .normalize import (
    is_active_status,
    normalize_cause,
    normalize_evac_status,
    normalize_fire_status,
)

POINT_COLUMNS = [
    "fire_number", "name", "status", "is_active", "cause", "size_ha", "ignition_date",
    "description", "centre", "zone", "url", "of_note", "lon", "lat",
]
EVAC_COLUMNS = [
    "name", "event_name", "event_type", "status", "agency", "homes", "population",
    "start_date", "modified", "is_wildfire",
]
HOTSPOT_COLUMNS = ["lon", "lat"]


def _first_coordinate(geometry: dict | None) -> tuple[float, float] | None:
    """Return the first (lon, lat) pair found in any GeoJSON geometry."""
    node: Any = (geometry or {}).get("coordinates")
    while isinstance(node, (list, tuple)) and node and isinstance(node[0], (list, tuple)):
        node = node[0]
    if isinstance(node, (list, tuple)) and len(node) >= 2:
        try:
            return float(node[0]), float(node[1])
        except (TypeError, ValueError):
            return None
    return None


def _features(fc: dict | None) -> list[dict]:
    return list((fc or {}).get("features") or [])


def _text(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str)


def _iso_dates(series: pd.Series) -> pd.Series:
    """Parse ISO dates. BC writes date-only values with a trailing Z ("2026-06-17Z"),
    which pandas rejects, so that Z is dropped first."""
    text = series.astype("string").str.replace(r"^(\d{4}-\d{2}-\d{2})Z$", r"\1", regex=True)
    return pd.to_datetime(text, errors="coerce", utc=True, format="ISO8601")


def points_frame(fc: dict | None) -> pd.DataFrame:
    rows: list[dict] = []
    for feature in _features(fc):
        props = feature.get("properties") or {}
        coord = _first_coordinate(feature.get("geometry"))
        lon = coord[0] if coord else props.get("LONGITUDE")
        lat = coord[1] if coord else props.get("LATITUDE")
        rows.append({**props, "_lon": lon, "_lat": lat})
    if not rows:
        return pd.DataFrame({c: pd.Series(dtype="object") for c in POINT_COLUMNS})

    raw = pd.DataFrame(rows)

    def col(name: str) -> pd.Series:
        return raw[name] if name in raw else pd.Series([None] * len(raw), index=raw.index)

    number = _text(col("FIRE_NUMBER"))
    incident = _text(col("INCIDENT_NAME")).str.strip()
    out = pd.DataFrame(
        {
            "fire_number": number,
            "name": incident.where(incident != "", number),
            "status": col("FIRE_STATUS").map(normalize_fire_status),
            "cause": col("FIRE_CAUSE").map(normalize_cause),
            "size_ha": pd.to_numeric(col("CURRENT_SIZE"), errors="coerce"),
            "ignition_date": _iso_dates(col("IGNITION_DATE")),
            "description": _text(col("GEOGRAPHIC_DESCRIPTION")),
            "centre": _text(col("FIRE_CENTRE")),
            "zone": _text(col("ZONE")),
            "url": _text(col("FIRE_URL")),
            "of_note": _text(col("FIRE_OF_NOTE_IND")).str.upper().eq("Y"),
            "lon": pd.to_numeric(raw["_lon"], errors="coerce"),
            "lat": pd.to_numeric(raw["_lat"], errors="coerce"),
        }
    )
    out["is_active"] = out["status"].map(is_active_status)
    return out[POINT_COLUMNS].reset_index(drop=True)


def evac_frame(fc: dict | None) -> pd.DataFrame:
    rows = [dict(f.get("properties") or {}) for f in _features(fc)]
    if not rows:
        return pd.DataFrame({c: pd.Series(dtype="object") for c in EVAC_COLUMNS})
    raw = pd.DataFrame(rows)

    def col(name: str) -> pd.Series:
        return raw[name] if name in raw else pd.Series([None] * len(raw), index=raw.index)

    out = pd.DataFrame(
        {
            "name": _text(col("ORDER_ALERT_NAME")),
            "event_name": _text(col("EVENT_NAME")),
            "event_type": _text(col("EVENT_TYPE")),
            "status": col("ORDER_ALERT_STATUS").map(normalize_evac_status),
            "agency": _text(col("ISSUING_AGENCY")),
            "homes": pd.to_numeric(col("MULTI_SOURCED_HOMES"), errors="coerce"),
            "population": pd.to_numeric(col("MULTI_SOURCED_POPULATION"), errors="coerce"),
            "start_date": pd.to_datetime(col("EVENT_START_DATE"), unit="ms", errors="coerce", utc=True),
            "modified": pd.to_datetime(col("DATE_MODIFIED"), unit="ms", errors="coerce", utc=True),
        }
    )
    out["is_wildfire"] = out["event_type"].str.contains("fire", case=False, na=False)
    return out[EVAC_COLUMNS].reset_index(drop=True)


def hotspots_frame(fc: dict | None) -> pd.DataFrame:
    coords: Iterable[tuple[float, float] | None] = (
        _first_coordinate(f.get("geometry")) for f in _features(fc)
    )
    rows = [{"lon": c[0], "lat": c[1]} for c in coords if c]
    if not rows:
        return pd.DataFrame({c: pd.Series(dtype="float64") for c in HOTSPOT_COLUMNS})
    return pd.DataFrame(rows, columns=HOTSPOT_COLUMNS)
