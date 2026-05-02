"""ECharts-backed chart helpers — replaces ad-hoc plotly calls.

A curated chart vocabulary covering every chart type the dashboard
currently produces with Plotly: bar, line, area, pie, scatter, radar,
heatmap, sankey, funnel, gauge, timeline, waterfall — plus an
``echarts_chart()`` escape hatch for one-offs that don't fit.

Each helper splits in two:

* ``_build_<type>_option(df, ...) -> dict`` — pure-function builder
  that takes a DataFrame and returns the ECharts JSON option dict.
  No streamlit, no echarts imports. Unit-testable in the lean
  ``[dev]`` install.
* ``<type>_chart(df, ...) -> None`` — thin wrapper that calls the
  builder and pipes the result into ``streamlit-echarts``.
  Lazy-imports ``streamlit`` and ``streamlit_echarts`` so the
  ``[dev]`` install can import this module.

Pages call the high-level functions (``bar_chart(df, x="period",
y="alerts")``); they never touch ECharts JSON directly. The escape
hatch ``echarts_chart(option)`` exists for the rare case the
curated vocabulary doesn't cover (e.g. a custom dual-axis combo).
"""

from __future__ import annotations

from typing import Any

from aml_framework.dashboard.chart_theme import (
    CATEGORICAL_PALETTE,
    DNA_ACCENT,
    DNA_INK_MUTED,
    DNA_RULE,
    echarts_theme,
    rag_color,
    severity_color,
)

# Default heights mirror the Plotly defaults that pages currently pass
# (chart_layout(fig, 320) etc.) so visual scale doesn't shift in the
# migration.
DEFAULT_HEIGHT = 320


def _series_color(label: str | None, palette_index: int) -> str:
    """Pick a colour for a series.

    If the label looks like a severity or RAG band, use that semantic
    colour; otherwise rotate the categorical palette by index. Lets a
    column called ``severity`` produce red/amber/green bars without
    the page having to wire colours per call.
    """
    if isinstance(label, str):
        label_lower = label.lower()
        if label_lower in ("critical", "high", "medium", "low"):
            return severity_color(label)
        if label_lower in ("green", "amber", "red", "breached", "unset"):
            return rag_color(label)
    return CATEGORICAL_PALETTE[palette_index % len(CATEGORICAL_PALETTE)]


# ---------------------------------------------------------------------------
# Bar chart — vertical / horizontal / stacked / grouped
# ---------------------------------------------------------------------------


def _build_bar_option(
    df: Any,
    *,
    x: str,
    y: str | list[str],
    color: str | None = None,
    orientation: str = "v",
    stacked: bool = False,
    title: str | None = None,
) -> dict:
    """Build an ECharts bar-chart option dict.

    Args:
        df: pandas DataFrame.
        x: column name for the category axis.
        y: column name (single series) or list of column names
            (multi-series — one bar group per category).
        color: optional column whose values map to severity / RAG
            colours (overrides the categorical palette).
        orientation: ``"v"`` (vertical, default) or ``"h"`` (horizontal).
        stacked: stack multi-series bars instead of grouping.
        title: optional chart title.

    Returns:
        ECharts option dict — pure data, no streamlit calls.
    """
    categories = [str(v) for v in df[x].tolist()]
    y_cols = y if isinstance(y, list) else [y]

    series = []
    for idx, col in enumerate(y_cols):
        values = [_to_number(v) for v in df[col].tolist()]
        item_color: Any
        if color and color in df.columns:
            # per-bar colour from a semantic column (e.g. severity)
            item_color = [
                {"value": v, "itemStyle": {"color": _series_color(c, idx)}}
                for v, c in zip(values, df[color].tolist(), strict=False)
            ]
            data = item_color
        else:
            data = values
        series.append(
            {
                "name": col,
                "type": "bar",
                "data": data,
                "itemStyle": {"color": _series_color(col, idx), "borderRadius": [3, 3, 0, 0]},
                **({"stack": "total"} if stacked else {}),
            }
        )

    cat_axis = {"type": "category", "data": categories}
    val_axis = {"type": "value"}

    option: dict[str, Any] = {
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "legend": {"data": y_cols, "show": len(y_cols) > 1},
        "xAxis": cat_axis if orientation == "v" else val_axis,
        "yAxis": val_axis if orientation == "v" else cat_axis,
        "series": series,
    }
    if title:
        option["title"] = {"text": title}
    return option


