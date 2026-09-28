"""Sanity-check ``data/curated/fire_centre_codes.csv`` against the live snapshot.

BACKGROUND (why this file replaces the old ``fetch_fire_centre_codes.py``): the
``FIRE_CENTRE`` field on the live fire-points feed (``bc_fire_points``) is a plain
integer with no coded-value domain anywhere in BC's WFS or ArcGIS schemas for that
layer - confirmed by inspecting both. BC does publish a fire-centre *name* lookup as
a separate ArcGIS layer (fire-centre boundaries, field ``MOF_FIRE_CENTRE_ID``), but
its numbering (141-146) is a different code space from ``FIRE_CENTRE`` (2-7) - they
are NOT the same codes. An earlier version of this script queried that boundary
layer and wrote its codes straight into the curated CSV, which silently produced the
wrong mapping (the dashboard fell back to "Fire centre 2" etc. because no code in the
live data matched a code in the CSV).

Since there is no reliable API that maps ``FIRE_CENTRE`` integers straight to names,
``data/curated/fire_centre_codes.csv`` is hand-verified instead: each code's fires
were geo-located against BC Wildfire Service's own published fire-centre boundary
descriptions (https://www2.gov.bc.ca/gov/content/safety/wildfire-status/about-bcws/fire-centres),
plus one independent news-source spot check (a reported Stump Lake fire under
"Kamloops Fire Centre" matches code 5's cluster). This script does not re-derive that
mapping; it prints each curated code's current centroid and example locations so a
human can glance at them each fire season and confirm nothing has shifted (BC very
rarely renumbers fire centres, but a mismatch here should be investigated, not
ignored).

Run it after ``python -m pipeline.run`` has produced a fresh snapshot:

    python -m pipeline.verify_fire_centre_codes
"""

from __future__ import annotations

import sys
from collections import defaultdict

import pandas as pd

from core import config
from core.io import read_json


def centre_centroids(fc: dict | None) -> pd.DataFrame:
    """One row per ``FIRE_CENTRE`` code: fire count, centroid, and example places."""
    buckets: dict[str, dict] = defaultdict(lambda: {"n": 0, "lon": 0.0, "lat": 0.0, "examples": []})
    for feature in (fc or {}).get("features", []):
        props = feature.get("properties") or {}
        code = str(props.get("FIRE_CENTRE"))
        lon, lat = feature["geometry"]["coordinates"][:2]
        b = buckets[code]
        b["n"] += 1
        b["lon"] += lon
        b["lat"] += lat
        if len(b["examples"]) < 3:
            b["examples"].append(str(props.get("GEOGRAPHIC_DESCRIPTION") or "").strip())
    columns = ["code", "fires", "centroid_lon", "centroid_lat", "examples"]
    if not buckets:
        return pd.DataFrame(columns=columns)
    rows = []
    for code, b in buckets.items():
        rows.append({
            "code": code, "fires": b["n"],
            "centroid_lon": round(b["lon"] / b["n"], 2) if b["n"] else None,
            "centroid_lat": round(b["lat"] / b["n"], 2) if b["n"] else None,
            "examples": ", ".join(e for e in b["examples"] if e),
        })
    return pd.DataFrame(rows, columns=columns).sort_values("code").reset_index(drop=True)


def main(argv: list[str] | None = None) -> int:
    del argv
    fc = read_json(config.LIVE_DIR / "bc_fire_points.geojson", default=None)
    if not isinstance(fc, dict) or not fc.get("features"):
        print("No live bc_fire_points.geojson snapshot to check against. "
              "Run `python -m pipeline.run` first.", file=sys.stderr)
        return 1

    names_path = config.CURATED_DIR / "fire_centre_codes.csv"
    names = pd.read_csv(names_path, dtype=str).fillna("") if names_path.exists() else pd.DataFrame(
        columns=["code", "name"])

    report = centre_centroids(fc).merge(names, on="code", how="left")
    report["name"] = report["name"].fillna("<not in fire_centre_codes.csv>")
    unmatched = report[report["name"].str.startswith("<")]

    print(report.to_string(index=False))
    if not unmatched.empty:
        print(f"\n{len(unmatched)} fire-centre code(s) in the live data have no curated name - "
              "add them to data/curated/fire_centre_codes.csv (see this script's docstring for "
              "how the existing rows were verified).", file=sys.stderr)
        return 1
    print("\nEvery FIRE_CENTRE code in the live snapshot has a curated name. Compare the centroids "
          "above with https://www2.gov.bc.ca/gov/content/safety/wildfire-status/about-bcws/fire-centres "
          "if anything looks off.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
