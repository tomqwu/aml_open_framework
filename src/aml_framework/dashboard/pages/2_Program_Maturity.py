"""Program Maturity Assessment — Big-4 style spider chart and dimension analysis."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from aml_framework.dashboard.components import RAG_COLORS, page_header
from aml_framework.dashboard.data_layer import MATURITY_LEVELS, compute_maturity_scores

page_header(
    "Program Maturity Assessment",
    "12-dimension maturity model based on leading consulting firm methodologies. "
    "Scores range from Level 1 (Ad-Hoc) to Level 5 (Optimized).",
)

spec = st.session_state.spec

if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo — Maturity Assessment**\n\n"
        "This radar chart mirrors what Deloitte, EY, PwC, and KPMG use "
        "to assess AML programs. Current scores are derived from your "
        "spec coverage (e.g., number of active rules, workflow queues, "
        "data quality checks). The target trace shows where you need to be."
    )

scores = compute_maturity_scores(spec)
dim_names = [s["name"] for s in scores]
current = [s["current"] for s in scores]
targets = [s["target"] for s in scores]

# --- Radar Chart ---
fig = go.Figure()
fig.add_trace(go.Scatterpolar(
    r=current + [current[0]],
    theta=dim_names + [dim_names[0]],
    fill="toself",
    name="Current State",
    line_color="#3b82f6",
    fillcolor="rgba(59, 130, 246, 0.2)",
))
fig.add_trace(go.Scatterpolar(
    r=targets + [targets[0]],
    theta=dim_names + [dim_names[0]],
    fill="toself",
    name="Target State",
    line_color="#22c55e",
    fillcolor="rgba(34, 197, 94, 0.1)",
))
fig.update_layout(
    polar=dict(
        radialaxis=dict(visible=True, range=[0, 5], tickvals=[1, 2, 3, 4, 5]),
    ),
    showlegend=True,
    height=550,
    margin=dict(t=30, b=30),
)
st.plotly_chart(fig, use_container_width=True)

# --- Overall score ---
avg_current = sum(current) / len(current)
avg_target = sum(targets) / len(targets)
gap = avg_target - avg_current

c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Average Current Score", f"{avg_current:.1f} / 5.0")
with c2:
    st.metric("Average Target Score", f"{avg_target:.1f} / 5.0")
with c3:
    st.metric("Gap to Close", f"{gap:.1f} levels")

st.divider()

# --- Level Legend ---
st.subheader("Maturity Levels")
level_cols = st.columns(5)
for i, (level, label) in enumerate(MATURITY_LEVELS.items()):
    with level_cols[i]:
        st.markdown(f"**Level {level}:** {label}")

st.divider()

# --- Dimension Details ---
st.subheader("Dimension Details")
for s in scores:
    gap_val = s["target"] - s["current"]
    rag = "green" if gap_val <= 0 else ("amber" if gap_val <= 1 else "red")
    color = RAG_COLORS[rag]
    with st.expander(
        f"{s['name']} — Current: {s['current']}/5 | Target: {s['target']}/5 | "
        f"Gap: {gap_val}"
    ):
        st.markdown(f"**Description:** {s['description']}")
        st.markdown(f"**Current Level:** {MATURITY_LEVELS[s['current']]}")
        st.markdown(f"**Target Level:** {MATURITY_LEVELS[s['target']]}")
        if s.get("recommendations"):
            st.markdown("**Recommendations:**")
            for rec in s["recommendations"]:
                st.markdown(f"- {rec}")
