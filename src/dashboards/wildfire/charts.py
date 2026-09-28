"""Plotly figures. Every function takes the colour mode and returns a Figure; no Shiny here.

Form follows the data's job: magnitude across categories is a one-hue bar chart, change
over time is a single line, and "the latest year is the point" is an emphasis bar chart
(one accent bar, the rest grey). No dual axes, no rainbow, values labelled directly.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from core.theme import tokens

FONT = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"

TREND_METRICS = {
    "fires_active": "Active fires",
    "fires_out_of_control": "Out-of-control fires",
    "hectares_season": "Area burned this season (ha)",
    "evac_orders": "Wildfire evacuation orders",
    "evac_alerts": "Wildfire evacuation alerts",
    "hotspots_bc_24h": "Satellite hotspots, last 24 h",
}


def _base(mode: str, height: int) -> go.Figure:
    t = tokens(mode)
    fig = go.Figure()
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=24, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, size=13, color=t["text_2"]),
        hoverlabel=dict(bgcolor=t["surface"], bordercolor=t["border"],
                        font=dict(family=FONT, color=t["text"])),
        showlegend=False,
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=t["grid"], tickfont=dict(color=t["text_2"]))
    fig.update_yaxes(gridcolor=t["grid"], zeroline=False, showline=False, tickfont=dict(color=t["text_2"]))
    return fig


def empty_figure(message: str, mode: str, height: int = 300) -> go.Figure:
    t = tokens(mode)
    fig = _base(mode, height)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.add_annotation(text=message, showarrow=False, x=0.5, y=0.5, xref="paper", yref="paper",
                       font=dict(size=14, color=t["muted"]), align="center")
    return fig


def horizontal_bars(labels: list[str], values: list[float], mode: str, *, unit: str,
                    height: int = 300) -> go.Figure:
    """One-hue horizontal bars, largest first, with the value at the end of each bar."""
    t = tokens(mode)
    fig = _base(mode, height)
    fig.add_bar(
        y=labels, x=values, orientation="h",
        marker=dict(color=t["accent"]),
        text=[f"{v:,.0f}" for v in values], textposition="outside", cliponaxis=False,
        textfont=dict(color=t["text"]),
        hovertemplate="%{y}: %{x:,.0f} " + unit + "<extra></extra>",
    )
    fig.update_layout(bargap=0.35)
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(visible=False, rangemode="tozero")
    return fig


def cause_bar(points: pd.DataFrame, mode: str) -> go.Figure:
    if points.empty:
        return empty_figure("No fires match the current filters", mode)
    counts = points["cause"].value_counts()
    return horizontal_bars(counts.index.tolist(), counts.tolist(), mode, unit="fires")


def centre_bar(points: pd.DataFrame, mode: str, centre_labels: dict[str, str]) -> go.Figure:
    if points.empty:
        return empty_figure("No fires match the current filters", mode)
    counts = points["centre"].map(lambda c: centre_labels.get(c) or (f"Fire centre {c}" if c else "Unknown")) \
        .value_counts()
    return horizontal_bars(counts.index.tolist(), counts.tolist(), mode, unit="fires")


def trend_line(history: pd.DataFrame, column: str, mode: str, *, height: int = 300) -> go.Figure:
    label = TREND_METRICS.get(column, column)
    if history.empty or column not in history:
        return empty_figure("History starts with the first daily pipeline run", mode, height)
    frame = history.dropna(subset=[column]).sort_values("date")
    if len(frame) < 2:
        return empty_figure(
            f"{len(frame)} day of history so far. A line appears once there are two or more days.",
            mode, height)
    t = tokens(mode)
    fig = _base(mode, height)
    fig.add_scatter(
        x=frame["date"], y=frame[column], mode="lines+markers", name=label,
        line=dict(color=t["accent"], width=2),
        marker=dict(size=8, color=t["accent"], line=dict(color=t["surface"], width=2)),
        hovertemplate="%{x|%b %d, %Y}<br>" + label + ": %{y:,.0f}<extra></extra>",
    )
    fig.update_layout(hovermode="x")
    fig.update_yaxes(rangemode="tozero")
    fig.update_xaxes(tickformat="%b %d")
    return fig


def emphasis_bars_by_year(indicators: pd.DataFrame, indicator_id: str, mode: str, *,
                          height: int = 280) -> go.Figure:
    """Bars per year with the latest year in the accent colour and earlier years in grey."""
    rows = indicators[(indicators["indicator_id"] == indicator_id)
                      & indicators["period"].astype(str).str.fullmatch(r"\d{4}")]
    if rows.empty:
        return empty_figure("No data in the curated indicators file", mode, height)
    rows = rows.assign(year=rows["period"].astype(int)).sort_values("year")
    t = tokens(mode)
    unit = str(rows["unit"].iloc[0])
    years = rows["year"].astype(str).tolist()
    values = rows["value"].tolist()
    colours = [t["context"]] * (len(values) - 1) + [t["accent"]]
    fig = _base(mode, height)
    fig.add_bar(
        x=years, y=values, marker=dict(color=colours),
        text=[f"{v:,.0f}" for v in values], textposition="outside", cliponaxis=False,
        textfont=dict(color=t["text"]),
        hovertemplate="%{x}: %{y:,.1f} " + unit + "<extra></extra>",
    )
    fig.update_layout(bargap=0.35)
    fig.update_yaxes(visible=False, rangemode="tozero")
    fig.update_xaxes(type="category")
    return fig
