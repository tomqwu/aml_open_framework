"""Pydantic models — input evidence and structured drafted narrative.

The contract between case data and the drafter:
  - CaseEvidence is the **input** (everything a backend needs to draft).
  - DraftedNarrative is the **output** (structured, citation-linked).

Both are frozen so a CaseEvidence built once can be safely passed to
multiple backends in parallel for A/B comparison.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RecommendedAction = Literal["file_str", "close_no_action", "investigate_further"]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Citation(_Base):
    """One citation tying a narrative claim back to a rule's regulation ref."""

    rule_id: str
    citation: str  # e.g. "PCMLTFA s.11.1"
    claim: str  # short text the citation supports


class CaseEvidence(_Base):
    """Bundle of facts a backend uses to draft a narrative.

    Mirrors the `cases/<case_id>.json` shape produced by the audit ledger
    plus the resolved customer profile and the case-window transactions.
    """

    case_id: str
    rule_id: str
    rule_name: str
    severity: str
    queue: str
    spec_program: str = ""
    jurisdiction: str = "US"

    customer: dict[str, Any] | None = None
    alert: dict[str, Any] = Field(default_factory=dict)
    transactions: list[dict[str, Any]] = Field(default_factory=list)
    regulation_refs: list[dict[str, str]] = Field(default_factory=list)

    feature_attribution: dict[str, float] | None = None
    explanation: str | None = None


class DraftedNarrative(_Base):
    """Structured output from a NarrativeDrafter backend."""

    case_id: str
    narrative_text: str
    key_findings: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    recommended_action: RecommendedAction = "investigate_further"
    confidence: float = Field(ge=0.0, le=1.0)
    drafted_by: str  # backend name, e.g. "template:v1" / "ollama:llama3.1"
    drafted_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


def case_to_evidence(
    case: dict[str, Any],
    customer: dict[str, Any] | None,
    transactions: list[dict[str, Any]],
    *,
    jurisdiction: str = "US",
) -> CaseEvidence:
    """Convert a `cases/<case_id>.json` record into a CaseEvidence.

    Pulls feature_attribution / explanation off the alert if present
    (those are produced by python_ref scorers per PR #38).
    """
    alert = case.get("alert") or {}
    return CaseEvidence(
        case_id=case.get("case_id", ""),
        rule_id=case.get("rule_id", ""),
        rule_name=case.get("rule_name", case.get("rule_id", "")),
        severity=case.get("severity", "unknown"),
        queue=case.get("queue", "unknown"),
        spec_program=case.get("spec_program", ""),
        jurisdiction=jurisdiction,
        customer=customer,
        alert=alert,
        transactions=transactions,
        regulation_refs=list(case.get("regulation_refs") or []),
        feature_attribution=alert.get("feature_attribution"),
        explanation=alert.get("explanation"),
    )


def load_case_evidence_from_run_dir(
    run_dir: Path,
    case_id: str,
    customers: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    *,
    jurisdiction: str = "US",
) -> CaseEvidence:
    """Read a finalised case file and build a CaseEvidence."""
    import json

    case_path = run_dir / "cases" / f"{case_id}.json"
    if not case_path.exists():
        raise FileNotFoundError(f"No case file at {case_path}")
    case = json.loads(case_path.read_bytes())

    cust_id = (case.get("alert") or {}).get("customer_id")
    customer = next((c for c in customers if c.get("customer_id") == cust_id), None)

    start = str((case.get("alert") or {}).get("window_start") or "")
    end = str((case.get("alert") or {}).get("window_end") or "")
    case_txns = [
        t
        for t in transactions
        if t.get("customer_id") == cust_id
        and (not start or str(t.get("booked_at", "")) >= start)
        and (not end or str(t.get("booked_at", "")) <= end)
    ]
    return case_to_evidence(case, customer, case_txns, jurisdiction=jurisdiction)
