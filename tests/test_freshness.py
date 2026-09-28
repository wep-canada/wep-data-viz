from datetime import datetime, timedelta, timezone

from core import freshness

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


def test_humanize_age():
    h = freshness.humanize_age
    assert h(timedelta(seconds=10)) == "just now"
    assert h(timedelta(minutes=5)) == "5 min ago"
    assert h(timedelta(hours=3, minutes=10)) == "3 h ago"
    assert h(timedelta(days=4)) == "4 d ago"
    assert h(timedelta(seconds=-5)) == "just now"


def test_iso_round_trip():
    assert freshness.parse_iso(freshness.to_iso(NOW)) == NOW
    assert freshness.parse_iso(None) is None
    assert freshness.parse_iso("not a date") is None


def test_status_missing_when_never_fetched():
    assert freshness.status_for(None, NOW)["state"] == "missing"
    assert freshness.status_for({}, NOW)["state"] == "missing"


def test_status_fresh_degraded_and_stale():
    m = freshness.empty_manifest()
    freshness.record_success(m, "a", label="A", url="u", rows=3, expected_max_age_hours=36,
                             now=NOW - timedelta(hours=2))
    assert freshness.status_for(m["sources"]["a"], NOW)["state"] == "fresh"

    freshness.record_failure(m, "a", label="A", url="u", error="boom", expected_max_age_hours=36, now=NOW)
    assert freshness.status_for(m["sources"]["a"], NOW)["state"] == "degraded"

    assert freshness.status_for(m["sources"]["a"], NOW + timedelta(hours=40))["state"] == "stale"


def test_failure_keeps_last_success_and_success_clears_error():
    m = freshness.empty_manifest()
    freshness.record_success(m, "a", label="A", url="u", rows=7, expected_max_age_hours=36,
                             now=NOW - timedelta(hours=5))
    freshness.record_failure(m, "a", label="A", url="u", error="x" * 900, expected_max_age_hours=36, now=NOW)
    entry = m["sources"]["a"]
    assert entry["rows"] == 7
    assert entry["last_success"] == freshness.to_iso(NOW - timedelta(hours=5))
    assert len(entry["last_error"]) == 500
    freshness.record_success(m, "a", label="A", url="u", rows=8, expected_max_age_hours=36, now=NOW)
    assert "last_error" not in m["sources"]["a"]


def test_manifest_save_and_load(tmp_path):
    path = tmp_path / "f.json"
    m = freshness.empty_manifest()
    freshness.record_success(m, "a", label="A", url="u", rows=1, expected_max_age_hours=1, now=NOW)
    freshness.save_manifest(m, path, now=NOW)
    assert freshness.load_manifest(path)["sources"]["a"]["rows"] == 1


def test_load_manifest_tolerates_missing_and_garbage(tmp_path):
    assert freshness.load_manifest(tmp_path / "nope.json") == freshness.empty_manifest()
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert freshness.load_manifest(bad) == freshness.empty_manifest()
    wrong = tmp_path / "wrong.json"
    wrong.write_text('["list"]', encoding="utf-8")
    assert freshness.load_manifest(wrong) == freshness.empty_manifest()