def bar_chart(
    df: Any,
    *,
    x: str,
    y: str | list[str],
    color: str | None = None,
    orientation: str = "v",
    stacked: bool = False,
    title: str | None = None,
    height: int = DEFAULT_HEIGHT,
    key: str | None = None,
) -> None:
    """Render a bar chart. See ``_build_bar_option`` for arguments."""
    option = _build_bar_option(
        df, x=x, y=y, color=color, orientation=orientation, stacked=stacked, title=title
    )
    _render(option, height=height, key=key)


# ---------------------------------------------------------------------------
# Line chart — single or multi-series, optional smooth / markers / area fill
# ---------------------------------------------------------------------------


def _build_line_option(
    df: Any,
    *,
    x: str,
    y: str | list[str],
    smooth: bool = True,
    area: bool = False,
    markers: bool = True,
    title: str | None = None,
) -> dict:
    """Build an ECharts line-chart option dict.

    ``area=True`` switches to a filled area chart with a gradient. Pass
    a list of columns for multi-series.
    """
    categories = [str(v) for v in df[x].tolist()]
    y_cols = y if isinstance(y, list) else [y]

    series = []
    for idx, col in enumerate(y_cols):
        values = [_to_number(v) for v in df[col].tolist()]
        color = _series_color(col, idx)
        s: dict[str, Any] = {
            "name": col,
            "type": "line",
            "data": values,
            "smooth": smooth,
            "showSymbol": markers,
            "symbol": "circle",
            "symbolSize": 6,
            "lineStyle": {"width": 2.5, "color": color},
            "itemStyle": {"color": color},
        }
        if area:
            s["areaStyle"] = {
                "color": {
                    "type": "linear",
                    "x": 0,
                    "y": 0,
                    "x2": 0,
                    "y2": 1,
                    "colorStops": [
                        {"offset": 0, "color": _hex_with_alpha(color, 0.45)},
                        {"offset": 1, "color": _hex_with_alpha(color, 0.05)},
                    ],
                }
            }
        series.append(s)

    option: dict[str, Any] = {
        "tooltip": {"trigger": "axis"},
        "legend": {"data": y_cols, "show": len(y_cols) > 1},
        "xAxis": {"type": "category", "data": categories, "boundaryGap": False},
        "yAxis": {"type": "value"},
        "series": series,
    }
    if title:
        option["title"] = {"text": title}
    return option


def line_chart(
    df: Any,
    *,
    x: str,
    y: str | list[str],
    smooth: bool = True,
    area: bool = False,
    markers: bool = True,
    title: str | None = None,
    height: int = DEFAULT_HEIGHT,
    key: str | None = None,
) -> None:
    """Render a line chart (or area chart if ``area=True``)."""
    option = _build_line_option(
        df, x=x, y=y, smooth=smooth, area=area, markers=markers, title=title
    )
    _render(option, height=height, key=key)


def area_chart(
    df: Any,
    *,
    x: str,
    y: str | list[str],
    smooth: bool = True,
    title: str | None = None,
    height: int = DEFAULT_HEIGHT,
    key: str | None = None,
) -> None:
    """Render a filled area chart — convenience for ``line_chart(..., area=True)``."""
    line_chart(df, x=x, y=y, smooth=smooth, area=True, title=title, height=height, key=key)


# ---------------------------------------------------------------------------
# Pie / donut chart
# ---------------------------------------------------------------------------


