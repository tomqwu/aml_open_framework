"""AML Open Framework -- Interactive Dashboard."""

from __future__ import annotations

import streamlit as st

from aml_framework.dashboard.audience import (
    AUDIENCE_PAGES,
    KNOWLEDGE_PAGES,
    NORTH_STAR_PAGES,
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

# PR-AZ-7: Azure Monitor exporter (no-op when env var unset).
from aml_framework.observability import init_observability as _init_otel  # noqa: E402

_init_otel()

# Announce which persistence backend is active so ops can confirm the
# right path is live without exec'ing into the container. Reuses the
# `aml.dashboard` logger name. db.py is streamlit-free so importing
# `_active_backend` here doesn't violate the lazy-import rule that
# applies to audience.py / data_layer.py / pages/.
import logging  # noqa: E402

from aml_framework.api.db import _active_backend  # noqa: E402

logging.getLogger("aml.dashboard").info("Persistence backend: %s", _active_backend())

# ---------------------------------------------------------------------------
# Navigation — role-based page visibility
# ---------------------------------------------------------------------------
# PR-NAV-1: hierarchical sidebar — 7 categories.
#
# Pre-PR-NAV-1, ALL_PAGES was a flat list of 32 st.Page entries. Even
# with the persona filter narrowing it to 6-9 pages per role, the
# "all pages" view was a wall of titles and the structure of the
# product wasn't visible. Streamlit's `st.navigation()` accepts a
# `Dict[str, List[st.Page]]` and renders each key as a collapsible
# section header in the sidebar — turning the phone-book into a map.
#
# The "" (empty-string) section renders flush at the top of the
# sidebar without a header — the standard Streamlit idiom for
# "ungrouped, always at the top." Today lives there because it's the
# personalised landing every persona sees first.
#
# Categories below match the existing tour prose groupings in
# `docs/dashboard-tour.md` (Operational / Strategic / Engineering /
# Audit / Compliance Workflow / Reference) plus a dedicated "Data"
# category for the PR-DATAVIZ surfaces and "FinTech" as a niche
# 1-MLRO surface.
ALL_PAGES: dict[str, list[st.Page]] = {
    # Welcome + Today are ungrouped above the first category header.
    # Welcome (page 0) is currently orphaned (on disk, not wired);
    # only Today is registered here, matching pre-PR-NAV-1 behaviour.
    "": [
        st.Page("pages/0_Today.py", title="Today", icon=":material/today:"),
    ],
    "Operations": [
        # Day-to-day analyst + manager surfaces. Triage, SLA, case
        # workflow, live transaction stream.
        st.Page("pages/3_Alert_Queue.py", title="Alert Queue", icon=":material/notifications:"),
        st.Page(
            "pages/4_Case_Investigation.py",
            title="Case Investigation",
            icon=":material/search:",
        ),
        st.Page(
            "pages/24_Investigations.py",
            title="Investigations",
            icon=":material/group_work:",
        ),
        st.Page("pages/21_My_Queue.py", title="My Queue", icon=":material/assignment_ind:"),
        st.Page(
            "pages/22_Analyst_Review_Queue.py",
            title="Analyst Review Queue",
            icon=":material/inbox:",
        ),
        st.Page("pages/11_Live_Monitor.py", title="Live Monitor", icon=":material/monitor_heart:"),
    ],
    "Risk & Compliance": [
        # 2LoD lane — exposure, sanctions screening, regulator-side
        # alignment, BOI, regulator-pulse intelligence.
        st.Page("pages/6_Risk_Assessment.py", title="Risk Assessment", icon=":material/map:"),
        st.Page(
            "pages/12_Sanctions_Screening.py",
            title="Sanctions Screening",
            icon=":material/shield:",
        ),
        st.Page("pages/10_Network_Explorer.py", title="Network Explorer", icon=":material/hub:"),
        st.Page(
            "pages/8_Framework_Alignment.py",
            title="Framework Alignment",
            icon=":material/rule:",
        ),
        st.Page(
            "pages/25_BOI_Workflow.py",
            title="BOI Workflow",
            icon=":material/business:",
        ),
        st.Page(
            "pages/27_Regulator_Pulse.py",
            title="Regulator Pulse",
            icon=":material/podcasts:",
        ),
    ],
    "Detection & Tuning": [
        # Spec author + threshold-tuner surfaces. Engineering's
        # detection lane.
        st.Page("pages/5_Rule_Performance.py", title="Rule Performance", icon=":material/tune:"),
        st.Page("pages/16_Rule_Tuning.py", title="Rule Tuning", icon=":material/tune:"),
        st.Page(
            "pages/13_Model_Performance.py",
            title="Model Performance",
            icon=":material/model_training:",
        ),
        st.Page(
            "pages/23_Tuning_Lab.py",
            title="Tuning Lab",
            icon=":material/science:",
        ),
        st.Page("pages/20_Spec_Editor.py", title="Spec Editor", icon=":material/edit_note:"),
    ],
    "Data": [
        # Data engineer + auditor lane (introduced in PR-DATAVIZ-1
        # / #193). The data layer the controls run on.
        st.Page(
            "pages/30_Data_Integration.py",
            title="Data Integration",
            icon=":material/lan:",
        ),
        st.Page("pages/14_Data_Quality.py", title="Data Quality", icon=":material/fact_check:"),
        st.Page("pages/17_Customer_360.py", title="Customer 360", icon=":material/person_search:"),
        st.Page(
            "pages/31_Information_Sharing.py",
            title="Information Sharing",
            icon=":material/share:",
        ),
    ],
    "Strategy & Reporting": [
        # Executive + program-management surfaces. Headline picture,
        # maturity, run-over-run trends, roadmap, metric catalogue,
        # typology library.
        st.Page(
            "pages/1_Executive_Dashboard.py",
            title="Executive Dashboard",
            icon=":material/dashboard:",
        ),
        st.Page("pages/2_Program_Maturity.py", title="Program Maturity", icon=":material/speed:"),
        st.Page(
            "pages/19_Comparative_Analytics.py",
            title="Comparative Analytics",
            icon=":material/trending_up:",
        ),
        st.Page(
            "pages/9_Transformation_Roadmap.py",
            title="Transformation Roadmap",
            icon=":material/rocket_launch:",
        ),
        st.Page(
            "pages/28_Metrics_Taxonomy.py",
            title="Metrics Taxonomy",
            icon=":material/category:",
        ),
        st.Page(
            "pages/18_Typology_Catalogue.py",
            title="Typology Catalogue",
            icon=":material/library_books:",
        ),
        # PR-NS-1 — north-star pillar coverage. Sits in Strategy &
        # Reporting because it's the strategic "are we honoring the
        # 8 pillars?" surface, even though it's universally routed
        # (every persona sees it via NORTH_STAR_PAGES, same idiom as
        # Today / Executive Dashboard / KNOWLEDGE_PAGES).
        st.Page(
            "pages/43_North_Star_Coverage.py",
            title="North-Star Pillar Coverage",
            icon=":material/explore:",
            # Pin URL to match title-derived slug (`replace(' ', '_')`)
            # so direct/bookmarked nav stays consistent with the rest of
            # the dashboard. Same idiom as the Knowledge pages above.
            url_path="North-Star_Pillar_Coverage",
        ),
    ],
    "Audit & Reference": [
        # Auditor lane + GenAI provenance surface.
        st.Page("pages/7_Audit_Evidence.py", title="Audit & Evidence", icon=":material/verified:"),
        st.Page(
            "pages/32_Lineage_Explorer.py",
            title="Lineage Explorer",
            icon=":material/account_tree:",
        ),
        st.Page("pages/15_Run_History.py", title="Run History", icon=":material/history:"),
        st.Page(
            "pages/29_AI_Assistant.py",
            title="AI Assistant",
            icon=":material/smart_toy:",
        ),
    ],
    "FinTech": [
        # 1-MLRO niche. Sponsor-bank cure-notice timer + 8 realities
        # + evidence pack. Lives alone in its own header — it's a
        # different product surface, not a child of Operations. The
        # persona filter drops this section for everyone except
        # `fintech_mlro`.
        st.Page(
            "pages/26_FinTech_Cockpit.py",
            title="FinTech Cockpit",
            icon=":material/rocket_launch:",
        ),
    ],
    "Knowledge": [
        # PR-U2 of the unified-product epic. The GitHub-Pages
        # marketing/knowledge site is being merged into the product so
        # the GH page can be retired ("one product, two doors, three
        # skins"). These 8 native pages are the ported Research
        # whitepapers — the prose lives in the generated
        # `dashboard/data/research.py` substrate. Placed AFTER the
        # operational categories: it's the reference shelf, not a
        # day-to-day surface. Every persona can see it (audience.py
        # maps all personas to these titles).
        # Knowledge filenames are `33_Knowledge_*`, so Streamlit's
        # filename-derived slug would be `Knowledge_Architecture`, not
        # the title-derived `Architecture` slug the rest of the app and
        # the e2e helper use (`title.replace(" & ", "_").replace(" ",
        # "_")`, see tests/test_e2e_dashboard.py). Pin `url_path`
        # explicitly so title-based deep links resolve to these pages.
        st.Page(
            "pages/33_Knowledge_Architecture.py",
            title="Architecture",
            url_path="Architecture",
            icon=":material/account_tree:",
        ),
        st.Page(
            "pages/34_Knowledge_Competitive_Landscape.py",
            title="Competitive Landscape",
            url_path="Competitive_Landscape",
            icon=":material/insights:",
        ),
        st.Page(
            "pages/35_Knowledge_Data_Is_The_Problem.py",
            title="Data Is The Problem",
            url_path="Data_Is_The_Problem",
            icon=":material/database:",
        ),
        st.Page(
            "pages/36_Knowledge_FinTech_AML_Reality.py",
            title="FinTech AML Reality",
            url_path="FinTech_AML_Reality",
            icon=":material/rocket_launch:",
        ),
        st.Page(
            "pages/37_Knowledge_Lineage_Deep_Dive.py",
            title="Lineage Deep-Dive",
            url_path="Lineage_Deep-Dive",
            icon=":material/timeline:",
        ),
        st.Page(
            "pages/38_Knowledge_AML_Process_Pain.py",
            title="AML Process Pain",
            url_path="AML_Process_Pain",
            icon=":material/healing:",
        ),
        st.Page(
            "pages/39_Knowledge_Regulator_Pulse_Brief.py",
            title="Regulator Pulse Brief",
            url_path="Regulator_Pulse_Brief",
            icon=":material/podcasts:",
        ),
        st.Page(
            "pages/40_Knowledge_TD_2024_Case_Study.py",
            title="TD 2024 Case Study",
            url_path="TD_2024_Case_Study",
            icon=":material/gavel:",
        ),
        # PR-U3 — board-pack business deck (12 slides + 64s board
        # video) and the engineer/MLRO technical deck (18 slides + 92s
        # walkthrough video). Image+video oriented (no prose extract
        # step), assets resolved via `Path(__file__).parents[4] /
        # docs/pitch/deck-v2/`. Universal-routed alongside the other
        # Knowledge pages.
        st.Page(
            "pages/41_Knowledge_Business_Deck.py",
            title="Business Deck",
            url_path="Business_Deck",
            icon=":material/slideshow:",
        ),
        st.Page(
            "pages/42_Knowledge_Technical_Deck.py",
            title="Technical Deck",
            url_path="Technical_Deck",
            icon=":material/code:",
        ),
    ],
}

# Filter pages by audience if one is selected. PR-NAV-1 made
# ALL_PAGES a nested dict; the filter walks the structure, applies
# the title-set filter to each section's page list, and DROPS any
# section that ends up empty. The "" (ungrouped) section that
# carries Today survives because Today is always in the universal
# title set.
selected_audience = st.session_state.get("selected_audience")
if selected_audience:
    relevant_titles = set(AUDIENCE_PAGES.get(selected_audience, []))
    # "Today" + Executive Dashboard are universal — every persona sees
    # them (Today is the personalised landing; Executive Dashboard is
    # the strategic-view fallback when no persona is selected).
    relevant_titles.add("Today")
    relevant_titles.add("Executive Dashboard")
    # PR-U2: the Knowledge reference shelf is universal too — every
    # persona keeps access to the merged knowledge site regardless of
    # the operational filter.
    relevant_titles.update(KNOWLEDGE_PAGES)
    # PR-NS-1: the North-Star pillar coverage page is the cross-cutting
    # "are we honoring the 8 pillars?" surface — pitch reviewers,
    # examiners, every persona needs it. Universal same as Knowledge.
    relevant_titles.update(NORTH_STAR_PAGES)
    visible_pages: dict[str, list[st.Page]] = {
        section: [p for p in pages if p.title in relevant_titles]
        for section, pages in ALL_PAGES.items()
    }
    # Drop empty sections (per PR-NAV-1 user decision in plan Phase 3).
    visible_pages = {section: pages for section, pages in visible_pages.items() if pages}
else:
    visible_pages = ALL_PAGES

pg = st.navigation(visible_pages)

initialize_session()

# ---------------------------------------------------------------------------
# Global topbar — wordmark anchored top-left of the viewport, mirroring
# the landing site's sticky navbar. Renders once at app start; the CSS
# (in components.py) pushes the main view + sidebar below it. PR-P.
# ---------------------------------------------------------------------------
import html as _html  # noqa: E402

from aml_framework.release import get_tag_summary, release_label  # noqa: E402

# Summary span renders ONLY when the deploy injected one — undeployed
# / local runs keep the historical compact topbar with no empty chrome.
# HTML-escape: tag annotations may contain quotes / special chars that
# would otherwise break the attribute or the surrounding markup.
_summary = get_tag_summary()
if _summary:
    _summary_attr = _html.escape(_summary, quote=True)
    _summary_text = _html.escape(_summary)
    _summary_html = (
        f'<span class="dna-topbar-summary" title="{_summary_attr}">{_summary_text}</span>'
    )
else:
    _summary_html = ""

st.markdown(
    '<div class="dna-topbar">'
    '<div class="dna-topbar-brand">'
    # Brand cluster is a home link (full-reload to root `/`, which IS
    # the default Today page in Streamlit multi-page apps — a title-slug
    # like `/Today` is not a real route and triggers a "Page not found"
    # toast before Streamlit falls back). `target="_top"` breaks out of
    # Streamlit's iframe; `st.page_link` can't live in this injected
    # fixed overlay.
    '<a class="dna-topbar-home" href="/" target="_top" '
    'title="AML Open Framework — home" aria-label="AML Open Framework — home">'
    '<span class="dna-topbar-dot"></span>'
    '<span class="dna-topbar-name">AML Open Framework</span>'
    '<span class="dna-topbar-tag">Spec-driven · Audit-ready</span>'
    "</a>"
    f'<span class="dna-topbar-release">{release_label()}</span>'
    f"{_summary_html}"
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

    def _apply_persona() -> None:
        # Runs as the selectbox's on_change callback — i.e. BEFORE the
        # next rerun's script body. Without this, `selected_audience`
        # would only be written further down (after `st.navigation()`
        # already built the sidebar from the *previous* value), so the
        # nav would lag one rerun behind the dropdown. Setting it here
        # means the early `st.navigation()` call sees the new persona
        # on the very rerun the change triggers.
        choice = st.session_state.get("audience_selectbox", "all")
        st.session_state["selected_audience"] = None if choice == "all" else choice

    audience = st.selectbox(
        "I am a…",
        options=_persona_options,
        index=0,
        format_func=_persona_format,
        key="audience_selectbox",
        on_change=_apply_persona,
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
    # Initial render (no change event yet) still needs the value set so
    # the first `st.navigation()` is consistent; the callback owns it
    # on every subsequent change.
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

pg.run()
