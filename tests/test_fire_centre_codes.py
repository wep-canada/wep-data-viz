"""verify_fire_centre_codes: centroid computation and the unmatched-code check."""

import pandas as pd

from pipeline import verify_fire_centre_codes as vfc


def feature(centre, lon, lat, desc=""):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"FIRE_CENTRE": centre, "GEOGRAPHIC_DESCRIPTION": desc}}


def test_centre_centroids_averages_per_code():
    fc = {"type": "FeatureCollection", "features": [
        feature(5, -120.0, 50.0, "Stump Lake"),
        feature(5, -120.2, 50.4, "Duck Range"),
        feature(6, -117.45, 49.93, "St. Mary River"),
    ]}
    out = vfc.centre_centroids(fc).set_index("code")
    assert out.loc["5", "fires"] == 2
    assert out.loc["5", "centroid_lon"] == -120.1
    assert out.loc["5", "centroid_lat"] == 50.2
    assert "Stump Lake" in out.loc["5", "examples"]
    assert out.loc["6", "fires"] == 1


def test_centre_centroids_handles_empty_collection():
    out = vfc.centre_centroids({"type": "FeatureCollection", "features": []})
    assert out.empty


def test_main_flags_codes_missing_from_curated_csv(tmp_path, monkeypatch, capsys):
    live_dir = tmp_path / "live"
    live_dir.mkdir()
    curated_dir = tmp_path / "curated"
    curated_dir.mkdir()
    (curated_dir / "fire_centre_codes.csv").write_text("code,name\n5,Kamloops Fire Centre\n",
                                                        encoding="utf-8")
    monkeypatch.setattr(vfc.config, "LIVE_DIR", live_dir)
    monkeypatch.setattr(vfc.config, "CURATED_DIR", curated_dir)

    from core.io import write_json
    write_json(live_dir / "bc_fire_points.geojson", {"type": "FeatureCollection", "features": [
        feature(5, -120.0, 50.0, "Stump Lake"),
        feature(9, -114.0, 49.0, "Unknown zone"),
    ]})

    assert vfc.main([]) == 1
    assert "<not in fire_centre_codes.csv>" in capsys.readouterr().out


def test_main_passes_when_every_code_is_curated(tmp_path, monkeypatch):
    live_dir = tmp_path / "live"
    live_dir.mkdir()
    curated_dir = tmp_path / "curated"
    curated_dir.mkdir()
    (curated_dir / "fire_centre_codes.csv").write_text("code,name\n5,Kamloops Fire Centre\n",
                                                        encoding="utf-8")
    monkeypatch.setattr(vfc.config, "LIVE_DIR", live_dir)
    monkeypatch.setattr(vfc.config, "CURATED_DIR", curated_dir)

    from core.io import write_json
    write_json(live_dir / "bc_fire_points.geojson", {"type": "FeatureCollection", "features": [
        feature(5, -120.0, 50.0, "Stump Lake"),
    ]})

    assert vfc.main([]) == 0


def test_main_fails_without_a_live_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(vfc.config, "LIVE_DIR", tmp_path / "empty")
    assert vfc.main([]) == 1
