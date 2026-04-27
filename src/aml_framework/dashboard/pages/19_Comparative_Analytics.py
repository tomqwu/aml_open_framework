"""Comparative Analytics -- run-over-run trend analysis."""

from __future__ import annotations

import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from aml_framework.dashboard.components import chart_layout, kpi_card, page_header

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
    names = [m.name[:30] for m in metrics_with_targets]
    values = [m.value for m in metrics_with_targets]
    target_met = [m.target_met for m in metrics_with_targets]
    colors = ["#16a34a" if t else "#dc2626" for t in target_met]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=names,
            y=values,
            marker_color=colors,
            text=[f"{'On' if t else 'Off'} target" for t in target_met],
            textposition="outside",
        )
    )
    fig.update_layout(yaxis_title="Value", xaxis_title="")
    st.plotly_chart(chart_layout(fig, 400), use_container_width=True)

# --- RAG distribution ---
st.markdown("### RAG Distribution")
rag_counts = {"green": 0, "amber": 0, "red": 0, "unset": 0}
for m in result.metrics:
    rag_counts[m.rag] = rag_counts.get(m.rag, 0) + 1

col_left, col_right = st.columns(2)
with col_left:
    rag_colors = {"green": "#16a34a", "amber": "#d97706", "red": "#dc2626", "unset": "#6b7280"}
    fig = go.Figure(
        go.Pie(
            labels=list(rag_counts.keys()),
            values=list(rag_counts.values()),
            marker_colors=[rag_colors[k] for k in rag_counts.keys()],
            hole=0.45,
        )
    )
    fig.update_traces(textposition="inside", textinfo="label+value")
    st.plotly_chart(chart_layout(fig, 300), use_container_width=True)

with col_right:
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
fig = go.Figure()
fig.add_trace(
    go.Bar(
        x=df_rules["Rule"],
        y=df_rules["Alerts"],
        marker_color=[
            "#dc2626" if s == "critical" else "#d97706" if s == "high" else "#2563eb"
            for s in df_rules["Severity"]
        ],
    )
)
fig.update_layout(xaxis_title="", yaxis_title="Alert Count")
st.plotly_chart(chart_layout(fig, 350), use_container_width=True)

# --- Historical trend placeholder ---
st.markdown("### Historical Trends")
try:
    from aml_framework.api.db import init_db, list_runs

    init_db()
    runs = list_runs()
    if runs:
        st.dataframe(pd.DataFrame(runs), use_container_width=True, hide_index=True)
    else:
        st.caption(
            "No historical runs stored. Use `aml api` or Docker Compose to enable "
            "run persistence for trend analysis."
        )
except Exception:
    st.caption("Run history not available (API persistence not configured).")
