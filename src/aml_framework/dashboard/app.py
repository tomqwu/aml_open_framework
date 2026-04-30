"""AML Open Framework -- Interactive Dashboard."""

from __future__ import annotations

import streamlit as st

from aml_framework.dashboard.audience import (
    AUDIENCE_PAGES,
    PERSONA_LABELS,
    persona_description,
)
from aml_framework.dashboard.components import apply_theme
from aml_framework.dashboard.state import initialize_session

st.set_page_config(
    page_title="AML Open Framework",
    page_icon=":shield:",
    layout="wide",
    # "auto" collapses the sidebar by default on narrow viewports
    # (issue #66); desktop users still see it expanded.
    initial_sidebar_state="auto",
)

apply_theme()
initialize_session()

# ---------------------------------------------------------------------------
# Global topbar — wordmark anchored top-left of the viewport, mirroring
# the landing site's sticky navbar. Renders once at app start; the CSS
# (in components.py) pushes the main view + sidebar below it. PR-P.
# ---------------------------------------------------------------------------
st.markdown(
    '<div class="dna-topbar">'
    '<div class="dna-topbar-brand">'
    '<span class="dna-topbar-dot"></span>'
    '<span class="dna-topbar-name">AML Open Framework</span>'
    '<span class="dna-topbar-tag">Spec-driven · Audit-ready</span>'
    "</div>"
    "</div>",
    unsafe_allow_html=True,
)

