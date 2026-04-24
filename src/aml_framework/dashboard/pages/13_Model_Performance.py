"""Model Performance -- python_ref model analytics and risk management."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from aml_framework.dashboard.components import chart_layout, kpi_card, page_header

page_header(
    "Model Performance",
    "ML model analytics, score distributions, and model risk management metadata.",
)

spec = st.session_state.spec
result = st.session_state.result
df_alerts = st.session_state.df_alerts

# Find python_ref rules.
ml_rules = [r for r in spec.rules if r.logic.type == "python_ref"]

if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo -- Model Performance**\n\n"
        f"The framework has **{len(ml_rules)}** python_ref model(s) deployed. "
        "This page shows score distributions, alert analysis, and model "
        "risk management metadata (model_id, version) for each model."
    )

if not ml_rules:
    st.warning("No python_ref models in this spec.")
    st.stop()

# --- Model inventory ---
st.markdown("### Model Inventory")

inventory_rows = []
for rule in ml_rules:
    alert_count = len(result.alerts.get(rule.id, []))
    inventory_rows.append({
        "Rule ID": rule.id,
        "Model ID": rule.logic.model_id,
        "Version": rule.logic.model_version,
        "Callable": rule.logic.callable,
        "Severity": rule.severity,
        "Status": rule.status,
        "Alerts": alert_count,
    })
st.dataframe(pd.DataFrame(inventory_rows), use_container_width=True, hide_index=True)

st.markdown("<br>", unsafe_allow_html=True)

# --- Per-model analysis ---
for rule in ml_rules:
    alerts = result.alerts.get(rule.id, [])
    st.markdown(f"### {rule.id} — {rule.logic.model_id} v{rule.logic.model_version}")

    # KPIs for this model.
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi_card("Alerts", len(alerts), "#dc2626")
    with c2:
        scores = [a.get("risk_score", 0) for a in alerts if a.get("risk_score")]
        avg_score = sum(scores) / len(scores) if scores else 0
        kpi_card("Avg Score", f"{avg_score:.3f}", "#2563eb")
    with c3:
        customers = len({a.get("customer_id") for a in alerts})
        kpi_card("Customers", customers, "#7c3aed")
    with c4:
        total_vol = sum(float(a.get("sum_amount", 0)) for a in alerts)
        kpi_card("Total Volume", f"${total_vol:,.0f}", "#059669")

    if not alerts:
        st.caption("No alerts from this model.")
        continue

    st.markdown("<br>", unsafe_allow_html=True)

    col_left, col_right = st.columns(2)

    with col_left:
        # Score distribution histogram.
        st.markdown("#### Score Distribution")
        if scores:
            fig = px.histogram(
                x=scores, nbins=20,
                labels={"x": "Risk Score", "y": "Count"},
                color_discrete_sequence=["#2563eb"],
            )
            fig.add_vline(x=0.65, line_dash="dash", line_color="#dc2626",
                         annotation_text="Threshold (0.65)")
            st.plotly_chart(chart_layout(fig, 300), use_container_width=True)

    with col_right:
        # Feature breakdown (from alert data if available).
        st.markdown("#### Alert Details")
        alert_df = pd.DataFrame(alerts)
        show_cols = ["customer_id", "risk_score", "sum_amount", "count"]
        available = [c for c in show_cols if c in alert_df.columns]
        st.dataframe(alert_df[available], use_container_width=True, hide_index=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Model risk management metadata.
    with st.expander("Model Risk Management Metadata"):
        st.markdown(f"""
| Field | Value |
|-------|-------|
| **Model ID** | {rule.logic.model_id} |
| **Version** | {rule.logic.model_version} |
| **Callable** | `{rule.logic.callable}` |
| **Severity** | {rule.severity} |
| **Regulation** | {', '.join(r.citation for r in rule.regulation_refs)} |
| **Evidence** | {', '.join(rule.evidence)} |
| **Tags** | {', '.join(rule.tags)} |
""")
