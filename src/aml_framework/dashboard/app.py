"""AML Open Framework -- Interactive Dashboard."""

from __future__ import annotations

import streamlit as st

from aml_framework.dashboard.audience import AUDIENCE_PAGES
from aml_framework.dashboard.components import apply_theme
from aml_framework.dashboard.state import initialize_session

st.set_page_config(
    page_title="AML Open Framework",
    page_icon=":shield:",
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
    st.markdown(
        '<h2 style="margin:0; font-size:1.3rem;">AML Open Framework</h2>'
        '<p style="margin:0 0 0.5rem 0; font-size:0.8rem; opacity:0.7;">'
        "Spec-driven compliance automation</p>",
        unsafe_allow_html=True,
    )
    st.divider()

    # Program info as a compact block
    jurisdiction_flag = {"CA": "CA", "US": "US", "UK": "UK", "EU": "EU"}.get(
        spec.program.jurisdiction, spec.program.jurisdiction
    )
    st.markdown(
        f"**{spec.program.name}**<br>"
        f"<span style='font-size:0.85rem;'>"
        f"{jurisdiction_flag} &middot; {spec.program.regulator} &middot; "
        f"{spec.program.owner.replace('_', ' ').title()}"
        f"</span>",
        unsafe_allow_html=True,
    )

    st.divider()

    audience = st.selectbox(
        "Audience view",
        options=["all", "svp", "vp", "director", "manager", "pm", "developer", "business"],
        index=0,
        help="Filter metrics and reports by audience role.",
    )
    st.session_state["selected_audience"] = audience if audience != "all" else None

    guided = st.toggle("Guided demo", value=False, help="Show narrative walkthrough.")
    st.session_state["guided_demo"] = guided

    st.divider()

    # Compact stats
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            f"<span style='font-size:0.78rem;'>Rules **{len(spec.rules)}**</span><br>"
            f"<span style='font-size:0.78rem;'>Alerts **{result.total_alerts}**</span>",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"<span style='font-size:0.78rem;'>Metrics **{len(spec.metrics)}**</span><br>"
            f"<span style='font-size:0.78rem;'>Cases **{len(result.case_ids)}**</span>",
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# Navigation — role-based page visibility
# ---------------------------------------------------------------------------
ALL_PAGES = [
    st.Page(
        "pages/1_Executive_Dashboard.py", title="Executive Dashboard", icon=":material/dashboard:"
    ),
    st.Page("pages/2_Program_Maturity.py", title="Program Maturity", icon=":material/speed:"),
    st.Page("pages/3_Alert_Queue.py", title="Alert Queue", icon=":material/notifications:"),
    st.Page("pages/4_Case_Investigation.py", title="Case Investigation", icon=":material/search:"),
    st.Page("pages/5_Rule_Performance.py", title="Rule Performance", icon=":material/tune:"),
    st.Page("pages/6_Risk_Assessment.py", title="Risk Assessment", icon=":material/map:"),
    st.Page("pages/7_Audit_Evidence.py", title="Audit & Evidence", icon=":material/verified:"),
    st.Page("pages/8_Framework_Alignment.py", title="Framework Alignment", icon=":material/rule:"),
    st.Page(
        "pages/9_Transformation_Roadmap.py",
        title="Transformation Roadmap",
        icon=":material/rocket_launch:",
    ),
    st.Page("pages/10_Network_Explorer.py", title="Network Explorer", icon=":material/hub:"),
    st.Page("pages/11_Live_Monitor.py", title="Live Monitor", icon=":material/monitor_heart:"),
    st.Page(
        "pages/12_Sanctions_Screening.py", title="Sanctions Screening", icon=":material/shield:"
    ),
    st.Page(
        "pages/13_Model_Performance.py", title="Model Performance", icon=":material/model_training:"
    ),
    st.Page("pages/14_Data_Quality.py", title="Data Quality", icon=":material/fact_check:"),
    st.Page("pages/15_Run_History.py", title="Run History", icon=":material/history:"),
    st.Page("pages/16_Rule_Tuning.py", title="Rule Tuning", icon=":material/tune:"),
    st.Page("pages/17_Customer_360.py", title="Customer 360", icon=":material/person_search:"),
    st.Page(
        "pages/18_Typology_Catalogue.py",
        title="Typology Catalogue",
        icon=":material/library_books:",
    ),
    st.Page(
        "pages/19_Comparative_Analytics.py",
        title="Comparative Analytics",
        icon=":material/trending_up:",
    ),
]

# Filter pages by audience if one is selected.
selected_audience = st.session_state.get("selected_audience")
if selected_audience:
    relevant_titles = set(AUDIENCE_PAGES.get(selected_audience, []))
    # Always show Executive Dashboard.
    relevant_titles.add("Executive Dashboard")
    visible_pages = [p for p in ALL_PAGES if p.title in relevant_titles]
else:
    visible_pages = ALL_PAGES

pg = st.navigation(visible_pages)

pg.run()