def _build_pie_option(
    df: Any,
    *,
    names: str,
    values: str,
    donut: bool = True,
    title: str | None = None,
) -> dict:
    """Build an ECharts pie-chart option dict.

    Default is donut (``donut=True``) — empty centre reads as more
    "modern dashboard" than full pie. Set ``donut=False`` for a
    classic pie.
    """
    data = [
        {
            "name": str(n),
            "value": _to_number(v),
            "itemStyle": {"color": _series_color(str(n), idx)},
        }
        for idx, (n, v) in enumerate(zip(df[names].tolist(), df[values].tolist(), strict=False))
    ]
    option: dict[str, Any] = {
        "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
        "legend": {"orient": "vertical", "left": "left", "show": True},
        "series": [
            {
                "name": values,
                "type": "pie",
                "radius": ["40%", "70%"] if donut else "70%",
                "center": ["55%", "50%"],
                "data": data,
                "label": {"show": True, "formatter": "{b}\n{d}%"},
                "labelLine": {"show": True},
            }
        ],
    }
    if title:
        option["title"] = {"text": title, "left": "center"}
    return option


def pie_chart(
    df: Any,
    *,
    names: str,
    values: str,
    donut: bool = True,
    title: str | None = None,
    height: int = DEFAULT_HEIGHT,
    key: str | None = None,
) -> None:
    """Render a pie or donut chart."""
    option = _build_pie_option(df, names=names, values=values, donut=donut, title=title)
    _render(option, height=height, key=key)


# ---------------------------------------------------------------------------
# Scatter / bubble chart
# ---------------------------------------------------------------------------


def _build_scatter_option(
    df: Any,
    *,
    x: str,
    y: str,
    size: str | None = None,
    color: str | None = None,
    label: str | None = None,
    title: str | None = None,
) -> dict:
    """Build an ECharts scatter-chart option dict.

    ``size``: optional column for bubble radius. ``color``: optional
    semantic column (severity / RAG / category). ``label``: optional
    column to show as text annotation per point.
    """
    points = []
    for idx in range(len(df)):
        row = df.iloc[idx]
        x_val = _to_number(row[x])
        y_val = _to_number(row[y])
        size_val = _to_number(row[size]) if size else 12
        color_val = row[color] if color else None
        label_val = str(row[label]) if label else None
        points.append(
            {
                "value": [x_val, y_val, size_val, label_val],
                "itemStyle": {"color": _series_color(color_val, idx) if color_val else DNA_ACCENT},
            }
        )

    option: dict[str, Any] = {
        "tooltip": {
            "trigger": "item",
            "formatter": (
                f"{{c[3]}}<br/>{x}: {{c[0]}}<br/>{y}: {{c[1]}}"
                if label
                else f"{x}: {{c[0]}}<br/>{y}: {{c[1]}}"
            ),
        },
        "xAxis": {"type": "value", "name": x},
        "yAxis": {"type": "value", "name": y},
        "series": [
            {
                "type": "scatter",
                "data": points,
                "symbolSize": (
                    "function (val) { return Math.max(8, Math.sqrt(val[2]) * 4); }" if size else 12
                ),
            }
        ],
    }
    if title:
        option["title"] = {"text": title}
    return option


def scatter_chart(
    df: Any,
    *,
    x: str,
    y: str,
    size: str | None = None,
    color: str | None = None,
    label: str | None = None,
    title: str | None = None,
    height: int = DEFAULT_HEIGHT,
    key: str | None = None,
) -> None:
    """Render a scatter or bubble chart."""
    option = _build_scatter_option(df, x=x, y=y, size=size, color=color, label=label, title=title)
    _render(option, height=height, key=key)


# ---------------------------------------------------------------------------
# Radar chart — multi-series polar (program maturity, executive scorecard)
# ---------------------------------------------------------------------------


