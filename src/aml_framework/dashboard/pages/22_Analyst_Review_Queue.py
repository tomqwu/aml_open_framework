"""Analyst Review Queue — triage cases with draft narratives + pKYC triggers.

Each row composes a finalised case with:
  - a deterministic STR/SAR draft (TemplateBackend; LLM backends opt-in
    via the CLI for now to avoid surprise PII transit),
  - the pKYC triggers active for the case's customer (sanctions, country
    risk, transaction pattern, stale KYC),
  - the recalculated risk rating delta if any.

Analyst actions (accept / amend / reject / escalate-to-STR) write into
the existing AuditLedger using the new event types `narrative_review`
and `pkyc_review`. The append-only hash chain means every queue action
is permanently part of the run's audit trail — same artefact a regulator
would inspect.
"""

from __future__ import annotations

import streamlit as st

from aml_framework.dashboard.audience import show_audience_context
from aml_framework.dashboard.components import kpi_card, page_header
from aml_framework.dashboard.queue_state import (
    NARRATIVE_ACCEPT,
    NARRATIVE_AMEND,
    NARRATIVE_ESCALATE,
    NARRATIVE_REJECT,
    build_queue_rows,
    event_for_narrative_action,
    event_for_pkyc_action,
    record_decision,
)

PAGE_TITLE = "Analyst Review Queue"

page_header(
    PAGE_TITLE,
    "Triage finalised cases with draft narratives and pKYC triggers — "
    "actions are recorded in the audit ledger.",
)
show_audience_context(PAGE_TITLE)

spec = st.session_state.spec
data = st.session_state.data
df_cases = st.session_state.df_cases
run_dir = st.session_state.run_dir
as_of = st.session_state.as_of

if df_cases.empty:
    st.warning("No cases in this run.")
    st.stop()

# --- Sidebar controls ---
st.sidebar.markdown(f"### {PAGE_TITLE} — Settings")
high_risk_input = st.sidebar.text_input(
    "High-risk countries (ISO-2, comma-separated)",
    value="RU,KP,IR",
    help="Used by the pKYC CountryRiskDetector to flag affected customers.",
)
alert_threshold = st.sidebar.number_input(
    "Pattern detector alert threshold", min_value=1, max_value=20, value=3
)
analyst_actor = st.sidebar.text_input(
    "Acting analyst", value=st.session_state.get("selected_audience", "analyst")
)
high_risk_set = {c.strip().upper() for c in high_risk_input.split(",") if c.strip()}

# --- Build queue rows (cached per run) ---
cases = df_cases.to_dict(orient="records")
alert_counts: dict[str, int] = {}
for case in cases:
    cid = (case.get("alert") or {}).get("customer_id")
    if cid:
        alert_counts[cid] = alert_counts.get(cid, 0) + 1

rows = build_queue_rows(
    cases,
    customers=data.get("customer", []),
    transactions=data.get("txn", []),
    as_of=as_of,
    jurisdiction=spec.program.jurisdiction,
    high_risk_countries=high_risk_set,
    alert_counts_by_customer=alert_counts,
    alert_threshold=alert_threshold,
)

# --- KPIs ---
c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_card("Cases", len(rows), "#2563eb")
with c2:
    kpi_card(
        "With pKYC triggers",
        sum(1 for r in rows if r.triggers),
        "#d97706",
    )
with c3:
    kpi_card(
        "Rating changes",
        sum(1 for r in rows if r.rating_change is not None),
        "#7c3aed",
    )
with c4:
    kpi_card(
        "Critical severity",
        sum(1 for r in rows if r.severity == "critical"),
        "#dc2626",
    )

st.markdown("<br>", unsafe_allow_html=True)

# --- Filter controls ---
filter_cols = st.columns([2, 2, 2])
with filter_cols[0]:
    severity_filter = st.multiselect("Severity", ["critical", "high", "medium", "low"], default=[])
with filter_cols[1]:
    only_with_triggers = st.checkbox("Only cases with pKYC triggers", value=False)
with filter_cols[2]:
    only_rating_change = st.checkbox("Only cases with rating changes", value=False)


def _row_visible(row) -> bool:
    if severity_filter and row.severity not in severity_filter:
        return False
    if only_with_triggers and not row.triggers:
        return False
    if only_rating_change and row.rating_change is None:
        return False
    return True


visible_rows = [r for r in rows if _row_visible(r)]
st.caption(f"Showing {len(visible_rows)} of {len(rows)} cases.")

# --- Per-case expanders ---
for row in visible_rows[:50]:  # cap render to keep page responsive
    triggers_label = f" — {len(row.triggers)} pKYC trigger(s)" if row.triggers else ""
    rating_label = (
        f" — risk {row.rating_change.old_rating} → {row.rating_change.new_rating}"
        if row.rating_change
        else ""
    )
    header = (
        f"**{row.case_id}**  ·  {row.severity.upper()}  ·  "
        f"customer={row.customer_id}{triggers_label}{rating_label}"
    )
    with st.expander(header, expanded=False):
        # Drafted narrative
        st.markdown("##### Drafted narrative")
        st.markdown(
            f"_Recommended action_: **{row.drafted.recommended_action}** "
            f"(confidence {row.drafted.confidence:.2f}, drafted by `{row.drafted.drafted_by}`)"
        )
        st.code(row.drafted.narrative_text, language="markdown")

        # Citations linked to rule definition (in-app anchor; we surface the rule_id text).
        if row.drafted.citations:
            st.markdown("**Citations** (each ties back to a `regulation_refs` entry):")
            for cit in row.drafted.citations:
                st.markdown(f"- `{cit.rule_id}` → **{cit.citation}**: {cit.claim}")

        # pKYC triggers
        if row.triggers:
            st.markdown("##### pKYC triggers for this customer")
            for t in row.triggers:
                st.markdown(
                    f"- **{t.kind}** (severity={t.severity}, action={t.recommended_action}) "
                    f"— evidence: `{t.evidence}`"
                )

        # Rating change
        if row.rating_change:
            st.warning(
                f"Risk recalculator: **{row.rating_change.old_rating} → "
                f"{row.rating_change.new_rating}** "
                f"({len(row.rating_change.triggers)} trigger(s))"
            )

        # Action panel
        st.markdown("##### Action")
        action_cols = st.columns(4)
        labels = {
            NARRATIVE_ACCEPT: "Accept draft",
            NARRATIVE_AMEND: "Amend",
            NARRATIVE_REJECT: "Reject",
            NARRATIVE_ESCALATE: "Escalate to STR",
        }
        for col, action in zip(action_cols, labels):
            with col:
                if st.button(labels[action], key=f"{row.case_id}-{action}"):
                    record_decision(
                        run_dir,
                        case_id=row.case_id,
                        event=event_for_narrative_action(action),
                        actor=analyst_actor,
                        disposition=action,
                        extra={"drafted_by": row.drafted.drafted_by},
                    )
                    # Also record any pKYC action one-shot (default: accept the recommendation)
                    for t in row.triggers:
                        record_decision(
                            run_dir,
                            case_id=row.case_id,
                            event=event_for_pkyc_action(f"approve_{t.recommended_action}"),
                            actor=analyst_actor,
                            disposition=f"approve_{t.recommended_action}",
                            extra={
                                "trigger_kind": t.kind,
                                "trigger_severity": t.severity,
                                "customer_id": t.customer_id,
                            },
                        )
                    st.success(f"Recorded `{action}` for {row.case_id} as `{analyst_actor}`.")

if len(visible_rows) > 50:
    st.caption(f"… {len(visible_rows) - 50} more cases not shown (filter to narrow).")
