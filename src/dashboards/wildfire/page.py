"""Shiny UI and server for the wildfire dashboard (a module, so more dashboards can sit beside it)."""

from __future__ import annotations

from typing import Callable

import pandas as pd
from shiny import module, reactive, render, ui
from shinywidgets import output_widget, render_widget

from core import config
from core.freshness import STATE_ICON, STATE_LABEL
from . import charts, data, filters, mapview
from . import kpis as kpi_calc

NOTICE = (
    "For awareness and analysis only, not an emergency alert service. For evacuation orders and "
    "safety information, use EmergencyInfoBC, the BC Wildfire Service and your local authority."
)


def kpi_tile(kpi: kpi_calc.Kpi):
    return ui.div(
        ui.div(kpi.label, class_="kpi-label"),
        ui.div(kpi.value, class_="kpi-value"),
        ui.div(kpi.sub, class_="kpi-sub"),
        class_="kpi",
    )


def freshness_pill(status: dict):
    state = status["state"]
    return ui.span(
        ui.span(STATE_ICON[state], {"aria-hidden": "true"}, class_=f"pill-icon st-{state}"),
        f"{status['label']}: ",
        ui.strong(STATE_LABEL[state]),
        f" · {status['text']}",
        class_="pill",
    )


def link_cell(url, label: str):
    """A clickable link for a data-grid cell, or "" if there's no safe URL to link to.

    Shiny's DataGrid renders htmltools tags in a cell as real HTML rather than escaping
    them to text, so this is what makes the fire list's and indicator table's "Link"
    columns actually clickable instead of showing a bare URL string.
    """
    safe = mapview.safe_https_url(url)
    return ui.a(label, href=safe, target="_blank", rel="noopener") if safe else ""


def legend():
    return ui.div(
        ui.span(ui.span(class_="lg lg-dot lg-ooc"), "Out-of-control fire", class_="lg-item"),
        ui.span(ui.span(class_="lg lg-dot lg-other"), "Other active fire", class_="lg-item"),
        ui.span(ui.span(class_="lg lg-box lg-order"), "Evacuation order (solid)", class_="lg-item"),
        ui.span(ui.span(class_="lg lg-box lg-alert"), "Evacuation alert (dashed)", class_="lg-item"),
        ui.span(ui.span(class_="lg lg-dot lg-hot"), "Satellite hotspot", class_="lg-item"),
        ui.span("Marker size grows with hectares burned.", class_="lg-note"),
        class_="legend",
    )


def _overview_panel():
    sidebar = ui.sidebar(
        ui.h5("Filters"),
        ui.p("Filters apply to the map, charts and fire list. The headline numbers are province-wide.",
             class_="side-note"),
        ui.input_selectize("centres", "Fire centre", choices={}, multiple=True,
                           options={"placeholder": "All fire centres"}),
        ui.input_selectize("statuses", "Fire status", choices=filters.status_choices(), multiple=True,
                           options={"placeholder": "All statuses"}),
        ui.input_selectize("causes", "Cause", choices=filters.cause_choices(), multiple=True,
                           options={"placeholder": "All causes"}),
        ui.input_select("min_size", "Minimum size", filters.MIN_SIZE_CHOICES, selected="0"),
        ui.input_switch("include_out", "Include fires declared out", value=False),
        ui.hr(),
        ui.input_checkbox_group("layers", "Map layers", mapview.LAYER_CHOICES,
                                selected=mapview.DEFAULT_LAYERS),
        width=300,
    )
    return ui.layout_sidebar(
        sidebar,
        ui.div(NOTICE, class_="notice"),
        ui.output_ui("freshness"),
        ui.output_ui("kpis"),
        ui.card(
            ui.card_header("Fires, evacuations and satellite detections"),
            output_widget("fire_map"),
            ui.output_ui("map_note"),
            ui.output_ui("fire_detail"),
            legend(),
            full_screen=True,
        ),
        ui.layout_columns(
            ui.card(ui.card_header("Fires by cause"), output_widget("cause_chart")),
            ui.card(ui.card_header("Fires by fire centre"), output_widget("centre_chart")),
            col_widths=[6, 6],
        ),
        ui.card(
            ui.card_header("Trend, one point per day since the pipeline started"),
            ui.input_select("trend_metric", None, charts.TREND_METRICS, width="280px"),
            output_widget("trend_chart"),
        ),
        ui.card(ui.card_header("Fire list (table view)"), ui.output_data_frame("fire_table"),
                full_screen=True),
        ui.card(ui.card_header("Wildfire evacuation orders and alerts in effect (table view)"),
                ui.output_data_frame("evac_table"), full_screen=True),
    )


