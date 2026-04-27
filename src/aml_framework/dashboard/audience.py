"""Audience context helper — shows which persona is viewing and what they see."""

from __future__ import annotations

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
        "Executive Dashboard",
        "Rule Performance",
        "Framework Alignment",
        "Sanctions Screening",
        "Tuning Lab",
    ],
    "director": [
        "Executive Dashboard",
        "Alert Queue",
        "Risk Assessment",
        "Data Quality",
        "Audit & Evidence",
        "Tuning Lab",
    ],
    "manager": [
        "Alert Queue",
        "Case Investigation",
        "Investigations",
        "Risk Assessment",
        "Live Monitor",
        "My Queue",
        "Analyst Review Queue",
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
        "Rule Performance",
        "Program Maturity",
        "Transformation Roadmap",
        "Model Performance",
        "Tuning Lab",
    ],
    "developer": ["Rule Performance", "Model Performance", "Data Quality", "Run History"],
    "business": ["Executive Dashboard", "Risk Assessment"],
    "auditor": ["Audit & Evidence", "Data Quality", "Framework Alignment", "Run History"],
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
