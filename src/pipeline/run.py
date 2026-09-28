"""Refresh the live-tier snapshots and the daily history.

    python -m pipeline.run                 # everything
    python -m pipeline.run --only bc_fire_points bc_evac_orders
    python -m pipeline.run --no-history

Design rules:
* Fail soft. A source that errors keeps its previous snapshot; the error is recorded in
  ``data/freshness.json`` so the dashboard can say so.
* Exit code 1 if any source failed, so the scheduled GitHub Action goes red and emails you.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from typing import Callable

from core import config, freshness
from core.io import write_json

from .fetchers import fetch_source
from .history import summarize, upsert_daily
from .sources import SOURCES, SourceSpec


def snapshot_path(spec: SourceSpec):
    return config.LIVE_DIR / f"{spec.key}.geojson"


def run(keys: list[str] | None = None, *, fetch: Callable[[SourceSpec], dict] = fetch_source,
        now: datetime | None = None, write_history: bool = True) -> dict[str, str | None]:
    """Refresh the chosen sources. Returns ``{key: None}`` on success or ``{key: error}``."""
    now = now or freshness.utcnow()
    manifest = freshness.load_manifest()
    results: dict[str, str | None] = {}
    fetched: dict[str, dict] = {}

    for key in keys or list(SOURCES):
        spec = SOURCES[key]
        try:
            fc = fetch(spec)
            write_json(snapshot_path(spec), fc, compact=True)
            freshness.record_success(
                manifest, key, label=spec.label, url=spec.landing_page,
                rows=len(fc["features"]), expected_max_age_hours=spec.expected_max_age_hours,
                licence=spec.licence, now=now)
            fetched[key] = fc
            results[key] = None
        except Exception as exc:  # noqa: BLE001 - fail soft on anything
            freshness.record_failure(
                manifest, key, label=spec.label, url=spec.landing_page,
                error=f"{type(exc).__name__}: {exc}",
                expected_max_age_hours=spec.expected_max_age_hours,
                licence=spec.licence, now=now)
            results[key] = f"{type(exc).__name__}: {exc}"

    freshness.save_manifest(manifest, now=now)

    if write_history and fetched:
        row = summarize(fetched.get("bc_fire_points"), fetched.get("bc_evac_orders"),
                        fetched.get("cwfis_hotspots"), today=now.date())
        upsert_daily(row)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--only", nargs="+", choices=sorted(SOURCES), help="refresh only these sources")
    parser.add_argument("--no-history", action="store_true", help="do not write the daily history row")
    args = parser.parse_args(argv)

    results = run(args.only, write_history=not args.no_history)
    failed = 0
    for key, error in results.items():
        if error is None:
            print(f"ok      {key}")
        else:
            failed += 1
            print(f"FAILED  {key}: {error}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
