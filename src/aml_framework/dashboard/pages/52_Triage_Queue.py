"""Triage Queue — sort alerts by the advisory N1 priority_score.

ADVISORY ONLY: this page re-orders a view of alerts by SAR-likelihood so an
investigator can work the highest-risk first. It never changes an alert's
disposition, queue, or open/close state — the deterministic rules stay
authoritative (governed-augmentation thesis).
"""

from __future__ import annotations

import streamlit as st

from aml_framework.dashboard import triage
from aml_framework.dashboard.audience import show_audience_context
from aml_framework.dashboard.components import (
    data_grid,
    page_footer,
    page_header,
    section_explainer,
)
from aml_framework.dashboard.state import ensure_initialized

ensure_initialized()

page_header(
    "Triage Queue",
    "Work the highest-risk alerts first — sorted by the advisory priority score.",
)
show_audience_context("Triage Queue")

st.caption(
    "⚖️ **Advisory only.** The priority score re-orders this queue by "
    "SAR-likelihood; it never changes an alert's disposition or open/close "
    "state. Deterministic rules remain authoritative."
)

df_alerts = st.session_state.df_alerts

_enabled = triage.has_priority(df_alerts)
_suppression_on = triage.has_suppression(df_alerts)
_scored = triage.triage_view(df_alerts) if _enabled else df_alerts.iloc[0:0]
if _suppression_on and len(_scored):
    _scored = triage.with_suppression_cols(_scored)
_suppressed_count = (
    int(_scored[triage.SUPPRESSED_COL].sum())
    if len(_scored) and triage.SUPPRESSED_COL in _scored.columns
    else 0
)
section_explainer(
    page="Triage Queue",
    section_id="triage.page",
    section_title="Triage Queue",
    data_summary={
        "prioritization_enabled": bool(_enabled),
        "total_alerts": int(len(df_alerts)),
        "scored_alerts": int(len(_scored)),
        "top_score": (
            round(float(_scored[triage.PRIORITY_COL].iloc[0]), 4) if len(_scored) else None
        ),
        "suppression_enabled": bool(_suppression_on),
        "suppressed_count": _suppressed_count,
    },
)

if df_alerts.empty:
    st.info("No alerts in this run.")
    page_footer()
    st.stop()

if not triage.has_priority(df_alerts):
    st.warning(
        "Alert prioritization is not enabled for this program. Add a "
        "`program.prioritization` block (enabled: true) to the spec to rank "
        "alerts by SAR-likelihood. See the N1 governed alert-prioritization layer."
    )
    page_footer()
    st.stop()

view = triage.triage_view(df_alerts)

if _suppression_on:
    view = triage.with_suppression_cols(view)
    st.caption(
        "🛈 **Suppression is advisory** — flagged alerts are de-prioritized, "
        "never closed; an investigator can override. The rule alert remains in "
        "the ledger."
    )
    hide_suppressed = st.checkbox(
        "Hide suppressed (advisory)",
        value=False,
        help=(
            "OFF by default — all alerts stay visible. Toggle on to focus the "
            "queue on alerts that were NOT advisory-suppressed. Suppressed "
            "alerts are never removed from the run, only filtered from this view."
        ),
    )
    if hide_suppressed:
        view = view[~view[triage.SUPPRESSED_COL]]

available = [c for c in triage.DISPLAY_COLS if c in view.columns]

st.subheader(f"{len(view)} scored alerts")
data_grid(
    view[available],
    key="triage_queue_table",
    severity_col="severity" if "severity" in available else None,
    gradient_cols=[triage.PRIORITY_COL],
    gradient_invert=True,  # high score = red = urgent
    pinned_left=[triage.PRIORITY_COL],
    drill_target="pages/17_Customer_360.py" if "customer_id" in available else None,
    drill_param="customer_id",
    drill_column="customer_id",
    height=420,
    hint="Click a row to open the customer's 360 view. Sort is advisory.",
)

st.divider()
st.subheader("Why this score?")
labels = [triage.alert_label(r) for _, r in view.iterrows()]
choice = st.selectbox("Pick a scored alert to see its explanation", labels, index=0)
selected = view.iloc[labels.index(choice)]
rows = triage.explanation_rows(selected.get(triage.EXPLANATION_COL))
if rows:
    st.caption("score = sigmoid(Σ contributions). Largest absolute contributions first.")
    st.dataframe(rows, hide_index=True, use_container_width=True)
else:
    st.caption("No explanation recorded for this alert.")

page_footer()
