"""Rule Performance -- per-rule analytics and regulation cross-reference."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from aml_framework.dashboard.audience import show_audience_context
from aml_framework.dashboard.components import (
    bar_chart,
    citation_link,
    data_grid,
    empty_state,
    id_link,
    kpi_card,
    page_header,
    pie_chart,
)

page_header(
    "Rule Performance",
    "Is each detector still earning its keep? Volume, severity mix, and the regulation each one answers.",
)
show_audience_context("Rule Performance")

spec = st.session_state.spec
result = st.session_state.result
df_alerts = st.session_state.df_alerts

# Phase E empty-state guard — degenerate specs with zero rules
# previously crashed the styled DataFrame call below
# (`.style.map(_sev_style, subset=["Severity"])` raises when "Severity"
# isn't a column in an empty DataFrame).
if not spec.rules:
    empty_state(
        "This spec declares zero rules — nothing to analyse.",
        icon="📭",
        detail=(
            "Add rules to your spec under the `rules:` section. See the "
            "Typology Catalogue page for 20+ ready-to-customize templates "
            "across structuring, layering, sanctions, behavioral, and "
            "geographic risk."
        ),
        stop=True,
    )

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

# --- Filter controls ---
all_severities = sorted({r.severity for r in spec.rules})
all_logics = sorted({r.logic.type for r in spec.rules})
fc1, fc2, fc3 = st.columns([2, 2, 1])
with fc1:
    selected_severities = st.multiselect(
        "Filter severity",
        options=all_severities,
        default=all_severities,
        help="Limit the table + charts to these severities.",
    )
with fc2:
    selected_logics = st.multiselect(
        "Filter logic type",
        options=all_logics,
        default=all_logics,
        help="aggregation_window / custom_sql / list_match / python_ref / network_pattern.",
    )
with fc3:
    only_fired = st.toggle(
        "Only fired",
        value=False,
        help="Hide rules that produced zero alerts in this run.",
    )

# --- Rule Analytics Table ---
st.markdown("### Rule Analytics")
rows = []
for rule in spec.rules:
    if rule.severity not in selected_severities:
        continue
    if rule.logic.type not in selected_logics:
        continue
    if only_fired and not result.alerts.get(rule.id):
        continue
    alert_count = len(result.alerts.get(rule.id, []))
    alerts = result.alerts.get(rule.id, [])
    cust_alerted = len({a.get("customer_id") for a in alerts if a.get("customer_id")})
    detection_rate = cust_alerted / n_customers if n_customers > 0 else 0
    refs = ", ".join(r.citation for r in rule.regulation_refs)
    rows.append(
        {
            "Rule": rule.id,
            "Name": rule.name,
            "Severity": rule.severity,
            "Logic": rule.logic.type,
            "Alerts": alert_count,
            "Customers": cust_alerted,
            "Detection %": f"{detection_rate:.1%}",
        }
    )

df_rules = pd.DataFrame(rows)
data_grid(
    df_rules,
    key="rule_perf_analytics_table",
    severity_col="Severity" if "Severity" in df_rules.columns else None,
    pinned_left=["Rule"] if "Rule" in df_rules.columns else None,
    height=min(35 * len(df_rules) + 60, 400),
)

# ID-link companion: rule IDs in the table aren't clickable in
# st.dataframe. Surface the rules that have a tuning_grid declared
# as a markdown bullet of links to Tuning Lab — these are the rules
# the MLRO can actually challenge / sweep / promote, so the deep
# link is high-leverage. Skipped silently when no rule has a grid.
_tunable = [r for r in spec.rules if getattr(r, "tuning_grid", None)]
if _tunable:
    rule_links = " · ".join(id_link(r.id, "23_Tuning_Lab", "rule_id") for r in _tunable)
    st.caption(f"🛠 Tunable rules — open one in the lab: {rule_links}")

st.markdown("<br>", unsafe_allow_html=True)

# --- Charts ---
col_left, col_right = st.columns(2)

with col_left:
    st.markdown("### Alerts by Severity")
    sev_data = df_rules.groupby("Severity")["Alerts"].sum().reset_index()
    bar_chart(
        sev_data,
        x="Severity",
        y="Alerts",
        color="Severity",
        height=320,
        key="rule_perf_severity_bar",
    )

with col_right:
    st.markdown("### Detection by Logic Type")
    logic_data = df_rules.groupby("Logic")["Alerts"].sum().reset_index()
    pie_chart(
        logic_data,
        names="Logic",
        values="Alerts",
        donut=True,
        height=320,
        key="rule_perf_logic_pie",
    )

st.markdown("<br>", unsafe_allow_html=True)

# --- Regulation Cross-Reference ---
st.markdown("### Regulation Cross-Reference")
ref_rows = []
for rule in spec.rules:
    for ref in rule.regulation_refs:
        ref_rows.append(
            {
                "Rule": rule.id,
                "Severity": rule.severity,
                # Cite-as-link: when the spec declares a `url`, render
                # the citation as a clickable markdown link so analysts
                # can jump straight to the source. Falls back to plain
                # text when no URL is on file.
                "Citation": citation_link(ref.citation, getattr(ref, "url", None)),
                "Description": ref.description,
            }
        )
df_refs = pd.DataFrame(ref_rows)
# Regulation-refs view — severity colour on each row's Severity cell.
# Citations remain plain text in the grid (AG Grid doesn't render
# embedded markdown either); the markdown companion view below
# turns the [citation](url) strings into live links.
data_grid(
    df_refs,
    key="rule_perf_refs_table",
    severity_col="Severity" if "Severity" in df_refs.columns else None,
    pinned_left=["Rule"] if "Rule" in df_refs.columns else None,
    height=min(35 * len(df_refs) + 60, 400),
)
# Clickable-citation companion view: rendered as a markdown table so
# the `[citation](url)` strings in the "Citation" column become live
# links in the browser. Skipped silently when no rule carries a URL.
if any(getattr(r, "url", None) for rule in spec.rules for r in rule.regulation_refs):
    with st.expander("Citation links (click to open the regulation)", expanded=False):
        st.markdown(df_refs.to_markdown(index=False), unsafe_allow_html=True)

st.markdown("---")
st.caption(
    "**See also** · "
    '[PAIN-3 — "95 of every 100 alerts are noise"]'
    "(https://github.com/tomqwu/aml_open_framework/blob/main/docs/research/2026-04-aml-process-pain.md)"
    ' · [PAIN-6 — "My monitoring system is a model and I cannot validate it"]'
    "(https://github.com/tomqwu/aml_open_framework/blob/main/docs/research/2026-04-aml-process-pain.md)"
    " · [SR 26-2 effective 2026-04-17 in the Regulator Pulse]"
    "(https://github.com/tomqwu/aml_open_framework/blob/main/docs/research/2026-04-regulator-pulse.md)"
)
