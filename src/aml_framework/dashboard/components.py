"""Shared UI components for the AML dashboard."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from aml_framework.metrics.engine import MetricResult

# ---------------------------------------------------------------------------
# Color system
# ---------------------------------------------------------------------------
RAG_COLORS = {
    "green": "#16a34a",
    "amber": "#d97706",
    "red": "#dc2626",
    "unset": "#6b7280",
}

SEVERITY_COLORS = {
    "critical": "#7c3aed",
    "high": "#dc2626",
    "medium": "#d97706",
    "low": "#16a34a",
}

CHART_TEMPLATE = "plotly_white"
CHART_PALETTE = ["#2563eb", "#7c3aed", "#db2777", "#d97706", "#059669", "#6b7280"]


# ---------------------------------------------------------------------------
# CSS Theme
# ---------------------------------------------------------------------------
CUSTOM_CSS = """
<style>
/* ---- Global ---- */
.block-container { padding-top: 1.5rem; padding-bottom: 1rem; }

/* ---- Sidebar ---- */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
}
section[data-testid="stSidebar"] * {
    color: #e2e8f0 !important;
}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
    font-size: 0.88rem;
    line-height: 1.5;
}
section[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.12) !important;
}

/* ---- KPI metric cards ---- */
[data-testid="stMetricValue"] {
    font-size: 1.8rem !important;
    font-weight: 700 !important;
    color: #1e293b !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.8rem !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #64748b !important;
}
div[data-testid="stMetric"] {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1rem 1.2rem 0.8rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}

/* ---- Page headers ---- */
h1 { font-weight: 700 !important; color: #0f172a !important; }
h2 { font-weight: 600 !important; color: #1e293b !important; }
h3 { font-weight: 600 !important; color: #334155 !important; }

/* ---- Tables ---- */
[data-testid="stDataFrame"] {
    border-radius: 8px;
    overflow: hidden;
}

/* ---- Tabs ---- */
button[data-baseweb="tab"] {
    font-weight: 600 !important;
}

/* ---- Cards (via HTML) ---- */
.metric-card {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1.2rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.metric-card-accent {
    border-left: 4px solid #2563eb;
}
.metric-card h4 { margin: 0 0 0.3rem 0; color: #0f172a; }
.metric-card .value {
    font-size: 2rem;
    font-weight: 700;
    color: #0f172a;
    margin: 0.2rem 0;
}
.metric-card .label {
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #64748b;
}
.rag-dot {
    display: inline-block;
    width: 10px; height: 10px;
    border-radius: 50%;
    margin-right: 6px;
}
</style>
"""


def apply_theme() -> None:
    """Inject custom CSS."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------


def page_header(title: str, description: str | None = None) -> None:
    """Consistent page header."""
    st.markdown(f"# {title}")
    if description:
        st.caption(description)
    st.divider()


def kpi_card(label: str, value: Any, accent_color: str = "#2563eb") -> None:
    """Render a styled KPI card with colored left border."""
    st.markdown(
        f"""<div class="metric-card" style="border-left: 4px solid {accent_color};">
            <div class="label">{label}</div>
            <div class="value">{value}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def rag_dot_html(rag: str) -> str:
    """Return an HTML colored dot."""
    color = RAG_COLORS.get(rag, RAG_COLORS["unset"])
    return f'<span class="rag-dot" style="background:{color};"></span>'


def severity_badge(severity: str) -> str:
    """Return an HTML badge for severity."""
    color = SEVERITY_COLORS.get(severity, "#6b7280")
    return (
        f'<span style="background:{color}; color:white; padding:2px 10px; '
        f'border-radius:12px; font-size:0.78rem; font-weight:600;">'
        f"{severity}</span>"
    )


def metric_table(metrics: list[MetricResult], audience: str | None = None) -> None:
    """Render a styled metric summary table with colored RAG dots."""
    filtered = metrics
    if audience:
        filtered = [m for m in metrics if audience in m.audience]

    if not filtered:
        st.info("No metrics for this audience.")
        return

    rows = []
    for m in filtered:
        rows.append(
            {
                "RAG": m.rag.upper() if m.rag != "unset" else "-",
                "Metric": m.name,
                "Category": m.category,
                "Value": _fmt_value(m),
                "Owner": m.owner or "\u2014",
            }
        )

    df = pd.DataFrame(rows)

    def _color_rag(val: str) -> str:
        colors = {"GREEN": "#16a34a", "AMBER": "#d97706", "RED": "#dc2626"}
        c = colors.get(val, "#94a3b8")
        return f"color: {c}; font-weight: 700;"

    styled = df.style.map(_color_rag, subset=["RAG"])
    st.dataframe(styled, use_container_width=True, hide_index=True)


def _fmt_value(m: MetricResult) -> str:
    if m.unit == "%":
        return f"{m.value * 100:.1f}%"
    if m.unit in ("usd", "USD", "CAD", "cad"):
        return f"${m.value:,.0f}"
    if m.unit == "hours":
        return f"{m.value:.1f}h"
    if isinstance(m.value, float) and not m.value.is_integer():
        return f"{m.value:.3f}"
    return str(int(m.value)) if float(m.value).is_integer() else str(m.value)


def chart_layout(fig: Any, height: int = 380) -> Any:
    """Apply consistent chart styling."""
    fig.update_layout(
        template=CHART_TEMPLATE,
        height=height,
        margin=dict(t=30, b=30, l=20, r=20),
        font=dict(family="Inter, system-ui, sans-serif", size=12),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig
