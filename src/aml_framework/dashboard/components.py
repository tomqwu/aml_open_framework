"""Shared UI components for the AML dashboard."""

from __future__ import annotations

from typing import Any

import streamlit as st

from aml_framework.metrics.engine import MetricResult

RAG_COLORS = {
    "green": "#22c55e",
    "amber": "#f59e0b",
    "red": "#ef4444",
    "unset": "#6b7280",
}
RAG_ICONS = {"green": "\U0001f7e2", "amber": "\U0001f7e1", "red": "\U0001f534", "unset": "\u26aa"}


def rag_dot(rag: str) -> str:
    """Return a colored HTML dot for a RAG status."""
    color = RAG_COLORS.get(rag, RAG_COLORS["unset"])
    return f'<span style="color:{color}; font-size:1.4em;">\u25cf</span>'


def kpi_tile(label: str, value: Any, delta: str | None = None) -> None:
    """Render a metric tile using ``st.metric``."""
    st.metric(label=label, value=value, delta=delta)


def metric_table(metrics: list[MetricResult], audience: str | None = None) -> None:
    """Render a styled metric summary table."""
    filtered = metrics
    if audience:
        filtered = [m for m in metrics if audience in m.audience]

    if not filtered:
        st.info("No metrics for this audience.")
        return

    rows = []
    for m in filtered:
        rag_icon = RAG_ICONS.get(m.rag, RAG_ICONS["unset"])
        value = _fmt_value(m)
        rows.append({
            "RAG": rag_icon,
            "Metric": m.name,
            "Category": m.category,
            "Value": value,
            "Owner": m.owner or "\u2014",
        })

    import pandas as pd

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)


def _fmt_value(m: MetricResult) -> str:
    if m.unit == "%":
        return f"{m.value * 100:.1f}%"
    if m.unit in ("usd", "USD"):
        return f"${m.value:,.0f}"
    if m.unit == "hours":
        return f"{m.value:.1f}h"
    if isinstance(m.value, float) and not m.value.is_integer():
        return f"{m.value:.3f}"
    return str(int(m.value)) if float(m.value).is_integer() else str(m.value)


def page_header(title: str, description: str | None = None) -> None:
    """Consistent page header."""
    st.header(title)
    if description:
        st.caption(description)
    st.divider()


CUSTOM_CSS = """
<style>
    /* Tighten main padding */
    .block-container { padding-top: 2rem; }
    /* Metric tiles */
    [data-testid="stMetricValue"] { font-size: 1.6rem; }
    [data-testid="stMetricLabel"] { font-size: 0.85rem; }
    /* Subtle card effect for columns */
    [data-testid="column"] > div { padding: 0.25rem; }
</style>
"""


def apply_theme() -> None:
    """Inject custom CSS."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
