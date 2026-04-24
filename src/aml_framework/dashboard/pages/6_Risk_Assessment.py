"""Risk Assessment -- customer risk distribution and geographic heatmaps."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from aml_framework.dashboard.components import chart_layout, kpi_card, page_header
from aml_framework.dashboard.audience import show_audience_context

page_header(
    "Risk Assessment",
    "Customer risk distribution, geographic exposure, and risk heatmaps.",
)
show_audience_context("Risk Assessment")

df_customers = st.session_state.df_customers
df_txns = st.session_state.df_txns
df_alerts = st.session_state.df_alerts

if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo -- Risk Assessment**\n\n"
        "Maps your institution's risk exposure across customers, geographies, "
        "and channels. The heatmap highlights where volume concentrates."
    )

# --- KPI row ---
risk_counts = df_customers["risk_rating"].value_counts()
c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card("Total Customers", len(df_customers), "#2563eb")
with c2:
    kpi_card("High Risk", int(risk_counts.get("high", 0)), "#dc2626")
with c3:
    kpi_card("Medium Risk", int(risk_counts.get("medium", 0)), "#d97706")
with c4:
    kpi_card("Countries", df_customers["country"].nunique(), "#059669")

st.markdown("<br>", unsafe_allow_html=True)

# --- Row 1: Pie + Geography ---
col_left, col_right = st.columns(2)

with col_left:
    st.markdown("### Customer Risk Distribution")
    rc = risk_counts.reset_index()
    rc.columns = ["Risk Rating", "Count"]
    color_map = {"high": "#dc2626", "medium": "#d97706", "low": "#16a34a"}
    fig = px.pie(
        rc, names="Risk Rating", values="Count",
        color="Risk Rating", color_discrete_map=color_map,
        hole=0.45,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    st.plotly_chart(chart_layout(fig, 340), use_container_width=True)

with col_right:
    st.markdown("### Customer Geography")
    geo = df_customers["country"].value_counts().reset_index()
    geo.columns = ["Country", "Count"]
    fig = px.bar(
        geo, x="Country", y="Count",
        color="Count", color_continuous_scale="Blues",
    )
    fig.update_layout(coloraxis_showscale=False, xaxis_title="", yaxis_title="")
    st.plotly_chart(chart_layout(fig, 340), use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)

# --- Transaction Volume by Country ---
st.markdown("### Transaction Volume by Country")
if not df_txns.empty:
    txn_with_country = df_txns.merge(
        df_customers[["customer_id", "country", "risk_rating"]],
        on="customer_id", how="left",
    )
    geo_vol = txn_with_country.groupby("country")["amount"].sum().reset_index()
    geo_vol.columns = ["Country", "Total Volume"]
    geo_vol = geo_vol.sort_values("Total Volume", ascending=False)
    fig = px.bar(
        geo_vol, x="Country", y="Total Volume",
        color="Total Volume", color_continuous_scale="Reds",
    )
    fig.update_layout(coloraxis_showscale=False, xaxis_title="", yaxis_title="Volume ($)")
    st.plotly_chart(chart_layout(fig, 340), use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)

# --- Heatmap: Risk x Channel ---
st.markdown("### Risk Heatmap: Risk Rating x Channel")
if not df_txns.empty:
    txn_with_risk = df_txns.merge(
        df_customers[["customer_id", "risk_rating"]], on="customer_id", how="left",
    )
    pivot = txn_with_risk.groupby(["risk_rating", "channel"])["amount"].sum().reset_index()
    heatmap_data = pivot.pivot_table(
        index="risk_rating", columns="channel", values="amount", fill_value=0,
    )
    order = ["low", "medium", "high"]
    heatmap_data = heatmap_data.reindex([r for r in order if r in heatmap_data.index])

    fig = px.imshow(
        heatmap_data,
        labels=dict(x="Channel", y="Risk Rating", color="Volume ($)"),
        color_continuous_scale="YlOrRd",
        aspect="auto",
        text_auto=",.0f",
    )
    st.plotly_chart(chart_layout(fig, 350), use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)

# --- Alerted Customers ---
st.markdown("### Alerted Customers")
if not df_alerts.empty and "customer_id" in df_alerts.columns:
    alerted_ids = df_alerts["customer_id"].dropna().unique()
    alerted = df_customers[df_customers["customer_id"].isin(alerted_ids)].copy()

    def _risk_style(val: str) -> str:
        c = {"high": "#dc2626", "medium": "#d97706", "low": "#16a34a"}.get(val, "")
        return f"color: {c}; font-weight: 700;" if c else ""

    styled = alerted[
        ["customer_id", "full_name", "country", "risk_rating"]
    ].style.map(_risk_style, subset=["risk_rating"])
    st.dataframe(styled, use_container_width=True, hide_index=True)
else:
    st.caption("No alerts with customer data.")
