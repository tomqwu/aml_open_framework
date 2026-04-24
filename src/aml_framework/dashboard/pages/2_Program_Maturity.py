"""Program Maturity Assessment -- Big-4 style spider chart and dimension analysis."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from aml_framework.dashboard.components import RAG_COLORS, chart_layout, kpi_card, page_header
from aml_framework.dashboard.data_layer import MATURITY_LEVELS, compute_maturity_scores

page_header(
    "Program Maturity Assessment",
    "12-dimension maturity model based on leading consulting firm methodologies "
    "(Level 1: Ad-Hoc to Level 5: Optimized).",
)

st.caption(
    "Scores are derived from spec coverage (rule count, queue structure, "
    "data quality checks) using heuristic weightings. A production assessment "
    "requires expert review of each dimension."
)

spec = st.session_state.spec
jurisdiction = spec.program.jurisdiction

if st.session_state.get("guided_demo"):
    regulator_note = "FINTRAC and OSFI" if jurisdiction == "CA" else "FinCEN"
    st.info(
        "**Guided Demo -- Maturity Assessment**\n\n"
        "This radar chart mirrors what Deloitte, EY, PwC, and KPMG use "
        f"to assess AML programs regulated by {regulator_note}. Current "
        "scores are derived from spec coverage. The gap between current "
        "and target drives the transformation roadmap."
    )

scores = compute_maturity_scores(spec)
dim_names = [s["name"] for s in scores]
current = [s["current"] for s in scores]
targets = [s["target"] for s in scores]

# --- KPI row ---
avg_current = sum(current) / len(current)
avg_target = sum(targets) / len(targets)
gap = avg_target - avg_current
at_target = sum(1 for c, t in zip(current, targets) if c >= t)

c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card("Current Score", f"{avg_current:.1f} / 5.0", "#2563eb")
with c2:
    kpi_card("Target Score", f"{avg_target:.1f} / 5.0", "#059669")
with c3:
    kpi_card("Gap to Close", f"{gap:.1f}", "#d97706")
with c4:
    kpi_card("At Target", f"{at_target} / {len(scores)}", "#7c3aed")

st.markdown("<br>", unsafe_allow_html=True)

# --- Radar Chart ---
fig = go.Figure()
fig.add_trace(go.Scatterpolar(
    r=current + [current[0]],
    theta=dim_names + [dim_names[0]],
    fill="toself",
    name="Current State",
    line=dict(color="#2563eb", width=2.5),
    fillcolor="rgba(37, 99, 235, 0.15)",
))
fig.add_trace(go.Scatterpolar(
    r=targets + [targets[0]],
    theta=dim_names + [dim_names[0]],
    fill="toself",
    name="Target State",
    line=dict(color="#16a34a", width=2, dash="dot"),
    fillcolor="rgba(22, 163, 74, 0.06)",
))
fig.update_layout(
    polar=dict(
        radialaxis=dict(visible=True, range=[0, 5.5], tickvals=[1, 2, 3, 4, 5],
                        showticklabels=True, tickfont_size=10),
        bgcolor="rgba(0,0,0,0)",
    ),
    showlegend=True,
    legend=dict(orientation="h", yanchor="bottom", y=-0.12, x=0.5, xanchor="center"),
)
st.plotly_chart(chart_layout(fig, 520), use_container_width=True)

# --- Level Legend ---
st.markdown("### Maturity Levels")
level_cols = st.columns(5)
level_colors = ["#dc2626", "#d97706", "#ca8a04", "#2563eb", "#059669"]
for i, (level, label) in enumerate(MATURITY_LEVELS.items()):
    with level_cols[i]:
        st.markdown(
            f'<div style="text-align:center; padding:0.5rem; border-radius:8px; '
            f'background:{level_colors[i]}10; border:1px solid {level_colors[i]}30;">'
            f'<div style="font-size:1.3rem; font-weight:700; color:{level_colors[i]};">{level}</div>'
            f'<div style="font-size:0.78rem; color:#475569;">{label}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

st.markdown("<br>", unsafe_allow_html=True)

# --- Dimension Details ---
st.markdown("### Dimension Details")
for s in scores:
    gap_val = s["target"] - s["current"]
    rag = "green" if gap_val <= 0 else ("amber" if gap_val <= 1 else "red")
    color = RAG_COLORS[rag]
    status = "At Target" if gap_val <= 0 else f"Gap: {gap_val}"
    with st.expander(f'{s["name"]}  --  Current: {s["current"]}/5  |  {status}'):
        st.markdown(f"**{s['description']}**")
        st.markdown(f"Current: **{MATURITY_LEVELS[s['current']]}** | "
                    f"Target: **{MATURITY_LEVELS[s['target']]}**")
        if s.get("recommendations"):
            st.markdown("**Recommendations:**")
            for rec in s["recommendations"]:
                st.markdown(f"- {rec}")
