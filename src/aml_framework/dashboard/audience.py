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
# ~9 pages becomes hard to navigate from the sidebar without scrolling.
# Bumped 8 → 9 in PR-I so the new Metrics Taxonomy reference page can
# join the senior personas (CCO / Manager / PM) without forcing a
# Phase-D commitment to be dropped. 9 is the practical ceiling — past
# that, the sidebar genuinely overflows on a laptop without scrolling.
MAX_PAGES_PER_PERSONA = 9


# Persona labels + one-line descriptions in business language. Surfaces
# in the sidebar selector dropdown so a leader can self-identify by
# title rather than guess what `cco` / `svp` / `cto` mean.
#
# Source: descriptions written to match the PAIN-N voice in
# docs/research/2026-04-aml-process-pain.md so the language is
# consistent across deck, README, dashboard.
PERSONA_LABELS: dict[str, tuple[str, str]] = {
    "svp": (
        "Senior VP of Risk",
        "Owns the risk function. Cares about board reporting and regulator relationship.",
    ),
    "cto": (
        "Chief Technology Officer",
        "Owns the platform. Cares about deployability, deterministic replay, vendor risk.",
    ),
    "cco": (
        "Chief Compliance Officer",
        "Owns the AML program. Cares about exam readiness and 'can we prove what we did?'",
    ),
    "vp": (
        "VP / MLRO",
        "Second line of defence. Reads the spec; challenges the rules; signs the STRs.",
    ),
    "director": (
        "Director of Financial Crime",
        "Runs the operation. Cares about backlog, SLA breaches, queue health.",
    ),
    "manager": (
        "AML Operations Manager",
        "Triage to escalation. Cares about queue throughput and analyst load balance.",
    ),
    "analyst": (
        "Analyst (L1 / L2)",
        "Works the alerts. Cares about evidence being pre-attached so they can write the narrative.",
    ),
    "pm": (
        "Program / Product Manager",
        "Plans the roadmap. Cares about coverage gaps and where to invest next.",
    ),
    "developer": (
        "Engineer / Detection Developer",
        "Authors the detectors. Cares about the spec, tests, and CI feedback loop.",
    ),
    "business": (
        "Business Stakeholder",
        "Outside FCC. Cares about the headline picture without operational detail.",
    ),
    "auditor": (
        "Auditor (Internal / External)",
        "Replays runs and verifies the chain. Cares about evidence completeness and reproducibility.",
    ),
    "fintech_mlro": (
        "FinTech / EMI / VASP MLRO",
        "1-MLRO program. Lives with sponsor-bank cure notices and Series-B AML diligence questionnaires.",
    ),
}


def persona_options_with_labels() -> list[tuple[str, str]]:
    """Return [(code, "Code — Title")] for the sidebar selector.

    Keeps the selectbox value as the bare code (so existing
    `selected_audience` lookups continue to work) but renders the
    full title to the user.
    """
    return [(code, f"{label} ({code.upper()})") for code, (label, _desc) in PERSONA_LABELS.items()]


def persona_description(code: str) -> str:
    """Return the one-line description for a persona code, or empty."""
    entry = PERSONA_LABELS.get(code)
    return entry[1] if entry else ""


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
        # Metrics Taxonomy added (PR-I) — defendable view of what
        # the program measures.
        "Executive Dashboard",
        "Program Maturity",
        "Framework Alignment",
        "Risk Assessment",
        "Audit & Evidence",
        "Investigations",
        "Regulator Pulse",
        "Transformation Roadmap",
        "Metrics Taxonomy",
    ],
    "vp": [
        # Tuning Lab dropped — VP consumes tuning outcomes via
        # Comparative Analytics, doesn't tune themselves.
        # Regulator Pulse added — MLRO needs to see what's moved.
        # Metrics Taxonomy added — 2LoD MLRO needs to defend what
        # the program measures for effectiveness.
        "Executive Dashboard",
        "Rule Performance",
        "Framework Alignment",
        "Sanctions Screening",
        "Comparative Analytics",
        "Regulator Pulse",
        "Metrics Taxonomy",
    ],
    "director": [
        # Added Investigations (drill-down when KPIs spike).
        # Tuning Lab dropped (consumes via Comparative Analytics).
        # Metrics Taxonomy added — director owns the metric program
        # and needs the catalogue when adjusting SLA targets.
        "Executive Dashboard",
        "Alert Queue",
        "Investigations",
        "Risk Assessment",
        "Data Quality",
        "Audit & Evidence",
        "Comparative Analytics",
        "Metrics Taxonomy",
    ],
    "manager": [
        # Dropped Case Investigation (overlaps Investigations); flow is
        # triage → investigate → tune. Reordered to match daily arc.
        # Typology Catalogue added — calibrating detection thresholds
        # against typology library is part of the manager's tuning loop.
        # Metrics Taxonomy added (PR-I) — needed when tuning thresholds
        # against the metric the rule is supposed to move.
        "Alert Queue",
        "Investigations",
        "My Queue",
        "Analyst Review Queue",
        "Risk Assessment",
        "Live Monitor",
        "Tuning Lab",
        "Typology Catalogue",
        "Metrics Taxonomy",
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
        # Typology Catalogue added — typology research drives roadmap
        # priorities (which detection patterns to invest in next).
        # Metrics Taxonomy added (PR-I) — coverage gaps drive what
        # gets added to the roadmap next quarter.
        "Rule Performance",
        "Program Maturity",
        "Transformation Roadmap",
        "Model Performance",
        "Risk Assessment",
        "Case Investigation",
        "Tuning Lab",
        "Typology Catalogue",
        "Metrics Taxonomy",
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
    "business": [
        # Business owner / CCO-equivalent at smaller institutions.
        # Per docs/personas.md, the business owner reads program-level
        # KPIs, the control matrix (Framework Alignment), and the
        # evidence bundle when an audit is on the calendar.
        "Executive Dashboard",
        "Risk Assessment",
        "Framework Alignment",
        "Audit & Evidence",
    ],
    "auditor": [
        # Added Investigations + Case Investigation — auditor reviews
        # specific cases, not just aggregate evidence.
        # Regulator Pulse added — auditors track regulator-side movement.
        # Metrics Taxonomy added — auditors verify what's measured
        # matches what the program claims to measure.
        "Audit & Evidence",
        "Investigations",
        "Case Investigation",
        "Data Quality",
        "Framework Alignment",
        "Regulator Pulse",
        "Run History",
        "Metrics Taxonomy",
    ],
    "fintech_mlro": [
        # FinTech / EMI / VASP MLRO — 1-person program. Operates from
        # the FinTech Cockpit (cure-notice timer + 8 realities + evidence
        # pack) and only opens the wider dashboard when an alert needs
        # triage or a regulator asks. Page list deliberately tight per
        # the persona's reality: no 2LoD, no separate validation team.
        # Metrics Taxonomy added — the 1-person MLRO IS the metric
        # program owner; the catalogue is their reference.
        "FinTech Cockpit",
        "Audit & Evidence",
        "Investigations",
        "Tuning Lab",
        "Regulator Pulse",
        "Framework Alignment",
        "Spec Editor",
        "Metrics Taxonomy",
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
