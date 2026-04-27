"""Deterministic baseline backend.

Wraps `generators/narrative.py` so the same template-driven STR/SAR text
is available through the new pluggable interface. This is what runs in
CI (no Ollama, no API keys) and what production should fall back to
when an LLM backend errors out.

Determinism: identical CaseEvidence in → identical DraftedNarrative out
(`drafted_at` aside, which the caller can pin via `_now` for testing).
"""

from __future__ import annotations

from datetime import datetime, timezone

from aml_framework.generators.narrative import generate_str_narrative
from aml_framework.narratives.models import (
    CaseEvidence,
    Citation,
    DraftedNarrative,
    RecommendedAction,
)

_SEVERITY_ACTION: dict[str, RecommendedAction] = {
    "critical": "file_str",
    "high": "investigate_further",
    "medium": "investigate_further",
    "low": "close_no_action",
}

_SEVERITY_CONFIDENCE = {"critical": 0.85, "high": 0.7, "medium": 0.55, "low": 0.4}


class TemplateBackend:
    """Template-driven baseline. No external dependencies beyond stdlib."""

    name = "template:v1"

    def __init__(self, *, _now: datetime | None = None) -> None:
        # `_now` is for tests; production should leave it None.
        self._now = _now

    def draft(self, evidence: CaseEvidence) -> DraftedNarrative:
        case = {
            "case_id": evidence.case_id,
            "rule_id": evidence.rule_id,
            "rule_name": evidence.rule_name,
            "severity": evidence.severity,
            "queue": evidence.queue,
            "alert": evidence.alert,
            "regulation_refs": evidence.regulation_refs,
        }
        narrative_text = generate_str_narrative(
            case=case,
            customer=evidence.customer,
            transactions=evidence.transactions,
            jurisdiction=evidence.jurisdiction,
        )

        citations = [
            Citation(
                rule_id=evidence.rule_id,
                citation=ref.get("citation", ""),
                claim=ref.get("description", ""),
            )
            for ref in evidence.regulation_refs
            if ref.get("citation")
        ]

        key_findings = self._derive_findings(evidence)
        action = _SEVERITY_ACTION.get(evidence.severity, "investigate_further")
        confidence = _SEVERITY_CONFIDENCE.get(evidence.severity, 0.5)

        return DraftedNarrative(
            case_id=evidence.case_id,
            narrative_text=narrative_text,
            key_findings=key_findings,
            citations=citations,
            recommended_action=action,
            confidence=confidence,
            drafted_by=self.name,
            drafted_at=self._now or datetime.now(tz=timezone.utc),
        )

    @staticmethod
    def _derive_findings(evidence: CaseEvidence) -> list[str]:
        findings: list[str] = []
        alert = evidence.alert or {}
        if alert.get("sum_amount"):
            findings.append(f"Aggregate amount: {alert['sum_amount']}")
        if alert.get("count"):
            findings.append(f"Transaction count: {alert['count']}")
        if alert.get("window_start") and alert.get("window_end"):
            findings.append(
                f"Window: {str(alert['window_start'])[:10]} → {str(alert['window_end'])[:10]}"
            )
        if evidence.feature_attribution:
            top = sorted(
                evidence.feature_attribution.items(),
                key=lambda kv: -abs(float(kv[1])),
            )[:3]
            for name, value in top:
                findings.append(f"Feature {name}: {float(value):+.3f}")
        if evidence.explanation:
            findings.append(evidence.explanation)
        return findings
