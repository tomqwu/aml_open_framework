"""Case Investigation — entity profile, transaction timeline, network graph."""

from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from aml_framework.dashboard.components import page_header

page_header(
    "Case Investigation",
    "Deep-dive into individual cases with entity profile, transaction timeline, and evidence.",
)

spec = st.session_state.spec
result = st.session_state.result
df_cases = st.session_state.df_cases
df_customers = st.session_state.df_customers
df_txns = st.session_state.df_txns

if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo — Case Investigation**\n\n"
        "Select a case to see the full investigation package: entity profile, "
        "triggering transactions highlighted on a timeline, the rule that fired, "
        "regulation citations, and evidence requested. This is what an L1 analyst "
        "sees when they open a case from the queue."
    )

if df_cases.empty:
    st.warning("No cases in this run.")
    st.stop()

# --- Case selector ---
case_ids = sorted(df_cases["case_id"].tolist())
selected_case = st.selectbox("Select case", case_ids)
case = df_cases[df_cases["case_id"] == selected_case].iloc[0].to_dict()

# --- Header ---
sev_colors = {"high": "red", "medium": "orange", "low": "green", "critical": "violet"}
st.markdown(
    f"### Case: `{case['case_id']}`\n"
    f"**Rule:** {case.get('rule_name', case.get('rule_id', ''))} | "
    f"**Severity:** :{sev_colors.get(case.get('severity', ''), 'gray')}[{case.get('severity', '')}] | "
    f"**Queue:** {case.get('queue', '')} | "
    f"**Status:** {case.get('status', '')}"
)

st.divider()

# --- Entity Profile + Alert Details ---
col_profile, col_alert = st.columns(2)

customer_id = case.get("alert", {}).get("customer_id", "")
customer_row = df_customers[df_customers["customer_id"] == customer_id]

with col_profile:
    st.subheader("Entity Profile")
    if not customer_row.empty:
        c = customer_row.iloc[0]
        st.markdown(f"**Customer ID:** {c['customer_id']}")
        st.markdown(f"**Name:** {c['full_name']}")
        st.markdown(f"**Country:** {c['country']}")
        st.markdown(f"**Risk Rating:** {c['risk_rating']}")
        st.markdown(f"**Onboarded:** {c['onboarded_at']}")
    else:
        st.caption(f"Customer {customer_id} not found in dataset.")

with col_alert:
    st.subheader("Alert Details")
    alert_data = case.get("alert", {})
    if "sum_amount" in alert_data:
        st.markdown(f"**Total Amount:** ${float(alert_data['sum_amount']):,.2f}")
    if "count" in alert_data:
        st.markdown(f"**Transaction Count:** {alert_data['count']}")
    if "window_start" in alert_data:
        st.markdown(f"**Window:** {alert_data['window_start']} \u2192 {alert_data['window_end']}")

    # Regulation references
    refs = case.get("regulation_refs", [])
    if refs:
        st.markdown("**Regulation References:**")
        for ref in refs:
            st.markdown(f"- **{ref['citation']}**: {ref['description']}")

st.divider()

# --- Transaction Timeline ---
st.subheader("Transaction Timeline")
if customer_id and not df_txns.empty:
    cust_txns = df_txns[df_txns["customer_id"] == customer_id].copy()
    if not cust_txns.empty:
        cust_txns["booked_at"] = cust_txns["booked_at"].astype(str)
        cust_txns["signed_amount"] = cust_txns.apply(
            lambda r: r["amount"] if r["direction"] == "in" else -r["amount"], axis=1
        )
        fig = px.scatter(
            cust_txns,
            x="booked_at",
            y="signed_amount",
            color="channel",
            size=cust_txns["amount"].abs(),
            hover_data=["txn_id", "direction", "amount", "channel"],
            labels={"booked_at": "Date", "signed_amount": "Amount (signed)"},
            color_discrete_map={
                "cash": "#f59e0b", "wire": "#3b82f6", "ach": "#8b5cf6", "card": "#6b7280"
            },
        )
        # Highlight alert window if available.
        w_start = alert_data.get("window_start")
        w_end = alert_data.get("window_end")
        if w_start and w_end:
            fig.add_vrect(
                x0=str(w_start), x1=str(w_end),
                fillcolor="rgba(239, 68, 68, 0.1)",
                line=dict(color="rgba(239, 68, 68, 0.5)", width=1),
                annotation_text="Alert Window",
                annotation_position="top left",
            )
        fig.update_layout(height=400, margin=dict(t=30))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("No transactions found for this customer.")
else:
    st.caption("No transaction data available.")

st.divider()

# --- Channel Flow (Network-like) ---
st.subheader("Transaction Flow by Channel")
if customer_id and not df_txns.empty:
    cust_txns = df_txns[df_txns["customer_id"] == customer_id].copy()
    if not cust_txns.empty:
        flow = cust_txns.groupby(["channel", "direction"]).agg(
            total=("amount", "sum"), count=("txn_id", "count")
        ).reset_index()

        # Sankey: direction -> customer -> channel
        labels = [customer_id, "Inflows", "Outflows"]
        channels = flow["channel"].unique().tolist()
        labels.extend(channels)

        sources, targets_list, values = [], [], []
        for _, row in flow.iterrows():
            ch_idx = labels.index(row["channel"])
            if row["direction"] == "in":
                sources.append(ch_idx)
                targets_list.append(0)  # customer
            else:
                sources.append(0)  # customer
                targets_list.append(ch_idx)
            values.append(float(row["total"]))

        fig = go.Figure(go.Sankey(
            node=dict(label=labels, pad=15, thickness=20),
            link=dict(source=sources, target=targets_list, value=values),
        ))
        fig.update_layout(height=350, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

# --- Evidence Requested ---
st.subheader("Evidence Requested")
evidence = case.get("evidence_requested", [])
if evidence:
    for item in evidence:
        st.markdown(f"- {item}")
else:
    st.caption("No evidence items specified.")
