import json

import pandas as pd
import pytest

from core.frames import evac_frame, points_frame
from core.theme import DARK, LIGHT, contrast_ratio, css, tokens
from dashboards.wildfire import charts, filters, kpis, mapview
from dashboards.wildfire.data import load_indicators
from helpers import FIXTURES


def fc(name):
    return json.loads((FIXTURES / "live" / f"{name}.geojson").read_text(encoding="utf-8"))


@pytest.fixture
def points():
    return points_frame(fc("bc_fire_points"))


@pytest.fixture
def evac():
    return evac_frame(fc("bc_evac_orders"))


# --------------------------------------------------------------- filters

def test_default_filters_hide_fires_that_are_out(points):
    shown = filters.apply_fire_filters(points, filters.FireFilters())
    assert (shown["status"] != "Out").all()
    assert len(shown) == int(points["is_active"].sum())
    with_out = filters.apply_fire_filters(points, filters.FireFilters(include_out=True))
    assert len(with_out) == len(points)


def test_filters_combine(points):
    f = filters.FireFilters(statuses=("Out of Control",), causes=("Lightning", "Person"), min_size_ha=100)
    shown = filters.apply_fire_filters(points, f)
    assert (shown["status"] == "Out of Control").all()
    assert shown["cause"].isin(["Lightning", "Person"]).all()
    assert (shown["size_ha"] >= 100).all()

    one = points["centre"].iloc[0]
    only = filters.apply_fire_filters(points, filters.FireFilters(centres=(one,), include_out=True))
    assert (only["centre"] == one).all() and not only.empty


def test_filtering_to_nothing_is_fine(points):
    shown = filters.apply_fire_filters(points, filters.FireFilters(min_size_ha=10**9))
    assert shown.empty and list(shown.columns) == list(points.columns)


def test_centre_labels_fall_back_to_the_code(points):
    assert filters.centre_label("3", {}) == "Fire centre 3"
    assert filters.centre_label("3", {"3": "Kamloops"}) == "Kamloops"
    assert filters.centre_label("", {}) == "Unknown"
    choices = filters.centre_choices(points, {"1": "Zed"})
    assert choices["1"] == "Zed" and all(v for v in choices.values())


# ------------------------------------------------------------------ KPIs

def test_kpis_match_the_data(points, evac):
    by_key = {k.key: k for k in kpis.compute_kpis(points, evac, 25)}
    assert by_key["active"].value == f"{int(points['is_active'].sum()):,}"
    assert by_key["ooc"].value == str(int((points["status"] == "Out of Control").sum()))
    assert by_key["orders"].value == "2"                 # wildfire orders only
    assert "2 alerts" in by_key["orders"].sub
    assert "165 homes" in by_key["orders"].sub           # 120 + 45
    assert by_key["hotspots"].value == "25"
    assert by_key["hectares"].value.endswith(" ha")


def test_kpis_with_no_data_say_so_instead_of_showing_zeros(points, evac):
    empty_points, empty_evac = points.iloc[0:0], evac.iloc[0:0]
    tiles = kpis.compute_kpis(empty_points, empty_evac, None)
    assert [t.value for t in tiles] == [kpis.DASH] * 5
    assert all(t.sub == "No data yet" for t in tiles)


def test_number_formats():
    assert kpis.fmt_int(1234567) == "1,234,567" and kpis.fmt_int(None) == kpis.DASH
    assert kpis.fmt_hectares(2_840_545) == "2.84 M ha"
    assert kpis.fmt_hectares(886_300) == "886,300 ha"
    assert kpis.fmt_hectares(float("nan")) == kpis.DASH


def test_equity_tiles_come_from_the_curated_file():
    tiles = {t.key: t for t in kpis.equity_tiles(load_indicators())}
    assert tiles["isc_fn_evacuees_bc"].value == "11,848"
    assert tiles["statcan_indigenous_evac_share_2023"].value == "42%"
    assert tiles["firesmart_funding_dispersed"].value == "$71 M"
    assert "Indigenous Services Canada" in tiles["isc_fn_evacuees_bc"].sub


# ---------------------------------------------------------------- charts

