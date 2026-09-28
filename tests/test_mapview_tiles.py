"""Basemap URL: the CARTO key is attached only when configured."""

from core import config
from dashboards.wildfire import mapview


def test_tile_url_without_key(monkeypatch):
    monkeypatch.setattr(config, "CARTO_KEY", "")
    assert "key=" not in mapview.tile_url("light")
    assert "dark_all" in mapview.tile_url("dark")


def test_tile_url_with_key(monkeypatch):
    monkeypatch.setattr(config, "CARTO_KEY", "abc123")
    assert mapview.tile_url("light").endswith(".png?key=abc123")
    assert mapview.tile_url("dark").endswith(".png?key=abc123")
    assert "{z}/{x}/{y}" in mapview.tile_url("light")
