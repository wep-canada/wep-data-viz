"""Loading data for the wildfire dashboard.

Live tier: the app fetches each feed itself, cached for ``LIVE_TTL_SECONDS`` (15 min by
default). If a live fetch fails it falls back to the last snapshot the pipeline committed
(``data/live``), and the panel says so. Slow tier: curated CSVs and the daily history.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

import pandas as pd

from core import config, freshness
from core.frames import evac_frame, hotspots_frame, points_frame
from core.io import read_json
from pipeline.fetchers import fetch_source
from pipeline.history import read_history
from pipeline.sources import SOURCES, SourceSpec

EMPTY_FC: dict = {"type": "FeatureCollection", "features": []}


@dataclass
class LayerResult:
    key: str
    fc: dict
    origin: str                      # "live" | "snapshot" | "missing"
    fetched_at: datetime | None
    error: str | None = None


@dataclass
class WildfireData:
    layers: dict[str, LayerResult]
    points: pd.DataFrame
    evac: pd.DataFrame
    hotspot_count: int | None

    def fc(self, key: str) -> dict:
        result = self.layers.get(key)
        return result.fc if result else EMPTY_FC


_cache: dict[str, tuple[float, LayerResult]] = {}
_key_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)


def clear_cache() -> None:
    _cache.clear()


def _snapshot(spec: SourceSpec) -> LayerResult:
    fc = read_json(config.LIVE_DIR / f"{spec.key}.geojson", default=None)
    if not isinstance(fc, dict) or "features" not in fc:
        return LayerResult(spec.key, EMPTY_FC, "missing", None)
    entry = freshness.load_manifest()["sources"].get(spec.key, {})
    return LayerResult(spec.key, fc, "snapshot", freshness.parse_iso(entry.get("last_success")))


def load_layer(spec: SourceSpec, *, fetch: Callable[[SourceSpec], dict] = fetch_source,
               clock: Callable[[], float] = time.monotonic) -> LayerResult:
    if not config.LIVE_FETCH_ENABLED:
        return _snapshot(spec)
    with _key_locks[spec.key]:            # one visitor fetches, the others wait then hit the cache
        cached = _cache.get(spec.key)
        if cached and clock() < cached[0]:
            return cached[1]
        try:
            result = LayerResult(spec.key, fetch(spec), "live", freshness.utcnow())
            ttl = config.LIVE_TTL_SECONDS
        except Exception as exc:  # noqa: BLE001 - any failure falls back to the snapshot
            result = _snapshot(spec)
            result.error = f"{type(exc).__name__}: {exc}"
            ttl = config.LIVE_FAILURE_TTL_SECONDS
        _cache[spec.key] = (clock() + ttl, result)
        return result


def load_all(fetch: Callable[[SourceSpec], dict] = fetch_source) -> WildfireData:
    specs = list(SOURCES.values())
    with ThreadPoolExecutor(max_workers=len(specs)) as pool:
        results = list(pool.map(lambda s: load_layer(s, fetch=fetch), specs))
    layers = {r.key: r for r in results}
    hotspots = layers["cwfis_hotspots"]
    return WildfireData(
        layers=layers,
        points=points_frame(layers["bc_fire_points"].fc),
        evac=evac_frame(layers["bc_evac_orders"].fc),
        hotspot_count=None if hotspots.origin == "missing" else len(hotspots_frame(hotspots.fc)),
    )


def layer_statuses(data: WildfireData, now: datetime | None = None) -> list[dict]:
    """One dict per layer for the freshness strip: label, state, text."""
    now = now or freshness.utcnow()
    manifest = freshness.load_manifest()["sources"]
    out: list[dict] = []
    for key, spec in SOURCES.items():
        layer = data.layers.get(key)
        if layer is None or layer.origin == "missing":
            out.append({"key": key, "label": spec.label, "state": "missing", "text": "No data yet"})
        elif layer.origin == "live":
            age = freshness.humanize_age(now - layer.fetched_at)
            out.append({"key": key, "label": spec.label, "state": "fresh", "text": f"Live, fetched {age}"})
        else:
            status = freshness.status_for(manifest.get(key), now)
            state = "degraded" if status["state"] == "fresh" and layer.error else status["state"]
            text = f"Snapshot. {status['text']}"
            if layer.error:
                text += " (live fetch failed)"
            out.append({"key": key, "label": spec.label, "state": state, "text": text})
    return out


# ------------------------------------------------------------------ slow tier

def load_history() -> pd.DataFrame:
    frame = read_history(config.HISTORY_DIR / "daily_summary.parquet")
    if not frame.empty:
        frame["date"] = pd.to_datetime(frame["date"])
    return frame


def load_indicators() -> pd.DataFrame:
    path = config.CURATED_DIR / "indicators.csv"
    if not path.exists():
        return pd.DataFrame(columns=["indicator_id", "label", "period", "value", "unit", "definition",
                                     "source_name", "source_url", "origin", "notes"])
    frame = pd.read_csv(path, dtype={"period": str}).fillna({"notes": ""})
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    return frame


def load_data_gaps() -> pd.DataFrame:
    path = config.CURATED_DIR / "data_gaps.csv"
    if not path.exists():
        return pd.DataFrame(columns=["gap_id", "question", "why_it_matters", "what_exists",
                                     "what_is_missing", "possible_path"])
    return pd.read_csv(path).fillna("")


def load_centre_names() -> dict[str, str]:
    path = config.CURATED_DIR / "fire_centre_codes.csv"
    if not path.exists():
        return {}
    frame = pd.read_csv(path, dtype=str).fillna("")
    return {row.code: row.name for row in frame.itertuples() if row.code and row.name}