def _build_radar_option(
    indicators: list[tuple[str, float]],
    series: list[tuple[str, list[float]]],
    *,
    title: str | None = None,
) -> dict:
    """Build an ECharts radar-chart option dict.

    Args:
        indicators: list of ``(name, max_value)`` tuples — one per axis.
        series: list of ``(series_name, values)`` tuples; ``values``
            length must match ``indicators``.
    """
    option: dict[str, Any] = {
        "tooltip": {"trigger": "item"},
        "legend": {"data": [name for name, _ in series], "bottom": 0},
        "radar": {
            "indicator": [{"name": name, "max": max_val} for name, max_val in indicators],
            "splitArea": {"show": False},
            "axisName": {"color": DNA_INK_MUTED, "fontSize": 11},
            "splitLine": {"lineStyle": {"color": DNA_RULE}},
        },
        "series": [
            {
                "type": "radar",
                "data": [
                    {
                        "name": name,
                        "value": values,
                        "lineStyle": {
                            "color": _series_color(name, idx),
                            "width": 2,
                        },
                        "areaStyle": {"color": _hex_with_alpha(_series_color(name, idx), 0.18)},
                        "itemStyle": {"color": _series_color(name, idx)},
                    }
                    for idx, (name, values) in enumerate(series)
                ],
            }
        ],
    }
    if title:
        option["title"] = {"text": title}
    return option


def radar_chart(
    indicators: list[tuple[str, float]],
    series: list[tuple[str, list[float]]],
    *,
    title: str | None = None,
    height: int = 480,  # radars need more headroom than bars
    key: str | None = None,
) -> None:
    """Render a radar (spider) chart."""
    option = _build_radar_option(indicators, series, title=title)
    _render(option, height=height, key=key)


# ---------------------------------------------------------------------------
# Heatmap — matrix (rule × period etc.)
# ---------------------------------------------------------------------------


def _build_heatmap_option(
    matrix: list[list[float]],
    *,
    x_labels: list[str],
    y_labels: list[str],
    title: str | None = None,
    color_scale: tuple[str, str] = ("#fef3e8", "#a44b30"),  # cream → burnt orange
) -> dict:
    """Build an ECharts heatmap option dict.

    ``matrix`` is a 2D list indexed ``matrix[y][x]``.
    """
    flat: list[list[float]] = []
    flat_min = float("inf")
    flat_max = float("-inf")
    for y_idx, row in enumerate(matrix):
        for x_idx, val in enumerate(row):
            n = _to_number(val)
            flat.append([x_idx, y_idx, n])
            if n < flat_min:
                flat_min = n
            if n > flat_max:
                flat_max = n

    if flat_min == float("inf"):
        flat_min, flat_max = 0, 1

    option: dict[str, Any] = {
        "tooltip": {"position": "top"},
        "xAxis": {"type": "category", "data": x_labels, "splitArea": {"show": True}},
        "yAxis": {"type": "category", "data": y_labels, "splitArea": {"show": True}},
        "visualMap": {
            "min": flat_min,
            "max": flat_max,
            "calculable": True,
            "orient": "horizontal",
            "left": "center",
            "bottom": 0,
            "inRange": {"color": list(color_scale)},
            "textStyle": {"color": DNA_INK_MUTED},
        },
        "series": [
            {
                "type": "heatmap",
                "data": flat,
                "label": {"show": False},
                "emphasis": {"itemStyle": {"shadowBlur": 8, "shadowColor": "rgba(0,0,0,0.3)"}},
            }
        ],
    }
    if title:
        option["title"] = {"text": title}
    return option


def heatmap_chart(
    matrix: list[list[float]],
    *,
    x_labels: list[str],
    y_labels: list[str],
    title: str | None = None,
    color_scale: tuple[str, str] = ("#fef3e8", "#a44b30"),
    height: int = DEFAULT_HEIGHT,
    key: str | None = None,
) -> None:
    """Render a heatmap."""
    option = _build_heatmap_option(
        matrix, x_labels=x_labels, y_labels=y_labels, title=title, color_scale=color_scale
    )
    _render(option, height=height, key=key)


# ---------------------------------------------------------------------------
# Sankey — flow diagram (effectiveness funnel breakdown, network flows)
# ---------------------------------------------------------------------------


