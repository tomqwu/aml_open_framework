"""Typology Catalogue -- pre-built AML rule templates."""

from __future__ import annotations

import streamlit as st

from aml_framework.dashboard.components import kpi_card, page_header

page_header(
    "Typology Catalogue",
    "Pre-built AML detection rule templates covering major financial crime patterns.",
)

TYPOLOGIES = [
    {
        "category": "Structuring",
        "rules": [
            {
                "name": "Cash structuring below reporting threshold",
                "severity": "high",
                "logic": "aggregation_window",
                "description": "Multiple cash deposits just below CTR/LCTR threshold within 30 days.",
            },
            {
                "name": "Structured wire transfers",
                "severity": "high",
                "logic": "aggregation_window",
                "description": "Multiple outgoing wires kept below reporting thresholds.",
            },
        ],
    },
    {
        "category": "Layering",
        "rules": [
            {
                "name": "Rapid pass-through",
                "severity": "critical",
                "logic": "custom_sql",
                "description": "Cash-in followed by wire/e-transfer-out within 48 hours.",
            },
            {
                "name": "Round-tripping",
                "severity": "high",
                "logic": "custom_sql",
                "description": "Circular fund flows returning to originator via intermediaries.",
            },
            {
                "name": "Funnel account",
                "severity": "high",
                "logic": "custom_sql",
                "description": "Many-to-one deposits from multiple sources into a single account.",
            },
        ],
    },
    {
        "category": "Shell Companies",
        "rules": [
            {
                "name": "Shell company indicators",
                "severity": "high",
                "logic": "custom_sql",
                "description": "Entity with no declared business receiving high-volume multi-jurisdiction wires.",
            },
            {
                "name": "Nominee account patterns",
                "severity": "high",
                "logic": "custom_sql",
                "description": "Account activity inconsistent with declared beneficial owner profile.",
            },
        ],
    },
    {
        "category": "Sanctions & PEP",
        "rules": [
            {
                "name": "Sanctions list screening",
                "severity": "critical",
                "logic": "list_match",
                "description": "Fuzzy match customer names against OFAC SDN, SEMA, EU sanctions lists.",
            },
            {
                "name": "PEP screening",
                "severity": "critical",
                "logic": "custom_sql",
                "description": "Enhanced monitoring for Politically Exposed Persons with significant activity.",
            },
            {
                "name": "Adverse media screening",
                "severity": "medium",
                "logic": "list_match",
                "description": "Match customer names against adverse media databases.",
            },
        ],
    },
    {
        "category": "Behavioral Anomalies",
        "rules": [
            {
                "name": "Unusual volume spike",
                "severity": "medium",
                "logic": "custom_sql",
                "description": "Recent activity exceeds 5x historical baseline.",
            },
            {
                "name": "Dormant account reactivation",
                "severity": "high",
                "logic": "custom_sql",
                "description": "Account inactive for 45+ days then sudden large activity.",
            },
            {
                "name": "Channel switching",
                "severity": "medium",
                "logic": "custom_sql",
                "description": "Sudden change from normal channels to high-risk channels.",
            },
        ],
    },
    {
        "category": "Trade-Based ML",
        "rules": [
            {
                "name": "Over/under invoicing",
                "severity": "high",
                "logic": "custom_sql",
                "description": "Trade invoice amounts significantly deviate from market prices.",
            },
            {
                "name": "Phantom shipments",
                "severity": "critical",
                "logic": "custom_sql",
                "description": "Trade payments with no corresponding goods movement.",
            },
        ],
    },
    {
        "category": "Mule Activity",
        "rules": [
            {
                "name": "Money mule detection",
                "severity": "high",
                "logic": "python_ref",
                "description": "ML-scored behavioral patterns consistent with mule recruitment.",
            },
            {
                "name": "Rapid onboarding + high volume",
                "severity": "medium",
                "logic": "custom_sql",
                "description": "New account with immediate high transaction volume.",
            },
        ],
    },
    {
        "category": "Crypto / Virtual Assets",
        "rules": [
            {
                "name": "Crypto-to-fiat conversion",
                "severity": "medium",
                "logic": "aggregation_window",
                "description": "Large virtual currency conversions to fiat within short windows.",
            },
            {
                "name": "Mixing service indicators",
                "severity": "high",
                "logic": "custom_sql",
                "description": "Transaction patterns consistent with cryptocurrency mixing services.",
            },
        ],
    },
    {
        "category": "Geographic Risk",
        "rules": [
            {
                "name": "High-risk jurisdiction activity",
                "severity": "high",
                "logic": "custom_sql",
                "description": "Significant transaction volume with FATF grey/black list countries.",
            },
            {
                "name": "Cross-border velocity",
                "severity": "medium",
                "logic": "aggregation_window",
                "description": "High frequency of cross-border transfers in short time windows.",
            },
        ],
    },
]

# KPIs.
total_rules = sum(len(cat["rules"]) for cat in TYPOLOGIES)
c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card("Categories", len(TYPOLOGIES), "#2563eb")
with c2:
    kpi_card("Rule Templates", total_rules, "#7c3aed")
with c3:
    critical = sum(1 for cat in TYPOLOGIES for r in cat["rules"] if r["severity"] == "critical")
    kpi_card("Critical", critical, "#dc2626")
with c4:
    logic_types = len({r["logic"] for cat in TYPOLOGIES for r in cat["rules"]})
    kpi_card("Logic Types", logic_types, "#059669")

st.markdown("<br>", unsafe_allow_html=True)

# Render each category.
for cat in TYPOLOGIES:
    with st.expander(f"**{cat['category']}** ({len(cat['rules'])} rules)"):
        for rule in cat["rules"]:
            sev_colors = {
                "critical": "#7c3aed",
                "high": "#dc2626",
                "medium": "#d97706",
                "low": "#16a34a",
            }
            color = sev_colors.get(rule["severity"], "#6b7280")
            st.markdown(
                f'<div class="metric-card" style="border-left:4px solid {color}; margin-bottom:0.5rem;">'
                f'<div style="font-weight:600;">{rule["name"]}</div>'
                f'<div style="font-size:0.85rem; color:#64748b; margin:0.2rem 0;">'
                f"{rule['description']}</div>"
                f'<div style="font-size:0.78rem;">'
                f'<span style="color:{color}; font-weight:700;">{rule["severity"].upper()}</span>'
                f" &middot; <code>{rule['logic']}</code></div>"
                f"</div>",
                unsafe_allow_html=True,
            )

st.markdown("<br>", unsafe_allow_html=True)
st.caption(
    "These are reference templates. To use a typology, add the corresponding "
    "rule to your aml.yaml spec with institution-specific thresholds and "
    "regulation citations."
)