def test_cause_bar_is_sorted_and_labelled(points):
    fig = charts.cause_bar(points, "light")
    bar = fig.data[0]
    assert list(bar.x) == sorted(bar.x, reverse=True)
    assert sum(bar.x) == len(points)
    assert bar.marker.color == LIGHT["accent"]           # one hue, magnitude
    assert fig.layout.showlegend is False and fig.layout.yaxis.autorange == "reversed"


def test_charts_show_a_message_when_there_is_nothing_to_draw(points):
    fig = charts.cause_bar(points.iloc[0:0], "light")
    assert len(fig.data) == 0 and "No fires match" in fig.layout.annotations[0].text
    assert charts.centre_bar(points.iloc[0:0], "dark", {}).layout.annotations


def test_centre_bar_uses_names_when_known(points):
    code = points["centre"].iloc[0]
    fig = charts.centre_bar(points, "light", {code: "Named Centre"})
    assert "Named Centre" in list(fig.data[0].y)


def test_trend_line_needs_two_days():
    import pandas as pd
    from pipeline.history import COLUMNS
    one = pd.DataFrame([{**{c: 1 for c in COLUMNS}, "date": pd.Timestamp("2026-09-01")}])
    fig = charts.trend_line(one, "fires_active", "light")
    assert len(fig.data) == 0 and "1 day of history" in fig.layout.annotations[0].text
    assert "first daily pipeline run" in charts.trend_line(one.iloc[0:0], "fires_active", "light").layout.annotations[0].text

    two = pd.concat([one, one.assign(date=pd.Timestamp("2026-09-02"), fires_active=5)], ignore_index=True)
    line = charts.trend_line(two, "fires_active", "light").data[0]
    assert line.line.width == 2 and line.marker.size >= 8 and list(line.y) == [1, 5]
    # A day where the source failed (NaN) is a gap, not a zero.
    gappy = two.assign(fires_active=[1.0, float("nan")])
    assert len(charts.trend_line(gappy, "fires_active", "light").data) == 0


def test_emphasis_bars_highlight_only_the_latest_year():
    fig = charts.emphasis_bars_by_year(load_indicators(), "cultural_fire_hectares", "light")
    bar = fig.data[0]
    assert list(bar.x) == ["2022", "2023", "2024", "2025"]
    assert list(bar.marker.color) == [LIGHT["context"]] * 3 + [LIGHT["accent"]]
    assert list(bar.y) == [1647, 2214.4, 3412.8, 6351]
    assert charts.emphasis_bars_by_year(load_indicators(), "no_such_id", "light").layout.annotations


def test_dark_charts_use_dark_tokens(points):
    fig = charts.cause_bar(points, "dark")
    assert fig.data[0].marker.color == DARK["accent"]
    assert fig.layout.font.color == DARK["text_2"]


# --------------------------------------------------------------- map

def layers_named(fmap, name):
    return [layer for layer in fmap.layers if getattr(layer, "name", "") == name]


def build(points, mode="light", layers=None, **kw):
    return mapview.build_map(
        points=points, perimeters_fc=fc("bc_fire_perimeters"), evac_fc=fc("bc_evac_orders"),
        hotspots_fc=fc("cwfis_hotspots"),
        layers=set(layers if layers is not None else mapview.LAYER_CHOICES), mode=mode, **kw)


def test_map_has_the_requested_layers_only(points):
    shown = filters.apply_fire_filters(points, filters.FireFilters())
    full = build(shown)
    assert layers_named(full, "Fire perimeters") and layers_named(full, "Evacuation orders and alerts")
    assert layers_named(full, "Satellite hotspots (24 h)") and layers_named(full, "Out-of-control fires")
    bare = build(shown, layers=[])
    assert len(bare.layers) == 1                                    # just the base map
    assert len(build(shown, layers=["hotspots"]).layers) == 2


def test_map_only_draws_wildfire_orders_in_effect(points):
    shown = mapview.wildfire_evac_features(fc("bc_evac_orders"))
    assert len(shown["features"]) == 4                              # no landslide, no All Clear


def test_evac_styles_differ_by_line_not_just_colour():
    order = mapview.evac_style({"properties": {"ORDER_ALERT_STATUS": "Order"}}, "light")
    alert = mapview.evac_style({"properties": {"ORDER_ALERT_STATUS": "Alert"}}, "light")
    assert order["color"] == LIGHT["critical"] and "dashArray" not in order
    assert alert["color"] == LIGHT["warning"] and alert["dashArray"]


