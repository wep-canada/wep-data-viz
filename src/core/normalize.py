"""Normalise the free-text categories the source systems use.

Sources spell the same thing several ways over time ("Out of Control", "OUT_OF_CONTROL",
"Out Of Control"). Everything downstream works with these canonical labels only.
"""

from __future__ import annotations

FIRE_STATUS_ORDER = ["Out of Control", "Being Held", "Under Control", "Out"]
CAUSES = ["Lightning", "Person", "Undetermined"]


def _clean(value) -> str:
    if value is None or (isinstance(value, float) and value != value):  # None or NaN
        return ""
    text = str(value).strip().lower().replace("_", " ").replace("-", " ")
    return " ".join(text.split())


def normalize_fire_status(value) -> str:
    text = _clean(value)
    table = {
        "out of control": "Out of Control",
        "oc": "Out of Control",
        "being held": "Being Held",
        "bh": "Being Held",
        "under control": "Under Control",
        "uc": "Under Control",
        "out": "Out",
    }
    if text in table:
        return table[text]
    return text.title() if text else "Unknown"


def is_active_status(status: str) -> bool:
    """A fire counts as active unless it is declared Out."""
    return status != "Out"


def normalize_evac_status(value) -> str:
    text = _clean(value)
    if "all clear" in text:
        return "All Clear"
    if "order" in text:
        return "Order"
    if "alert" in text:
        return "Alert"
    return text.title() if text else "Unknown"


def normalize_cause(value) -> str:
    text = _clean(value)
    if text in {"", "unknown", "undetermined", "under investigation"}:
        return "Undetermined"
    if text in {"person", "human", "human caused", "people"}:
        return "Person"
    if text == "lightning":
        return "Lightning"
    return text.title()
