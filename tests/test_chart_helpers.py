"""Pure-function shape tests for the ECharts helper builders.

These tests assert the structure of the option dicts returned by the
``_build_*_option`` private builders in ``dashboard/charts.py`` — the
high-level ``*_chart()`` wrappers just pipe these into ``st_echarts``,
so once the option dict is right the wrapper has nothing left to break.

The point of these tests is *contract*: pages call the helpers and
trust them to emit ECharts-shaped JSON. If the option dict drifts,
every chart in the dashboard breaks at the same time. CI catches it
without needing to spin up Streamlit.

No streamlit, no streamlit-echarts imports — runs in the lean
``[dev]`` install on the unit-tests CI job.
"""

from __future__ import annotations

import pytest

# pandas is part of the [dashboard] extra, not [dev]. The unit-tests CI
# job installs only [dev] and runs every test file in tests/ — so this
# file must skip cleanly when pandas isn't around. Mirrors the pattern
# in test_dashboard_today.py and test_dashboard_today_cards_reachable.py.
pd = pytest.importorskip("pandas")

from aml_framework.dashboard.chart_theme import (  # noqa: E402
    CATEGORICAL_PALETTE,
    DNA_INK,
    RAG_PALETTE,
    SEVERITY_PALETTE,
    echarts_theme,
    rag_color,
    severity_color,
)
from aml_framework.dashboard.charts import (  # noqa: E402
    _build_bar_option,
    _build_funnel_option,
    _build_gauge_option,
    _build_heatmap_option,
    _build_line_option,
    _build_pie_option,
    _build_radar_option,
    _build_sankey_option,
    _build_scatter_option,
    _build_timeline_option,
    _build_waterfall_option,
    _hex_with_alpha,
    _to_iso,
    _to_number,
)


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------


def test_echarts_theme_has_brand_palette():
    theme = echarts_theme()
    assert theme["color"] == list(CATEGORICAL_PALETTE)
    # Ink colour propagates into text style — keeps charts visually
    # consistent with the cream/ink dashboard chrome.
    assert theme["textStyle"]["color"] == DNA_INK
    # Animation must be on but short — chart load shouldn't feel like
    # a marketing site.
    assert theme["animation"] is True
    assert theme["animationDuration"] == 300


def test_severity_color_falls_back_to_muted():
    assert severity_color("critical") == SEVERITY_PALETTE["critical"]
    assert severity_color("nonsense") != SEVERITY_PALETTE["critical"]
    assert severity_color(None) != SEVERITY_PALETTE["critical"]


def test_rag_color_handles_breached_state():
    # SLA "breached" is its own colour, distinct from plain "red".
    assert rag_color("breached") == RAG_PALETTE["breached"]
    assert rag_color("red") == RAG_PALETTE["red"]
    assert rag_color("breached") != rag_color("red")


# ---------------------------------------------------------------------------
# Bar
# ---------------------------------------------------------------------------


def test_bar_option_single_series():
    df = pd.DataFrame({"period": ["Q1", "Q2", "Q3"], "alerts": [10, 20, 15]})
    opt = _build_bar_option(df, x="period", y="alerts")

    assert opt["xAxis"]["data"] == ["Q1", "Q2", "Q3"]
    assert opt["series"][0]["type"] == "bar"
    assert opt["series"][0]["data"] == [10.0, 20.0, 15.0]
    # Legend hidden for single-series — clutter that adds nothing.
    assert opt["legend"]["show"] is False


def test_bar_option_multi_series_groups_by_default():
    df = pd.DataFrame({"period": ["Q1", "Q2"], "alerts": [10, 20], "cases": [3, 7]})
    opt = _build_bar_option(df, x="period", y=["alerts", "cases"])

    assert len(opt["series"]) == 2
    assert opt["series"][0]["name"] == "alerts"
    assert opt["series"][1]["name"] == "cases"
    # No "stack" key when stacked=False
    assert "stack" not in opt["series"][0]
    assert opt["legend"]["show"] is True


def test_bar_option_stacked():
    df = pd.DataFrame({"period": ["Q1"], "a": [1], "b": [2]})
    opt = _build_bar_option(df, x="period", y=["a", "b"], stacked=True)
    assert opt["series"][0]["stack"] == "total"
    assert opt["series"][1]["stack"] == "total"


def test_bar_option_horizontal_swaps_axes():
    df = pd.DataFrame({"name": ["A", "B"], "value": [10, 20]})
    opt = _build_bar_option(df, x="name", y="value", orientation="h")
    # Horizontal: category axis is yAxis, value axis is xAxis.
    assert opt["yAxis"]["type"] == "category"
    assert opt["xAxis"]["type"] == "value"


