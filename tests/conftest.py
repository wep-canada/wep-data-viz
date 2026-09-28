from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import config  # noqa: E402
from helpers import prepare_data_dir  # noqa: E402


@pytest.fixture
def data_dir(tmp_path, monkeypatch) -> Path:
    """A temp data folder holding the synthetic fixtures, wired into ``core.config``."""
    target = prepare_data_dir(tmp_path / "data")
    monkeypatch.setattr(config, "DATA_DIR", target)
    monkeypatch.setattr(config, "LIVE_DIR", target / "live")
    monkeypatch.setattr(config, "HISTORY_DIR", target / "history")
    monkeypatch.setattr(config, "WATCH_DIR", target / "watch")
    monkeypatch.setattr(config, "FRESHNESS_PATH", target / "freshness.json")
    monkeypatch.setattr(config, "LIVE_FETCH_ENABLED", False)
    return target


@pytest.fixture
def empty_data_dir(tmp_path, monkeypatch) -> Path:
    """A temp data folder with nothing in it (as on a brand-new checkout)."""
    target = tmp_path / "empty"
    target.mkdir()
    monkeypatch.setattr(config, "DATA_DIR", target)
    monkeypatch.setattr(config, "LIVE_DIR", target / "live")
    monkeypatch.setattr(config, "HISTORY_DIR", target / "history")
    monkeypatch.setattr(config, "WATCH_DIR", target / "watch")
    monkeypatch.setattr(config, "FRESHNESS_PATH", target / "freshness.json")
    monkeypatch.setattr(config, "LIVE_FETCH_ENABLED", False)
    return target


@pytest.fixture(autouse=True)
def _clear_live_cache():
    from dashboards.wildfire import data
    data.clear_cache()
    yield
    data.clear_cache()