def test_map_theme_follows_mode(points):
    assert "light_all" in build(points, "light").layers[0].url
    assert "dark_all" in build(points, "dark").layers[0].url


def test_fire_markers_report_clicks(points):
    shown = filters.apply_fire_filters(points, filters.FireFilters())
    clicked = []
    fmap = build(shown, layers=["fires"], on_select=clicked.append)
    marker_layers = layers_named(fmap, "Out-of-control fires") + layers_named(fmap, "Other fires")
    assert marker_layers
    feature = marker_layers[0].data["features"][0]
    marker_layers[0]._click_callbacks(feature=feature, event="click")
    assert clicked == [feature["properties"]["fire_number"]]
    marker_layers[0]._click_callbacks(feature=None)                 # a click with no feature is ignored
    assert len(clicked) == 1


def test_every_fire_is_drawn_exactly_once(points):
    shown = filters.apply_fire_filters(points, filters.FireFilters(include_out=True))
    fmap = build(shown, layers=["fires"])
    drawn = [f["properties"]["fire_number"] for layer in fmap.layers[1:] for f in layer.data["features"]]
    assert sorted(drawn) == sorted(shown["fire_number"])


def test_out_of_control_fires_are_drawn_last_in_the_accent_colour(points):
    shown = filters.apply_fire_filters(points, filters.FireFilters())
    fmap = build(shown, layers=["fires"])
    names = [layer.name for layer in fmap.layers[1:]]
    assert names.index("Out-of-control fires") > max(i for i, n in enumerate(names) if n == "Other fires")
    ooc = layers_named(fmap, "Out-of-control fires")[0]
    assert ooc.point_style["fillColor"] == LIGHT["orange"]


def test_perimeters_follow_the_filtered_fires(points):
    all_perims = fc("bc_fire_perimeters")
    number = all_perims["features"][0]["properties"]["FIRE_NUMBER"]
    kept = mapview.filter_perimeters(all_perims, {number})
    assert [f["properties"]["FIRE_NUMBER"] for f in kept["features"]] == [number]
    assert mapview.filter_perimeters(all_perims, set())["features"] == []


def test_marker_radius_grows_with_size():
    r = mapview.radius_for
    assert r(0.01) == 3 and r(5) == 5 and r(500) == 8 and r(5000) == 11 and r(50000) == 14
    assert r(None) == 3 and r(float("nan")) == 3


def test_only_https_links_are_used():
    assert mapview.safe_https_url("https://x.example/a") == "https://x.example/a"
    assert mapview.safe_https_url("javascript:alert(1)") is None
    assert mapview.safe_https_url("http://insecure") is None
    assert mapview.safe_https_url("") is None


def test_fire_detail_items_handle_unknowns(points):
    row = points.iloc[0].copy()
    row["size_ha"] = float("nan")
    row["ignition_date"] = pd.NaT
    items = dict(mapview.fire_detail_items(row))
    assert items["Size"] == "unknown" and items["Ignited"] == "unknown"


def test_evac_table_lists_only_wildfire_orders_and_alerts(evac):
    table = mapview.evac_summary(fc("bc_evac_orders"))
    assert len(table) == 4 and set(table["status"]) == {"Order", "Alert"}


# ----------------------------------------------------------------- theme

@pytest.mark.parametrize("mode", ["light", "dark"])
def test_text_colours_are_readable(mode):
    t = tokens(mode)
    for name in ("text", "text_2", "muted"):
        for background in ("surface", "page"):
            assert contrast_ratio(t[name], t[background]) >= 4.5, f"{mode}: {name} on {background}"
    for name in ("accent", "orange", "violet"):
        assert contrast_ratio(t[name], t["surface"]) >= 3.0, f"{mode}: mark colour {name}"


def test_css_defines_every_token_for_both_modes():
    text = css()
    for key in LIGHT:
        assert f"--wd-{key.replace('_', '-')}:" in text
    assert LIGHT.keys() == DARK.keys()
    assert '[data-bs-theme="dark"]' in text and "prefers-color-scheme: dark" in text


def test_contrast_ratio_reference_values():
    assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0)
    assert contrast_ratio("#777777", "#777777") == pytest.approx(1.0)
