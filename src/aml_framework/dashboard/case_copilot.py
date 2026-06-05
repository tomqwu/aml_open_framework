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
