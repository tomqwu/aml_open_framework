"""Rule Performance — per-rule analytics and regulation cross-reference."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from aml_framework.dashboard.components import page_header

page_header(
    "Rule Performance",
    "Per-rule alert analytics, severity distribution, and regulation mapping.",
)

spec = st.session_state.spec
result = st.session_state.result
df_alerts = st.session_state.df_alerts

if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo — Rule Performance**\n\n"
        "This view shows how each rule performed: alert counts, detection "
        "rates, and the regulation citations that justify each rule. "
        "In a production deployment, you'd also see false positive rates "
        "and threshold tuning recommendations."
    )

# --- Rule Metrics Table ---
st.subheader("Rule Analytics")

rows = []
n_customers = len(st.session_state.df_customers)
for rule in spec.rules:
    alert_count = len(result.alerts.get(rule.id, []))
    alerts = result.alerts.get(rule.id, [])
    cust_alerted = len({a.get("customer_id") for a in alerts if a.get("customer_id")})
    detection_rate = cust_alerted / n_customers if n_customers > 0 else 0
    refs = ", ".join(r.citation for r in rule.regulation_refs)
    rows.append({
        "Rule ID": rule.id,
        "Name": rule.name,
        "Severity": rule.severity,
        "Status": rule.status,
        "Logic Type": rule.logic.type,
        "Alerts": alert_count,
        "Customers": cust_alerted,
        "Detection Rate": f"{detection_rate:.1%}",
        "Regulations": refs,
    })

df_rules = pd.DataFrame(rows)
st.dataframe(df_rules, use_container_width=True, hide_index=True)

st.divider()

# --- Alert Distribution ---
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Alerts by Severity")
    sev_data = df_rules.groupby("Severity")["Alerts"].sum().reset_index()
    color_map = {"high": "#ef4444", "medium": "#f59e0b", "low": "#22c55e", "critical": "#7c3aed"}
    fig = px.bar(
        sev_data, x="Severity", y="Alerts", color="Severity",
        color_discrete_map=color_map,
    )
    fig.update_layout(height=350, margin=dict(t=10), showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

with col_right:
    st.subheader("Detection Coverage")
    logic_data = df_rules.groupby("Logic Type")["Alerts"].sum().reset_index()
    fig = px.pie(logic_data, names="Logic Type", values="Alerts")
    fig.update_layout(height=350, margin=dict(t=10))
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# --- Regulation Cross-Reference Matrix ---
st.subheader("Rule \u2192 Regulation Cross-Reference")
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
st.dataframe(df_refs, use_container_width=True, hide_index=True)

# --- Tags / Typology Coverage ---
st.subheader("Typology Tag Coverage")
all_tags = set()
fired_tags = set()
for rule in spec.rules:
    all_tags.update(rule.tags)
    if result.alerts.get(rule.id):
        fired_tags.update(rule.tags)
unfired = all_tags - fired_tags

tag_data = []
for tag in sorted(all_tags):
    tag_data.append({
        "Tag": tag,
        "Status": "Fired" if tag in fired_tags else "Not Fired",
    })
df_tags = pd.DataFrame(tag_data)
st.dataframe(df_tags, use_container_width=True, hide_index=True)
