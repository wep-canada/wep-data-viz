"""Shared test helpers."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "data"


def prepare_data_dir(target: Path, *, now: datetime | None = None, with_manifest: bool = True) -> Path:
    """Copy the synthetic fixtures to ``target`` and write a fresh freshness manifest."""
    now = now or datetime.now(timezone.utc)
    shutil.copytree(FIXTURES, target, dirs_exist_ok=True)
    if with_manifest:
        stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        sources = {}
        for key, label in [
            ("bc_fire_points", "BC current fire locations"),
            ("bc_fire_perimeters", "BC current fire perimeters"),
            ("bc_evac_orders", "BC evacuation orders and alerts"),
            ("cwfis_hotspots", "Satellite hotspots, last 24 h (BC)"),
        ]:
            sources[key] = {"label": label, "url": "https://example.invalid", "licence": "test",
                            "expected_max_age_hours": 36, "last_attempt": stamp,
                            "last_success": stamp, "rows": 1}
        (target / "freshness.json").write_text(
            json.dumps({"generated_at": stamp, "sources": sources}), encoding="utf-8")
    return target
