import json
from datetime import timedelta

import pytest

from core import config, freshness
from dashboards.wildfire import data
from pipeline.sources import SOURCES
from helpers import FIXTURES


def fixture_fc(key):
    return json.loads((FIXTURES / "live" / f"{key}.geojson").read_text(encoding="utf-8"))


SPEC = SOURCES["bc_fire_points"]


def test_snapshot_used_when_live_fetch_is_off(data_dir):
    result = data.load_layer(SPEC)
    assert result.origin == "snapshot" and result.error is None
    assert len(result.fc["features"]) == 40
    assert result.fetched_at is not None


def test_missing_snapshot_is_reported_not_raised(empty_data_dir):
    result = data.load_layer(SPEC)
    assert result.origin == "missing" and result.fc["features"] == []


def test_live_fetch_is_cached_within_the_ttl(data_dir, monkeypatch):
    monkeypatch.setattr(config, "LIVE_FETCH_ENABLED", True)
    calls = []
    clock = {"t": 1000.0}

    def fetch(spec):
        calls.append(spec.key)
        return fixture_fc(spec.key)

    first = data.load_layer(SPEC, fetch=fetch, clock=lambda: clock["t"])
    clock["t"] += config.LIVE_TTL_SECONDS - 1
    second = data.load_layer(SPEC, fetch=fetch, clock=lambda: clock["t"])
    assert first.origin == "live" and second is first and len(calls) == 1

    clock["t"] += 2                                     # TTL has now passed
    data.load_layer(SPEC, fetch=fetch, clock=lambda: clock["t"])
    assert len(calls) == 2


def test_failed_live_fetch_falls_back_to_snapshot_and_backs_off(data_dir, monkeypatch):
    monkeypatch.setattr(config, "LIVE_FETCH_ENABLED", True)
    calls = []
    clock = {"t": 0.0}

    def broken(spec):
        calls.append(1)
        raise ConnectionError("source is down")

    result = data.load_layer(SPEC, fetch=broken, clock=lambda: clock["t"])
    assert result.origin == "snapshot" and "source is down" in result.error
    assert len(result.fc["features"]) == 40             # the visitor still gets a map

    clock["t"] += 10                                    # inside the short failure window: no hammering
    data.load_layer(SPEC, fetch=broken, clock=lambda: clock["t"])
    assert len(calls) == 1
    clock["t"] += config.LIVE_FAILURE_TTL_SECONDS
    data.load_layer(SPEC, fetch=broken, clock=lambda: clock["t"])
    assert len(calls) == 2


def test_load_all_builds_frames(data_dir):
    d = data.load_all()
    assert len(d.points) == 40 and len(d.evac) == 6 and d.hotspot_count == 25
    assert d.fc("bc_fire_perimeters")["features"]
    assert d.fc("nonexistent")["features"] == []


def test_load_all_on_empty_checkout(empty_data_dir):
    d = data.load_all()
    assert d.points.empty and d.evac.empty and d.hotspot_count is None


def test_layer_statuses(data_dir):
    d = data.load_all()
    now = freshness.utcnow()
    assert {s["state"] for s in data.layer_statuses(d, now)} == {"fresh"}

    stale = data.layer_statuses(d, now + timedelta(days=3))
    assert {s["state"] for s in stale} == {"stale"}
    assert "Snapshot" in stale[0]["text"]

    live = data.LayerResult("bc_fire_points", {"features": []}, "live", now)
    d.layers["bc_fire_points"] = live
    first = data.layer_statuses(d, now + timedelta(minutes=3))[0]
    assert first["state"] == "fresh" and first["text"].startswith("Live")

    d.layers["bc_fire_points"] = data.LayerResult("bc_fire_points", {"features": []}, "missing", None)
    assert data.layer_statuses(d, now)[0]["state"] == "missing"


def test_layer_statuses_flag_a_failed_live_fetch(data_dir):
    d = data.load_all()
    d.layers["bc_fire_points"].error = "ConnectionError: down"
    first = data.layer_statuses(d)[0]
    assert first["state"] == "degraded" and "live fetch failed" in first["text"]


def test_history_loader(data_dir):
    frame = data.load_history()
    assert len(frame) == 14 and str(frame["date"].dtype).startswith("datetime64")


def test_history_loader_when_missing(empty_data_dir):
    assert data.load_history().empty


# ----------------------------------------------------- the real curated files

def test_indicators_file_is_well_formed():
    frame = data.load_indicators()
    assert not frame.empty
    assert not frame.duplicated(["indicator_id", "period"]).any(), "an indicator has two values for one period"
    assert frame["value"].notna().all()
    assert frame["source_url"].str.startswith("https://").all()
    assert frame["origin"].str.len().gt(0).all(), "every figure must say whether it was re-checked"
    assert frame["definition"].str.len().gt(0).all()


def test_first_nations_involvement_is_flagged_as_not_comparable():
    frame = data.load_indicators()
    rows = frame[frame["indicator_id"] == "cultural_fire_first_nations"]
    assert len(rows) >= 2 and rows["notes"].str.contains("not chart or compare", case=False).all()


def test_data_gaps_file_is_well_formed():
    gaps = data.load_data_gaps()
    assert len(gaps) >= 4
    assert gaps["gap_id"].is_unique
    for column in ("question", "why_it_matters", "what_exists", "what_is_missing", "possible_path"):
        assert gaps[column].str.len().gt(0).all(), column


def test_fire_centre_codes_are_optional_but_parse():
    assert isinstance(data.load_centre_names(), dict)
