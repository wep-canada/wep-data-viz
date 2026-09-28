"""Freshness bookkeeping: how recent is each dataset, and can we trust it?

The pipeline writes ``data/freshness.json``. The app reads it to show an
"as of" time on every panel and to flag anything that has gone stale, so the
dashboard is honest about its own age instead of silently showing old data.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import config
from .io import read_json, write_json


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def humanize_age(delta: timedelta) -> str:
    secs = max(int(delta.total_seconds()), 0)
    if secs < 90:
        return "just now"
    if secs < 90 * 60:
        return f"{secs // 60} min ago"
    if secs < 36 * 3600:
        return f"{secs // 3600} h ago"
    return f"{secs // 86400} d ago"


def empty_manifest() -> dict[str, Any]:
    return {"generated_at": None, "sources": {}}


def load_manifest(path: Path | str | None = None) -> dict[str, Any]:
    data = read_json(path or config.FRESHNESS_PATH, default=None)
    if not isinstance(data, dict) or not isinstance(data.get("sources"), dict):
        return empty_manifest()
    return data


def save_manifest(manifest: dict[str, Any], path: Path | str | None = None,
                  now: datetime | None = None) -> None:
    manifest["generated_at"] = to_iso(now or utcnow())
    write_json(path or config.FRESHNESS_PATH, manifest)


def _entry(manifest: dict[str, Any], key: str) -> dict[str, Any]:
    return manifest["sources"].setdefault(key, {})


def record_success(manifest: dict[str, Any], key: str, *, label: str, url: str,
                   rows: int, expected_max_age_hours: float,
                   licence: str = "", now: datetime | None = None,
                   source_updated_at: str | None = None) -> None:
    now = now or utcnow()
    entry = _entry(manifest, key)
    entry.update(
        label=label,
        url=url,
        licence=licence,
        expected_max_age_hours=expected_max_age_hours,
        last_attempt=to_iso(now),
        last_success=to_iso(now),
        rows=rows,
        source_updated_at=source_updated_at,
    )
    entry.pop("last_error", None)


def record_failure(manifest: dict[str, Any], key: str, *, label: str, url: str,
                   error: str, expected_max_age_hours: float,
                   licence: str = "", now: datetime | None = None) -> None:
    """Note a failed refresh. Earlier ``last_success`` and ``rows`` are kept."""
    now = now or utcnow()
    entry = _entry(manifest, key)
    entry.update(
        label=label,
        url=url,
        licence=licence,
        expected_max_age_hours=expected_max_age_hours,
        last_attempt=to_iso(now),
        last_error=error[:500],
    )


def status_for(entry: dict[str, Any] | None, now: datetime | None = None) -> dict[str, Any]:
    """Return ``{"state", "age", "text"}`` for one manifest entry.

    States: ``fresh``, ``degraded`` (recent data but the latest refresh failed),
    ``stale`` (older than expected), ``missing`` (never fetched).
    """
    now = now or utcnow()
    last_success = parse_iso((entry or {}).get("last_success"))
    if last_success is None:
        return {"state": "missing", "age": None, "text": "No data yet"}
    age = now - last_success
    max_age = float((entry or {}).get("expected_max_age_hours") or 36)
    text = f"Updated {humanize_age(age)}"
    if age > timedelta(hours=max_age):
        return {"state": "stale", "age": age, "text": text}
    if (entry or {}).get("last_error"):
        return {"state": "degraded", "age": age, "text": text}
    return {"state": "fresh", "age": age, "text": text}
