"""Sanctions Screening -- match results and review queue."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from aml_framework.dashboard.components import kpi_card, page_header

page_header(
    "Sanctions Screening",
    "Sanctions list match results from SEMA, OFAC SDN, and other reference lists.",
)

spec = st.session_state.spec
result = st.session_state.result
df_alerts = st.session_state.df_alerts
df_customers = st.session_state.df_customers

# Find sanctions-related alerts.
sanctions_rules = [r for r in spec.rules if r.logic.type == "list_match"]
sanctions_alerts = []
for rule in sanctions_rules:
    for alert in result.alerts.get(rule.id, []):
        sanctions_alerts.append({"rule": rule.id, "severity": rule.severity, **alert})

if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo -- Sanctions Screening**\n\n"
        f"The engine screened **{len(df_customers)}** customers against "
        f"reference sanctions lists and found **{len(sanctions_alerts)}** matches. "
        "Each match shows the customer name, matched list entry, match type "
        "(exact or fuzzy), and confidence score."
    )

# KPIs.
c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card("Customers Screened", len(df_customers), "#2563eb")
with c2:
    kpi_card("Matches Found", len(sanctions_alerts), "#dc2626")
with c3:
    exact = sum(1 for a in sanctions_alerts if a.get("match_type") == "exact")
    kpi_card("Exact Matches", exact, "#7c3aed")
with c4:
    fuzzy = sum(1 for a in sanctions_alerts if a.get("match_type") == "fuzzy")
    kpi_card("Fuzzy Matches", fuzzy, "#d97706")

st.markdown("<br>", unsafe_allow_html=True)

# Match results table.
if sanctions_alerts:
    st.markdown("### Match Results")
    match_df = pd.DataFrame(sanctions_alerts)
    show_cols = ["customer_id", "matched_name", "list_name", "match_type", "match_score", "severity"]
    available = [c for c in show_cols if c in match_df.columns]
    if "list_entry" in match_df.columns:
        available.insert(2, "list_entry")

    def _score_color(val):
        if isinstance(val, float):
            if val >= 0.95:
                return "color: #dc2626; font-weight: 700;"
            if val >= 0.8:
                return "color: #d97706; font-weight: 700;"
        return ""

    styled = match_df[available].style.map(_score_color, subset=["match_score"])
    st.dataframe(styled, use_container_width=True, hide_index=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Matched customer profiles.
    st.markdown("### Matched Customer Profiles")
    matched_ids = [a["customer_id"] for a in sanctions_alerts]
    matched = df_customers[df_customers["customer_id"].isin(matched_ids)]
    cols = ["customer_id", "full_name", "country", "risk_rating"]
    st.dataframe(matched[[c for c in cols if c in matched.columns]],
                 use_container_width=True, hide_index=True)
else:
    st.success("No sanctions matches found.")

# List of screening rules.
st.markdown("<br>", unsafe_allow_html=True)
st.markdown("### Screening Rules in Spec")
for rule in sanctions_rules:
    st.markdown(
        f"- **{rule.id}** — list: `{rule.logic.list}`, "
        f"field: `{rule.logic.field}`, match: `{rule.logic.match}`, "
        f"threshold: {rule.logic.threshold or 'N/A'}"
    )