def _build_sankey_option(
    nodes: list[str],
    edges: list[tuple[str, str, float]],
    *,
    title: str | None = None,
) -> dict:
    """Build an ECharts sankey-chart option dict.

    Args:
        nodes: list of node names.
        edges: list of ``(source, target, value)`` tuples.
    """
    option: dict[str, Any] = {
        "tooltip": {"trigger": "item"},
        "series": [
            {
                "type": "sankey",
                "data": [
                    {"name": n, "itemStyle": {"color": _series_color(n, idx)}}
                    for idx, n in enumerate(nodes)
                ],
                "links": [{"source": s, "target": t, "value": _to_number(v)} for s, t, v in edges],
                "lineStyle": {"color": "gradient", "curveness": 0.5, "opacity": 0.5},
                "label": {"color": DNA_INK_MUTED, "fontSize": 11},
                "emphasis": {"focus": "adjacency"},
            }
        ],
    }
    if title:
        option["title"] = {"text": title}
    return option


def sankey_chart(
    nodes: list[str],
    edges: list[tuple[str, str, float]],
    *,
    title: str | None = None,
    height: int = 400,
    key: str | None = None,
) -> None:
    """Render a sankey flow diagram."""
    option = _build_sankey_option(nodes, edges, title=title)
    _render(option, height=height, key=key)


# ---------------------------------------------------------------------------
# Funnel — outcomes funnel (alerts → cases → escalated → STR)
# ---------------------------------------------------------------------------


def _build_funnel_option(
    stages: list[tuple[str, float]],
    *,
    title: str | None = None,
) -> dict:
    """Build an ECharts funnel-chart option dict.

    ``stages``: list of ``(stage_name, value)`` tuples in funnel order.
    """
    data = [
        {
            "name": str(name),
            "value": _to_number(value),
            "itemStyle": {"color": _series_color(str(name), idx)},
        }
        for idx, (name, value) in enumerate(stages)
    ]
    option: dict[str, Any] = {
        "tooltip": {"trigger": "item", "formatter": "{b}: {c}"},
        "legend": {"data": [n for n, _ in stages], "bottom": 0},
        "series": [
            {
                "type": "funnel",
                "left": "10%",
                "right": "10%",
                "top": 30,
                "bottom": 30,
                "sort": "descending",
                "gap": 4,
                "label": {"show": True, "position": "inside"},
                "labelLine": {"length": 10, "lineStyle": {"width": 1, "type": "solid"}},
                "data": data,
            }
        ],
    }
    if title:
        option["title"] = {"text": title}
    return option


def funnel_chart(
    stages: list[tuple[str, float]],
    *,
    title: str | None = None,
    height: int = 400,
    key: str | None = None,
) -> None:
    """Render an outcomes funnel."""
    option = _build_funnel_option(stages, title=title)
    _render(option, height=height, key=key)


# ---------------------------------------------------------------------------
# Gauge — RAG dial for a single metric value
# ---------------------------------------------------------------------------


def _build_gauge_option(
    value: float,
    *,
    bands: list[tuple[float, str]] | None = None,
    label: str = "",
    max_value: float = 100,
    title: str | None = None,
) -> dict:
    """Build an ECharts gauge-chart option dict.

    Args:
        value: metric value (0..max_value).
        bands: list of ``(threshold, colour)`` tuples in ascending
            threshold order — segments the dial. Defaults to
            red(0-50%) → amber(50-80%) → green(80-100%).
        label: text below the value (e.g. "STR latency p95").
        max_value: dial maximum.
    """
    if bands is None:
        bands = [
            (0.5 * max_value, RAG_PALETTE_RED := "#dc2626"),  # noqa: F841
            (0.8 * max_value, "#d97706"),
            (max_value, "#16a34a"),
        ]
    color_stops = [[threshold / max_value, c] for threshold, c in bands]

    option: dict[str, Any] = {
        "series": [
            {
                "type": "gauge",
                "min": 0,
                "max": max_value,
                "axisLine": {"lineStyle": {"width": 14, "color": color_stops}},
                "pointer": {"itemStyle": {"color": "auto"}},
                "axisTick": {"distance": -18, "length": 6, "lineStyle": {"color": "#fff"}},
                "splitLine": {"distance": -22, "length": 14, "lineStyle": {"color": "#fff"}},
                "axisLabel": {"distance": 24, "color": DNA_INK_MUTED, "fontSize": 10},
                "title": {"offsetCenter": [0, "60%"], "fontSize": 12, "color": DNA_INK_MUTED},
                "detail": {
                    "valueAnimation": True,
                    "formatter": "{value}",
                    "color": "auto",
                    "fontSize": 24,
                    "offsetCenter": [0, "30%"],
                },
                "data": [{"value": _to_number(value), "name": label}],
            }
        ]
    }
    if title:
        option["title"] = {"text": title, "left": "center"}
    return option


