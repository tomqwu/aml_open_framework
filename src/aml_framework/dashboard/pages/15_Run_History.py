"""Run History -- past runs from API persistence layer."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from aml_framework.dashboard.audience import show_audience_context
from aml_framework.dashboard.components import (
    data_grid,
    empty_state,
    kpi_card,
    page_header,
    see_also_footer,
)

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
    kpi_card(
        "Spec Hash",
        st.session_state.result.manifest.get("spec_content_hash", "")[:12] + "...",
        "#7c3aed",
    )

st.markdown("<br>", unsafe_allow_html=True)

# Current session.
st.markdown("### Current Session")
st.json(current_run)

st.markdown("<br>", unsafe_allow_html=True)

# Stored runs.
st.markdown("### Stored Runs")
if runs:
    df = pd.DataFrame(runs)
    # Find the rag-band column if persisted by the API.
    rag_col = next((c for c in ("rag", "RAG", "rag_band") if c in df.columns), None)
    # total_alerts gradient — thresholds tied to the typical run volume
    # so a 3× median spike reads red regardless of absolute counts.
    gradient_cols = []
    g_low = 0.5
    g_high = 0.8
    if "total_alerts" in df.columns and df["total_alerts"].max():
        gradient_cols = ["total_alerts"]
        median_alerts = float(df["total_alerts"].median()) or 1.0
        g_low = median_alerts
        g_high = median_alerts * 3
    data_grid(
        df,
        key="run_history_table",
        rag_col=rag_col,
        gradient_cols=gradient_cols,
        gradient_low=g_low,
        gradient_high=g_high,
        pinned_left=["run_id"] if "run_id" in df.columns else None,
        height=400,
    )
else:
    empty_state(
        "No stored runs yet.",
        icon="📦",
        detail=(
            "Runs are persisted when the API is running (`aml api` or Docker "
            "Compose). Once a run lands, it shows here with spec hashes, "
            "alert counts, and metric snapshots. Quick start:\n\n"
            "```bash\n"
            "curl -X POST localhost:8000/api/v1/login \\\n"
            '  -d \'{"username":"admin","password":"admin"}\'\n'
            "curl -X POST localhost:8000/api/v1/runs \\\n"
            "  -H 'Authorization: Bearer <token>'\n"
            "```"
        ),
    )

# Manifest from current run.
st.markdown("<br>", unsafe_allow_html=True)
with st.expander("Current Run Manifest"):
    st.json(result.manifest)


# --- See also (cross-page nav) ---
see_also_footer(
    [
        "[Comparative Analytics — run-over-run trend deltas](./19_Comparative_Analytics)",
        "[Audit & Evidence — hash-chain provenance per run](./7_Audit_Evidence)",
    ]
)
