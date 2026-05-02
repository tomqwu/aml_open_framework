"""ECharts theme derived from the dashboard brand DNA tokens.

The cream / ink / burnt-orange palette comes from the landing site
(``docs/pitch/landing/index.html``) and is mirrored in the dashboard
CSS variables (``--dna-canvas`` / ``--dna-ink`` / ``--dna-accent`` in
``components.py::CUSTOM_CSS``). This module exposes the same palette
as a Python dict shape that ECharts consumes via
``st_pyecharts(... theme=...)`` or ``st_echarts(... theme=...)``.

Pure-data module — no streamlit, no echarts imports — so unit tests
in the lean ``[dev]`` install can read theme tokens without pulling
the dashboard extras.
"""

from __future__ import annotations

# Brand DNA — keep in lockstep with components.py CUSTOM_CSS :root vars
# and the landing site at docs/pitch/landing/index.html.
DNA_CANVAS = "#f7f4ec"  # cream — page background
DNA_INK = "#1c1f26"  # near-black ink — text + axes
DNA_INK_MUTED = "#5a5e69"  # secondary text
DNA_RULE = "#e6e1d3"  # divider rules
DNA_ACCENT = "#a44b30"  # burnt orange — primary brand accent

# Categorical palette — burnt orange first (brand-anchored), then a set
# of muted complements that stay legible on the cream canvas. Avoids
# the saturated blues / purples that read as "generic SaaS dashboard".
CATEGORICAL_PALETTE = [
    "#a44b30",  # burnt orange (brand)
    "#2e5c4a",  # forest green
    "#7d5a3c",  # tobacco brown
    "#3b5b8a",  # ink blue
    "#a06a7a",  # muted plum
    "#c08a3e",  # ochre
    "#5a6b6f",  # slate
]

# Severity / RAG — keep in sync with components.py SEVERITY_COLORS / RAG_COLORS.
# These are loud on purpose (red = breach, amber = warning, green = ok) and
# override the categorical palette anywhere a column carries that semantic.
SEVERITY_PALETTE = {
    "critical": "#7c3aed",
    "high": "#dc2626",
    "medium": "#d97706",
    "low": "#16a34a",
}

RAG_PALETTE = {
    "green": "#16a34a",
    "amber": "#d97706",
    "red": "#dc2626",
    "breached": "#7c2d12",
    "unset": "#6b7280",
}


def echarts_theme() -> dict:
    """Return the ECharts theme dict honouring the dashboard brand DNA.

    Pass to ``st_echarts(option, theme=echarts_theme())``. Sets cream
    canvas, ink-on-cream text, burnt-orange accent line, and the
    categorical palette above. Animation is on but short (300ms) —
    chart load shouldn't feel like a marketing site.

    The returned dict is JSON-serialisable; nothing here references
    streamlit or echarts so it's importable without the dashboard
    extras installed.
    """
    return {
        "color": list(CATEGORICAL_PALETTE),
        "backgroundColor": "transparent",  # let dashboard CSS show through
        "textStyle": {
            "fontFamily": "Inter, system-ui, -apple-system, sans-serif",
            "color": DNA_INK,
            "fontSize": 12,
        },
        "title": {
            "textStyle": {
                "fontFamily": "'Source Serif 4', Georgia, serif",
                "color": DNA_INK,
                "fontWeight": 600,
                "fontSize": 14,
            },
            "subtextStyle": {"color": DNA_INK_MUTED, "fontSize": 11},
        },
        "line": {
            "itemStyle": {"borderWidth": 0},
            "lineStyle": {"width": 2.5},
            "symbolSize": 6,
            "symbol": "circle",
            "smooth": True,
        },
        "bar": {
            "itemStyle": {"barBorderWidth": 0, "barBorderColor": DNA_RULE},
        },
        "pie": {
            "itemStyle": {"borderWidth": 1, "borderColor": DNA_CANVAS},
        },
        "categoryAxis": {
            "axisLine": {"show": True, "lineStyle": {"color": DNA_RULE}},
            "axisTick": {"show": False},
            "axisLabel": {"color": DNA_INK_MUTED, "fontSize": 11},
            "splitLine": {"show": False},
        },
        "valueAxis": {
            "axisLine": {"show": False},
            "axisTick": {"show": False},
            "axisLabel": {"color": DNA_INK_MUTED, "fontSize": 11},
            "splitLine": {"show": True, "lineStyle": {"color": DNA_RULE, "type": "dashed"}},
        },
        "legend": {
            "textStyle": {"color": DNA_INK_MUTED, "fontSize": 11},
            "icon": "roundRect",
            "itemWidth": 12,
            "itemHeight": 8,
        },
        "tooltip": {
            "backgroundColor": DNA_INK,
            "borderColor": DNA_INK,
            "textStyle": {"color": DNA_CANVAS, "fontSize": 12},
            "axisPointer": {"lineStyle": {"color": DNA_ACCENT, "width": 1}},
        },
        "grid": {
            "left": "3%",
            "right": "4%",
            "bottom": "8%",
            "top": "10%",
            "containLabel": True,
        },
        "animation": True,
        "animationDuration": 300,
    }


def severity_color(value: str | None) -> str:
    """Map a severity string to its palette colour, or fall back to muted."""
    if not isinstance(value, str):
        return DNA_INK_MUTED
    return SEVERITY_PALETTE.get(value.lower(), DNA_INK_MUTED)


def rag_color(value: str | None) -> str:
    """Map a RAG-band string to its palette colour, or fall back to muted."""
    if not isinstance(value, str):
        return DNA_INK_MUTED
    return RAG_PALETTE.get(value.lower(), DNA_INK_MUTED)
