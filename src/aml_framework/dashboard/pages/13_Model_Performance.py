"""Model Performance -- python_ref model analytics and risk management."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from aml_framework.dashboard.audience import show_audience_context
from aml_framework.dashboard.components import (
    bar_chart,
    kpi_card,
    metric_gradient_style,
    page_header,
    severity_cell_style,
)

page_header(
    "Model Performance",
    "How the scoring models behave — and what your validation team would ask about them.",
)
show_audience_context("Model Performance")

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
    inventory_rows.append(
        {
            "Rule ID": rule.id,
            "Model ID": rule.logic.model_id,
            "Version": rule.logic.model_version,
            "Callable": rule.logic.callable,
            "Severity": rule.severity,
            "Status": rule.status,
            "Alerts": alert_count,
        }
    )
_inventory_df = pd.DataFrame(inventory_rows)
styled_inventory = _inventory_df.style
if "Severity" in _inventory_df.columns:
    styled_inventory = styled_inventory.map(severity_cell_style, subset=["Severity"])
st.dataframe(styled_inventory, use_container_width=True, hide_index=True)

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
        # Score distribution histogram. ECharts has no native histogram
        # type, so we pre-bin into 20 buckets and render as a bar chart.
        # The score-band shading (green ≤ 0.65 / amber 0.65-0.85 /
        # red ≥ 0.85) is preserved by per-bar colouring keyed off the
        # bin's centre value. Threshold 0.65 = the model card's action
        # line — analyst sees the cliff in the bar gradient.
        st.markdown("#### Score Distribution")
        if scores:
            import math

            n_bins = 20
            bin_width = 1.0 / n_bins
            bins = [0] * n_bins
            for s in scores:
                idx = min(int(s / bin_width), n_bins - 1) if not math.isnan(s) else 0
                bins[idx] += 1

            def _band(centre: float) -> str:
                # Returns the severity-token that the bar palette resolves
                # via _series_color() in dashboard.charts.
                if centre >= 0.85:
                    return "high"  # red
                if centre >= 0.65:
                    return "medium"  # amber
                return "low"  # green

            band_centres = [(i + 0.5) * bin_width for i in range(n_bins)]
            score_df = pd.DataFrame(
                {
                    "score": [f"{c:.2f}" for c in band_centres],
                    "count": bins,
                    "band": [_band(c) for c in band_centres],
                }
            )
            bar_chart(
                score_df,
                x="score",
                y="count",
                color="band",
                title="Score Distribution (Threshold 0.65)",
                height=300,
                key=f"model_perf_score_hist_{rule.id}",
            )

    with col_right:
        # Feature breakdown (from alert data if available).
        st.markdown("#### Alert Details")
        alert_df = pd.DataFrame(alerts)
        show_cols = ["customer_id", "risk_score", "sum_amount", "count"]
        available = [c for c in show_cols if c in alert_df.columns]
        styled_alerts = alert_df[available].style
        if "risk_score" in available:
            # Higher risk_score = more suspicious → trend toward red.
            styled_alerts = styled_alerts.map(
                metric_gradient_style(
                    low_color="#16a34a",
                    mid_color="#d97706",
                    high_color="#dc2626",
                    low_threshold=0.65,
                    high_threshold=0.85,
                ),
                subset=["risk_score"],
            )
        st.dataframe(styled_alerts, use_container_width=True, hide_index=True)

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
| **Regulation** | {", ".join(r.citation for r in rule.regulation_refs)} |
| **Evidence** | {", ".join(rule.evidence)} |
| **Tags** | {", ".join(rule.tags)} |
""")
