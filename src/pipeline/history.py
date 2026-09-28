"""Append-only daily history.

The live services only show "now". Saving one summary row per day builds a time
series nobody else publishes (for example how many evacuation orders were active
each day of the season).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from core import config
from core.frames import evac_frame, hotspots_frame, points_frame

COLUMNS = [
    "date", "fires_season", "fires_active", "fires_out_of_control", "hectares_season",
    "evac_orders", "evac_alerts", "hotspots_bc_24h",
]


def history_path() -> Path:
    return config.HISTORY_DIR / "daily_summary.parquet"


def summarize(points_fc: dict | None, evac_fc: dict | None, hotspots_fc: dict | None,
              *, today: date) -> dict:
    """One row of headline numbers. A source that failed today contributes ``None``."""
    row: dict = {c: None for c in COLUMNS}
    row["date"] = today.isoformat()
    if points_fc is not None:
        pts = points_frame(points_fc)
        row["fires_season"] = int(len(pts))
        row["fires_active"] = int(pts["is_active"].sum())
        row["fires_out_of_control"] = int((pts["status"] == "Out of Control").sum())
        row["hectares_season"] = float(pts["size_ha"].fillna(0).sum())
    if evac_fc is not None:
        ev = evac_frame(evac_fc)
        ev = ev[ev["is_wildfire"]]
        row["evac_orders"] = int((ev["status"] == "Order").sum())
        row["evac_alerts"] = int((ev["status"] == "Alert").sum())
    if hotspots_fc is not None:
        row["hotspots_bc_24h"] = int(len(hotspots_frame(hotspots_fc)))
    return row


def read_history(path: Path | None = None) -> pd.DataFrame:
    path = path or history_path()
    if not path.exists():
        return pd.DataFrame({c: pd.Series(dtype="object") for c in COLUMNS})
    return pd.read_parquet(path)


def upsert_daily(row: dict, path: Path | None = None) -> pd.DataFrame:
    """Insert today's row, or update it if the pipeline ran more than once today.

    Values that are ``None`` in the new row never overwrite an earlier real value
    from the same day.
    """
    path = path or history_path()
    frame = read_history(path)
    new = pd.DataFrame([row], columns=COLUMNS)
    if not frame.empty and (frame["date"] == row["date"]).any():
        idx = frame.index[frame["date"] == row["date"]][0]
        for column in COLUMNS:
            if column != "date" and row.get(column) is not None:
                frame.loc[idx, column] = row[column]
    else:
        frame = pd.concat([frame, new], ignore_index=True) if not frame.empty else new
    frame = frame.sort_values("date").reset_index(drop=True)
    for column in COLUMNS[1:]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return frame