def gauge_chart(
    value: float,
    *,
    bands: list[tuple[float, str]] | None = None,
    label: str = "",
    max_value: float = 100,
    title: str | None = None,
    height: int = 240,
    key: str | None = None,
) -> None:
    """Render a single-value RAG gauge."""
    option = _build_gauge_option(value, bands=bands, label=label, max_value=max_value, title=title)
    _render(option, height=height, key=key)


# ---------------------------------------------------------------------------
# Timeline — Gantt-ish horizontal bars over time (transformation roadmap)
# ---------------------------------------------------------------------------


def _build_timeline_option(
    df: Any,
    *,
    task: str,
    start: str,
    finish: str,
    color: str | None = None,
    title: str | None = None,
) -> dict:
    """Build an ECharts timeline (Gantt) option dict using a custom series."""
    tasks = [str(v) for v in df[task].tolist()]
    starts = [_to_iso(v) for v in df[start].tolist()]
    finishes = [_to_iso(v) for v in df[finish].tolist()]
    colors = (
        [_series_color(c, idx) for idx, c in enumerate(df[color].tolist())]
        if color and color in df.columns
        else [_series_color(None, idx) for idx in range(len(df))]
    )

    data = [
        {
            "value": [idx, starts[idx], finishes[idx], tasks[idx]],
            "itemStyle": {"color": colors[idx]},
        }
        for idx in range(len(df))
    ]

    option: dict[str, Any] = {
        "tooltip": {"trigger": "item", "formatter": "{c[3]}<br/>{c[1]} → {c[2]}"},
        "xAxis": {"type": "time"},
        "yAxis": {"type": "category", "data": tasks, "inverse": True},
        "series": [
            {
                "type": "custom",
                "renderItem": (
                    "function (params, api) {"
                    "  var categoryIndex = api.value(0);"
                    "  var start = api.coord([api.value(1), categoryIndex]);"
                    "  var end = api.coord([api.value(2), categoryIndex]);"
                    "  var height = api.size([0, 1])[1] * 0.55;"
                    "  return {"
                    "    type: 'rect',"
                    "    transition: ['shape'],"
                    "    shape: {x: start[0], y: start[1] - height/2,"
                    "            width: Math.max(end[0] - start[0], 2), height: height,"
                    "            r: 3},"
                    "    style: api.style()"
                    "  };"
                    "}"
                ),
                "encode": {"x": [1, 2], "y": 0},
                "data": data,
            }
        ],
    }
    if title:
        option["title"] = {"text": title}
    return option


def timeline_chart(
    df: Any,
    *,
    task: str,
    start: str,
    finish: str,
    color: str | None = None,
    title: str | None = None,
    height: int = 320,
    key: str | None = None,
) -> None:
    """Render a Gantt-style timeline."""
    option = _build_timeline_option(
        df, task=task, start=start, finish=finish, color=color, title=title
    )
    _render(option, height=height, key=key)


# ---------------------------------------------------------------------------
# Waterfall — running positive/negative deltas
# ---------------------------------------------------------------------------