def _equity_panel():
    return ui.div(
        ui.div(
            "These figures are maintained by hand in data/curated/indicators.csv, each with its source "
            "link and whether it was re-checked against the source page. They change once or twice a "
            "year. Definitions differ between years for some measures, so compare with care.",
            class_="notice",
        ),
        ui.output_ui("equity_tiles"),
        ui.layout_columns(
            ui.card(ui.card_header("Cultural and prescribed fire: hectares treated"),
                    output_widget("cultural_ha_chart")),
            ui.card(ui.card_header("Cultural and prescribed fire: projects"),
                    output_widget("cultural_projects_chart")),
            col_widths=[6, 6],
        ),
        ui.card(ui.card_header("All curated indicators"), ui.output_data_frame("indicator_table"),
                full_screen=True),
    )


def _gaps_panel():
    gaps = data.load_data_gaps()
    panels = []
    for row in gaps.itertuples():
        panels.append(ui.accordion_panel(
            row.question,
            ui.p(ui.strong("Why it matters. "), row.why_it_matters),
            ui.p(ui.strong("What exists. "), row.what_exists),
            ui.p(ui.strong("What is missing. "), row.what_is_missing),
            ui.p(ui.strong("A possible path. "), row.possible_path),
            value=row.gap_id,
        ))
    return ui.div(
        ui.div("Where data are not available the dashboard shows the gap rather than inventing a proxy. "
               "The gaps are themselves a finding: they show what governments cannot currently measure.",
               class_="notice"),
        ui.accordion(*panels, open=False, id="gaps") if panels else ui.p("No data gaps recorded."),
    )


@module.ui
def wildfire_ui():
    return ui.navset_pill(
        ui.nav_panel("Overview", _overview_panel()),
        ui.nav_panel("Equity and governance", _equity_panel()),
        ui.nav_panel("Data gaps", _gaps_panel()),
        id="section",
    )


