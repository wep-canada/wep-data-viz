import json

import pandas as pd

from core.frames import evac_frame, hotspots_frame, points_frame
from core.normalize import (
    is_active_status,
    normalize_cause,
    normalize_evac_status,
    normalize_fire_status,
)
from helpers import FIXTURES


def load(name):
    return json.loads((FIXTURES / "live" / f"{name}.geojson").read_text(encoding="utf-8"))


def test_fire_status_spellings():
    assert normalize_fire_status("OUT_OF_CONTROL") == "Out of Control"
    assert normalize_fire_status(" being  held ") == "Being Held"
    assert normalize_fire_status("Under-Control") == "Under Control"
    assert normalize_fire_status("out") == "Out"
    assert normalize_fire_status(None) == "Unknown"
    assert normalize_fire_status(float("nan")) == "Unknown"
    assert normalize_fire_status("Something New") == "Something New"


def test_active_means_not_out():
    assert is_active_status("Being Held")
    assert is_active_status("Unknown")
    assert not is_active_status("Out")


def test_evac_status_and_cause():
    assert normalize_evac_status("Evacuation Order") == "Order"
    assert normalize_evac_status("ALERT") == "Alert"
    assert normalize_evac_status("All Clear") == "All Clear"
    assert normalize_cause("person") == "Person"
    assert normalize_cause("Lightning") == "Lightning"
    assert normalize_cause(None) == "Undetermined"
    assert normalize_cause("Under Investigation") == "Undetermined"


def test_points_frame_from_fixture():
    frame = points_frame(load("bc_fire_points"))
    assert len(frame) == 40
    assert {"fire_number", "status", "size_ha", "lon", "lat", "is_active"} <= set(frame.columns)
    assert frame["lon"].between(-140, -110).all()
    assert frame["lat"].between(48, 60).all()
    assert frame["centre"].map(type).eq(str).all()      # codes are kept as text
    assert frame["ignition_date"].notna().all()


def test_points_frame_parses_bc_date_only_values_with_trailing_z():
    fc = {"features": [{"geometry": {"type": "Point", "coordinates": [-121.5, 51.1]},
                        "properties": {"FIRE_NUMBER": "C1", "IGNITION_DATE": "2026-06-17Z"}}]}
    frame = points_frame(fc)
    assert frame.loc[0, "ignition_date"] == pd.Timestamp("2026-06-17", tz="UTC")


def test_points_frame_copes_with_missing_columns_and_values():
    fc = {"features": [
        {"geometry": {"type": "Point", "coordinates": [-121.5, 51.1]}, "properties": {"FIRE_NUMBER": "C1"}},
        {"geometry": None, "properties": {"FIRE_NUMBER": "C2", "LATITUDE": 50.0, "LONGITUDE": -120.0,
                                          "FIRE_STATUS": "Out", "CURRENT_SIZE": "not a number"}},
    ]}
    frame = points_frame(fc)
    assert frame["status"].tolist() == ["Unknown", "Out"]
    assert frame.loc[1, "lon"] == -120.0            # falls back to the property columns
    assert pd.isna(frame.loc[1, "size_ha"])
    assert frame["name"].tolist() == ["C1", "C2"]   # name falls back to the fire number


def test_empty_inputs_give_empty_frames_with_columns():
    for frame in (points_frame(None), points_frame({"features": []})):
        assert frame.empty and "fire_number" in frame.columns
    assert evac_frame(None).empty and "status" in evac_frame(None).columns
    assert hotspots_frame({"features": []}).empty


def test_evac_frame_flags_wildfire_and_parses_dates():
    frame = evac_frame(load("bc_evac_orders"))
    assert frame["is_wildfire"].sum() == 5          # the landslide is not a wildfire
    assert set(frame["status"]) == {"Order", "Alert", "All Clear"}
    assert frame["start_date"].notna().all()
    assert str(frame["start_date"].dt.tz) == "UTC"


def test_hotspots_frame():
    frame = hotspots_frame(load("cwfis_hotspots"))
    assert len(frame) == 25 and list(frame.columns) == ["lon", "lat"]