def _build_waterfall_option(
    labels: list[str],
    deltas: list[float],
    *,
    title: str | None = None,
    pos_color: str = "#16a34a",
    neg_color: str = "#dc2626",
) -> dict:
    """Build an ECharts waterfall option using stacked transparent + value bars."""
    placeholders: list[float] = [0]
    running = 0.0
    for d in deltas[:-1]:
        running += float(d)
        placeholders.append(running if d >= 0 else running + float(d))
    # adjust placeholder for negative bars so the visible bar drops below the running line
    fixed_placeholders = []
    fixed_values: list[Any] = []
    running = 0.0
    for d in deltas:
        d_f = float(d)
        if d_f >= 0:
            fixed_placeholders.append(running)
            fixed_values.append(
                {"value": d_f, "itemStyle": {"color": pos_color, "borderRadius": [3, 3, 0, 0]}}
            )
        else:
            fixed_placeholders.append(running + d_f)
            fixed_values.append(
                {"value": -d_f, "itemStyle": {"color": neg_color, "borderRadius": [3, 3, 0, 0]}}
            )
        running += d_f

    option: dict[str, Any] = {
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "xAxis": {"type": "category", "data": labels},
        "yAxis": {"type": "value"},
        "series": [
            {
                "name": "placeholder",
                "type": "bar",
                "stack": "total",
                "itemStyle": {"borderColor": "transparent", "color": "transparent"},
                "emphasis": {"itemStyle": {"borderColor": "transparent", "color": "transparent"}},
                "data": fixed_placeholders,
            },
            {
                "name": "delta",
                "type": "bar",
                "stack": "total",
                "data": fixed_values,
                "label": {"show": True, "position": "top"},
            },
        ],
    }
    if title:
        option["title"] = {"text": title}
    return option


def waterfall_chart(
    labels: list[str],
    deltas: list[float],
    *,
    title: str | None = None,
    pos_color: str = "#16a34a",
    neg_color: str = "#dc2626",
    height: int = DEFAULT_HEIGHT,
    key: str | None = None,
) -> None:
    """Render a waterfall (cascade) chart."""
    option = _build_waterfall_option(
        labels, deltas, title=title, pos_color=pos_color, neg_color=neg_color
    )
    _render(option, height=height, key=key)


# ---------------------------------------------------------------------------
# Escape hatch — for one-offs that don't fit the curated vocabulary
# ---------------------------------------------------------------------------


def echarts_chart(option: dict, *, height: int = DEFAULT_HEIGHT, key: str | None = None) -> None:
    """Render a raw ECharts option dict.

    Use only when none of the typed helpers fit — keep the page-side
    JSON small and lift it to a typed helper if the same pattern
    shows up twice.
    """
    _render(option, height=height, key=key)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _render(option: dict, *, height: int, key: str | None) -> None:
    """Lazy-import streamlit-echarts and render.

    Streamlit and the wrapper are optional deps — keep imports inside
    the helper body so unit-test CI (which only installs ``[dev]``)
    can import this module without them.
    """
    from streamlit_echarts import st_echarts  # type: ignore[import-not-found]

    st_echarts(
        options=option,
        theme=echarts_theme(),
        height=f"{height}px",
        key=key,
    )


def _to_number(v: Any) -> float:
    """Coerce a value to float, treating None / NaN / non-numeric as 0."""
    if v is None:
        return 0.0
    try:
        f = float(v)
        # NaN check without importing math
        if f != f:  # noqa: PLR0124
            return 0.0
        return f
    except (TypeError, ValueError):
        return 0.0


def _to_iso(v: Any) -> str:
    """Coerce a value to an ISO-8601 string for ECharts time axes."""
    if v is None:
        return ""
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def _hex_with_alpha(hex_color: str, alpha: float) -> str:
    """Convert ``#rrggbb`` + alpha to ``rgba(r, g, b, a)`` for ECharts colour stops."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return hex_color
    try:
        r = int(h[0:2], 16)
        g = int(h[2:4], 16)
        b = int(h[4:6], 16)
    except ValueError:
        return hex_color
    return f"rgba({r}, {g}, {b}, {alpha})"
