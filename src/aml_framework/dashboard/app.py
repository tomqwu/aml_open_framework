"""AML Open Framework — Interactive Dashboard.

Entry point for the Streamlit multi-page application.
"""

from __future__ import annotations

import streamlit as st

from aml_framework.dashboard.components import apply_theme
from aml_framework.dashboard.state import initialize_session

st.set_page_config(
    page_title="AML Open Framework",
    page_icon="\U0001f6e1\ufe0f",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_theme()
initialize_session()

spec = st.session_state.spec
result = st.session_state.result

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("\U0001f6e1\ufe0f AML Framework")
    st.caption("Spec-driven compliance automation")
    st.divider()

    st.markdown(f"**Program:** {spec.program.name}")
    st.markdown(f"**Jurisdiction:** {spec.program.jurisdiction}")
    st.markdown(f"**Regulator:** {spec.program.regulator}")
    st.markdown(f"**Owner:** {spec.program.owner}")
    st.divider()

    audience = st.selectbox(
        "Audience view",
        options=["all", "svp", "vp", "director", "manager", "pm", "developer", "business"],
        index=0,
        help="Filter metrics and reports by audience role.",
    )
    st.session_state["selected_audience"] = audience if audience != "all" else None

    guided = st.toggle("Guided demo", value=False, help="Show narrative walkthrough annotations.")
    st.session_state["guided_demo"] = guided

    st.divider()
    st.caption(f"Rules: {len(spec.rules)} | Metrics: {len(spec.metrics)}")
    st.caption(f"Alerts: {result.total_alerts} | Cases: {len(result.case_ids)}")
    st.caption(f"Seed: {st.session_state.seed}")

# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------
pages = {
    "Executive Dashboard": "pages/1_Executive_Dashboard.py",
    "Program Maturity": "pages/2_Program_Maturity.py",
    "Alert Queue": "pages/3_Alert_Queue.py",
    "Case Investigation": "pages/4_Case_Investigation.py",
    "Rule Performance": "pages/5_Rule_Performance.py",
    "Risk Assessment": "pages/6_Risk_Assessment.py",
    "Audit & Evidence": "pages/7_Audit_Evidence.py",
    "Framework Alignment": "pages/8_Framework_Alignment.py",
    "Transformation Roadmap": "pages/9_Transformation_Roadmap.py",
}

pg = st.navigation([
    st.Page("pages/1_Executive_Dashboard.py", title="Executive Dashboard", icon="\U0001f4ca"),
    st.Page("pages/2_Program_Maturity.py", title="Program Maturity", icon="\U0001f3af"),
    st.Page("pages/3_Alert_Queue.py", title="Alert Queue", icon="\U0001f514"),
    st.Page("pages/4_Case_Investigation.py", title="Case Investigation", icon="\U0001f50d"),
    st.Page("pages/5_Rule_Performance.py", title="Rule Performance", icon="\u2699\ufe0f"),
    st.Page("pages/6_Risk_Assessment.py", title="Risk Assessment", icon="\U0001f5fa\ufe0f"),
    st.Page("pages/7_Audit_Evidence.py", title="Audit & Evidence", icon="\U0001f4dc"),
    st.Page("pages/8_Framework_Alignment.py", title="Framework Alignment", icon="\U0001f4d0"),
    st.Page("pages/9_Transformation_Roadmap.py", title="Transformation Roadmap", icon="\U0001f680"),
])

pg.run()
