"""Run History -- past runs from API persistence layer."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from aml_framework.dashboard.components import kpi_card, page_header
from aml_framework.dashboard.audience import show_audience_context

page_header(
    "Run History",
    "Past engine executions stored in the persistence layer.",
)
show_audience_context("Run History")

if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo -- Run History**\n\n"
        "Each `aml run` or API `POST /runs` creates a record. This page "
        "shows the history with run metadata, alert/metric counts, and "
        "spec hashes for audit traceability."
    )

# Try to load from SQLite/PostgreSQL.
try:
    from aml_framework.api.db import init_db, list_runs

    init_db()
    runs = list_runs()
except Exception:
    runs = []

# Also show the current session run.
result = st.session_state.result
current_run = {
    "run_id": "current_session",
    "spec_path": str(st.session_state.spec_path),
    "seed": st.session_state.seed,
    "created_at": st.session_state.as_of.isoformat(),
    "total_alerts": result.total_alerts,
    "total_cases": len(result.case_ids),
    "total_metrics": len(result.metrics),
}

# KPIs.
c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card("Stored Runs", len(runs), "#2563eb")
with c2:
    kpi_card("Current Alerts", result.total_alerts, "#dc2626")
with c3:
    kpi_card("Current Cases", len(result.case_ids), "#d97706")
with c4:
    kpi_card("Spec Hash", st.session_state.result.manifest.get(
        "spec_content_hash", "")[:12] + "...", "#7c3aed")

st.markdown("<br>", unsafe_allow_html=True)

# Current session.
st.markdown("### Current Session")
st.json(current_run)

st.markdown("<br>", unsafe_allow_html=True)

# Stored runs.
st.markdown("### Stored Runs")
if runs:
    df = pd.DataFrame(runs)
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.caption(
        "No stored runs yet. Runs are persisted when using the API "
        "(`aml api` or Docker Compose). Try: "
        "`curl -X POST localhost:8000/api/v1/login -d '{\"username\":\"admin\",\"password\":\"admin\"}'` "
        "then `curl -X POST localhost:8000/api/v1/runs -H 'Authorization: Bearer <token>'`"
    )

# Manifest from current run.
st.markdown("<br>", unsafe_allow_html=True)
with st.expander("Current Run Manifest"):
    st.json(result.manifest)
