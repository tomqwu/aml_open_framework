"""Guided tour state machine + persona arcs.

Pure-python module — no streamlit at module level so this runs on the
unit-test CI image without ``.[dashboard]`` installed.

Each tour is an ordered list of :class:`TourStep` objects, one per page
the user is meant to land on. ``components.tour_panel()`` reads the
current step from session state and renders a navigation card at the
top of every page when a tour is active.

Design notes
------------

The pre-tour "Guided demo" toggle was a thin per-page ``st.info()``
banner — useful as tooltip mode but not actually a tour. v1 of this
module ships the **Analyst** arc as a 5-step end-to-end onboarding:
Today → Alert Queue → Case Investigation → Customer 360 → Audit &
Evidence. The other three personas (Manager / CCO / Auditor) get added
in follow-up PRs once the analyst pattern is validated.

"Skip tour" wipes tour state. "End tour" on the last step shows a
completion message and offers another arc.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TourStep:
    """One step of a guided tour.

    Attributes:
        page_path: Streamlit page file path, e.g. ``"pages/3_Alert_Queue.py"``.
            Used by :func:`streamlit.switch_page` when advancing.
        page_title: Human-readable page title (matches the entry in
            ``app.py`` ``ALL_PAGES``). Tour panel uses it in the header.
        step_title: Short imperative title for this step, e.g.
            "Triage the queue".
        narrative: Multi-sentence explainer rendered in the panel. Can
            include markdown (bold, code spans).
        task: One-line "what to do here" prompt — gives the user a
            concrete action to perform on the page before advancing.
        duration: Estimated time on this step, e.g. ``"~30s"``.
    """

    page_path: str
    page_title: str
    step_title: str
    narrative: str
    task: str
    duration: str


# ---------------------------------------------------------------------------
# Tour arcs, keyed by persona id (matches AUDIENCE_PAGES keys where they
# overlap, but the tour focuses on the canonical journey rather than the
# full persona page set).
# ---------------------------------------------------------------------------

ANALYST_ARC: tuple[TourStep, ...] = (
    TourStep(
        page_path="pages/3_Alert_Queue.py",
        page_title="Alert Queue",
        step_title="🎯 Start at the queue",
        narrative=(
            "Welcome, analyst. The Alert Queue is your day's starting point — every alert "
            "the engine produced this run lands here, sortable by severity, rule, and "
            "customer. **Critical** (purple) and **high** (red) get triaged first. Each "
            "row carries the regulation citation behind the rule, so you know **why** the "
            "engine flagged it before you open the case."
        ),
        task="Filter to severity='high'. Pick C0007 (rapid_pass_through, critical) for the next step.",
        duration="~45s",
    ),
    TourStep(
        page_path="pages/4_Case_Investigation.py",
        page_title="Case Investigation",
        step_title="🔍 Drill into a case",
        narrative=(
            "Case investigation surfaces everything you need to decide: customer KYC, "
            "transaction timeline, the Sankey channel-flow diagram, and the regulation "
            "citation that triggered the alert. The decision (escalate / close / "
            "request-info) writes a hashed line to the audit ledger — no silent rewrites."
        ),
        task="Pick a case from the dropdown. Read the timeline, decide what to do.",
        duration="~60s",
    ),
    TourStep(
        page_path="pages/17_Customer_360.py",
        page_title="Customer 360",
        step_title="👤 Full customer view",
        narrative=(
            "Customer 360 stitches together every signal we have on this entity — KYC "
            "snapshot, all alerts (this run + historical), transactions by channel, and "
            "open cases. Use this when the case-level view doesn't carry the context "
            "you need (cross-account patterns, prior alerting history)."
        ),
        task="Scroll through the channels chart. Look for unusual pass-through patterns.",
        duration="~45s",
    ),
    TourStep(
        page_path="pages/7_Audit_Evidence.py",
        page_title="Audit & Evidence",
        step_title="🔒 Lock the receipt",
        narrative=(
            "Every decision you just made was written to the audit ledger as a hashed line. "
            "The chain is **append-only** — no silent overwrites. Auditors verify by "
            "replaying the spec at this run's hash; a mismatched output is a reportable "
            "control failure, not a debate. The integrity check runs automatically on "
            "page-load."
        ),
        task="Find the 'Decision Log Integrity Verified' banner. Note the rule output hashes.",
        duration="~40s",
    ),
    TourStep(
        page_path="pages/8_Framework_Alignment.py",
        page_title="Framework Alignment",
        step_title="⚖️ Trace it back to the regulator",
        narrative=(
            "Every rule you triaged is mapped to specific regulation clauses — FATF "
            "Recommendations, the Bank Secrecy Act, PCMLTFR sections. This page is what "
            "your auditor reads first. **One spec, every regulator, every clause** — no "
            "tribal knowledge, no Slack archaeology."
        ),
        task="Switch tabs (FATF / PCMLTFA / OSFI / Wolfsberg). See the same spec mapped to each.",
        duration="~30s",
    ),
)


# Future arcs — placeholder so the persona selector knows what's available.
# Populate in follow-up PRs.
MANAGER_ARC: tuple[TourStep, ...] = ()
CCO_ARC: tuple[TourStep, ...] = ()
AUDITOR_ARC: tuple[TourStep, ...] = ()


TOUR_ARCS: dict[str, tuple[TourStep, ...]] = {
    "analyst": ANALYST_ARC,
    # Other arcs added in follow-up PRs. Keys present so the dropdown
    # can list them as "Coming soon" rather than hide them.
    "manager": MANAGER_ARC,
    "cco": CCO_ARC,
    "auditor": AUDITOR_ARC,
}


# Human-readable labels for the persona dropdown.
TOUR_LABELS: dict[str, str] = {
    "analyst": "Analyst — Day in the life",
    "manager": "Manager — Triage and tune  (coming soon)",
    "cco": "CCO — Board prep  (coming soon)",
    "auditor": "Auditor — Examination prep  (coming soon)",
}


# ---------------------------------------------------------------------------
# State helpers — pure functions over a session-state-shaped dict.
# Streamlit pages call these via session_state; tests pass a plain dict.
# ---------------------------------------------------------------------------


def is_active(state: dict) -> bool:
    """True if a tour is currently running."""
    return bool(state.get("tour_active") and state.get("tour_arc"))


def current_step(state: dict) -> TourStep | None:
    """Return the active TourStep, or None if no tour is running or the
    selected arc is empty (e.g., manager arc placeholder)."""
    if not is_active(state):
        return None
    arc = TOUR_ARCS.get(state.get("tour_arc", ""), ())
    if not arc:
        return None
    idx = state.get("tour_step", 0)
    if idx < 0 or idx >= len(arc):
        return None
    return arc[idx]


def start(state: dict, arc_id: str) -> None:
    """Begin a tour — sets tour_active, tour_arc, tour_step=0."""
    if arc_id not in TOUR_ARCS:
        raise ValueError(f"Unknown tour arc: {arc_id!r}")
    state["tour_active"] = True
    state["tour_arc"] = arc_id
    state["tour_step"] = 0


def advance(state: dict) -> TourStep | None:
    """Move to the next step. Returns the new step, or None if the tour
    just completed (hit end of arc)."""
    if not is_active(state):
        return None
    arc = TOUR_ARCS.get(state.get("tour_arc", ""), ())
    next_idx = state.get("tour_step", 0) + 1
    if next_idx >= len(arc):
        # Completed — leave tour_active=True so the panel can render
        # the completion message. Step set to len(arc) to mark "done".
        state["tour_step"] = next_idx
        return None
    state["tour_step"] = next_idx
    return arc[next_idx]


def retreat(state: dict) -> TourStep | None:
    """Move to the previous step. Returns the new step, or None at the
    start of the arc."""
    if not is_active(state):
        return None
    arc = TOUR_ARCS.get(state.get("tour_arc", ""), ())
    prev_idx = state.get("tour_step", 0) - 1
    if prev_idx < 0:
        return None
    state["tour_step"] = prev_idx
    return arc[prev_idx] if prev_idx < len(arc) else None


def end(state: dict) -> None:
    """End the tour — wipes all tour_* keys."""
    for key in ("tour_active", "tour_arc", "tour_step", "tour_started_at"):
        state.pop(key, None)


def is_complete(state: dict) -> bool:
    """True if the tour has run past its last step (showing completion)."""
    if not state.get("tour_active") or not state.get("tour_arc"):
        return False
    arc = TOUR_ARCS.get(state.get("tour_arc", ""), ())
    return state.get("tour_step", 0) >= len(arc) and len(arc) > 0


def step_position(state: dict) -> tuple[int, int]:
    """Return (current_step_one_indexed, total_steps) for display."""
    arc = TOUR_ARCS.get(state.get("tour_arc", ""), ())
    return (state.get("tour_step", 0) + 1, len(arc))
