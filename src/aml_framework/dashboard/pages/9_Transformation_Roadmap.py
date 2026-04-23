"""Transformation Roadmap — 4-phase Gantt chart with milestones and deliverables."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from aml_framework.dashboard.components import page_header
from aml_framework.dashboard.data_layer import get_roadmap_phases

spec = st.session_state.spec
jurisdiction = spec.program.jurisdiction
ROADMAP_PHASES = get_roadmap_phases(jurisdiction)

regulator_label = "FINTRAC / OSFI" if jurisdiction == "CA" else "FinCEN"

page_header(
    "Transformation Roadmap",
    f"4-phase AML program transformation roadmap for {jurisdiction} ({regulator_label}).",
)

if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo — Transformation Roadmap**\n\n"
        "This roadmap follows the pattern used by Big-4 firms for AML "
        "program transformations: Assessment \u2192 Foundation \u2192 Advanced \u2192 "
        "Optimization over 12 months. Phase 1 is complete; Phase 2 "
        "(this framework deployment) is in progress."
    )

# --- Gantt Chart ---
st.subheader("Program Timeline")
gantt_data = []
for phase in ROADMAP_PHASES:
    gantt_data.append({
        "Phase": phase["phase"],
        "Start": f"2026-W{phase['start_week']:02d}",
        "Finish": f"2026-W{phase['end_week']:02d}",
        "Start_date": pd.Timestamp("2026-01-01") + pd.Timedelta(weeks=phase["start_week"] - 1),
        "Finish_date": pd.Timestamp("2026-01-01") + pd.Timedelta(weeks=phase["end_week"]),
        "Status": phase["status"],
        "Color": phase["color"],
    })

df_gantt = pd.DataFrame(gantt_data)
status_colors = {"complete": "#22c55e", "in_progress": "#3b82f6", "planned": "#6b7280"}
fig = px.timeline(
    df_gantt, x_start="Start_date", x_end="Finish_date", y="Phase",
    color="Status", color_discrete_map=status_colors,
)
fig.update_yaxes(autorange="reversed")
fig.update_layout(height=300, margin=dict(t=10, b=10), showlegend=True)
st.plotly_chart(fig, use_container_width=True)

# --- Phase Status ---
status_icons = {"complete": "\u2705", "in_progress": "\U0001f504", "planned": "\u23f3"}
cols = st.columns(len(ROADMAP_PHASES))
for i, phase in enumerate(ROADMAP_PHASES):
    with cols[i]:
        icon = status_icons.get(phase["status"], "\u2753")
        st.markdown(f"### {icon}")
        st.markdown(f"**{phase['phase']}**")
        st.caption(f"Weeks {phase['start_week']}\u2013{phase['end_week']}")

st.divider()

# --- Phase Details ---
st.subheader("Phase Details")
for phase in ROADMAP_PHASES:
    icon = status_icons.get(phase["status"], "\u2753")
    with st.expander(f"{icon} {phase['phase']} (Weeks {phase['start_week']}\u2013{phase['end_week']})"):
        st.markdown(f"**Status:** {phase['status'].replace('_', ' ').title()}")

        st.markdown("**Milestones:**")
        for m in phase["milestones"]:
            st.markdown(f"- {m}")

        st.markdown("**Deliverables:**")
        for d in phase["deliverables"]:
            st.markdown(f"- {d}")

st.divider()

# --- Key Stats ---
st.subheader("Transformation at a Glance")
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Total Duration", "52 weeks")
with c2:
    completed = sum(1 for p in ROADMAP_PHASES if p["status"] == "complete")
    st.metric("Phases Complete", f"{completed} / {len(ROADMAP_PHASES)}")
with c3:
    st.metric("Current Phase", "Foundation")
with c4:
    progress = sum(
        p["end_week"] - p["start_week"] + 1
        for p in ROADMAP_PHASES if p["status"] == "complete"
    )
    total = sum(p["end_week"] - p["start_week"] + 1 for p in ROADMAP_PHASES)
    st.metric("Progress", f"{progress / total:.0%}")