@module.server
def wildfire_server(input, output, session, mode: Callable[[], str]):
    centre_names = data.load_centre_names()
    indicators = data.load_indicators()

    @reactive.calc
    def live():
        reactive.invalidate_later(config.LIVE_TTL_SECONDS)
        return data.load_all()

    selected_fire = reactive.Value(None)   # fire number of the fire clicked on the map

    @reactive.calc
    def history():
        reactive.invalidate_later(3600)
        return data.load_history()

    @reactive.effect
    def _centre_choices():
        choices = filters.centre_choices(live().points, centre_names)
        with reactive.isolate():
            selected = [c for c in (input.centres() or ()) if c in choices]
        ui.update_selectize("centres", choices=choices, selected=selected)

    @reactive.calc
    def current_filters() -> filters.FireFilters:
        return filters.FireFilters(
            centres=tuple(input.centres() or ()),
            statuses=tuple(input.statuses() or ()),
            causes=tuple(input.causes() or ()),
            min_size_ha=float(input.min_size() or 0),
            include_out=bool(input.include_out()),
        )

    @reactive.calc
    def filtered() -> pd.DataFrame:
        return filters.apply_fire_filters(live().points, current_filters())

    # ------------------------------------------------------------- overview
    @render.ui
    def freshness():
        return ui.div(*[freshness_pill(s) for s in data.layer_statuses(live())], class_="pills")

    @render.ui
    def kpis():
        d = live()
        return ui.div(*[kpi_tile(k) for k in kpi_calc.compute_kpis(d.points, d.evac, d.hotspot_count)],
                      class_="kpi-row")

    @render.ui
    def map_note():
        return ui.p(f"Showing {len(filtered()):,} fires. Click a fire for details.", class_="map-note")

    @render.ui
    def fire_detail():
        number = selected_fire()
        points = live().points
        match = points[points["fire_number"] == number] if number else points.iloc[0:0]
        if match.empty:
            return ui.div()
        row = match.iloc[0]
        url = mapview.safe_https_url(row["url"])
        return ui.div(
            ui.div(ui.strong(row["name"]), f" ({row['fire_number']})", class_="fd-title"),
            ui.tags.dl(*[part for label, value in mapview.fire_detail_items(row)
                         for part in (ui.tags.dt(label), ui.tags.dd(value))], class_="fd-list"),
            ui.a("BC Wildfire Service page", href=url, target="_blank", rel="noopener") if url else ui.span(),
            class_="fire-detail",
        )

    @render_widget
    def fire_map():
        d = live()
        return mapview.build_map(
            points=filtered(),
            perimeters_fc=d.fc("bc_fire_perimeters"),
            evac_fc=d.fc("bc_evac_orders"),
            hotspots_fc=d.fc("cwfis_hotspots"),
            layers=set(input.layers() or ()),
            mode=mode(),
            on_select=selected_fire.set,
        )

    @render_widget
    def cause_chart():
        return charts.cause_bar(filtered(), mode())

    @render_widget
    def centre_chart():
        return charts.centre_bar(filtered(), mode(), centre_names)

    @render_widget
    def trend_chart():
        return charts.trend_line(history(), input.trend_metric(), mode())

    @render.data_frame
    def fire_table():
        frame = filtered().sort_values("size_ha", ascending=False, na_position="last")
        view = pd.DataFrame({
            "Fire": frame["name"],
            "Number": frame["fire_number"],
            "Status": frame["status"],
            "Cause": frame["cause"],
            "Size (ha)": frame["size_ha"].round(1),
            "Ignited": frame["ignition_date"].dt.strftime("%Y-%m-%d").fillna("—"),
            "Fire centre": frame["centre"].map(lambda c: filters.centre_label(c, centre_names)),
            "Near": frame["description"],
            "Link": frame["url"].map(lambda u: link_cell(u, "Details")),
        })
        return render.DataGrid(view, width="100%", height="420px")

    @render.data_frame
    def evac_table():
        view = mapview.evac_summary(live().fc("bc_evac_orders")).rename(columns={
            "name": "Area", "status": "Status", "agency": "Issued by", "homes": "Homes",
            "population": "People", "start_date": "Event start"})
        view["Event start"] = view["Event start"].dt.strftime("%Y-%m-%d").fillna("—")
        return render.DataGrid(view, width="100%", height="300px")

    # ------------------------------------------------------ equity and governance
    @render.ui
    def equity_tiles():
        return ui.div(*[kpi_tile(k) for k in kpi_calc.equity_tiles(indicators)], class_="kpi-row")

    @render_widget
    def cultural_ha_chart():
        return charts.emphasis_bars_by_year(indicators, "cultural_fire_hectares", mode())

    @render_widget
    def cultural_projects_chart():
        return charts.emphasis_bars_by_year(indicators, "cultural_fire_projects", mode())

    @render.data_frame
    def indicator_table():
        view = indicators[["label", "period", "value", "unit", "definition", "source_name",
                           "origin", "notes"]].rename(columns={
            "label": "Indicator", "period": "Period", "value": "Value", "unit": "Unit",
            "definition": "Definition", "source_name": "Source", "origin": "Checked",
            "notes": "Notes"})
        view["Link"] = indicators["source_url"].map(lambda u: link_cell(u, "Open"))
        return render.DataGrid(view, width="100%", height="420px")

