"""Program Maturity Assessment -- Big-4 style spider chart and dimension analysis."""

from __future__ import annotations

import streamlit as st

from aml_framework.dashboard.components import (
    RAG_COLORS,
    kpi_card,
    page_header,
    radar_chart,
    research_link,
    see_also_footer,
)
from aml_framework.dashboard.data_layer import MATURITY_LEVELS, compute_maturity_scores

page_header(
    "Program Maturity Assessment",
    "Where the program sits today — and the concrete gaps to close before the next exam.",
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
# ECharts radar takes (indicator_name, max_value) tuples per axis +
# (series_name, values) tuples per ring. radar_chart applies the
# brand palette + cream/ink theme automatically.
indicators = [(name, 5.5) for name in dim_names]
radar_chart(
    indicators=indicators,
    series=[("Current State", current), ("Target State", targets)],
    height=520,
    key="program_maturity_radar",
)

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
            f"</div>",
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
    with st.expander(f"{s['name']}  --  Current: {s['current']}/5  |  {status}"):
        st.markdown(f"**{s['description']}**")
        st.markdown(
            f"Current: **{MATURITY_LEVELS[s['current']]}** | "
            f"Target: **{MATURITY_LEVELS[s['target']]}**"
        )
        if s.get("recommendations"):
            st.markdown("**Recommendations:**")
            for rec in s["recommendations"]:
                st.markdown(f"- {rec}")


# --- See also (cross-page nav + research) ---
see_also_footer(
    [
        "[Framework Alignment — controls per regulation](./8_Framework_Alignment)",
        "[Transformation Roadmap — phased plan to close gaps](./9_Transformation_Roadmap)",
        research_link(
            "PAIN-4 — process-debt blocking maturity progress",
            "2026-04-aml-process-pain.md",
            "pain-4--every-control-is-a-detective-after-the-loss",
        ),
    ]
)
