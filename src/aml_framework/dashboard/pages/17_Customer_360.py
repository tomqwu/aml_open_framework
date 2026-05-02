"""Customer 360 -- complete view of a single customer across all data."""

from __future__ import annotations

import streamlit as st

from aml_framework.dashboard.audience import show_audience_context
from aml_framework.dashboard.components import (
    bar_chart,
    data_grid,
    kpi_card,
    page_header,
    pie_chart,
    risk_color,
    tooltip_banner,
    tour_panel,
)
from aml_framework.dashboard.query_params import read_param

page_header(
    "Customer 360",
    "Complete view of a customer: profile, transactions, alerts, cases, and risk.",
)
show_audience_context("Customer 360")

df_customers = st.session_state.df_customers
df_txns = st.session_state.df_txns
df_alerts = st.session_state.df_alerts
df_cases = st.session_state.df_cases
spec = st.session_state.spec

tour_panel("Customer 360")
tooltip_banner(
    "Customer 360",
    "Select a customer to see their complete profile: KYC data, "
    "transaction history, alerts triggered, open cases, and risk "
    "indicators. This is the view an analyst uses for investigation.",
)

# --- Customer selector ---
# Pre-select via deep link from Alert Queue / Network Explorer / Executive
# Dashboard. `read_param` (not consume_param) keeps the value sticky across
# page reruns so a selectbox change still works without losing the link state.
customer_ids = sorted(df_customers["customer_id"].tolist())
deep_link_cid = read_param("customer_id")
default_cid_idx = customer_ids.index(deep_link_cid) if deep_link_cid in customer_ids else 0
selected_cid = st.selectbox("Select customer", customer_ids, index=default_cid_idx)

cust = df_customers[df_customers["customer_id"] == selected_cid].iloc[0]

# --- Profile card ---
profile_color = risk_color(cust["risk_rating"])
st.markdown(
    f'<div class="metric-card" style="border-left: 4px solid {profile_color};">'
    f'<div style="font-size:1.3rem; font-weight:700;">{cust["full_name"]}</div>'
    f'<div style="color:#64748b; margin:0.3rem 0;">'
    f"{cust['customer_id']} &middot; {cust['country']} &middot; "
    f'<span style="color:{profile_color}; font-weight:700;">{cust["risk_rating"].upper()}</span>'
    f"</div>"
    f'<div style="font-size:0.85rem; color:#64748b;">'
    f"Onboarded: {str(cust['onboarded_at'])[:10]}"
    f"</div>"
    f"</div>",
    unsafe_allow_html=True,
)

st.markdown("<br>", unsafe_allow_html=True)

# --- KPIs ---
cust_txns = df_txns[df_txns["customer_id"] == selected_cid]
cust_alerts = (
    df_alerts[df_alerts["customer_id"] == selected_cid]
    if not df_alerts.empty and "customer_id" in df_alerts.columns
    else df_alerts.iloc[0:0]
)
cust_cases = (
    df_cases[df_cases["case_id"].str.contains(selected_cid, na=False)]
    if not df_cases.empty
    else df_cases.iloc[0:0]
)

c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card("Transactions", len(cust_txns), "#2563eb")
with c2:
    total_vol = float(cust_txns["amount"].sum()) if not cust_txns.empty else 0
    kpi_card("Total Volume", f"${total_vol:,.0f}", "#059669")
with c3:
    kpi_card("Alerts", len(cust_alerts), "#dc2626" if len(cust_alerts) > 0 else "#6b7280")
with c4:
    open_cases = (
        len(cust_cases[cust_cases["status"] != "closed_no_action"])
        if not cust_cases.empty and "status" in cust_cases.columns
        else 0
    )
    kpi_card("Open Cases", open_cases, "#d97706" if open_cases > 0 else "#6b7280")

st.markdown("<br>", unsafe_allow_html=True)

