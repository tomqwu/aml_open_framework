"""Risk Assessment — customer risk distribution and geographic heatmaps."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from aml_framework.dashboard.components import page_header

page_header(
    "Risk Assessment",
    "Customer risk distribution, geographic exposure, and risk heatmaps.",
)

df_customers = st.session_state.df_customers
df_txns = st.session_state.df_txns
df_alerts = st.session_state.df_alerts

if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo — Risk Assessment**\n\n"
        "This view maps your institution's risk exposure across customers, "
        "geographies, and channels. The heatmap shows where transaction "
        "volume concentrates — high-risk intersections warrant enhanced due diligence."
    )

# --- Customer Risk Distribution ---
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Customer Risk Distribution")
    risk_counts = df_customers["risk_rating"].value_counts().reset_index()
    risk_counts.columns = ["Risk Rating", "Count"]
    color_map = {"high": "#ef4444", "medium": "#f59e0b", "low": "#22c55e"}
    fig = px.pie(
        risk_counts, names="Risk Rating", values="Count",
        color="Risk Rating", color_discrete_map=color_map,
    )
    fig.update_layout(height=350, margin=dict(t=10))
    st.plotly_chart(fig, use_container_width=True)

with col_right:
    st.subheader("Customer Geography")
    geo_counts = df_customers["country"].value_counts().reset_index()
    geo_counts.columns = ["Country", "Count"]
    fig = px.bar(
        geo_counts, x="Country", y="Count", color="Country",
    )
    fig.update_layout(height=350, margin=dict(t=10), showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# --- Transaction Volume by Geography ---
st.subheader("Transaction Volume by Country")
if not df_txns.empty:
    # Join customer country to transactions.
    txn_with_country = df_txns.merge(
        df_customers[["customer_id", "country", "risk_rating"]],
        on="customer_id", how="left",
    )
    geo_vol = txn_with_country.groupby("country")["amount"].sum().reset_index()
    geo_vol.columns = ["Country", "Total Volume"]
    fig = px.bar(
        geo_vol.sort_values("Total Volume", ascending=False),
        x="Country", y="Total Volume",
        color="Total Volume", color_continuous_scale="Reds",
    )
    fig.update_layout(height=350, margin=dict(t=10))
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# --- Risk Heatmap: Risk Rating x Channel ---
st.subheader("Risk Heatmap: Risk Rating \u00d7 Channel")
if not df_txns.empty:
    txn_with_risk = df_txns.merge(
        df_customers[["customer_id", "risk_rating"]],
        on="customer_id", how="left",
    )
    pivot = txn_with_risk.groupby(["risk_rating", "channel"])["amount"].sum().reset_index()
    heatmap_data = pivot.pivot_table(index="risk_rating", columns="channel", values="amount", fill_value=0)
    # Reorder risk ratings.
    order = ["low", "medium", "high"]
    heatmap_data = heatmap_data.reindex([r for r in order if r in heatmap_data.index])

    fig = px.imshow(
        heatmap_data,
        labels=dict(x="Channel", y="Risk Rating", color="Volume ($)"),
        color_continuous_scale="YlOrRd",
        aspect="auto",
        text_auto=".0f",
    )
    fig.update_layout(height=400, margin=dict(t=10))
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# --- Alerted Customers Profile ---
st.subheader("Alerted Customers")
if not df_alerts.empty and "customer_id" in df_alerts.columns:
    alerted_ids = df_alerts["customer_id"].dropna().unique()
    alerted_customers = df_customers[df_customers["customer_id"].isin(alerted_ids)]
    st.dataframe(
        alerted_customers[["customer_id", "full_name", "country", "risk_rating", "onboarded_at"]],
        use_container_width=True, hide_index=True,
    )
else:
    st.caption("No alerts with customer data.")
