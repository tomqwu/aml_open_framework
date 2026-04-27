"""Sanctions Screening -- match results and review queue."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from aml_framework.dashboard.components import kpi_card, page_header
from aml_framework.dashboard.audience import show_audience_context

page_header(
    "Sanctions Screening",
    "Sanctions list match results from SEMA, OFAC SDN, and other reference lists.",
)
show_audience_context("Sanctions Screening")

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

# --- Filter controls ---
all_match_types = sorted({a.get("match_type", "") for a in sanctions_alerts if a.get("match_type")})
all_severities = sorted({a.get("severity", "") for a in sanctions_alerts if a.get("severity")})
fc1, fc2, fc3 = st.columns([2, 2, 1])
with fc1:
    selected_match_types = st.multiselect(
        "Filter match type",
        options=all_match_types,
        default=all_match_types,
        help="Show only exact / fuzzy matches.",
    )
with fc2:
    selected_severities = st.multiselect(
        "Filter severity",
        options=all_severities,
        default=all_severities,
    )
with fc3:
    min_score = st.slider(
        "Min match score",
        min_value=0.0,
        max_value=1.0,
        value=0.0,
        step=0.05,
        help="Hide matches scoring below this confidence threshold.",
    )

# Apply filters to the working set.
filtered_alerts = [
    a
    for a in sanctions_alerts
    if (not selected_match_types or a.get("match_type") in selected_match_types)
    and (not selected_severities or a.get("severity") in selected_severities)
    and (a.get("match_score", 1.0) or 1.0) >= min_score
]

# Match results table.
if filtered_alerts:
    st.markdown(f"### Match Results ({len(filtered_alerts)} of {len(sanctions_alerts)} shown)")
    match_df = pd.DataFrame(filtered_alerts)
    show_cols = [
        "customer_id",
        "matched_name",
        "list_name",
        "match_type",
        "match_score",
        "severity",
    ]
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
    matched_ids = [a["customer_id"] for a in filtered_alerts]
    matched = df_customers[df_customers["customer_id"].isin(matched_ids)]
    cols = ["customer_id", "full_name", "country", "risk_rating"]
    st.dataframe(
        matched[[c for c in cols if c in matched.columns]],
        use_container_width=True,
        hide_index=True,
    )
elif sanctions_alerts:
    st.info(
        f"No matches pass the current filters "
        f"({len(sanctions_alerts)} total matches available). Adjust the filters above."
    )
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


# ---------------------------------------------------------------------------
# VoP outcomes (PSD3 / Verification of Payee — Round-7 PR #77)
# ---------------------------------------------------------------------------
# When the txn data carries a `confirmation_of_payee_status` column
# (populated by the data/psd3 ingestion adapter or the UK CoP scheme),
# this section breaks down the outcomes. PSD3 + UK PSR SD17 use the
# same vocabulary so one column serves both regulators.
st.markdown("<br>", unsafe_allow_html=True)
st.markdown("### Verification of Payee outcomes (PSD3 / UK CoP)")
st.caption(
    "Per-outcome breakdown of payee-name verification responses. Same "
    "vocabulary covers EU PSD3 VoP and UK Confirmation of Payee — one "
    "txn column for both regulators. Populated by `data/psd3` ingestion "
    "or written directly by the UK CoP scheme."
)
df_txns = st.session_state.get("df_txns")
if df_txns is None or df_txns.empty:
    st.caption("No transaction data loaded.")
elif "confirmation_of_payee_status" not in df_txns.columns:
    st.info(
        "This run's txn data does not carry a `confirmation_of_payee_status` "
        "column. Populate it via the `data/psd3` adapter or by extending "
        "your `txn` data contract. (Round-5 ISO 20022 enrichment leaves "
        "this field blank by default; UK APP-fraud spec declares it.)"
    )
else:
    _vop_status = df_txns["confirmation_of_payee_status"].fillna("").replace("", "not_set")
    _vop_counts = _vop_status.value_counts().reset_index()
    _vop_counts.columns = ["outcome", "count"]

    # 5 PSD3 outcomes per data/psd3/parser.py:VOP_OUTCOMES + the
    # synthetic "not_set" bucket for txns that haven't been screened.
    _vop_kpi_cols = st.columns(5)
    _vop_outcomes_order = ["match", "close_match", "no_match", "not_checked", "outside_scope"]
    _vop_outcome_colors = {
        "match": "#16a34a",
        "close_match": "#d97706",
        "no_match": "#dc2626",
        "not_checked": "#6b7280",
        "outside_scope": "#0891b2",
    }
    for _idx, _outcome in enumerate(_vop_outcomes_order):
        _count = int(_vop_counts.loc[_vop_counts["outcome"] == _outcome, "count"].sum())
        with _vop_kpi_cols[_idx]:
            kpi_card(_outcome, _count, _vop_outcome_colors[_outcome])
    # Show the table in case operators want to see counts for non-canonical
    # outcome values (e.g. "not_set" or institution-specific extensions).
    st.dataframe(_vop_counts, use_container_width=True, hide_index=True)
