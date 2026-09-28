"""One-off: populate ``data/curated/fire_centre_codes.csv`` from BC's official lookup layer.

The live fire-points feed (``bc_fire_points``) only gives a numeric ``FIRE_CENTRE`` code
(1-6); without a name lookup the dashboard has to show "Fire centre 5" instead of, say,
"Cariboo Fire Centre". BC publishes the code-to-name mapping as a separate ArcGIS layer
(the fire-centre boundaries), not as a coded-value domain on the fire-points layer itself,
so it has to be fetched once and saved as curated data rather than derived at runtime.

This is deliberately NOT part of the daily pipeline: fire centre boundaries and their
names change on the order of years, not days, and it is exactly the kind of thing this
project prefers to keep as a small, git-reviewable curated file rather than an opaque
daily overwrite (see ``data/curated/README`` / ``pipeline/watch.py`` for the same
philosophy applied to the hand-watched pages).

Run it once, review the diff, commit the result:

    python -m pipeline.fetch_fire_centre_codes

Re-run any time you suspect BC has renamed or renumbered a fire centre.
"""

from __future__ import annotations

import csv
import sys

from core import config
from core.http import get_json

LAYER_URL = (
    "https://delivery.maps.gov.bc.ca/arcgis/rest/services/whse/"
    "bcgw_pub_whse_legal_admin_boundaries/MapServer/1/query"
)
ID_FIELD = "MOF_FIRE_CENTRE_ID"
NAME_FIELD = "MOF_FIRE_CENTRE_NAME"


def fetch_codes(*, get=get_json) -> dict[str, str]:
    """Return ``{code: name}`` for every fire centre in the lookup layer."""
    page = get(LAYER_URL, params={
        "where": "1=1",
        "outFields": f"{ID_FIELD},{NAME_FIELD}",
        "returnGeometry": "false",
        "returnDistinctValues": "true",
        "f": "json",
    })
    if not isinstance(page, dict) or "features" not in page:
        raise RuntimeError(f"Unexpected response from {LAYER_URL}: {page!r}")
    codes: dict[str, str] = {}
    for feature in page["features"]:
        attrs = feature.get("attributes") or {}
        code, name = attrs.get(ID_FIELD), attrs.get(NAME_FIELD)
        if code is not None and name:
            codes[str(int(code))] = str(name).strip()
    if not codes:
        raise RuntimeError(
            f"{LAYER_URL} returned no usable rows - check the field names still match "
            f"(expected {ID_FIELD!r} and {NAME_FIELD!r})."
        )
    return codes


def write_csv(codes: dict[str, str]) -> None:
    path = config.CURATED_DIR / "fire_centre_codes.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["code", "name"])
        for code in sorted(codes, key=int):
            writer.writerow([code, codes[code]])
    print(f"wrote {len(codes)} fire centres to {path}")


def main(argv: list[str] | None = None) -> int:
    del argv
    try:
        codes = fetch_codes()
    except Exception as exc:  # noqa: BLE001 - this is a one-off CLI tool, not the pipeline
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    for code, name in sorted(codes.items(), key=lambda kv: int(kv[0])):
        print(f"  {code}  {name}")
    write_csv(codes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
