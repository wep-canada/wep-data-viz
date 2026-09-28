import copy

import pytest

from core.http import FetchError
from pipeline import fetchers
from pipeline.sources import BC_BBOX, SOURCES, SourceSpec


def feat(i, lon=-122.0, lat=51.0, **props):
    return {"type": "Feature", "id": f"L.{i}", "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {"n": i, **props}}


def test_wfs_pages_until_a_short_page_and_drops_duplicates():
    pages = [
        {"features": [feat(1), feat(2)]},
        {"features": [feat(2), feat(3)]},   # feature 2 repeats across pages
        {"features": [feat(4)]},
    ]
    calls = []

    def fake_get(url, params=None, **kw):
        calls.append(params["startIndex"])
        return pages[len(calls) - 1]

    fc = fetchers.fetch_wfs_geojson("http://x", "layer", page_size=2, get=fake_get)
    assert [f["properties"]["n"] for f in fc["features"]] == [1, 2, 3, 4]
    assert calls == [0, 2, 4]


def test_wfs_asks_for_geojson_lonlat():
    seen = {}

    def fake_get(url, params=None, **kw):
        seen.update(params)
        return {"features": []}

    fetchers.fetch_wfs_geojson("http://x", "pub:LAYER", get=fake_get)
    assert seen["outputFormat"] == "application/json" and seen["srsName"] == "EPSG:4326"
    assert seen["typeNames"] == "pub:LAYER" and seen["version"] == "2.0.0"


def test_wfs_rejects_non_geojson():
    with pytest.raises(FetchError):
        fetchers.fetch_wfs_geojson("http://x", "l", get=lambda *a, **k: {"unexpected": True})


def test_wfs_gives_up_on_runaway_paging(monkeypatch):
    monkeypatch.setattr(fetchers, "MAX_PAGES", 3)
    with pytest.raises(FetchError):
        fetchers.fetch_wfs_geojson("http://x", "l", page_size=1,
                                   get=lambda *a, **k: {"features": [feat(1)]})


def test_arcgis_pages_and_reports_errors():
    pages = [{"features": [feat(1), feat(2)]}, {"features": [feat(3)]}]
    offsets = []

    def fake_get(url, params=None, **kw):
        assert url.endswith("/query")
        offsets.append(params["resultOffset"])
        return pages[len(offsets) - 1]

    fc = fetchers.fetch_arcgis_geojson("http://x/FeatureServer/0/", page_size=2, get=fake_get)
    assert len(fc["features"]) == 3 and offsets == [0, 2]

    with pytest.raises(FetchError, match="ArcGIS error"):
        fetchers.fetch_arcgis_geojson("http://x", get=lambda *a, **k: {"error": {"code": 400}})


def test_ensure_lonlat_swaps_only_when_needed():
    swapped = {"features": [feat(1, lon=51.0, lat=-122.0)]}     # (lat, lon) as some servers return
    fixed = fetchers.ensure_lonlat(swapped)
    assert fixed["features"][0]["geometry"]["coordinates"] == [-122.0, 51.0]
    assert swapped["features"][0]["geometry"]["coordinates"] == [51.0, -122.0]   # input untouched

    correct = {"features": [feat(1, lon=-122.0, lat=51.0)]}
    assert fetchers.ensure_lonlat(correct) is correct
    assert fetchers.ensure_lonlat({"features": []}) == {"features": []}


def test_ensure_lonlat_handles_polygons():
    poly = {"type": "Feature", "geometry": {"type": "Polygon",
            "coordinates": [[[51.0, -122.0], [51.5, -122.0], [51.5, -121.5], [51.0, -122.0]]]},
            "properties": {}}
    out = fetchers.ensure_lonlat({"features": [poly]})
    assert out["features"][0]["geometry"]["coordinates"][0][0] == [-122.0, 51.0]


def test_round_coords():
    fc = {"features": [feat(1, lon=-122.123456789, lat=51.987654321)]}
    out = fetchers.round_coords(fc, 4)
    assert out["features"][0]["geometry"]["coordinates"] == [-122.1235, 51.9877]


def test_filter_bbox_keeps_only_bc():
    fc = {"features": [feat(1, -122, 51), feat(2, -80, 45), feat(3, -150, 60), feat(4, -115, 61)]}
    kept = fetchers.filter_bbox(fc, BC_BBOX)
    assert [f["properties"]["n"] for f in kept["features"]] == [1]


def test_stable_sort_is_deterministic():
    a = {"features": [feat(3, FIRE_NUMBER="C"), feat(1, FIRE_NUMBER="A"), feat(2, FIRE_NUMBER="B")]}
    b = copy.deepcopy(a)
    b["features"].reverse()
    order = lambda fc: [f["properties"]["FIRE_NUMBER"] for f in fetchers.stable_sort(fc, ("FIRE_NUMBER",))["features"]]
    assert order(a) == order(b) == ["A", "B", "C"]


def test_fetch_source_applies_every_tidy_up():
    spec = SourceSpec(key="t", label="T", kind="wfs", url="http://x", layer="l", licence="l", licence_url="u",
                      landing_page="u", bbox=BC_BBOX, sort_keys=("k",), coord_digits=2)
    raw = {"features": [feat(1, 51.111, -122.999, k="b"),      # lat/lon swapped, in BC
                        feat(2, 45.0, -80.0, k="a"),           # outside BC
                        feat(3, 52.222, -121.001, k="a")]}
    fc = fetchers.fetch_source(spec, get=lambda *a, **k: raw)
    assert [f["properties"]["k"] for f in fc["features"]] == ["a", "b"]
    assert fc["features"][1]["geometry"]["coordinates"] == [-123.0, 51.11]


def test_fetch_source_rejects_unknown_kind():
    spec = SourceSpec(key="t", label="T", kind="carrier-pigeon", url="u", licence="l", licence_url="u",
                      landing_page="u")
    with pytest.raises(FetchError):
        fetchers.fetch_source(spec)


def test_registry_is_complete():
    for key, spec in SOURCES.items():
        assert spec.key == key
        assert spec.kind in {"wfs", "arcgis"}
        assert spec.url.startswith("https://") and spec.licence_url.startswith("https://")
        assert spec.landing_page.startswith("https://")
        assert (spec.layer or spec.kind == "arcgis")
