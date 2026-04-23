"""Executive Dashboard — program-level KPIs and health overview."""

from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from aml_framework.dashboard.components import metric_table, page_header

page_header(
    "Executive Dashboard",
    "Program-level KPIs, alert summary, and compliance health at a glance.",
)

spec = st.session_state.spec
result = st.session_state.result
df_alerts = st.session_state.df_alerts
df_metrics = st.session_state.df_metrics
audience = st.session_state.get("selected_audience")

if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo — Executive Dashboard**\n\n"
        "This is the board-level view your CCO presents quarterly. "
        f"The engine detected **{result.total_alerts} alerts** across "
        f"**{len(spec.rules)} rules**, covering multiple AML typologies. "
        "RAG indicators show program health at a glance."
    )

# --- KPI Tiles ---
metrics_by_id = {m.id: m for m in result.metrics}
c1, c2, c3, c4, c5, c6 = st.columns(6)
with c1:
    st.metric("Total Alerts", result.total_alerts)
with c2:
    st.metric("Open Cases", len(result.case_ids))
with c3:
    active = len([r for r in spec.rules if r.status == "active"])
    st.metric("Active Rules", active)
with c4:
    tc = metrics_by_id.get("typology_coverage")
    st.metric("Typology Coverage", f"{tc.value * 100:.0f}%" if tc else "N/A")
with c5:
    dc = metrics_by_id.get("distinct_customers_alerted")
    st.metric("Customers Alerted", int(dc.value) if dc else 0)
with c6:
    tv = metrics_by_id.get("transaction_volume_usd")
    st.metric("Volume Screened", f"${tv.value:,.0f}" if tv else "N/A")

st.divider()

# --- Charts row ---
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Alerts by Rule")
    if not df_alerts.empty:
        # Merge severity from spec
        sev_map = {r.id: r.severity for r in spec.rules}
        chart_df = df_alerts.groupby("rule_id").size().reset_index(name="count")
        chart_df["severity"] = chart_df["rule_id"].map(sev_map)
        color_map = {"high": "#ef4444", "medium": "#f59e0b", "low": "#22c55e", "critical": "#7c3aed"}
        fig = px.bar(
            chart_df, x="rule_id", y="count", color="severity",
            color_discrete_map=color_map,
            labels={"rule_id": "Rule", "count": "Alerts"},
        )
        fig.update_layout(showlegend=True, height=350, margin=dict(t=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No alerts generated.")

with col_right:
    st.subheader("RAG Status Grid")
    metric_table(result.metrics, audience=audience)

st.divider()

# --- Program Health Radar ---
col_radar, col_summary = st.columns(2)

with col_radar:
    st.subheader("Program Health Radar")
    categories = [m.name for m in result.metrics if m.rag != "unset"][:8]
    values = []
    for m in result.metrics:
        if m.rag == "unset" or m.name not in categories:
            continue
        # Map RAG to score: green=3, amber=2, red=1
        values.append({"green": 3, "amber": 2, "red": 1}.get(m.rag, 0))

    if categories and values:
        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(
            r=values + [values[0]],
            theta=categories + [categories[0]],
            fill="toself",
            name="Current",
            line_color="#3b82f6",
        ))
        fig.add_trace(go.Scatterpolar(
            r=[3] * (len(categories) + 1),
            theta=categories + [categories[0]],
            fill="toself",
            name="Target",
            line_color="#22c55e",
            opacity=0.2,
        ))
        fig.update_layout(
            polar=dict(radialaxis=dict(visible=True, range=[0, 3])),
            showlegend=True, height=400, margin=dict(t=30),
        )
        st.plotly_chart(fig, use_container_width=True)

with col_summary:
    st.subheader("Run Summary")
    st.json({
        "program": spec.program.name,
        "jurisdiction": spec.program.jurisdiction,
        "regulator": spec.program.regulator,
        "rules_executed": len(spec.rules),
        "total_alerts": result.total_alerts,
        "total_cases": len(result.case_ids),
        "total_metrics": len(result.metrics),
        "reports_generated": len(result.reports),
    })