spec = st.session_state.spec
result = st.session_state.result

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    # Tenant selector — only shown when multiple tenants are configured AND
    # the dashboard wasn't launched with an explicit CLI spec path. Single-
    # tenant deployments and `aml dashboard <spec>` invocations see no
    # selector (zero added UI noise for the common case).
    all_tenants = st.session_state.get("all_tenants", [])
    active_tenant = st.session_state.get("active_tenant")
    if len(all_tenants) > 1 and active_tenant is not None:
        tenant_ids = [t.id for t in all_tenants]
        labels = {t.id: t.display_name for t in all_tenants}
        current_idx = tenant_ids.index(active_tenant.id)
        selected = st.selectbox(
            "Tenant",
            options=tenant_ids,
            index=current_idx,
            format_func=lambda tid: labels.get(tid, tid),
            help="Switch between configured AML programs. "
            "Display-only — server-side authorization lives in the REST API.",
        )
        if selected != active_tenant.id:
            # Trigger re-run of the engine for the newly selected tenant.
            st.session_state["selected_tenant_id"] = selected
            st.session_state.pop("active_cache_key", None)
            st.rerun()
        st.divider()

    # Program info as a compact block
    jurisdiction_flag = {"CA": "CA", "US": "US", "UK": "UK", "EU": "EU"}.get(
        spec.program.jurisdiction, spec.program.jurisdiction
    )
    # Map known AML role keys to their canonical display form. The raw
    # `program.owner` field uses snake_case keys; without this map the
    # naive `.replace('_',' ').title()` produces "Chief Anti Money
    # Laundering Officer" (no hyphens) which mis-renders the Canadian
    # CAMLO role. Falls back to the generic title-case for unknown keys.
    _ROLE_LABELS = {
        "chief_compliance_officer": "Chief Compliance Officer",
        "chief_anti_money_laundering_officer": "Chief Anti-Money Laundering Officer",
        "chief_aml_officer": "Chief Anti-Money Laundering Officer",
        "money_laundering_reporting_officer": "Money Laundering Reporting Officer",
        "mlro": "Money Laundering Reporting Officer",
        "head_of_aml_ops": "Head of AML Operations",
        "head_of_financial_crime": "Head of Financial Crime",
        "bsa_officer": "BSA Officer",
    }
    _owner_label = _ROLE_LABELS.get(
        spec.program.owner, spec.program.owner.replace("_", " ").title()
    )
    st.markdown(
        f"**{spec.program.name}**<br>"
        f"<span style='font-size:0.85rem;'>"
        f"{jurisdiction_flag} &middot; {spec.program.regulator}"
        f"</span><br>"
        f"<span style='font-size:0.78rem; color: var(--dna-ink-dim);'>"
        f"Owned by {_owner_label}"
        f"</span>",
        unsafe_allow_html=True,
    )

    st.divider()

    # Persona codes carry a human-readable title rendered in the dropdown
    # so a leader can self-identify ("Chief Compliance Officer") rather
    # than guess what `cco` means. The selectbox value stays the bare
    # code so existing `selected_audience` lookups continue to work.
    _persona_options = ["all"] + list(PERSONA_LABELS.keys())

    def _persona_format(code: str) -> str:
        if code == "all":
            return "All pages"
        title = PERSONA_LABELS.get(code, (code.upper(), ""))[0]
        return f"{title}"

    audience = st.selectbox(
        "I am a…",
        options=_persona_options,
        index=0,
        format_func=_persona_format,
        help=(
            "Pick your role to filter the sidebar to the pages most relevant "
            "to you. Executive personas (SVP/CTO/CCO/VP/Director) also get a "
            "larger font scale for meeting-room readability."
        ),
    )
    if audience != "all":
        # One-line description grounds the selection so a leader knows
        # they picked the right persona before the page list updates.
        st.caption(persona_description(audience))
    st.session_state["selected_audience"] = audience if audience != "all" else None

    # Guided mode — the legacy "Guided demo" toggle was a thin per-page
    # info banner. Now offers a real onboarding tour (one persona arc
    # built so far; others ship in follow-up PRs) plus the legacy
    # tooltip mode for users who just want context strings.
    from aml_framework.dashboard import tour as tour_mod

    mode_options = ["Off", "Tooltip mode"] + [
        f"Tour · {tour_mod.TOUR_LABELS[k]}" for k in ("analyst", "manager", "cco", "auditor")
    ]
    current_mode = st.session_state.get("guided_mode_label", "Off")
    if current_mode not in mode_options:
        current_mode = "Off"
    selected_mode = st.selectbox(
        "Guided mode",
        options=mode_options,
        index=mode_options.index(current_mode),
        help=(
            "Off: no overlays. "
            "Tooltip mode: legacy info-strip per page. "
            "Tour: end-to-end onboarding through a persona arc."
        ),
    )
    st.session_state["guided_mode_label"] = selected_mode

    # Map the dropdown selection to internal state. "Tour · Analyst — …"
    # → arc_id "analyst", etc.
    if selected_mode == "Off":
        st.session_state["guided_mode"] = "off"
        st.session_state["guided_demo"] = False  # legacy compat
        if tour_mod.is_active(st.session_state) and not tour_mod.is_complete(st.session_state):
            tour_mod.end(st.session_state)
    elif selected_mode == "Tooltip mode":
        st.session_state["guided_mode"] = "tooltip"
        st.session_state["guided_demo"] = True  # legacy compat — shows existing banners
        if tour_mod.is_active(st.session_state):
            tour_mod.end(st.session_state)
    else:
        # Tour mode — find the arc id from the label.
        st.session_state["guided_mode"] = "tour"
        st.session_state["guided_demo"] = False
        for arc_id, label in tour_mod.TOUR_LABELS.items():
            if selected_mode.endswith(label):
                arc = tour_mod.TOUR_ARCS.get(arc_id, ())
                if not arc:
                    st.warning(
                        f"The {arc_id} tour ships in a follow-up PR. Try the Analyst tour for now."
                    )
                    break
                # Start the tour if it isn't already running with this arc.
                if (
                    not tour_mod.is_active(st.session_state)
                    or st.session_state.get("tour_arc") != arc_id
                ):
                    tour_mod.start(st.session_state, arc_id)
                    first = tour_mod.current_step(st.session_state)
                    if first:
                        st.switch_page(first.page_path)
                break

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
    # "Today" is the first entry so it becomes the default landing for
    # every persona — replaces the pre-PR-3 default of dropping all
    # users on Executive Dashboard regardless of role.
    st.Page("pages/0_Today.py", title="Today", icon=":material/today:"),
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
    st.Page("pages/20_Spec_Editor.py", title="Spec Editor", icon=":material/edit_note:"),
    st.Page("pages/21_My_Queue.py", title="My Queue", icon=":material/assignment_ind:"),
    st.Page(
        "pages/22_Analyst_Review_Queue.py",
        title="Analyst Review Queue",
        icon=":material/inbox:",
    ),
    st.Page(
        "pages/23_Tuning_Lab.py",
        title="Tuning Lab",
        icon=":material/science:",
    ),
    st.Page(
        "pages/24_Investigations.py",
        title="Investigations",
        icon=":material/group_work:",
    ),
]

# Filter pages by audience if one is selected.
selected_audience = st.session_state.get("selected_audience")
if selected_audience:
    relevant_titles = set(AUDIENCE_PAGES.get(selected_audience, []))
    # "Today" + Executive Dashboard are universal — every persona sees
    # them (Today is the personalised landing; Executive Dashboard is
    # the strategic-view fallback when no persona is selected).
    relevant_titles.add("Today")
    relevant_titles.add("Executive Dashboard")
    visible_pages = [p for p in ALL_PAGES if p.title in relevant_titles]
else:
    visible_pages = ALL_PAGES

pg = st.navigation(visible_pages)

pg.run()
