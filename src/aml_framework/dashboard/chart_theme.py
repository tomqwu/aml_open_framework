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
DNA_INK_MUTED = "#5a5e69"  # secondary text (DOM/markdown chrome)
DNA_RULE = "#e6e1d3"  # divider rules (DOM/markdown chrome)
DNA_ACCENT = "#a44b30"  # burnt orange — primary brand accent

# --- Theme-neutral chart chrome -------------------------------------------
# ECharts is canvas-rendered: it can't read the CSS dark theme that
# components.py drives off `@media (prefers-color-scheme: dark)`. A
# server-side dark *detector* (st.context.theme / a JS bridge) either
# desyncs from that CSS or forces a page reload that re-runs the AML
# engine with a new `as_of`, breaking run determinism (Codex PR-2). So
# charts are theme-NEUTRAL instead: a transparent background lets the
# CSS-themed card show through, and the chrome colours below clear
# WCAG 1.4.11 non-text contrast (>=3:1) against BOTH the cream canvas
# (#f7f4ec) AND the darkest dark surface (#0e1116) — their relative
# luminance sits in the dual-safe band ~[0.12, 0.27]. Pinned by
# test_chart_chrome_is_dual_contrast_safe.
DNA_CHART_LABEL = "#6b7280"  # axis/legend/label text (L~0.167)
# Gridlines/axis lines: a translucent grey reads as a faint hairline on
# either background (it blends with whatever surface is behind it).
DNA_CHART_RULE = "rgba(128,128,128,0.32)"
DNA_CHART_ACCENT = "#c2603f"  # axisPointer / emphasis (L~0.20)

# Categorical palette — burnt orange first (brand-anchored), then muted
# complements. Every entry is a mid-tone (relative luminance ~0.18–0.23)
# so each series clears >=3:1 on BOTH the cream and the near-black
# surface — no light/dark variant needed (Simplicity First). Avoids the
# saturated blues / purples that read as "generic SaaS dashboard".
CATEGORICAL_PALETTE = [
    "#c2603f",  # burnt orange (brand)
    "#388f78",  # forest green
    "#9a7048",  # tobacco brown
    "#5577a8",  # ink blue
    "#a06d83",  # muted plum
    "#a87d35",  # ochre
    "#6f8488",  # slate
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
    """Return the theme-neutral ECharts theme dict.

    Pass to ``st_echarts(option, theme=echarts_theme())``. The chart
    background is transparent so the CSS-themed dashboard card shows
    through (light *or* dark — whichever the OS / page CSS resolves);
    all chrome uses the dual-contrast-safe ``DNA_CHART_*`` tokens and
    the dual-safe ``CATEGORICAL_PALETTE`` so every surface is legible
    on both without any server-side dark detection. The tooltip is the
    one opaque element — ECharts paints it as its own box, so it gets
    a fixed dark slab with light text that reads on either page theme.

    Stays pure-data / streamlit-free so the lean ``[dev]`` install can
    import it. The returned dict is JSON-serialisable.
    """
    return {
        "color": list(CATEGORICAL_PALETTE),
        "backgroundColor": "transparent",  # let dashboard CSS show through
        "textStyle": {
            "fontFamily": "Inter, system-ui, -apple-system, sans-serif",
            "color": DNA_CHART_LABEL,
            "fontSize": 12,
        },
        "title": {
            "textStyle": {
                "fontFamily": "'Source Serif 4', Georgia, serif",
                "color": DNA_CHART_LABEL,
                "fontWeight": 600,
                "fontSize": 14,
            },
            "subtextStyle": {"color": DNA_CHART_LABEL, "fontSize": 11},
        },
        "line": {
            "itemStyle": {"borderWidth": 0},
            "lineStyle": {"width": 2.5},
            "symbolSize": 6,
            "symbol": "circle",
            "smooth": True,
        },
        "bar": {
            "itemStyle": {"barBorderWidth": 0, "barBorderColor": DNA_CHART_RULE},
        },
        "pie": {
            # Hairline gap between slices — translucent so it works on
            # whatever page surface shows through the transparent bg.
            "itemStyle": {"borderWidth": 1, "borderColor": DNA_CHART_RULE},
        },
        "categoryAxis": {
            "axisLine": {"show": True, "lineStyle": {"color": DNA_CHART_RULE}},
            "axisTick": {"show": False},
            "axisLabel": {"color": DNA_CHART_LABEL, "fontSize": 11},
            "splitLine": {"show": False},
        },
        "valueAxis": {
            "axisLine": {"show": False},
            "axisTick": {"show": False},
            "axisLabel": {"color": DNA_CHART_LABEL, "fontSize": 11},
            "splitLine": {"show": True, "lineStyle": {"color": DNA_CHART_RULE, "type": "dashed"}},
        },
        "legend": {
            "textStyle": {"color": DNA_CHART_LABEL, "fontSize": 11},
            "icon": "roundRect",
            "itemWidth": 12,
            "itemHeight": 8,
        },
        "tooltip": {
            "backgroundColor": "#2b2f36",
            "borderColor": "#646a73",
            "textStyle": {"color": "#f2f3f5", "fontSize": 12},
            "axisPointer": {"lineStyle": {"color": DNA_CHART_ACCENT, "width": 1}},
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