def test_bar_option_per_bar_severity_color():
    df = pd.DataFrame(
        {"rule": ["R1", "R2", "R3"], "alerts": [5, 10, 15], "sev": ["high", "low", "critical"]}
    )
    opt = _build_bar_option(df, x="rule", y="alerts", color="sev")
    # Each bar carries its own itemStyle when a semantic colour column is given.
    bars = opt["series"][0]["data"]
    assert all(isinstance(b, dict) for b in bars)
    assert bars[0]["itemStyle"]["color"] == SEVERITY_PALETTE["high"]
    assert bars[2]["itemStyle"]["color"] == SEVERITY_PALETTE["critical"]


# ---------------------------------------------------------------------------
# Line / area
# ---------------------------------------------------------------------------


def test_line_option_smooth_default_on():
    df = pd.DataFrame({"t": ["a", "b"], "y": [1, 2]})
    opt = _build_line_option(df, x="t", y="y")
    assert opt["series"][0]["smooth"] is True
    # No areaStyle on a plain line chart.
    assert "areaStyle" not in opt["series"][0]


def test_line_option_area_adds_gradient_fill():
    df = pd.DataFrame({"t": ["a", "b"], "y": [1, 2]})
    opt = _build_line_option(df, x="t", y="y", area=True)
    area = opt["series"][0]["areaStyle"]
    # Gradient must start at higher alpha (top) and fade to near-zero (bottom).
    stops = area["color"]["colorStops"]
    assert stops[0]["offset"] == 0
    assert stops[-1]["offset"] == 1
    # Top stop is more opaque than bottom stop.
    assert "0.45" in stops[0]["color"]
    assert "0.05" in stops[-1]["color"]


def test_line_option_handles_nan_as_zero():
    df = pd.DataFrame({"t": ["a", "b"], "y": [1, float("nan")]})
    opt = _build_line_option(df, x="t", y="y")
    assert opt["series"][0]["data"] == [1.0, 0.0]


# ---------------------------------------------------------------------------
# Pie
# ---------------------------------------------------------------------------


def test_pie_option_donut_by_default():
    df = pd.DataFrame({"name": ["A", "B"], "v": [10, 20]})
    opt = _build_pie_option(df, names="name", values="v")
    # Donut = inner radius > 0
    assert opt["series"][0]["radius"] == ["40%", "70%"]


def test_pie_option_full_pie_when_donut_false():
    df = pd.DataFrame({"name": ["A"], "v": [1]})
    opt = _build_pie_option(df, names="name", values="v", donut=False)
    assert opt["series"][0]["radius"] == "70%"


# ---------------------------------------------------------------------------
# Scatter
# ---------------------------------------------------------------------------


def test_scatter_option_with_size_uses_jscode_sizer():
    df = pd.DataFrame({"x": [1, 2], "y": [3, 4], "n": [10, 100]})
    opt = _build_scatter_option(df, x="x", y="y", size="n")
    # symbolSize is a JS callback string when size column is given.
    assert isinstance(opt["series"][0]["symbolSize"], str)
    assert "Math.sqrt" in opt["series"][0]["symbolSize"]


def test_scatter_option_without_size_uses_constant():
    df = pd.DataFrame({"x": [1, 2], "y": [3, 4]})
    opt = _build_scatter_option(df, x="x", y="y")
    assert opt["series"][0]["symbolSize"] == 12


# ---------------------------------------------------------------------------
# Radar
# ---------------------------------------------------------------------------


def test_radar_option_two_series():
    indicators = [("Coverage", 100), ("Quality", 100), ("Efficiency", 100)]
    series = [("Current", [70, 80, 60]), ("Target", [90, 90, 90])]
    opt = _build_radar_option(indicators, series)

    assert len(opt["radar"]["indicator"]) == 3
    assert opt["radar"]["indicator"][0] == {"name": "Coverage", "max": 100}
    assert len(opt["series"][0]["data"]) == 2
    # Each series gets a distinct categorical palette colour.
    c0 = opt["series"][0]["data"][0]["lineStyle"]["color"]
    c1 = opt["series"][0]["data"][1]["lineStyle"]["color"]
    assert c0 != c1


# ---------------------------------------------------------------------------
# Heatmap
# ---------------------------------------------------------------------------


def test_heatmap_option_flattens_matrix():
    matrix = [[1, 2], [3, 4]]
    opt = _build_heatmap_option(matrix, x_labels=["X1", "X2"], y_labels=["Y1", "Y2"])
    # 4 cells flattened to [x_idx, y_idx, value] triples.
    assert len(opt["series"][0]["data"]) == 4
    assert opt["series"][0]["data"][0] == [0, 0, 1.0]
    assert opt["series"][0]["data"][3] == [1, 1, 4.0]
    # visualMap range matches matrix min/max.
    assert opt["visualMap"]["min"] == 1.0
    assert opt["visualMap"]["max"] == 4.0


