"""Investigator Decision Trail — case ↔ disposition ↔ STR/SAR chain.

PR-F3 (closes #385). Read-only synthesis page that walks every case's
full event chain — `case_opened` → intermediate disposition events
(escalated / closed / narrative_review / etc.) → terminal state
(closed_no_action / STR / SAR / pending). Answers the examiner's
"show me the audit trail for case X" question without re-walking
`decisions.jsonl` by hand.

Pure read of the cached `df_cases` + `df_decisions` populated by
`state.initialize_session()`. No engine call, no spec write, no
side-effect buttons. Cross-links to Case Investigation for the
per-case "Why this fired" panel + lineage drill-down.
"""

from __future__ import annotations

import streamlit as st

from aml_framework.dashboard.components import (
    link_to_page,
    page_footer,
    page_header,
    section_explainer,
)
from aml_framework.dashboard.state import ensure_initialized
from aml_framework.engine.constants import Event, Queue

ensure_initialized()

page_header(
    "Investigator Decision Trail",
    "Per-case event chain from `case_opened` through every disposition "
    "event to the terminal state. The audit trail an examiner asks for.",
)

section_explainer(
    page="Investigator Decision Trail",
    section_id="decision_trail.page",
    collapsed=True,
    section_title="Investigator Decision Trail",
    data_summary={
        "total_alerts": getattr(st.session_state.get("result"), "total_alerts", 0),
        "case_count": (
            len(st.session_state.get("df_cases"))
            if st.session_state.get("df_cases") is not None
            else 0
        ),
    },
)

df_cases = st.session_state.get("df_cases")
df_decisions = st.session_state.get("df_decisions")

if df_cases is None or df_cases.empty:
    st.info(
        "No cases in this run. The decision trail surface lights up once "
        "the engine emits at least one case_opened event."
    )
    page_footer()
    st.stop()

# ---------------------------------------------------------------------------
# Roll-up — disposition mix at the top so a reviewer can see the shape
# of this run's outcomes in one glance.
# ---------------------------------------------------------------------------
st.markdown("### Disposition mix")
# Each case's terminal disposition is its `status` field (set by
# `_simulate_case_resolution`). We bucket into the four canonical queue
# outcomes plus an "in-flight" bucket for cases that never reached a
# terminal event in this run.
_TERMINAL_BUCKETS = {
    Queue.CLOSED_NO_ACTION: "Closed — no action",
    Queue.L2_INVESTIGATOR: "Open with L2 investigator",
    Queue.STR_FILING: "Escalated → STR filing",
    Queue.SAR_FILING: "Escalated → SAR filing",
}
status_series = df_cases.get("status")
status_counts: dict[str, int] = {label: 0 for label in _TERMINAL_BUCKETS.values()}
unknown_count = 0
if status_series is not None:
    for raw in status_series.fillna("").tolist():
        label = _TERMINAL_BUCKETS.get(raw)
        if label is None:
            unknown_count += 1
        else:
            status_counts[label] += 1

cols = st.columns(len(status_counts) + (1 if unknown_count else 0))
for i, (label, count) in enumerate(status_counts.items()):
    with cols[i]:
        st.metric(label, count)
if unknown_count:
    with cols[-1]:
        st.metric("Other / in-flight", unknown_count)

st.caption(
    "Buckets follow `engine/constants.py:Queue`. STR / SAR buckets are the "
    "escalation tail an examiner cares about first. Click a case below to "
    "see its full event chain."
)

# ---------------------------------------------------------------------------
# Per-case event chain — one expander per case, listing every
# decisions.jsonl event tied to that case_id in chronological order.
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("### Per-case event chain")

# Reverse-chronological case ordering — newest cases first.
_case_records = df_cases.to_dict(orient="records")

# Index decisions by case_id for O(1) lookup.
_events_by_case: dict[str, list[dict]] = {}
if df_decisions is not None and not df_decisions.empty:
    for ev in df_decisions.to_dict(orient="records"):
        cid = ev.get("case_id")
        if cid:
            _events_by_case.setdefault(cid, []).append(ev)
    # Stable chronological ordering by `ts`, then by line-order within ts.
    for cid in _events_by_case:
        _events_by_case[cid].sort(key=lambda e: str(e.get("ts", "")))


def _is_meaningful(value: object) -> bool:
    """True when `value` is renderable — not None, not pandas NaN, not empty.

    The decision-events DataFrame mixes heterogeneous rows (case_opened
    has no `disposition`, `dq_exception` has no `queue`), so pandas
    fills missing cells with `NaN`. Python truthiness on NaN is True,
    so a naive `if value:` shows `nan` for absent fields — false data
    in an examiner-facing audit trail. Use this guard instead.
    """
    if value is None:
        return False
    # NaN is the only float that compares not-equal to itself.
    if isinstance(value, float) and value != value:
        return False
    if value == "":
        return False
    return True