# --- Transaction history ---
st.markdown("### Transaction History")
if not cust_txns.empty:
    col_chart, col_table = st.columns([3, 2])
    with col_chart:
        txn_plot = cust_txns.copy()
        txn_plot["booked_at"] = txn_plot["booked_at"].astype(str)
        txn_plot["signed"] = txn_plot.apply(
            lambda r: r["amount"] if r["direction"] == "in" else -r["amount"], axis=1
        )
        # Channel hue carries from the centralised categorical palette
        # in chart_theme — no per-page colour map. Direction-signed
        # amount preserved via the `signed` column (in: positive,
        # out: negative).
        bar_chart(
            txn_plot,
            x="booked_at",
            y="signed",
            color="channel",
            title="Transaction History (signed)",
            height=300,
            key="customer360_txn_history",
        )

    with col_table:
        show = ["booked_at", "amount", "channel", "direction"]
        available = [c for c in show if c in cust_txns.columns]
        data_grid(
            cust_txns[available].sort_values("booked_at", ascending=False),
            key="customer360_txn_table",
            pinned_left=["booked_at"] if "booked_at" in available else None,
            height=300,
        )
else:
    st.caption("No transactions for this customer.")

st.markdown("<br>", unsafe_allow_html=True)

# --- Alerts ---
st.markdown("### Alerts")
if not cust_alerts.empty:
    sev_map = {r.id: r.severity for r in spec.rules}
    alert_display = cust_alerts.copy()
    if "rule_id" in alert_display.columns:
        alert_display["severity"] = alert_display["rule_id"].map(sev_map)
    show_cols = ["rule_id", "severity", "sum_amount", "count", "window_start", "window_end"]
    available = [c for c in show_cols if c in alert_display.columns]
    # Per-customer alerts table — no drill (alerts are already scoped
    # to this customer). Severity column gets the gradient cell colour
    # so high/critical entries jump off the row.
    data_grid(
        alert_display[available],
        key="customer360_alerts_table",
        severity_col="severity",
        pinned_left=["rule_id"] if "rule_id" in available else None,
        height=300,
    )
else:
    st.success("No alerts for this customer.")

# --- Cases (with live SLA) ---
st.markdown("### Cases")
if not cust_cases.empty:
    from datetime import datetime, timezone

    from aml_framework.cases.sla import compute_sla_status

    show_cols = ["case_id", "rule_id", "severity", "status"]
    # Live SLA per case — same helpers My Queue uses; computed against
    # the engine's as_of timestamp for determinism.
    queue_map = {q.id: q for q in spec.workflow.queues}
    as_of = st.session_state.get("as_of") or datetime.now(tz=timezone.utc).replace(tzinfo=None)

    def _sla_state(row: dict) -> str:
        queue_obj = queue_map.get(row.get("queue", ""))
        if queue_obj is None:
            return "—"
        status = compute_sla_status(row, queue_obj, as_of=as_of)
        return status["state"] if status is not None else "—"

    cust_cases = cust_cases.copy()
    cust_cases["sla_state"] = [_sla_state(r) for r in cust_cases.to_dict(orient="records")]
    show_cols = show_cols + ["sla_state"]

    available = [c for c in show_cols if c in cust_cases.columns]
    data_grid(
        cust_cases[available],
        key="customer360_cases_table",
        severity_col="severity",
        rag_col="sla_state",
        pinned_left=["case_id"],
        drill_target="pages/4_Case_Investigation.py",
        drill_param="case_id",
        drill_column="case_id",
        hint="Click any case row to open the investigation package.",
        height=300,
    )
else:
    st.caption("No cases for this customer.")

# --- Channel breakdown ---
st.markdown("### Channel Breakdown")
if not cust_txns.empty:
    channel_vol = cust_txns.groupby("channel")["amount"].agg(["sum", "count"]).reset_index()
    channel_vol.columns = ["Channel", "Volume", "Count"]
    pie_chart(
        channel_vol,
        names="Channel",
        values="Volume",
        donut=True,
        height=300,
        key="customer360_channel_pie",
    )
