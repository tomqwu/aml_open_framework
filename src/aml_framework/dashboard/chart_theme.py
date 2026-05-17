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

# Dark-theme tokens — mirror the `@media (prefers-color-scheme: dark)`
# block in components.py role-for-role so charts match the rest of the
# dark UI (canvas #0e1116, ink #e8eaed, dim #9aa3ad, accent #e0795a).
DNA_CANVAS_DARK = "#0e1116"
DNA_INK_DARK = "#e8eaed"
DNA_INK_MUTED_DARK = "#9aa3ad"
DNA_RULE_DARK = "#3a4048"  # solid hairline visible on near-black
DNA_ACCENT_DARK = "#e0795a"  # lightened rust (the #a44b30 muddies on dark)
DNA_TOOLTIP_BG_DARK = "#212832"  # raised card surface
DNA_TOOLTIP_BORDER_DARK = "#646a73"

# Same earth-tone categorical roles, brightened so each series stays
# legible on the near-black canvas (the cream-tuned values go muddy).
CATEGORICAL_PALETTE_DARK = [
    "#e0795a",  # burnt orange (brand, lightened)
    "#5fae8e",  # forest green
    "#c2986a",  # tobacco brown
    "#7aa0d4",  # ink blue
    "#c99aa8",  # muted plum
    "#e0b15f",  # ochre
    "#9bb0b4",  # slate
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


def echarts_theme(dark: bool = False) -> dict:
    """Return the ECharts theme dict honouring the dashboard brand DNA.

    Pass to ``st_echarts(option, theme=echarts_theme(dark=...))``.
    Light: cream canvas, ink-on-cream text, burnt-orange accent.
    ``dark=True``: the dark-DNA mirror — light ink/axes on the
    transparent (near-black via page CSS) canvas, brightened
    categorical palette, raised-surface tooltip. ECharts is rendered
    client-side and can't read `prefers-color-scheme`, so the caller
    (``charts.py``, which has streamlit) detects the active scheme via
    ``st.context.theme`` and passes the flag — this module stays
    pure-data / streamlit-free so the lean ``[dev]`` install can
    import it.

    The returned dict is JSON-serialisable.
    """
    palette = CATEGORICAL_PALETTE_DARK if dark else CATEGORICAL_PALETTE
    ink = DNA_INK_DARK if dark else DNA_INK
    ink_muted = DNA_INK_MUTED_DARK if dark else DNA_INK_MUTED
    rule = DNA_RULE_DARK if dark else DNA_RULE
    accent = DNA_ACCENT_DARK if dark else DNA_ACCENT
    # Pie slices separate against the page canvas behind the
    # transparent chart bg — use the active scheme's canvas colour.
    canvas = DNA_CANVAS_DARK if dark else DNA_CANVAS
    tooltip_bg = DNA_TOOLTIP_BG_DARK if dark else DNA_INK
    tooltip_border = DNA_TOOLTIP_BORDER_DARK if dark else DNA_INK
    tooltip_text = DNA_INK_DARK if dark else DNA_CANVAS
    return {
        "color": list(palette),
        "backgroundColor": "transparent",  # let dashboard CSS show through
        "textStyle": {
            "fontFamily": "Inter, system-ui, -apple-system, sans-serif",
            "color": ink,
            "fontSize": 12,
        },
        "title": {
            "textStyle": {
                "fontFamily": "'Source Serif 4', Georgia, serif",
                "color": ink,
                "fontWeight": 600,
                "fontSize": 14,
            },
            "subtextStyle": {"color": ink_muted, "fontSize": 11},
        },
        "line": {
            "itemStyle": {"borderWidth": 0},
            "lineStyle": {"width": 2.5},
            "symbolSize": 6,
            "symbol": "circle",
            "smooth": True,
        },
        "bar": {
            "itemStyle": {"barBorderWidth": 0, "barBorderColor": rule},
        },
        "pie": {
            "itemStyle": {"borderWidth": 1, "borderColor": canvas},
        },
        "categoryAxis": {
            "axisLine": {"show": True, "lineStyle": {"color": rule}},
            "axisTick": {"show": False},
            "axisLabel": {"color": ink_muted, "fontSize": 11},
            "splitLine": {"show": False},
        },
        "valueAxis": {
            "axisLine": {"show": False},
            "axisTick": {"show": False},
            "axisLabel": {"color": ink_muted, "fontSize": 11},
            "splitLine": {"show": True, "lineStyle": {"color": rule, "type": "dashed"}},
        },
        "legend": {
            "textStyle": {"color": ink_muted, "fontSize": 11},
            "icon": "roundRect",
            "itemWidth": 12,
            "itemHeight": 8,
        },
        "tooltip": {
            "backgroundColor": tooltip_bg,
            "borderColor": tooltip_border,
            "textStyle": {"color": tooltip_text, "fontSize": 12},
            "axisPointer": {"lineStyle": {"color": accent, "width": 1}},
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
