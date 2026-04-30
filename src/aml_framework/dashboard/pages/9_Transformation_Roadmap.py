"""Transformation Roadmap -- 4-phase Gantt chart with milestones."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from aml_framework.dashboard.components import (
    chart_layout,
    kpi_card,
    page_header,
    see_also_footer,
)
from aml_framework.dashboard.data_layer import get_roadmap_phases

spec = st.session_state.spec
jurisdiction = spec.program.jurisdiction
ROADMAP_PHASES = get_roadmap_phases(jurisdiction)

regulator_label = "FINTRAC / OSFI" if jurisdiction == "CA" else "FinCEN"

page_header(
    "Transformation Roadmap",
    f"4-phase AML program transformation for {jurisdiction} ({regulator_label}).",
)

st.caption(
    "This is a reference roadmap template. Phases, timelines, and milestones "
    "should be customized to your institution's risk profile and remediation priorities."
)

if st.session_state.get("guided_demo"):
    st.info(
        "**Guided Demo -- Transformation Roadmap**\n\n"
        "Big-4 style transformation: Assessment, Foundation, Advanced Analytics, "
        "Optimization over 12 months. Phase 1 complete; Phase 2 in progress."
    )

# --- KPI row ---
completed = sum(1 for p in ROADMAP_PHASES if p["status"] == "complete")
progress_weeks = sum(
    p["end_week"] - p["start_week"] + 1 for p in ROADMAP_PHASES if p["status"] == "complete"
)
total_weeks = sum(p["end_week"] - p["start_week"] + 1 for p in ROADMAP_PHASES)
current_phase = next((p["phase"] for p in ROADMAP_PHASES if p["status"] == "in_progress"), "N/A")

c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card("Total Duration", "52 weeks", "#2563eb")
with c2:
    kpi_card("Phases Complete", f"{completed} / {len(ROADMAP_PHASES)}", "#059669")
with c3:
    kpi_card(
        "Current Phase",
        current_phase.split(": ")[-1] if ": " in current_phase else current_phase,
        "#7c3aed",
    )
with c4:
    kpi_card("Progress", f"{progress_weeks / total_weeks:.0%}", "#d97706")

st.markdown("<br>", unsafe_allow_html=True)

# --- Gantt Chart ---
st.markdown("### Program Timeline")
gantt_data = []
for phase in ROADMAP_PHASES:
    gantt_data.append(
        {
            "Phase": phase["phase"],
            "Start_date": pd.Timestamp("2026-01-01") + pd.Timedelta(weeks=phase["start_week"] - 1),
            "Finish_date": pd.Timestamp("2026-01-01") + pd.Timedelta(weeks=phase["end_week"]),
            "Status": phase["status"].replace("_", " ").title(),
        }
    )

df_gantt = pd.DataFrame(gantt_data)
status_colors = {"Complete": "#16a34a", "In Progress": "#2563eb", "Planned": "#94a3b8"}
fig = px.timeline(
    df_gantt,
    x_start="Start_date",
    x_end="Finish_date",
    y="Phase",
    color="Status",
    color_discrete_map=status_colors,
)
fig.update_yaxes(autorange="reversed")
fig.update_layout(
    showlegend=True,
    legend_title_text="",
    legend=dict(orientation="h", yanchor="bottom", y=-0.25, x=0.5, xanchor="center"),
)
st.plotly_chart(chart_layout(fig, 300), use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)

# --- Phase cards ---
status_colors_card = {"complete": "#16a34a", "in_progress": "#2563eb", "planned": "#94a3b8"}
cols = st.columns(len(ROADMAP_PHASES))
for i, phase in enumerate(ROADMAP_PHASES):
    color = status_colors_card.get(phase["status"], "#94a3b8")
    with cols[i]:
        st.markdown(
            f'<div class="metric-card" style="border-top:4px solid {color}; text-align:center;">'
            f'<div class="label">{phase["status"].replace("_", " ").upper()}</div>'
            f'<div style="font-weight:700; font-size:0.95rem; margin:0.3rem 0;">'
            f"{phase['phase'].split(': ')[-1]}</div>"
            f'<div style="font-size:0.78rem; color:#64748b;">'
            f"Weeks {phase['start_week']}\u2013{phase['end_week']}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

st.markdown("<br>", unsafe_allow_html=True)

# --- Phase Details ---
st.markdown("### Phase Details")
for phase in ROADMAP_PHASES:
    color = status_colors_card.get(phase["status"], "#94a3b8")
    status_label = phase["status"].replace("_", " ").title()
    with st.expander(
        f"{phase['phase']} (Weeks {phase['start_week']}\u2013{phase['end_week']}) -- {status_label}"
    ):
        col_m, col_d = st.columns(2)
        with col_m:
            st.markdown("**Milestones**")
            for m in phase["milestones"]:
                st.markdown(f"- {m}")
        with col_d:
            st.markdown("**Deliverables**")
            for d in phase["deliverables"]:
                st.markdown(f"- {d}")


# --- See also (cross-page nav) ---
see_also_footer(
    [
        "[Program Maturity — current vs. target by dimension](./2_Program_Maturity)",
        "[Audit & Evidence — phase deliverables become audit pack](./7_Audit_Evidence)",
        "[Framework Alignment — gap-to-roadmap traceability](./8_Framework_Alignment)",
    ]
)
