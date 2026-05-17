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
    DNA_CHART_ACCENT,
    DNA_CHART_LABEL,
    DNA_CHART_RULE,
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
    # Chart text uses the dual-contrast-safe label token (not the
    # cream-tuned DNA_INK) so it reads on a light OR dark page card.
    assert theme["textStyle"]["color"] == DNA_CHART_LABEL
    # Canvas is transparent so the CSS-themed card shows through —
    # this is what makes the chart theme-neutral (no dark detection).
    assert theme["backgroundColor"] == "transparent"
    # Animation must be on but short — chart load shouldn't feel like
    # a marketing site.
    assert theme["animation"] is True
    assert theme["animationDuration"] == 300


# WCAG 2.x relative luminance + contrast — same maths as the e2e
# dark-mode test, so the unit guard and the browser guard agree.
def _rel_lum(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    chans = []
    for i in (0, 2, 4):
        c = int(h[i : i + 2], 16) / 255.0
        chans.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = chans
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    la, lb = _rel_lum(a), _rel_lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# The two real chart-container surfaces: the cream card in light mode
# and the raised dark card (#212832) in OS-dark mode (from the
# `@media (prefers-color-scheme: dark)` block in components.py). A
# theme-neutral chart must clear WCAG 1.4.11 non-text 3:1 on BOTH.
_LIGHT_SURFACE = "#f7f4ec"
_DARK_SURFACE = "#212832"


def test_chart_chrome_is_dual_contrast_safe():
    """The NEUTRAL chrome — every CATEGORICAL_PALETTE series colour, the
    label/accent tokens, AND the heatmap default ramp endpoints — must
    clear WCAG 1.4.11 non-text 3:1 against BOTH the light cream card and
    the dark (#212832) card. That is what lets the charts be
    theme-neutral (no dark detection, no determinism-breaking reload —
    Codex PR-2).

    SCOPE: the semantic SEVERITY_PALETTE / RAG_PALETTE are deliberately
    excluded — they encode a regulator-standard meaning by convention
    (a breach must read red) and are shared with the DOM badges; their
    dark legibility is a separate tracked follow-up (see chart_theme.py).
    """
    # Heatmap default ramp endpoints are chrome too — the old
    # cream→rust default was invisible on the cream card.
    heatmap_default = _build_heatmap_option(
        [[1, 2], [3, 4]], x_labels=["a", "b"], y_labels=["c", "d"]
    )["visualMap"]["inRange"]["color"]
    swatches = (
        list(CATEGORICAL_PALETTE) + [DNA_CHART_LABEL, DNA_CHART_ACCENT] + list(heatmap_default)
    )
    for color in swatches:
        on_light = _contrast(color, _LIGHT_SURFACE)
        on_dark = _contrast(color, _DARK_SURFACE)
        assert on_light >= 3.0, f"{color} only {on_light:.2f}:1 on the light card (<3:1)"
        assert on_dark >= 3.0, f"{color} only {on_dark:.2f}:1 on the dark card (<3:1)"
    # The rule token is a translucent grey by design (blends with
    # whatever surface shows through) — assert it stays translucent,
    # never an opaque light-only hairline.
    assert DNA_CHART_RULE.startswith("rgba("), DNA_CHART_RULE
    assert echarts_theme()["backgroundColor"] == "transparent"


def test_tooltip_box_is_self_contained_and_legible():
    """The tooltip is the one opaque element (ECharts paints its own
    box). Its text must clear 4.5:1 and its border the 3:1 non-text bar
    against the box bg, so it reads on either page theme without any
    dark detection (Codex PR-2 re-review flagged the old #646a73
    border at 2.5:1)."""
    tip = echarts_theme()["tooltip"]
    bg = tip["backgroundColor"]
    text_ratio = _contrast(tip["textStyle"]["color"], bg)
    border_ratio = _contrast(tip["borderColor"], bg)
    assert text_ratio >= 4.5, f"tooltip text only {text_ratio:.2f}:1 on the box (<4.5:1)"
    assert border_ratio >= 3.0, f"tooltip border only {border_ratio:.2f}:1 on the box (<3:1)"


def test_render_is_theme_neutral_no_dark_detection():
    """Source + signature guard: `_render` must call `echarts_theme()`
    with NO `dark=` argument and must NOT do server-side scheme
    detection (no scheme bridge import, no `current_color_scheme`, no
    `st.context`). Detecting dark either desyncs from the CSS theme or
    forces a page reload that re-runs the AML engine with a new
    `as_of` — a determinism regression in a compliance tool (Codex
    PR-2)."""
    import inspect

    from aml_framework.dashboard import charts as charts_mod
    from aml_framework.dashboard import chart_theme as theme_mod

    # echarts_theme is parameterless now — a re-added dark flag is the
    # exact regression Codex blocked.
    assert list(inspect.signature(theme_mod.echarts_theme).parameters) == [], (
        "echarts_theme() must take no parameters — no dark flag"
    )

    src = inspect.getsource(charts_mod._render)
    assert "echarts_theme()" in src, "_render must call the parameterless echarts_theme()"
    assert "echarts_theme(dark" not in src, "_render must not pass a dark flag"
    code_only = "\n".join(line.split("#", 1)[0] for line in src.splitlines())
    for forbidden in ("current_color_scheme", "scheme import", "st.context"):
        assert forbidden not in code_only, (
            f"_render must not do server-side scheme detection (found {forbidden!r})"
        )


def test_option_builders_emit_dual_safe_chrome_not_light_only():
    """BLOCKER[3] regression: the per-chart builders used to bake the
    cream-only DNA_INK_MUTED (#5a5e69) / DNA_RULE (#e6e1d3) straight
    into options, which overrode the theme and were invisible on a
    dark card. They must now emit the dual-contrast-safe tokens."""
    import json

    radar = _build_radar_option([("Coverage", 100), ("Quality", 100)], [("Now", [70, 80])])
    assert radar["radar"]["axisName"]["color"] == DNA_CHART_LABEL
    assert radar["radar"]["splitLine"]["lineStyle"]["color"] == DNA_CHART_RULE

    heatmap = _build_heatmap_option([[1, 2], [3, 4]], x_labels=["X1", "X2"], y_labels=["Y1", "Y2"])
    assert heatmap["visualMap"]["textStyle"]["color"] == DNA_CHART_LABEL

    sankey = _build_sankey_option(["a", "b"], [("a", "b", 5)])
    assert sankey["series"][0]["label"]["color"] == DNA_CHART_LABEL

    gauge = _build_gauge_option(75, max_value=100, label="p95")
    assert gauge["series"][0]["axisLabel"]["color"] == DNA_CHART_LABEL
    assert gauge["series"][0]["title"]["color"] == DNA_CHART_LABEL

    # No light-only literal may survive anywhere in any of these.
    blob = json.dumps([radar, heatmap, sankey, gauge])
    assert "#5a5e69" not in blob, "cream-only DNA_INK_MUTED leaked into a chart option"
    assert "#e6e1d3" not in blob, "cream-only DNA_RULE leaked into a chart option"


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
