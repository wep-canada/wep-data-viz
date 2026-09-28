"""Headline numbers. Province-wide, deliberately not affected by the sidebar filters."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

DASH = "—"


@dataclass(frozen=True)
class Kpi:
    key: str
    label: str
    value: str
    sub: str


def fmt_int(value) -> str:
    if value is None or pd.isna(value):
        return DASH
    return f"{int(round(float(value))):,}"


def fmt_hectares(value) -> str:
    if value is None or pd.isna(value):
        return DASH
    value = float(value)
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f} M ha"
    return f"{value:,.0f} ha"


def compute_kpis(points: pd.DataFrame, evac: pd.DataFrame, hotspot_count: int | None) -> list[Kpi]:
    have_points = len(points) > 0
    active = int(points["is_active"].sum()) if have_points else None
    ooc = int((points["status"] == "Out of Control").sum()) if have_points else None
    of_note = int(points["of_note"].sum()) if have_points else 0
    hectares = float(points["size_ha"].fillna(0).sum()) if have_points else None

    wild = evac[evac["is_wildfire"]] if len(evac) else evac
    orders = wild[wild["status"] == "Order"] if len(wild) else wild
    alerts = wild[wild["status"] == "Alert"] if len(wild) else wild
    homes = float(orders["homes"].fillna(0).sum()) if len(orders) else 0.0

    orders_sub = f"{len(alerts):,} alerts"
    if homes > 0:
        orders_sub += f" · about {fmt_int(homes)} homes under order"

    return [
        Kpi("active", "Active fires", fmt_int(active),
            f"of {len(points):,} this season" if have_points else "No data yet"),
        Kpi("ooc", "Out of control", fmt_int(ooc),
            f"{of_note:,} fires of note" if have_points else "No data yet"),
        Kpi("hectares", "Area burned this season", fmt_hectares(hectares),
            "current size, all fires" if have_points else "No data yet"),
        Kpi("orders", "Wildfire evacuation orders", fmt_int(len(orders)) if len(evac) else DASH,
            orders_sub if len(evac) else "No data yet"),
        Kpi("hotspots", "Satellite hotspots (24 h)", fmt_int(hotspot_count),
            "BC detections, last 24 hours" if hotspot_count is not None else "No data yet"),
    ]


EQUITY_TILE_IDS = [
    "isc_fn_evacuees_bc",
    "isc_fn_long_term_evacuees_bc",
    "statcan_indigenous_evac_share_2023",
    "firesmart_funding_dispersed",
    "fness_training_participants",
]


def _fmt_indicator(value: float, unit: str) -> str:
    if unit == "percent":
        return f"{value:g}%"
    if unit == "CAD":
        return f"${value / 1_000_000:g} M"
    return fmt_int(value)


def equity_tiles(indicators: pd.DataFrame) -> list[Kpi]:
    tiles: list[Kpi] = []
    for indicator_id in EQUITY_TILE_IDS:
        rows = indicators[indicators["indicator_id"] == indicator_id]
        if rows.empty:
            continue
        row = rows.iloc[-1]
        sub = f"{row['period']} · {row['source_name']}"
        tiles.append(Kpi(indicator_id, str(row["label"]),
                         _fmt_indicator(float(row["value"]), str(row["unit"])), sub))
    return tiles
