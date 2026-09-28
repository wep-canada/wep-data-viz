"""fetch_fire_centre_codes: parsing/validation logic, without touching the real ArcGIS server."""

import pytest

from pipeline import fetch_fire_centre_codes as fcc


def fake_get(response):
    def get(url, params=None):
        return response
    return get


def test_fetch_codes_parses_attributes():
    response = {"features": [
        {"attributes": {"MOF_FIRE_CENTRE_ID": 1, "MOF_FIRE_CENTRE_NAME": "Cariboo Fire Centre"}},
        {"attributes": {"MOF_FIRE_CENTRE_ID": 2, "MOF_FIRE_CENTRE_NAME": "Coastal Fire Centre"}},
    ]}
    assert fcc.fetch_codes(get=fake_get(response)) == {
        "1": "Cariboo Fire Centre",
        "2": "Coastal Fire Centre",
    }


def test_fetch_codes_skips_incomplete_rows():
    response = {"features": [
        {"attributes": {"MOF_FIRE_CENTRE_ID": 1, "MOF_FIRE_CENTRE_NAME": "Cariboo Fire Centre"}},
        {"attributes": {"MOF_FIRE_CENTRE_ID": None, "MOF_FIRE_CENTRE_NAME": "Nameless"}},
        {"attributes": {"MOF_FIRE_CENTRE_ID": 3, "MOF_FIRE_CENTRE_NAME": ""}},
    ]}
    assert fcc.fetch_codes(get=fake_get(response)) == {"1": "Cariboo Fire Centre"}


def test_fetch_codes_raises_on_unexpected_shape():
    with pytest.raises(RuntimeError):
        fcc.fetch_codes(get=fake_get({"error": "boom"}))


def test_fetch_codes_raises_when_layer_has_no_usable_rows():
    with pytest.raises(RuntimeError):
        fcc.fetch_codes(get=fake_get({"features": []}))


def test_write_csv_sorts_numerically(tmp_path, monkeypatch):
    monkeypatch.setattr(fcc.config, "CURATED_DIR", tmp_path)
    fcc.write_csv({"10": "Ten", "2": "Two", "1": "One"})
    text = (tmp_path / "fire_centre_codes.csv").read_text(encoding="utf-8")
    assert text.splitlines() == ["code,name", "1,One", "2,Two", "10,Ten"]
