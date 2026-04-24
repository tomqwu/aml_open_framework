"""Executive Dashboard -- program-level KPIs and health overview."""

from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from aml_framework.dashboard.components import (
    SEVERITY_COLORS,
    chart_layout,
    kpi_card,
    metric_table,
    page_header,
)

page_header(
    "Executive Dashboard",
    "Program-level KPIs, alert summary, and compliance health at a glance.",
)

spec = st.session_state.spec
result = st.session_state.result
df_alerts = st.session_state.df_alerts
audience = st.session_state.get("selected_audience")

if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo -- Executive Dashboard**\n\n"
        f"The engine detected **{result.total_alerts} alerts** across "
        f"**{len(spec.rules)} rules**, covering multiple AML typologies. "
        "KPI cards show program health. The RAG grid below tracks every "
        "metric with red/amber/green thresholds."
    )

# --- KPI tiles ---
metrics_by_id = {m.id: m for m in result.metrics}

c1, c2, c3, c4, c5, c6 = st.columns(6)
with c1:
    kpi_card("Total Alerts", result.total_alerts, "#dc2626")
with c2:
    kpi_card("Open Cases", len(result.case_ids), "#d97706")
with c3:
    active = len([r for r in spec.rules if r.status == "active"])
    kpi_card("Active Rules", active, "#2563eb")
with c4:
    tc = metrics_by_id.get("typology_coverage")
    kpi_card("Typology Coverage", f"{tc.value * 100:.0f}%" if tc else "N/A", "#059669")
with c5:
    dc = metrics_by_id.get("distinct_customers_alerted")
    kpi_card("Customers Alerted", int(dc.value) if dc else 0, "#7c3aed")
with c6:
    # Find the volume metric by checking common ids
    tv = metrics_by_id.get("transaction_volume_usd") or metrics_by_id.get("transaction_volume_cad")
    if tv:
        unit = spec.program.jurisdiction
        kpi_card("Volume Screened", f"${tv.value:,.0f}", "#0891b2")
    else:
        kpi_card("Volume Screened", "N/A", "#6b7280")

st.markdown("<br>", unsafe_allow_html=True)

# --- Charts row ---
col_left, col_right = st.columns([3, 2])

with col_left:
    st.markdown("### Alerts by Rule")
    if not df_alerts.empty:
        sev_map = {r.id: r.severity for r in spec.rules}
        chart_df = df_alerts.groupby("rule_id").size().reset_index(name="count")
        chart_df["severity"] = chart_df["rule_id"].map(sev_map)
        chart_df = chart_df.sort_values("count", ascending=True)
        fig = px.bar(
            chart_df,
            y="rule_id",
            x="count",
            color="severity",
            orientation="h",
            color_discrete_map=SEVERITY_COLORS,
            labels={"rule_id": "", "count": "Alerts"},
        )
        fig.update_layout(yaxis_title="", showlegend=True, legend_title_text="")
        st.plotly_chart(chart_layout(fig, 350), use_container_width=True)
    else:
        st.info("No alerts generated.")

with col_right:
    st.markdown("### RAG Status")
    metric_table(result.metrics, audience=audience)

st.markdown("<br>", unsafe_allow_html=True)

# --- Bottom row: Radar + summary ---
col_radar, col_summary = st.columns([3, 2])

with col_radar:
    st.markdown("### Program Health")
    categories = [m.name[:25] for m in result.metrics if m.rag != "unset"][:8]
    values = []
    colors_list = []
    for m in result.metrics:
        if m.rag == "unset" or len(values) >= 8:
            continue
        score = {"green": 3, "amber": 2, "red": 1}.get(m.rag, 0)
        values.append(score)
        colors_list.append(m.rag)

    if categories and values:
        fig = go.Figure()
        fig.add_trace(
            go.Scatterpolar(
                r=values + [values[0]],
                theta=categories + [categories[0]],
                fill="toself",
                name="Current",
                line=dict(color="#2563eb", width=2),
                fillcolor="rgba(37, 99, 235, 0.15)",
            )
        )
        fig.add_trace(
            go.Scatterpolar(
                r=[3] * (len(categories) + 1),
                theta=categories + [categories[0]],
                fill="toself",
                name="Target",
                line=dict(color="#16a34a", width=1, dash="dot"),
                fillcolor="rgba(22, 163, 74, 0.05)",
            )
        )
        fig.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, range=[0, 3.5], showticklabels=False),
                bgcolor="rgba(0,0,0,0)",
            ),
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=-0.15, x=0.5, xanchor="center"),
        )
        st.plotly_chart(chart_layout(fig, 400), use_container_width=True)

with col_summary:
    st.markdown("### Run Summary")
    st.markdown(
        f"""
| | |
|---|---|
| **Program** | {spec.program.name} |
| **Jurisdiction** | {spec.program.jurisdiction} |
| **Regulator** | {spec.program.regulator} |
| **Rules executed** | {len(spec.rules)} |
| **Total alerts** | {result.total_alerts} |
| **Cases opened** | {len(result.case_ids)} |
| **Metrics computed** | {len(result.metrics)} |
| **Reports generated** | {len(result.reports)} |
"""
    )
