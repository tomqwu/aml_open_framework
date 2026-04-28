"""Audience context helper — shows which persona is viewing and what they see.

Phase D of the dashboard workflow plan rebalanced the persona arcs so
that each shipping persona has a coherent task flow and no persona
exceeds 8 pages (the cognitive-load cap from the workflow audit).

Notable rebalances:
  - Manager: dropped Case Investigation (overlaps Investigations);
    flow is now triage → investigate → tune.
  - Developer: added Spec Editor + Rule Tuning + Analyst Review Queue +
    Tuning Lab — the spec authoring + model performance + tuning arc.
  - PM: added Risk Assessment + Case Investigation — exposure +
    impact analysis when planning roadmap items.
  - Director: added Investigations — needs the drill-down when KPIs
    spike. Tuning Lab dropped (Director consumes tuning *outcomes*
    via Comparative Analytics, doesn't tune themselves).
  - Auditor: added Investigations + Case Investigation — auditor
    reviews specific cases, not just aggregate evidence.
  - VP: Tuning Lab dropped (same reasoning as Director).
"""

from __future__ import annotations

# Page-count cap per persona — the workflow audit found anything past
# 8 pages becomes hard to navigate from the sidebar without scrolling.
MAX_PAGES_PER_PERSONA = 8

# Which pages are most relevant per audience.
AUDIENCE_PAGES = {
    "svp": [
        "Executive Dashboard",
        "Program Maturity",
        "Framework Alignment",
        "Transformation Roadmap",
    ],
    "cto": [
        "Executive Dashboard",
        "Program Maturity",
        "Framework Alignment",
        "Model Performance",
        "Run History",
        "Transformation Roadmap",
    ],
    "cco": [
        "Executive Dashboard",
        "Program Maturity",
        "Framework Alignment",
        "Risk Assessment",
        "Audit & Evidence",
        "Investigations",
        "Transformation Roadmap",
    ],
    "vp": [
        # Tuning Lab dropped — VP consumes tuning outcomes via
        # Comparative Analytics, doesn't tune themselves.
        "Executive Dashboard",
        "Rule Performance",
        "Framework Alignment",
        "Sanctions Screening",
        "Comparative Analytics",
    ],
    "director": [
        # Added Investigations (drill-down when KPIs spike).
        # Tuning Lab dropped (consumes via Comparative Analytics).
        "Executive Dashboard",
        "Alert Queue",
        "Investigations",
        "Risk Assessment",
        "Data Quality",
        "Audit & Evidence",
        "Comparative Analytics",
    ],
    "manager": [
        # Dropped Case Investigation (overlaps Investigations); flow is
        # triage → investigate → tune. Reordered to match daily arc.
        "Alert Queue",
        "Investigations",
        "My Queue",
        "Analyst Review Queue",
        "Risk Assessment",
        "Live Monitor",
        "Tuning Lab",
    ],
    "analyst": [
        "Alert Queue",
        "Case Investigation",
        "Investigations",
        "Network Explorer",
        "Sanctions Screening",
        "Customer 360",
        "My Queue",
        "Analyst Review Queue",
    ],
    "pm": [
        # Added Risk Assessment + Case Investigation — exposure +
        # impact analysis when planning roadmap items.
        "Rule Performance",
        "Program Maturity",
        "Transformation Roadmap",
        "Model Performance",
        "Risk Assessment",
        "Case Investigation",
        "Tuning Lab",
    ],
    "developer": [
        # Added Spec Editor + Rule Tuning + Analyst Review Queue +
        # Tuning Lab — spec authoring + model perf + tuning arc.
        "Spec Editor",
        "Rule Performance",
        "Rule Tuning",
        "Tuning Lab",
        "Model Performance",
        "Data Quality",
        "Analyst Review Queue",
        "Run History",
    ],
    "business": ["Executive Dashboard", "Risk Assessment"],
    "auditor": [
        # Added Investigations + Case Investigation — auditor reviews
        # specific cases, not just aggregate evidence.
        "Audit & Evidence",
        "Investigations",
        "Case Investigation",
        "Data Quality",
        "Framework Alignment",
        "Run History",
    ],
}


def show_audience_context(page_title: str) -> None:
    """Show a subtle context line if an audience is selected."""
    import streamlit as st

    audience = st.session_state.get("selected_audience")
    if not audience:
        return
    relevant = AUDIENCE_PAGES.get(audience, [])
    if page_title in relevant:
        st.caption(
            f"Viewing as **{audience.upper()}** — this page is in your recommended workflow."
        )
    else:
        st.caption(
            f"Viewing as **{audience.upper()}** — this page is outside your primary workflow."
        )
