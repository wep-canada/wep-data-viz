"""Filtering of the fire list. Pure functions, no Shiny, easy to test."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from core.normalize import CAUSES, FIRE_STATUS_ORDER

MIN_SIZE_CHOICES = {
    "0": "Any size",
    "1": "1 hectare or more",
    "10": "10 hectares or more",
    "100": "100 hectares or more",
    "1000": "1,000 hectares or more",
}


@dataclass(frozen=True)
class FireFilters:
    """An empty tuple means "no restriction" for that field."""

    centres: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ()
    causes: tuple[str, ...] = ()
    min_size_ha: float = 0.0
    include_out: bool = False


def centre_label(code: str, names: dict[str, str]) -> str:
    if not code:
        return "Unknown"
    return names.get(code) or f"Fire centre {code}"


def apply_fire_filters(points: pd.DataFrame, f: FireFilters) -> pd.DataFrame:
    mask = pd.Series(True, index=points.index)
    if not f.include_out:
        mask &= points["status"] != "Out"
    if f.centres:
        mask &= points["centre"].isin(f.centres)
    if f.statuses:
        mask &= points["status"].isin(f.statuses)
    if f.causes:
        mask &= points["cause"].isin(f.causes)
    if f.min_size_ha > 0:
        mask &= points["size_ha"].fillna(0) >= f.min_size_ha
    return points[mask].reset_index(drop=True)


def centre_choices(points: pd.DataFrame, names: dict[str, str]) -> dict[str, str]:
    """``{code: label}`` for the fire centres present in the data, sorted by label."""
    codes = sorted({c for c in points["centre"].tolist() if c})
    choices = {code: centre_label(code, names) for code in codes}
    return dict(sorted(choices.items(), key=lambda kv: kv[1]))


def status_choices() -> dict[str, str]:
    return {s: s for s in FIRE_STATUS_ORDER}


def cause_choices() -> dict[str, str]:
    return {c: c for c in CAUSES}


def default_selection(points: pd.DataFrame) -> dict:
    """A sensible starting filter instead of "show everything at once".

    A first-time, public visitor is better served by one representative slice than by
    every fire in the province at once, so this picks a narrower Fire status, Fire centre,
    Cause and Minimum size the same way a person would: start with Under Control fires
    (a calmer opening view for the public than leading with Out of Control), find the fire
    centre and cause those fires are most often associated with, and hide anything under
    1 hectare. Each step only narrows what the previous step already left standing, so the
    combination is never empty - a real, visible fire always beats a tidier-looking default.
    Returns ``{"statuses": [...], "centres": [...], "causes": [...], "min_size": "0" | "1"}``,
    each list empty (meaning "no restriction") if that step found nothing to narrow to.
    """
    result: dict = {"statuses": [], "centres": [], "causes": [], "min_size": "0"}
    subset = points[points["status"] == "Under Control"]
    if subset.empty:
        return result
    result["statuses"] = ["Under Control"]

    counts = subset["centre"].value_counts()
    counts = counts[counts.index != ""]
    if not counts.empty:
        top_centre = counts.idxmax()
        subset = subset[subset["centre"] == top_centre]
        result["centres"] = [top_centre]

    counts = subset["cause"].value_counts()
    if not counts.empty:
        top_cause = counts.idxmax()
        subset = subset[subset["cause"] == top_cause]
        result["causes"] = [top_cause]

    if (subset["size_ha"].fillna(0) >= 1).any():
        result["min_size"] = "1"

    return result
