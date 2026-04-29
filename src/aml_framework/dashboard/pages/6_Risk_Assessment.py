"""Risk Assessment -- customer risk distribution and geographic heatmaps."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from aml_framework.dashboard.components import (
    RISK_RATING_COLORS,
    chart_layout,
    kpi_card_rag,
    page_header,
    risk_color,
)
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

# --- Filter controls ---
all_countries = sorted(df_customers["country"].dropna().unique())
all_risks = sorted(df_customers["risk_rating"].dropna().unique())
fc1, fc2 = st.columns(2)
with fc1:
    selected_countries = st.multiselect(
        "Filter countries",
        options=all_countries,
        default=all_countries,
        help="Limit charts + table to customers in these countries.",
    )
with fc2:
    selected_risks = st.multiselect(
        "Filter risk ratings",
        options=all_risks,
        default=all_risks,
        help="Limit charts + table to customers with these risk ratings.",
    )

# Apply filters across the page (downstream KPIs, charts, table all read
# from the filtered frame so the view is consistent).
df_customers = df_customers[
    df_customers["country"].isin(selected_countries)
    & df_customers["risk_rating"].isin(selected_risks)
]
if df_customers.empty:
    st.warning("No customers match the selected filters.")
    st.stop()

# --- KPI row ---
# High-risk count carries an actual assessment — any high-risk
# customer is a "state to notice" for compliance. Medium binds amber.
# Total customers + country count are facts (neutral).
risk_counts = df_customers["risk_rating"].value_counts()
high_risk = int(risk_counts.get("high", 0))
medium_risk = int(risk_counts.get("medium", 0))
high_risk_rag = "red" if high_risk else None
medium_risk_rag = "amber" if medium_risk else None

c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card_rag("Total Customers", len(df_customers))
with c2:
    kpi_card_rag("High Risk", high_risk, rag=high_risk_rag)
with c3:
    kpi_card_rag("Medium Risk", medium_risk, rag=medium_risk_rag)
with c4:
    kpi_card_rag("Countries", df_customers["country"].nunique())

st.markdown("<br>", unsafe_allow_html=True)

# --- Row 1: Pie + Geography ---
col_left, col_right = st.columns(2)

with col_left:
    st.markdown("### Customer Risk Distribution")
    rc = risk_counts.reset_index()
    rc.columns = ["Risk Rating", "Count"]
    fig = px.pie(
        rc,
        names="Risk Rating",
        values="Count",
        color="Risk Rating",
        color_discrete_map=RISK_RATING_COLORS,
        hole=0.45,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    st.plotly_chart(chart_layout(fig, 340), use_container_width=True)

with col_right:
    st.markdown("### Customer Geography")
    # Stack by risk rating so the chart tells where risk concentrates
    # geographically — not just where customers count is highest.
    # Pre-PR-5 this was a monochrome blue gradient on raw count which
    # had no story beyond bar height.
    geo = df_customers.groupby(["country", "risk_rating"]).size().reset_index(name="Count")
    geo = geo.sort_values("Count", ascending=False)
    fig = px.bar(
        geo,
        x="country",
        y="Count",
        color="risk_rating",
        color_discrete_map=RISK_RATING_COLORS,
        category_orders={"risk_rating": ["high", "medium", "low"]},
    )
    fig.update_layout(
        xaxis_title="",
        yaxis_title="",
        legend_title_text="Risk",
        barmode="stack",
    )
    st.plotly_chart(chart_layout(fig, 340), use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)

# --- Transaction Volume by Country ---
st.markdown("### Transaction Volume by Country")
if not df_txns.empty:
    txn_with_country = df_txns.merge(
        df_customers[["customer_id", "country", "risk_rating"]],
        on="customer_id",
        how="left",
    )
    geo_vol = txn_with_country.groupby("country")["amount"].sum().reset_index()
    geo_vol.columns = ["Country", "Total Volume"]
    geo_vol = geo_vol.sort_values("Total Volume", ascending=False)
    fig = px.bar(
        geo_vol,
        x="Country",
        y="Total Volume",
        color="Total Volume",
        color_continuous_scale="Reds",
    )
    fig.update_layout(coloraxis_showscale=False, xaxis_title="", yaxis_title="Volume ($)")
    st.plotly_chart(chart_layout(fig, 340), use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)

# --- Heatmap: Risk x Channel ---
st.markdown("### Risk Heatmap: Risk Rating x Channel")
if not df_txns.empty:
    txn_with_risk = df_txns.merge(
        df_customers[["customer_id", "risk_rating"]],
        on="customer_id",
        how="left",
    )
    pivot = txn_with_risk.groupby(["risk_rating", "channel"])["amount"].sum().reset_index()
    heatmap_data = pivot.pivot_table(
        index="risk_rating",
        columns="channel",
        values="amount",
        fill_value=0,
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
        c = risk_color(val)
        return f"color: {c}; font-weight: 700;" if val in RISK_RATING_COLORS else ""

    styled = alerted[["customer_id", "full_name", "country", "risk_rating"]].style.map(
        _risk_style, subset=["risk_rating"]
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)
else:
    st.caption("No alerts with customer data.")
