"""The "Data and sources" page: where every number comes from, its licence and how fresh it is.

Shared by every dashboard. It reads the source registry and the freshness manifest the
pipeline writes, so it never needs editing when a source is added.
"""

from __future__ import annotations

from datetime import datetime

from shiny import module, reactive, render, ui

from core import config, freshness
from pipeline.sources import SOURCES
from pipeline.watch import PAGES

STATE_ICON = {"fresh": "✓", "degraded": "!", "stale": "!", "missing": "✕"}
STATE_LABEL = {"fresh": "Fresh", "degraded": "Last refresh failed", "stale": "Stale", "missing": "No data yet"}


def source_rows(manifest: dict, now: datetime | None = None) -> list[dict]:
    rows = []
    for key, spec in SOURCES.items():
        entry = manifest.get("sources", {}).get(key)
        status = freshness.status_for(entry, now)
        rows.append({
            "label": spec.label,
            "landing_page": spec.landing_page,
            "licence": spec.licence,
            "licence_url": spec.licence_url,
            "state": status["state"],
            "text": status["text"],
            "rows": (entry or {}).get("rows"),
            "error": (entry or {}).get("last_error"),
        })
    return rows


def _row_ui(row: dict):
    return ui.tags.tr(
        ui.tags.td(ui.a(row["label"], href=row["landing_page"], target="_blank", rel="noopener")),
        ui.tags.td(ui.a(row["licence"], href=row["licence_url"], target="_blank", rel="noopener")),
        ui.tags.td(
            ui.span(STATE_ICON[row["state"]], {"aria-hidden": "true"}, class_=f"pill-icon st-{row['state']}"),
            ui.strong(STATE_LABEL[row["state"]]),
            f" · {row['text']}",
        ),
        ui.tags.td("" if row["rows"] is None else f"{row['rows']:,}"),
        ui.tags.td(row["error"] or ""),
    )


@module.ui
def sources_ui():
    return ui.div(
        ui.h3("Data and sources"),
        ui.p("The map, headline numbers and charts read open government data. The live feeds are fetched "
             "when you open the dashboard (and cached for 15 minutes); a copy is saved every day so "
             "the dashboard still works if a feed is down. Each panel shows how old its data is."),
        ui.output_ui("snapshot_table"),
        ui.h4("Pages watched for changes"),
        ui.p("These sources publish numbers as text and have no data feed. A weekly check flags when a "
             "page changes, and the figures in the curated indicators file are then updated by hand."),
        ui.tags.ul(*[ui.tags.li(ui.a(p.label, href=p.url, target="_blank", rel="noopener")) for p in PAGES]),
        ui.h4("Attribution"),
        ui.p("Contains information licensed under the Open Government Licence – British Columbia and "
             "the Open Government Licence – Canada. Base map © OpenStreetMap contributors "
             "© CARTO. This is an independent analysis and is not endorsed by the data providers."),
        class_="sources-page",
    )


@module.server
def sources_server(input, output, session):
    @reactive.calc
    def manifest():
        reactive.invalidate_later(300)
        return freshness.load_manifest(config.FRESHNESS_PATH)

    @render.ui
    def snapshot_table():
        m = manifest()
        generated = freshness.parse_iso(m.get("generated_at"))
        note = (f"Last pipeline run: {freshness.humanize_age(freshness.utcnow() - generated)}."
                if generated else "The pipeline has not run yet.")
        return ui.div(
            ui.p(note, class_="side-note"),
            ui.tags.table(
                ui.tags.thead(ui.tags.tr(*[ui.tags.th(h) for h in
                                           ("Source", "Licence", "Daily snapshot", "Features", "Last error")])),
                ui.tags.tbody(*[_row_ui(r) for r in source_rows(m)]),
                class_="table sources-table",
            ),
        )
