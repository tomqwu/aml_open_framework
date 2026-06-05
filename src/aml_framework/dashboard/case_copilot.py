"""Governed GenAI case copilot — pure context builder + canned prompts.

This module is dashboard-only and NEVER part of the engine run path. The
copilot produces DRAFT, human-reviewed, audited output: an investigator
selects a canned action, the dashboard builds a case-scoped
`AssistantContext`, and the existing governed assistant backend answers.

It intentionally has no side effects and no Streamlit dependency — every
function here is pure and unit-testable. Module-level imports are limited
to stdlib plus the existing assistant model so unit CI (which installs
only ``.[dev]``, no streamlit) can import it.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from aml_framework.assistant.models import AssistantContext

CASE_COPILOT_ACTIONS = ("summarize", "typology", "draft_narrative", "network", "risk")

_PROMPTS: dict[str, str] = {
    "summarize": (
        "Summarize this case for an investigator: what triggered the alert, "
        "the customer and their risk profile, and the key transaction activity. "
        "Keep it factual and cite the case, customer, and rule IDs."
    ),
    "typology": (
        "Identify the money-laundering typology this case most closely matches "
        "(e.g. structuring, layering, rapid movement of funds, mule activity). "
        "Explain which transaction patterns support that classification."
    ),
    "draft_narrative": (
        "Draft a DRAFT STR/SAR narrative for this case covering WHO (the subject "
        "and counterparties), WHAT (the suspicious activity and amounts), WHEN "
        "(the timeframe), WHERE (channels, geographies, accounts), and WHY (why it "
        "is suspicious). This is a draft for human review, not a filing."
    ),
    "network": (
        "Map the counterparty network for this case: who is the customer transacting "
        "with, in which direction, and at what concentration. Highlight counterparties "
        "that warrant further investigation."
    ),
    "risk": (
        "Assess the highest-risk elements of this case and recommend a disposition — "
        "escalate, file an STR/SAR, or close — with a short rationale tied to the "
        "customer risk rating and the transaction activity."
    ),
}


def case_copilot_prompt(action: str) -> str:
    """Return the canned investigator prompt for ``action``.

    Raises ``ValueError`` for any action not in ``CASE_COPILOT_ACTIONS``.
    """
    if action not in _PROMPTS:
        raise ValueError(f"unknown case-copilot action: {action!r}")
    return _PROMPTS[action]


def _json_safe(value: Any) -> Any:
    """Coerce a value to something ``json.dumps`` accepts.

    Numbers stay numeric (Decimals become float), datetimes/dates become
    ISO strings, anything else falls back to ``str`` so the resulting
    ``section_data`` never makes ``json.dumps`` raise.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    # Decimal and other numeric-likes — coerce to float when possible.
    try:
        return float(value)  # handles Decimal, numpy scalars, etc.
    except (TypeError, ValueError):
        return str(value)


def _to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def build_case_copilot_context(
    *,
    page: str,
    action: str,
    case: dict[str, Any] | None,
    customer: dict[str, Any] | None,
    txns: list[dict[str, Any]],
    spec_name: str,
    spec_jurisdiction: str,
    spec_regulator: str,
    run_id: str,
    persona: str | None = None,
) -> AssistantContext:
    """Build a case-scoped ``AssistantContext`` for the copilot.

    The returned context reuses the existing governed assistant model; the
    case, customer, and transaction summary ride in ``section_data`` and are
    guaranteed JSON-safe so the assistant audit log can serialize them.
    """
    if action not in _PROMPTS:
        raise ValueError(f"unknown case-copilot action: {action!r}")

    case = case or {}
    cust = customer or {}

    top_channels: dict[str, int] = {}
    for t in txns:
        channel = t.get("channel")
        if channel is None:
            continue
        key = str(channel)
        top_channels[key] = top_channels.get(key, 0) + 1

    section_data: dict[str, Any] = {
        "case_id": _json_safe(case.get("case_id")),
        "severity": _json_safe(case.get("severity")),
        "queue": _json_safe(case.get("queue")),
        "status": _json_safe(case.get("status")),
        "rule_id": _json_safe(case.get("rule_id")),
        "rule_name": _json_safe(case.get("rule_name")),
        "customer_id": _json_safe(cust.get("customer_id")),
        "customer_risk_rating": _json_safe(cust.get("risk_rating")),
        "customer_country": _json_safe(cust.get("country")),
        "txn_count": len(txns),
        "total_amount": sum(_to_float(t.get("amount", 0)) for t in txns),
        "top_channels": top_channels,
    }

    return AssistantContext(
        page=page,
        persona=persona,
        spec_name=spec_name,
        spec_jurisdiction=spec_jurisdiction,
        spec_regulator=spec_regulator,
        run_id=run_id,
        case_count=1,
        selected_case_id=case.get("case_id"),
        selected_customer_id=cust.get("customer_id"),
        section_id=f"case_copilot.{action}",
        section_title=f"Case Copilot · {action}",
        section_data=section_data,
    )


