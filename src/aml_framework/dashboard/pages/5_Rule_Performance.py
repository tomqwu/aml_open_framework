"""Rule Performance -- per-rule analytics and regulation cross-reference."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from aml_framework.dashboard.components import SEVERITY_COLORS, chart_layout, kpi_card, page_header

page_header(
    "Rule Performance",
    "Per-rule alert analytics, severity distribution, and regulation mapping.",
)

spec = st.session_state.spec
result = st.session_state.result
df_alerts = st.session_state.df_alerts

if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo -- Rule Performance**\n\n"
        "Each rule's detection rate, alert counts, and regulation citations. "
        "In production, this drives threshold tuning and model validation."
    )

# --- KPI row ---
n_customers = len(st.session_state.df_customers)
total_alerts = result.total_alerts
rules_fired = sum(1 for r in spec.rules if result.alerts.get(r.id))
c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card("Active Rules", len([r for r in spec.rules if r.status == "active"]), "#2563eb")
with c2:
    kpi_card("Rules Fired", rules_fired, "#059669")
with c3:
    kpi_card("Total Alerts", total_alerts, "#d97706")
with c4:
    tags = {t for r in spec.rules for t in r.tags}
    fired_tags = {t for r in spec.rules for t in r.tags if result.alerts.get(r.id)}
    coverage = f"{len(fired_tags)}/{len(tags)}" if tags else "N/A"
    kpi_card("Tag Coverage", coverage, "#7c3aed")

st.markdown("<br>", unsafe_allow_html=True)

# --- Rule Analytics Table ---
st.markdown("### Rule Analytics")
rows = []
for rule in spec.rules:
    alert_count = len(result.alerts.get(rule.id, []))
    alerts = result.alerts.get(rule.id, [])
    cust_alerted = len({a.get("customer_id") for a in alerts if a.get("customer_id")})
    detection_rate = cust_alerted / n_customers if n_customers > 0 else 0
    refs = ", ".join(r.citation for r in rule.regulation_refs)
    rows.append({
        "Rule": rule.id,
        "Name": rule.name,
        "Severity": rule.severity,
        "Logic": rule.logic.type,
        "Alerts": alert_count,
        "Customers": cust_alerted,
        "Detection %": f"{detection_rate:.1%}",
    })

df_rules = pd.DataFrame(rows)

def _sev_style(val: str) -> str:
    c = SEVERITY_COLORS.get(val, "")
    return f"color: {c}; font-weight: 700;" if c else ""

styled = df_rules.style.map(_sev_style, subset=["Severity"])
st.dataframe(styled, use_container_width=True, hide_index=True)

st.markdown("<br>", unsafe_allow_html=True)

# --- Charts ---
col_left, col_right = st.columns(2)

with col_left:
    st.markdown("### Alerts by Severity")
    sev_data = df_rules.groupby("Severity")["Alerts"].sum().reset_index()
    fig = px.bar(
        sev_data, x="Severity", y="Alerts", color="Severity",
        color_discrete_map=SEVERITY_COLORS,
    )
    fig.update_layout(showlegend=False)
    st.plotly_chart(chart_layout(fig, 320), use_container_width=True)

with col_right:
    st.markdown("### Detection by Logic Type")
    logic_data = df_rules.groupby("Logic")["Alerts"].sum().reset_index()
    fig = px.pie(logic_data, names="Logic", values="Alerts", hole=0.45,
                 color_discrete_sequence=["#2563eb", "#7c3aed", "#d97706"])
    fig.update_traces(textposition="inside", textinfo="percent+label")
    st.plotly_chart(chart_layout(fig, 320), use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)

# --- Regulation Cross-Reference ---
st.markdown("### Regulation Cross-Reference")
ref_rows = []
for rule in spec.rules:
    for ref in rule.regulation_refs:
        ref_rows.append({
            "Rule": rule.id,
            "Severity": rule.severity,
            "Citation": ref.citation,
            "Description": ref.description,
        })
df_refs = pd.DataFrame(ref_rows)
st.dataframe(
    df_refs.style.map(_sev_style, subset=["Severity"]),
    use_container_width=True, hide_index=True,
)
