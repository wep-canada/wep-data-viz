"""A floating "Ask a question" assistant, grounded in the dashboard's own data and docs.

Uses chatlas (https://posit-dev.github.io/chatlas/) with Groq's free API tier, so the
dashboard can ship an AI assistant with no paid key (see README for setup). The model
only ever sees what this module hands it in `build_context()` - the current wildfire
numbers, the equity/governance indicators, the documented data gaps and the source
registry - plus a system prompt telling it not to use anything else. That keeps its
answers tied to what the dashboard actually shows, rather than the model's own (and
possibly stale or wrong) general knowledge about a specific, fast-moving wildfire.

If no ``GROQ_API_KEY`` is configured, the widget still renders but says so instead of
trying to chat - local dev, tests and forks all keep working with zero setup.

Each session builds its own chat client (inside ``assistant_server``, not at UI-build
time), so concurrent visitors never share conversation state - see chatlas's own
web-apps guide for why a single shared client across sessions is the wrong pattern.
"""

from __future__ import annotations

from shiny import module, ui

from core import config
from dashboards.wildfire import data as wildfire_data
from dashboards.wildfire import kpis as kpi_calc
from pipeline.sources import SOURCES
from pipeline.watch import PAGES

GREETING = (
    "Hi! I can answer questions about this dashboard - the current wildfire numbers, the "
    "equity and governance indicators, documented data gaps, and where the data comes from. "
    "I only know what's shown here and I can be wrong, so for anything safety-related please "
    "use EmergencyInfoBC, the BC Wildfire Service or your local authority instead."
)

SYSTEM_PROMPT_TEMPLATE = """\
You are the built-in assistant for the WEP Canada wildfire resilience dashboard, a public \
tool from Women's Environmental Programme Canada (WEP Canada). Answer questions using ONLY \
the dashboard data and documentation given below under "Current dashboard data" - never your \
own outside knowledge about specific fires, evacuation orders or incidents, since you have no \
live feed of your own and a fast-moving wildfire situation can easily have changed since your \
training. If a question isn't covered by that data, say you don't know rather than guessing, \
and point to the relevant tab (Overview, Equity and governance, Data gaps, or Data and \
sources). Never invent a number. Keep answers short - a few plain-language sentences, no \
markdown tables. This dashboard is for awareness and analysis, not an emergency alert \
service: for evacuation orders or safety information, always point people to EmergencyInfoBC, \
the BC Wildfire Service and their local authority rather than answering yourself.

=== Current dashboard data (snapshot as of this conversation's start) ===
{context}
"""


def _bullets(label: str, items: list[str]) -> str:
    body = "\n".join(f"- {item}" for item in items) if items else "- (none)"
    return f"{label}:\n{body}"


def build_context() -> str:
    """A plain-text snapshot of what the dashboard currently shows, for the system prompt.

    Built once per chat session from the same cached loaders the dashboard itself uses
    (see ``dashboards.wildfire.data``), so it costs no extra network fetch beyond what the
    dashboard was already going to do, and it is never more than the 15-minute live cache
    out of date. Each section is independent and fails soft: if one source is unavailable
    the rest of the context (and the assistant) still works.
    """
    sections: list[str] = [
        "About this dashboard: it tracks BC wildfires, evacuation orders/alerts and satellite "
        "hotspots on an interactive map, alongside equity and governance indicators (for example "
        "Indigenous evacuee counts and FireSmart funding) and a page of documented data gaps. It "
        "is built by WEP Canada from public open government data, for awareness and analysis - "
        "it is not an emergency alert service."
    ]

    try:
        d = wildfire_data.load_all()
        kpis = kpi_calc.compute_kpis(d.points, d.evac, d.hotspot_count)
        sections.append(_bullets("Province-wide wildfire headline numbers right now",
                                  [f"{k.label}: {k.value} ({k.sub})" for k in kpis]))
        statuses = wildfire_data.layer_statuses(d)
        sections.append(_bullets("Freshness of each live data feed",
                                  [f"{s['label']}: {s['text']}" for s in statuses]))
    except Exception:
        sections.append("Live wildfire data is not available right now.")

    try:
        indicators = wildfire_data.load_indicators()
        eq = kpi_calc.equity_tiles(indicators)
        sections.append(_bullets("Headline equity and governance indicators",
                                  [f"{k.label}: {k.value} ({k.sub})" for k in eq]))
        rows = indicators[["label", "period", "value", "unit", "definition", "source_name"]]
        sections.append(_bullets(
            "All curated equity/governance indicators (label, period, value, unit, definition, source)",
            [" | ".join(str(v) for v in row) for row in rows.itertuples(index=False)]))
    except Exception:
        sections.append("Equity and governance indicators are not available right now.")

    try:
        gaps = wildfire_data.load_data_gaps()
        sections.append(_bullets(
            "Documented data gaps (question; why it matters; what exists; what is missing; a possible path)",
            [f"{row.question} -- why it matters: {row.why_it_matters} -- what exists: "
             f"{row.what_exists} -- what is missing: {row.what_is_missing} -- a possible path: "
             f"{row.possible_path}" for row in gaps.itertuples()]))
    except Exception:
        sections.append("Data gap notes are not available right now.")

    sections.append(_bullets(
        "Where the data comes from",
        [f"{spec.label}: licensed under {spec.licence} ({spec.landing_page})" for spec in SOURCES.values()]
        + [f"{p.label} (a page checked weekly for changes, not a data feed): {p.url}" for p in PAGES]))

    return "\n\n".join(sections)


def _make_client():
    import chatlas
    return chatlas.ChatGroq(
        api_key=config.GROQ_API_KEY,
        model=config.ASSISTANT_MODEL,
        system_prompt=SYSTEM_PROMPT_TEMPLATE.format(context=build_context()),
    )


@module.ui
def assistant_ui():
    toggle = ui.tags.input(type="checkbox", id="open", class_="assistant-toggle-state")
    header = ui.div(
        ui.span("Ask a question", class_="assistant-panel-title"),
        ui.tags.label("Close", {"for": "open"}, class_="assistant-close"),
        class_="assistant-panel-header",
    )
    if config.GROQ_API_KEY:
        body = ui.chat_ui("chat", greeting=GREETING, height="100%", placeholder="Ask about this dashboard...")
    else:
        body = ui.div(
            ui.p("The assistant isn't set up yet.", class_="fd-title"),
            ui.p("An administrator needs to add a GROQ_API_KEY environment variable (see README) "
                 "to turn this on. The rest of the dashboard works normally without it.",
                 class_="side-note"),
            class_="assistant-disabled-note",
        )
    return ui.div(
        toggle,
        ui.tags.label("💬 Ask a question", {"for": "open"}, class_="assistant-toggle"),
        ui.div(header, body, class_="assistant-panel"),
        class_="assistant-widget",
    )


@module.server
def assistant_server(input, output, session):
    if not config.GROQ_API_KEY:
        return
    ui.Chat("chat", client=_make_client(), on_error="sanitize")