# Human-readable labels for the radio widget, in CASE_COPILOT_ACTIONS order.
_ACTION_LABELS: dict[str, str] = {
    "summarize": "Summarize",
    "typology": "Identify typology",
    "draft_narrative": "Draft STR/SAR narrative",
    "network": "Counterparty network",
    "risk": "Risk & recommended action",
}
# Sentinel for the freeform option (not a real action — anchored to
# `summarize` when building the context, see case_copilot_panel).
_FREEFORM_LABEL = "Freeform question"


def case_copilot_panel(*, page: str) -> None:
    """Render the governed Case Copilot sidebar panel for ``page``.

    A human-reviewed DRAFT surface (SR-26-2 governed): the investigator
    picks a canned action (or asks a freeform question) about the
    currently-selected case, the existing governed assistant backend
    answers, and the reply is rendered with the same DRAFT banner +
    confidence + backend chip as the page-level AI advisor and logged to
    the AI audit trail. It is NEVER an auto-decision.

    All Streamlit / dashboard imports are lazy (inside this function) so
    the module stays Streamlit-free for unit CI, which installs only
    ``.[dev]``.
    """
    import os
    from pathlib import Path

    import streamlit as st

    from aml_framework.assistant.factory import get_assistant
    from aml_framework.assistant.models import reply_to_audit_dict
    from aml_framework.dashboard.components import _render_assistant_reply
    from aml_framework.engine.audit import AuditLedger

    backend_name = os.environ.get("AML_AI_BACKEND", "template").lower()

    # Label → action value; freeform maps to the sentinel label itself.
    label_to_action = {label: action for action, label in _ACTION_LABELS.items()}
    options = [_ACTION_LABELS[a] for a in CASE_COPILOT_ACTIONS] + [_FREEFORM_LABEL]

    with st.sidebar:
        st.markdown("---")
        st.markdown("### 🔍 Case Copilot")
        st.caption(
            "AI-assisted DRAFT — an investigator reviews and decides; "
            "never an auto-decision. Logged to the AI audit trail."
        )
        st.caption(f"Backend · `{backend_name}`")
        if backend_name in ("openai", "azure_openai", "azure-openai"):
            st.caption("⚠️ PII may be transmitted to the cloud backend. Use `ollama` for on-prem.")

        choice = st.radio(
            "Case Copilot action",
            options,
            key=f"case_copilot_action_{page}",
            label_visibility="collapsed",
        )
        is_freeform = choice == _FREEFORM_LABEL
        # Real assistant action; for freeform we anchor the context to
        # `summarize` (a valid known action) and pass the user's text as
        # the question instead of a canned prompt.
        action = "summarize" if is_freeform else label_to_action[choice]

        user_text = ""
        if is_freeform:
            user_text = st.text_area(
                "Ask about this case",
                key=f"case_copilot_freeform_{page}",
                height=88,
                placeholder="e.g. is the structuring pattern consistent across both accounts?",
                label_visibility="collapsed",
            )

        if st.button("Ask", key=f"case_copilot_ask_{page}", use_container_width=True):
            try:
                selected_case_id = st.session_state.get("selected_case_id")
                df_cases = st.session_state.get("df_cases")
                df_customers = st.session_state.get("df_customers")
                df_txns = st.session_state.get("df_txns")
                spec = st.session_state.get("spec")
                result = st.session_state.get("result")
                run_dir = st.session_state.get("run_dir")
                persona = st.session_state.get("selected_audience")

                if not selected_case_id or df_cases is None or df_cases.empty:
                    st.info("Select a case to use the Case Copilot.")
                    return

                if is_freeform and not user_text.strip():
                    st.info("Type a question first.")
                    return

                # Fail-closed governance (SR-26-2): a GenAI investigation
                # action MUST be durably audited. Without an active run +
                # audit trail we refuse to run the action at all — never
                # produce an unaudited reply. (Stricter than the
                # best-effort page-level ai_panel: the copilot drafts
                # SAR narratives and is audit-mandatory.)
                if not run_dir:
                    st.error(
                        "Case Copilot needs an active run with an audit trail "
                        "(no run_dir) — cannot run an unaudited investigation action."
                    )
                    return

                case_rows = df_cases[df_cases["case_id"] == selected_case_id]
                if case_rows.empty:
                    st.info("Select a case to use the Case Copilot.")
                    return
                case = case_rows.iloc[0].to_dict()

                customer_id = case.get("alert", {}).get("customer_id") or case.get("customer_id")
                customer: dict[str, Any] | None = None
                if customer_id and df_customers is not None and not df_customers.empty:
                    cust_rows = df_customers[df_customers["customer_id"] == customer_id]
                    if not cust_rows.empty:
                        customer = cust_rows.iloc[0].to_dict()

                txns: list[dict[str, Any]] = []
                if customer_id and df_txns is not None and not df_txns.empty:
                    txns = df_txns[df_txns["customer_id"] == customer_id].to_dict("records")

                program = getattr(spec, "program", None)
                ctx = build_case_copilot_context(
                    page=page,
                    action=action,
                    case=case,
                    customer=customer,
                    txns=txns,
                    spec_name=getattr(program, "name", "") or "",
                    spec_jurisdiction=getattr(program, "jurisdiction", "") or "",
                    spec_regulator=getattr(program, "regulator", "") or "",
                    run_id=str(getattr(result, "run_id", "")) if result else "",
                    persona=persona,
                )

                question = user_text.strip() if is_freeform else case_copilot_prompt(action)

                with st.spinner("Thinking…"):
                    reply = get_assistant(backend_name).reply(question, ctx)

                # Mandatory audit (fail-closed): write the interaction to
                # the immutable ledger FIRST. If the append raises, the
                # reply is discarded and NOT rendered — an investigation
                # action that cannot be durably audited must not be shown.
                # Only after the audit append succeeds do we store/render
                # the reply.
                try:
                    audit_mode = getattr(program, "ai_audit_log", "hash_only")
                    row = reply_to_audit_dict(reply, full_text=(audit_mode == "full_text"))
                    row["question"] = question
                    row["action"] = "freeform" if is_freeform else action
                    AuditLedger.append_to_run_dir(
                        Path(run_dir),
                        {"event": "ai_case_copilot_action", **row},
                        jsonl_name="ai_interactions.jsonl",
                    )
                except Exception as audit_exc:  # noqa: BLE001
                    st.error(
                        "Case Copilot reply was generated but the audit write "
                        "failed — not shown (audit is mandatory): "
                        f"{audit_exc}"
                    )
                    return

                st.session_state.setdefault("case_copilot_transcript", {})[page] = reply
            except Exception as exc:  # noqa: BLE001
                st.error(f"Case Copilot failed: {exc}")

        # Only re-display a stored (already-audited) reply while an active
        # run + audit trail is present — never surface a copilot reply
        # outside an auditable run context (SR-26-2 fail-closed posture).
        last = st.session_state.get("case_copilot_transcript", {}).get(page)
        if last is not None and st.session_state.get("run_dir"):
            _render_assistant_reply(last)
