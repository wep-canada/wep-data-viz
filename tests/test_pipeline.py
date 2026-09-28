import json
from datetime import date, datetime, timezone

import pandas as pd
import pytest

from core import freshness
from pipeline import history, run, watch
from pipeline.sources import SOURCES
from helpers import FIXTURES

NOW = datetime(2026, 9, 20, 13, 0, tzinfo=timezone.utc)


def fixture_fc(key):
    return json.loads((FIXTURES / "live" / f"{key}.geojson").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- history

def test_summarize_counts_from_fixtures():
    row = history.summarize(fixture_fc("bc_fire_points"), fixture_fc("bc_evac_orders"),
                            fixture_fc("cwfis_hotspots"), today=date(2026, 9, 20))
    assert row["date"] == "2026-09-20"
    assert row["fires_season"] == 40
    assert row["evac_orders"] == 2 and row["evac_alerts"] == 2      # landslide and All Clear excluded
    assert row["hotspots_bc_24h"] == 25
    assert row["fires_out_of_control"] <= row["fires_active"] <= row["fires_season"]
    assert row["hectares_season"] > 0


def test_summarize_leaves_failed_sources_empty():
    row = history.summarize(fixture_fc("bc_fire_points"), None, None, today=date(2026, 9, 20))
    assert row["evac_orders"] is None and row["hotspots_bc_24h"] is None


def test_upsert_inserts_updates_and_never_overwrites_with_none(tmp_path):
    path = tmp_path / "h.parquet"
    a = history.summarize(fixture_fc("bc_fire_points"), fixture_fc("bc_evac_orders"), None, today=date(2026, 9, 19))
    history.upsert_daily(a, path)
    b = history.summarize(fixture_fc("bc_fire_points"), None, fixture_fc("cwfis_hotspots"), today=date(2026, 9, 20))
    history.upsert_daily(b, path)
    assert len(history.read_history(path)) == 2

    # A second run on the same day where the evac feed failed keeps the earlier real value.
    c = history.summarize(None, fixture_fc("bc_evac_orders"), None, today=date(2026, 9, 20))
    frame = history.upsert_daily(c, path)
    today = frame[frame["date"] == "2026-09-20"].iloc[0]
    assert len(frame) == 2
    assert today["fires_season"] == 40 and today["evac_orders"] == 2 and today["hotspots_bc_24h"] == 25
    assert frame["date"].is_monotonic_increasing


def test_read_history_when_missing(tmp_path):
    frame = history.read_history(tmp_path / "nope.parquet")
    assert frame.empty and list(frame.columns) == history.COLUMNS


# -------------------------------------------------------------------- run

def fake_fetch(spec):
    return fixture_fc(spec.key)


def test_run_writes_snapshots_manifest_and_history(empty_data_dir):
    results = run.run(fetch=fake_fetch, now=NOW)
    assert all(v is None for v in results.values()) and set(results) == set(SOURCES)
    for key in SOURCES:
        assert (empty_data_dir / "live" / f"{key}.geojson").exists()
    manifest = freshness.load_manifest()
    assert manifest["generated_at"] == freshness.to_iso(NOW)
    assert manifest["sources"]["bc_fire_points"]["rows"] == 40
    frame = history.read_history()
    assert frame["date"].tolist() == ["2026-09-20"] and frame.loc[0, "fires_season"] == 40


def test_run_fails_soft_and_keeps_the_old_snapshot(empty_data_dir):
    run.run(fetch=fake_fetch, now=NOW)
    before = (empty_data_dir / "live" / "bc_evac_orders.geojson").read_text(encoding="utf-8")

    def flaky(spec):
        if spec.key == "bc_evac_orders":
            raise RuntimeError("server on fire")
        return fake_fetch(spec)

    later = datetime(2026, 9, 21, 13, 0, tzinfo=timezone.utc)
    results = run.run(fetch=flaky, now=later)
    assert results["bc_evac_orders"].startswith("RuntimeError")
    assert results["bc_fire_points"] is None
    assert (empty_data_dir / "live" / "bc_evac_orders.geojson").read_text(encoding="utf-8") == before

    entry = freshness.load_manifest()["sources"]["bc_evac_orders"]
    assert entry["last_success"] == freshness.to_iso(NOW)             # not advanced
    assert "server on fire" in entry["last_error"]
    frame = history.read_history()
    assert len(frame) == 2
    assert pd.isna(frame.iloc[1]["evac_orders"]) and frame.iloc[1]["fires_season"] == 40


def test_run_can_target_one_source_and_skip_history(empty_data_dir):
    results = run.run(["bc_fire_points"], fetch=fake_fetch, now=NOW, write_history=False)
    assert list(results) == ["bc_fire_points"]
    assert not (empty_data_dir / "history").exists()


def test_main_exit_code_reflects_failures(empty_data_dir, monkeypatch, capsys):
    monkeypatch.setattr(run, "fetch_source", fake_fetch)
    monkeypatch.setattr(run, "run", lambda keys=None, **kw: {"a": None})
    assert run.main([]) == 0
    monkeypatch.setattr(run, "run", lambda keys=None, **kw: {"a": None, "b": "boom"})
    assert run.main([]) == 1
    assert "FAILED  b: boom" in capsys.readouterr().err


# ------------------------------------------------------------------ watch

PAGE = "<html><head><style>x{}</style><script>var t=Date.now()</script></head><body><h1>Numbers</h1><p>71 million</p></body></html>"


def test_visible_text_ignores_scripts_styles_and_whitespace():
    assert watch.visible_text(PAGE) == "Numbers 71 million"
    assert watch.fingerprint(PAGE) == watch.fingerprint(PAGE.replace("<p>", "\n\n  <p>"))
    assert watch.fingerprint(PAGE) != watch.fingerprint(PAGE.replace("71", "72"))


def test_ignore_patterns_remove_volatile_text():
    a = "<p>Numbers. Last updated 2026-09-01</p>"
    b = "<p>Numbers. Last updated 2026-09-08</p>"
    ignore = (r"Last updated \d{4}-\d{2}-\d{2}",)
    assert watch.fingerprint(a, ignore) == watch.fingerprint(b, ignore)
    assert watch.fingerprint(a) != watch.fingerprint(b)


def test_check_pages_baseline_then_unchanged_then_changed_then_error(empty_data_dir):
    pages = [watch.WatchedPage("p1", "Page one", "https://example.invalid/1"),
             watch.WatchedPage("p2", "Page two", "https://example.invalid/2")]
    html = {"https://example.invalid/1": PAGE, "https://example.invalid/2": PAGE}
    kinds = lambda changes: [c.kind for c in changes]

    first = watch.check_pages(pages, fetch=lambda url: html[url])
    assert kinds(first) == ["baseline", "baseline"]
    assert watch.render_report(first) == ""             # the first run never raises an alarm

    assert kinds(watch.check_pages(pages, fetch=lambda url: html[url])) == ["unchanged", "unchanged"]

    html["https://example.invalid/1"] = PAGE.replace("71", "72")
    assert kinds(watch.check_pages(pages, fetch=lambda url: html[url])) == ["changed", "unchanged"]

    def broken(url):
        raise OSError("no route")

    third = watch.check_pages(pages, fetch=broken)
    assert kinds(third) == ["error", "error"]
    assert watch.render_report(third) == ""             # errors alone do not open an issue


def test_only_real_changes_reach_the_report(empty_data_dir):
    pages = [watch.WatchedPage("p1", "Page one", "https://example.invalid/1"),
             watch.WatchedPage("p2", "Page two", "https://example.invalid/2")]
    html = {"https://example.invalid/1": PAGE, "https://example.invalid/2": PAGE}
    watch.check_pages(pages, fetch=lambda url: html[url])
    html["https://example.invalid/1"] = PAGE.replace("71", "72")
    changes = watch.check_pages(pages, fetch=lambda url: html[url])
    assert {c.page.key: c.kind for c in changes} == {"p1": "changed", "p2": "unchanged"}
    report = watch.render_report(changes)
    assert "Page one" in report and "Page two" not in report
    assert "https://example.invalid/1" in report