def _event_icon(event_name: str | None) -> str:
    """Single-glance icon for the event type."""
    if event_name == Event.CASE_OPENED:
        return ":material/flag:"
    if event_name == Event.ESCALATED:
        return ":material/north_east:"
    if event_name == Event.ESCALATED_TO_STR:
        return ":material/gavel:"
    if event_name == Event.CLOSED:
        return ":material/done_all:"
    if event_name == Event.NARRATIVE_REVIEW:
        return ":material/edit_note:"
    if event_name == Event.MANUAL_REVIEW:
        return ":material/person_search:"
    if event_name == Event.RULE_FAILED:
        return ":material/error:"
    if event_name == Event.PKYC_REVIEW:
        return ":material/badge:"
    if event_name == Event.DQ_EXCEPTION:
        return ":material/data_alert:"
    return ":material/circle:"


# Cap the rendered chain count so a 1000-case run doesn't blow the page.
# An examiner reaching the cap typically wants the filter UX of Alert
# Queue / Investigations — link to those rather than dumping everything.
_MAX_CASES_RENDERED = 50
_records_shown = _case_records[:_MAX_CASES_RENDERED]

for case in _records_shown:
    cid = case.get("case_id") or "<unknown>"
    rule_id = case.get("rule_id") or "<unknown>"
    severity = case.get("severity") or "—"
    status = case.get("status") or "—"
    status_label = _TERMINAL_BUCKETS.get(status, status)

    title = f"{cid} · `{rule_id}` · severity={severity} · {status_label}"
    with st.expander(title, expanded=False):
        events = _events_by_case.get(cid, [])
        if not events:
            st.caption(
                "No decision events recorded for this case yet. "
                "(The case row exists but `decisions.jsonl` hasn't "
                "produced a `case_opened` event linked to it — usually "
                "a stale-data symptom rather than an engine bug.)"
            )
            continue
        for ev in events:
            event_name = ev.get("event") or "<unknown>"
            icon = _event_icon(event_name)
            ts = ev.get("ts") or ""
            queue = ev.get("queue")
            disposition = ev.get("disposition")
            line_bits = [f"{icon} **{event_name}**"]
            # `df_decisions` is built from heterogeneous JSONL rows
            # (case_opened has no disposition; dq_exception has no
            # queue), so pandas fills missing fields with `NaN`. NaN
            # is truthy in Python, so a naive `if queue` would render
            # `queue=nan` on every case_opened event — false data in
            # an examiner-facing audit trail. `_is_meaningful` guards
            # against that. Codex pass 2 on PR-F3.
            if _is_meaningful(queue):
                line_bits.append(f"queue=`{queue}`")
            if _is_meaningful(disposition):
                line_bits.append(f"disposition=`{disposition}`")
            if _is_meaningful(ts):
                line_bits.append(f"`{ts}`")
            st.markdown(" · ".join(line_bits))
        # Cross-link to Case Investigation. Two correctness constraints,
        # caught by codex passes 3 + 4 on PR-F3:
        #
        # (1) `link_to_page(..., case_id=cid)` writes its query-param
        #     kwargs to `st.session_state` at RENDER time, not click
        #     time — so a naive call inside this per-case loop would
        #     let the LAST rendered case overwrite all the others and
        #     every "Open" click would land on the wrong case. Hence
        #     the button + switch_page pattern: session_state only
        #     receives `cid` when THIS specific button is clicked.
        #
        # (2) Decision Trail is universally routed but
        #     `pages/4_Case_Investigation.py` is NOT — some personas
        #     filter it out. `st.switch_page` raises
        #     `StreamlitPageNotFoundError` for hidden targets, so we
        #     catch + degrade to a caption that explains the cause.
        #     Same posture as `link_to_page`'s graceful-degrade path.
        if st.button(
            f"Open {cid} in Case Investigation",
            key=f"open_case_investigation__{cid}",
            type="secondary",
        ):
            st.session_state["selected_case_id"] = cid
            try:
                st.switch_page("pages/4_Case_Investigation.py")
            except Exception as exc:
                is_nav_failure = type(exc).__name__ == "StreamlitPageNotFoundError" or (
                    isinstance(exc, KeyError) and "url_pathname" in str(exc)
                )
                if not is_nav_failure:
                    raise
                st.caption(
                    f"_Case Investigation is hidden under your current persona — "
                    f"switch to a persona that includes it to drill into {cid}._"
                )

if len(_case_records) > _MAX_CASES_RENDERED:
    st.caption(
        f"Showing the first {_MAX_CASES_RENDERED} of {len(_case_records)} "
        "cases — use Alert Queue / Investigations for filtered views."
    )

# ---------------------------------------------------------------------------
# Cross-links to related surfaces. Same `link_to_page` discipline as
# PR-NS-1: degrade to a "switch persona" caption when target is hidden.
# ---------------------------------------------------------------------------
st.markdown("---")
st.markdown("### Related surfaces")
link_to_page("pages/4_Case_Investigation.py", "Case Investigation — Why this fired + lineage")
link_to_page("pages/24_Investigations.py", "Investigations — L1 → L2 → MLRO lifecycle")
link_to_page("pages/7_Audit_Evidence.py", "Audit & Evidence — hash-chain replay verifier")

page_footer()