# ---------------------------------------------------------------------------
# Sankey / funnel
# ---------------------------------------------------------------------------


def test_sankey_option_nodes_and_links():
    nodes = ["alerts", "cases", "STR"]
    edges = [("alerts", "cases", 100), ("cases", "STR", 30)]
    opt = _build_sankey_option(nodes, edges)
    assert [n["name"] for n in opt["series"][0]["data"]] == nodes
    assert opt["series"][0]["links"][0] == {"source": "alerts", "target": "cases", "value": 100.0}


def test_funnel_option_descending_sort():
    stages = [("alerts", 1000), ("cases", 200), ("STR", 30)]
    opt = _build_funnel_option(stages)
    assert opt["series"][0]["sort"] == "descending"
    assert len(opt["series"][0]["data"]) == 3


# ---------------------------------------------------------------------------
# Gauge
# ---------------------------------------------------------------------------


def test_gauge_option_default_bands():
    opt = _build_gauge_option(75, max_value=100, label="STR p95")
    series = opt["series"][0]
    assert series["min"] == 0
    assert series["max"] == 100
    # Three bands by default — red / amber / green segments.
    color_stops = series["axisLine"]["lineStyle"]["color"]
    assert len(color_stops) == 3


def test_gauge_option_custom_bands_normalises_to_max():
    bands = [(20, "#dc2626"), (60, "#d97706"), (100, "#16a34a")]
    opt = _build_gauge_option(50, bands=bands, max_value=100)
    color_stops = opt["series"][0]["axisLine"]["lineStyle"]["color"]
    # Thresholds are normalised to the [0, 1] scale ECharts expects.
    assert color_stops[0][0] == 0.2
    assert color_stops[2][0] == 1.0


# ---------------------------------------------------------------------------
# Timeline (Gantt)
# ---------------------------------------------------------------------------


def test_timeline_option_uses_custom_series():
    df = pd.DataFrame(
        {
            "task": ["A", "B"],
            "start": ["2026-01-01", "2026-02-01"],
            "finish": ["2026-01-15", "2026-02-20"],
        }
    )
    opt = _build_timeline_option(df, task="task", start="start", finish="finish")
    # Timeline must use a custom series with a renderItem JS function —
    # native bar series don't support time-axis Gantt rendering.
    assert opt["series"][0]["type"] == "custom"
    assert "renderItem" in opt["series"][0]
    assert opt["xAxis"]["type"] == "time"


# ---------------------------------------------------------------------------
# Waterfall
# ---------------------------------------------------------------------------


def test_waterfall_option_stacks_placeholder_and_value():
    opt = _build_waterfall_option(["a", "b", "c"], [10, -5, 3])
    series = opt["series"]
    assert len(series) == 2
    # Both series stack on the same axis — that's how the waterfall
    # "floats" each value off the running total.
    assert series[0]["stack"] == "total"
    assert series[1]["stack"] == "total"
    # First (placeholder) series renders transparent.
    assert series[0]["itemStyle"]["color"] == "transparent"


def test_waterfall_negative_bars_use_neg_color():
    opt = _build_waterfall_option(["a", "b"], [10, -5], pos_color="#0f0", neg_color="#f00")
    values = opt["series"][1]["data"]
    assert values[0]["itemStyle"]["color"] == "#0f0"
    assert values[1]["itemStyle"]["color"] == "#f00"
    # Negative delta is rendered as positive bar height (ECharts stacks
    # both as positive; the placeholder underneath does the lifting).
    assert values[1]["value"] == 5.0


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        (1, 1.0),
        (1.5, 1.5),
        ("3", 3.0),
        (None, 0.0),
        ("not a number", 0.0),
        (float("nan"), 0.0),
    ],
)
def test_to_number_coerces_safely(raw, expected):
    assert _to_number(raw) == expected


def test_to_iso_handles_datetime_and_string():
    import datetime as dt

    assert _to_iso(dt.date(2026, 5, 2)) == "2026-05-02"
    assert _to_iso("2026-05-02") == "2026-05-02"
    assert _to_iso(None) == ""


def test_hex_with_alpha_returns_rgba():
    assert _hex_with_alpha("#a44b30", 0.5) == "rgba(164, 75, 48, 0.5)"


def test_hex_with_alpha_passes_through_invalid():
    # Bad input shouldn't throw — return the original so the chart
    # still renders with the unparsed colour string.
    assert _hex_with_alpha("not-a-hex", 0.5) == "not-a-hex"
