"""Entry point. Run locally with ``shiny run --reload src/app.py``.

To add a dashboard: create ``dashboards/<name>/`` (copy ``wildfire/``), then add one
``ui.nav_panel`` below and one ``*_server`` call in ``server``.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make ``core``, ``pipeline`` and ``dashboards`` importable however the host starts the app.
SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from shiny import App, reactive, ui  # noqa: E402

from core import theme  # noqa: E402
from dashboards import sources  # noqa: E402
from dashboards.wildfire import page as wildfire  # noqa: E402

WWW = SRC / "www"

app_ui = ui.page_navbar(
    ui.nav_panel("BC wildfire", wildfire.wildfire_ui("wildfire")),
    ui.nav_panel("Data and sources", sources.sources_ui("sources")),
    ui.nav_spacer(),
    ui.nav_control(ui.input_dark_mode(id="mode")),
    title="WEP Canada · Wildfire resilience",
    id="page",
    lang="en",
    header=ui.TagList(
        ui.head_content(ui.tags.style(theme.css()),
                        ui.tags.meta(name="viewport", content="width=device-width, initial-scale=1")),
        ui.include_css(WWW / "styles.css"),
    ),
    fillable=False,
    window_title="WEP Canada wildfire resilience dashboard",
)


def server(input, output, session):
    mode = reactive.calc(lambda: "dark" if input.mode() == "dark" else "light")
    wildfire.wildfire_server("wildfire", mode)
    sources.sources_server("sources")


app = App(app_ui, server, static_assets=WWW)
