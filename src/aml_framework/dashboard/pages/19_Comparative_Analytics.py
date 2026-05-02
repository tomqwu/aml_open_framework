"""Comparative Analytics -- run-over-run trend analysis."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from aml_framework.dashboard.components import (
    bar_chart,
    empty_state,
    kpi_card,
    page_header,
    pie_chart,
    rag_cell_style,
)

page_header(
    "Comparative Analytics",
    "Compare current run results against baseline metrics and historical trends.",
)

result = st.session_state.result
spec = st.session_state.spec

if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo -- Comparative Analytics**\n\n"
        "This page shows how the current run compares to expected baselines. "
        "In production with multiple stored runs, it would show trends over time."
    )

# --- Current run summary ---
st.markdown("### Current Run")
c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card("Total Alerts", result.total_alerts, "#2563eb")
with c2:
    kpi_card("Total Cases", len(result.case_ids), "#d97706")
with c3:
    kpi_card("Active Rules", len([r for r in spec.rules if r.status == "active"]), "#059669")
with c4:
    kpi_card("Metrics Computed", len(result.metrics), "#7c3aed")

st.markdown("<br>", unsafe_allow_html=True)

# --- Metric comparison against thresholds ---
st.markdown("### Metrics vs Targets")

metrics_with_targets = [m for m in result.metrics if m.target_met is not None]
if metrics_with_targets:
    # On-target → green, off-target → red. Re-projecting as a `band`
    # column lets the bar palette resolver pick the colour from the
    # severity palette without per-call colour wiring.
    metric_df = pd.DataFrame(
        {
            "metric": [m.name[:30] for m in metrics_with_targets],
            "value": [m.value for m in metrics_with_targets],
            "band": ["low" if m.target_met else "high" for m in metrics_with_targets],
        }
    )
    bar_chart(
        metric_df,
        x="metric",
        y="value",
        color="band",
        title="Metrics vs Targets (green = on target, red = off)",
        height=400,
        key="comparative_metrics_bar",
    )

# --- RAG distribution ---
st.markdown("### RAG Distribution")
rag_counts = {"green": 0, "amber": 0, "red": 0, "unset": 0}
for m in result.metrics:
    rag_counts[m.rag] = rag_counts.get(m.rag, 0) + 1

col_left, col_right = st.columns(2)
with col_left:
    # `names="rag"` triggers the RAG palette resolver in
    # _series_color() so each slice gets its semantic colour.
    rag_df = pd.DataFrame({"rag": list(rag_counts.keys()), "count": list(rag_counts.values())})
    pie_chart(
        rag_df,
        names="rag",
        values="count",
        donut=True,
        height=300,
        key="comparative_rag_pie",
    )

with col_right:
    rag_colors = {
        "green": "#16a34a",
        "amber": "#d97706",
        "red": "#dc2626",
        "unset": "#6b7280",
    }
    for rag, count in rag_counts.items():
        if count > 0:
            color = rag_colors[rag]
            st.markdown(
                f'<div style="display:flex; align-items:center; margin:0.3rem 0;">'
                f'<span style="width:12px; height:12px; border-radius:50%; '
                f'background:{color}; display:inline-block; margin-right:8px;"></span>'
                f'<span style="font-weight:600;">{rag.upper()}</span>: {count} metric(s)'
                f"</div>",
                unsafe_allow_html=True,
            )

st.markdown("<br>", unsafe_allow_html=True)

# --- Per-rule alert comparison ---

st.markdown("### Alerts by Rule")

# Interactive controls — let operators slice the rule comparison view
# (otherwise it's an unfilterable bar chart that gets noisy on big specs).
all_severities = sorted({r.severity for r in spec.rules})
fc1, fc2 = st.columns([3, 1])
with fc1:
    selected_severities = st.multiselect(
        "Severity filter",
        options=all_severities,
        default=all_severities,
        key="comparative_sev_filter",
    )
with fc2:
    hide_silent = st.toggle(
        "Hide silent rules",
        value=False,
        help="Drop rules that produced zero alerts in this run.",
        key="comparative_hide_silent",
    )

rule_data = []
for rule in spec.rules:
    if rule.severity not in selected_severities:
        continue
    alert_count = len(result.alerts.get(rule.id, []))
    if hide_silent and alert_count == 0:
        continue
    rule_data.append(
        {
            "Rule": rule.id,
            "Severity": rule.severity,
            "Alerts": alert_count,
            "Status": "Active" if alert_count > 0 else "Silent",
        }
    )

if not rule_data:
    st.info("No rules match the current filters.")
    st.stop()

df_rules = pd.DataFrame(rule_data)
# `color="Severity"` paints each rule's bar with its severity colour
# from the centralised SEVERITY_PALETTE (no per-page colour map).
bar_chart(
    df_rules,
    x="Rule",
    y="Alerts",
    color="Severity",
    title="Alerts by Rule (coloured by severity)",
    height=350,
    key="comparative_alerts_by_rule",
)

# --- Historical trend placeholder ---
st.markdown("### Historical Trends")
try:
    from aml_framework.api.db import init_db, list_runs

    init_db()
    runs = list_runs()
    if runs:
        runs_df = pd.DataFrame(runs)
        # Colour the RAG-band column when present so a glance separates
        # green/amber/red runs without reading the value.
        styled_runs = runs_df.style
        for col in ("rag", "RAG", "rag_band", "overall_rag"):
            if col in runs_df.columns:
                styled_runs = styled_runs.map(rag_cell_style, subset=[col])
        st.dataframe(styled_runs, use_container_width=True, hide_index=True)
    else:
        empty_state(
            "No historical runs stored yet.",
            icon="📈",
            detail=(
                "Trend analytics need persisted runs. Enable the API "
                "(`aml api` or Docker Compose) so each engine execution "
                "writes to the runs table — this view will then chart deltas."
            ),
        )
except Exception:
    empty_state(
        "Run history not available.",
        icon="🔌",
        detail=(
            "API persistence is not configured. Run `aml api` to start the "
            "FastAPI service that persists each `aml run` for trend analysis."
        ),
    )
