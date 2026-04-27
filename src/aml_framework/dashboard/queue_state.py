"""Helpers for the Analyst Review Queue page.

These functions compose the existing `narratives/` and `pkyc/` packages
so the Streamlit page stays declarative — every piece of logic with a
non-trivial branch lives here and is unit-testable without importing
streamlit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from aml_framework.engine.audit import AuditLedger
from aml_framework.engine.constants import Event
from aml_framework.engine.explain import (
    ExplainPayload,
    NotANetworkAlert,
    explain_network_alert,
)
from aml_framework.narratives import (
    DraftedNarrative,
    TemplateBackend,
    case_to_evidence,
)
from aml_framework.pkyc import (
    ScanContext,
    Trigger,
    run_scan,
)
from aml_framework.pkyc.scan import RatingChange


@dataclass(frozen=True)
class QueueRow:
    """One row in the analyst review queue.

    Bundles a case with its drafted narrative and any pKYC triggers
    affecting the same customer. Built once per case so the Streamlit
    table render stays cheap.
    """

    case_id: str
    customer_id: str
    rule_id: str
    severity: str
    queue: str
    drafted: DraftedNarrative
    triggers: list[Trigger]
    rating_change: RatingChange | None  # None when no rating movement
    explanation: ExplainPayload | None = None  # set for network_pattern alerts only


def _draft_for_case(
    case: dict[str, Any],
    customer: dict[str, Any] | None,
    transactions: list[dict[str, Any]],
    *,
    jurisdiction: str,
) -> DraftedNarrative:
    """Build a DraftedNarrative for one case using the deterministic
    TemplateBackend (the only backend that's safe to call at page-render
    time — Ollama/OpenAI need explicit user opt-in)."""
    evidence = case_to_evidence(case, customer, transactions, jurisdiction=jurisdiction)
    return TemplateBackend().draft(evidence)


def _txns_for_case(case: dict[str, Any], txns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    alert = case.get("alert") or {}
    cust_id = alert.get("customer_id")
    if cust_id is None:
        return []
    start = str(alert.get("window_start") or "")
    end = str(alert.get("window_end") or "")
    matched: list[dict[str, Any]] = []
    for t in txns:
        if t.get("customer_id") != cust_id:
            continue
        ts = str(t.get("booked_at") or "")
        if start and ts < start:
            continue
        if end and ts > end:
            continue
        matched.append(t)
    return matched


def build_queue_rows(
    cases: list[dict[str, Any]],
    customers: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    *,
    as_of: datetime,
    jurisdiction: str = "US",
    high_risk_countries: set[str] | None = None,
    alert_counts_by_customer: dict[str, int] | None = None,
    alert_threshold: int = 3,
) -> list[QueueRow]:
    """Compose the queue: one row per case with narrative + triggers.

    The pKYC scan is run **once** for the whole customer set (not per
    case) and its triggers are then attached to the matching case rows.
    Same for rating changes.
    """
    customer_idx = {c["customer_id"]: c for c in customers if "customer_id" in c}

    ctx = ScanContext(
        as_of=as_of,
        sanctions_added=[],  # external — comes from CLI/sanctions-sync, not the dashboard
        adverse_media_entries=[],
        high_risk_countries=high_risk_countries or set(),
        recent_alerts_by_customer=alert_counts_by_customer or {},
        lookback_days=90,
    )

    scan = run_scan(customers, ctx)
    triggers_by_customer: dict[str, list[Trigger]] = {}
    for t in scan.triggers:
        triggers_by_customer.setdefault(t.customer_id, []).append(t)
    changes_by_customer = {rc.customer_id: rc for rc in scan.rating_changes}

    rows: list[QueueRow] = []
    for case in cases:
        cust_id = (case.get("alert") or {}).get("customer_id", "")
        customer = customer_idx.get(cust_id)
        case_txns = _txns_for_case(case, transactions)
        drafted = _draft_for_case(case, customer, case_txns, jurisdiction=jurisdiction)
        explanation: ExplainPayload | None = None
        try:
            explanation = explain_network_alert(case.get("alert") or {})
        except NotANetworkAlert:
            explanation = None
        rows.append(
            QueueRow(
                case_id=case.get("case_id", ""),
                customer_id=cust_id,
                rule_id=case.get("rule_id", ""),
                severity=case.get("severity", "unknown"),
                queue=case.get("queue", "unknown"),
                drafted=drafted,
                triggers=triggers_by_customer.get(cust_id, []),
                rating_change=changes_by_customer.get(cust_id),
                explanation=explanation,
            )
        )
    return rows


def record_decision(
    run_dir: Path,
    *,
    case_id: str,
    event: str,
    actor: str,
    disposition: str,
    notes: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    """Append a decision to the run's audit ledger.

    Wraps `AuditLedger.append_to_run_dir` so the page only needs one
    function and we can keep the decision shape consistent across all
    queue actions (accept/amend/reject/escalate).
    """
    payload: dict[str, Any] = {
        "event": event,
        "case_id": case_id,
        "actor": actor,
        "disposition": disposition,
        "notes": notes,
    }
    if extra:
        payload.update(extra)
    AuditLedger.append_to_run_dir(run_dir, payload)


# Action constants kept here so the Streamlit page and tests stay in sync.
NARRATIVE_ACCEPT = "accept"
NARRATIVE_AMEND = "amend"
NARRATIVE_REJECT = "reject"
NARRATIVE_ESCALATE = "escalate_to_str"

PKYC_ACTIONS = {
    "approve_re_review",
    "approve_escalate",
    "approve_monitor",
    "dismiss",
}


def supported_narrative_actions() -> list[str]:
    return [NARRATIVE_ACCEPT, NARRATIVE_AMEND, NARRATIVE_REJECT, NARRATIVE_ESCALATE]


def event_for_narrative_action(action: str) -> str:
    """Map a narrative-review action to the audit-ledger event string."""
    if action == NARRATIVE_ESCALATE:
        return Event.ESCALATED_TO_STR
    return Event.NARRATIVE_REVIEW


def event_for_pkyc_action(action: str) -> str:
    if action == "approve_escalate":
        return Event.ESCALATED
    return Event.PKYC_REVIEW
