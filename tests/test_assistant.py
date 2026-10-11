"""The "Ask a question" assistant: the context it hands the model, and its on/off UI states.

No test here talks to Groq - ``build_context`` is pure, and the UI tests only check which
markup gets built for a given ``config.GROQ_API_KEY``, never construct a real network call.
See ``tests/e2e/test_app_smoke.py`` for proof the whole app still boots with the widget in
its disabled (no key) state.
"""

from __future__ import annotations

from core import config
from dashboards import assistant


def test_build_context_covers_every_section(data_dir):
    ctx = assistant.build_context()
    assert "About this dashboard" in ctx
    assert "Province-wide wildfire headline numbers" in ctx
    assert "Active fires" in ctx                           # a KPI label, from kpis.compute_kpis
    assert "Headline equity and governance indicators" in ctx
    assert "Documented data gaps" in ctx
    assert "Where the data comes from" in ctx
    assert "BC current fire locations" in ctx               # a SOURCES label
    assert "Open Government Licence" in ctx


def test_build_context_fails_soft_when_curated_data_is_missing(empty_data_dir, monkeypatch):
    # No indicators.csv / data_gaps.csv at this path. load_indicators/load_data_gaps already
    # treat that as "nothing curated yet" rather than an error (see dashboards.wildfire.data),
    # so build_context must not raise either - it should just say there's nothing there.
    monkeypatch.setattr(config, "CURATED_DIR", empty_data_dir / "curated")
    ctx = assistant.build_context()
    assert "Headline equity and governance indicators:\n- (none)" in ctx
    assert "Documented data gaps" in ctx and "- (none)" in ctx
    # Sections that don't depend on the curated CSVs still come through.
    assert "About this dashboard" in ctx
    assert "Where the data comes from" in ctx


def test_build_context_fails_soft_when_live_data_is_broken(data_dir, monkeypatch):
    # A section that raises outright (unlike the merely-empty case above) must not take the
    # rest of the context down with it.
    def _boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(assistant.wildfire_data, "load_all", _boom)
    ctx = assistant.build_context()
    assert "Live wildfire data is not available right now." in ctx
    assert "Where the data comes from" in ctx


def test_widget_shows_a_disabled_note_without_an_api_key(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "")
    html = str(assistant.assistant_ui("assistant"))
    assert "isn't set up yet" in html
    assert "shiny-chat-container" not in html


def test_widget_renders_the_chat_component_with_an_api_key(monkeypatch):
    monkeypatch.setattr(config, "GROQ_API_KEY", "fake-key-for-tests")
    html = str(assistant.assistant_ui("assistant"))
    assert "shiny-chat-container" in html
    assert "isn't set up yet" not in html
