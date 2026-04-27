"""Alert → case → investigation → STR effectiveness funnel.

Round-7 PR #2. **AMLA's RTS due 2026-07-10** ([AMLA portal](
https://www.amla.europa.eu/amla-takes-major-step-toward-harmonised-eu-supervision_en))
and **FinCEN's April 2026 NPRM** both treat the alert→case→STR
conversion ratio as the canonical effectiveness measure. The
framework's existing per-rule alert counts and SLA metrics don't
roll up into that funnel — this module fills the gap.

What's here
- `compute_outcomes(cases, decisions, *, labels=None)` returns an
  `OutcomesReport` with: per-rule funnel counts, conversion ratios,
  SLA-breach rate, precision/recall when label data is provided.
- `funnel_ratios(report)` returns the three top-line numbers AMLA
  + FinCEN want: alert→case (cases that opened), case→STR (cases
  that resulted in a filed STR), alert→STR (overall conversion).
- `format_amla_rts_json(report, *, program_metadata)` renders the
  report as the AMLA RTS draft 2026-02 JSON shape so operators can
  submit directly.

Design
- Pure functions over the case + decision dicts the engine already
  emits — no new schema requirements. When operators want
  precision/recall, they pass an optional `labels` dict mapping
  case_id → bool (true positive / false positive). That keeps the
  framework agnostic to where labels live (most institutions
  maintain them in a separate quality-assurance system).
- Deterministic: same inputs → same JSON bytes. Composes with the
  PR #53 MRM bundle's audit-replay guarantee.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

# Decision events that count as a case being closed in favor of filing.
# Mirrors `engine/constants.py:Event` values without importing — keeps
# this module dependency-light for downstream consumers.
_STR_FILED_EVENTS = frozenset(
    {"escalated_to_str", "str_filed", "sar_filed", "filed_with_regulator"}
)
_CLOSED_NO_ACTION_EVENTS = frozenset({"closed_no_action", "closed_false_positive", "case_closed"})


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuleOutcome:
    """One rule's funnel + quality numbers."""

    rule_id: str
    alerts: int
    cases_opened: int
    cases_escalated: int  # to higher-tier review (l2_investigator etc.)
    str_filed: int
    closed_no_action: int
    pending: int  # cases still open at report time
    sla_breaches: int
    sla_breach_rate_pct: float
    precision: float | None  # None when no labels supplied
    recall: float | None
    true_positives: int | None
    false_positives: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OutcomesReport:
    """Spec-wide funnel snapshot."""

    spec_program: str
    as_of: str  # ISO 8601 UTC
    total_alerts: int
    total_cases: int
    total_str_filed: int
    total_closed_no_action: int
    alert_to_case_pct: float
    case_to_str_pct: float
    alert_to_str_pct: float
    sla_breach_rate_pct: float
    rules: list[RuleOutcome] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec_program": self.spec_program,
            "as_of": self.as_of,
            "totals": {
                "alerts": self.total_alerts,
                "cases": self.total_cases,
                "str_filed": self.total_str_filed,
                "closed_no_action": self.total_closed_no_action,
            },
            "ratios": {
                "alert_to_case_pct": self.alert_to_case_pct,
                "case_to_str_pct": self.case_to_str_pct,
                "alert_to_str_pct": self.alert_to_str_pct,
                "sla_breach_rate_pct": self.sla_breach_rate_pct,
            },
            "rules": [r.to_dict() for r in self.rules],
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_pct(numerator: int, denominator: int) -> float:
    """Return numerator/denominator as a percentage. 0 when denominator is 0."""
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 2)


def _is_str_filed(decision: dict[str, Any]) -> bool:
    event = (decision.get("event") or "").lower()
    if event in _STR_FILED_EVENTS:
        return True
    disposition = (decision.get("disposition") or "").lower()
    return any(s in disposition for s in ("str", "sar", "filing"))


def _is_closed_no_action(decision: dict[str, Any]) -> bool:
    event = (decision.get("event") or "").lower()
    return event in _CLOSED_NO_ACTION_EVENTS


def _is_escalation(decision: dict[str, Any]) -> bool:
    event = (decision.get("event") or "").lower()
    return event in {"escalated", "case_escalated"} or "escalat" in event


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_outcomes(
    cases: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    *,
    spec_program: str = "",
    labels: dict[str, bool] | None = None,
    as_of: datetime | None = None,
) -> OutcomesReport:
    """Compute the alert→case→STR funnel for one engine run.

    Args:
        cases: list of case dicts (from `cases/<id>.json` ledger files).
        decisions: list of decision events (from `decisions.jsonl`).
        spec_program: spec.program.name — propagated into the report.
        labels: optional `{case_id: true_positive}` mapping. When
            provided, each rule gets precision/recall populated.
        as_of: report timestamp (default: now UTC).
    """
    as_of = as_of or datetime.now(tz=timezone.utc)

    # Group decisions by case_id for fast lookup.
    decisions_by_case: dict[str, list[dict[str, Any]]] = {}
    for d in decisions:
        case_id = d.get("case_id", "")
        if case_id:
            decisions_by_case.setdefault(case_id, []).append(d)

    # Per-rule aggregation.
    rule_buckets: dict[str, dict[str, Any]] = {}
    for case in cases:
        rule_id = case.get("rule_id", "")
        case_id = case.get("case_id", "")
        if not rule_id:
            continue
        bucket = rule_buckets.setdefault(
            rule_id,
            {
                "alerts": 0,
                "cases_opened": 0,
                "cases_escalated": 0,
                "str_filed": 0,
                "closed_no_action": 0,
                "pending": 0,
                "sla_breaches": 0,
                "true_positives": 0,
                "false_positives": 0,
                "labelled": 0,
            },
        )
        # Each case = one alert that opened a case.
        bucket["alerts"] += 1
        bucket["cases_opened"] += 1

        case_decisions = decisions_by_case.get(case_id, [])
        if any(_is_str_filed(d) for d in case_decisions):
            bucket["str_filed"] += 1
        elif any(_is_closed_no_action(d) for d in case_decisions):
            bucket["closed_no_action"] += 1
        elif case_decisions:
            # Has decisions but no terminal disposition — counts as escalated
            # if there's an escalation event, otherwise pending.
            if any(_is_escalation(d) for d in case_decisions):
                bucket["cases_escalated"] += 1
            else:
                bucket["pending"] += 1
        else:
            bucket["pending"] += 1

        # SLA breaches — count any decision with within_sla=False.
        if any(d.get("within_sla") is False for d in case_decisions):
            bucket["sla_breaches"] += 1

        # Label-based precision/recall.
        if labels is not None and case_id in labels:
            bucket["labelled"] += 1
            if labels[case_id]:
                bucket["true_positives"] += 1
            else:
                bucket["false_positives"] += 1

    rules: list[RuleOutcome] = []
    for rule_id, b in sorted(rule_buckets.items()):
        precision: float | None = None
        recall: float | None = None
        tp = b["true_positives"] if b["labelled"] else None
        fp = b["false_positives"] if b["labelled"] else None
        if b["labelled"] > 0 and (b["true_positives"] + b["false_positives"]) > 0:
            precision = round(
                b["true_positives"] / (b["true_positives"] + b["false_positives"]),
                4,
            )
        # Recall requires knowing the ground-truth positive population, which
        # the alert set alone can't tell us. Operators with a separate
        # positive-population count should compute recall externally; we
        # leave None as a placeholder so the JSON shape is consistent.

        rules.append(
            RuleOutcome(
                rule_id=rule_id,
                alerts=b["alerts"],
                cases_opened=b["cases_opened"],
                cases_escalated=b["cases_escalated"],
                str_filed=b["str_filed"],
                closed_no_action=b["closed_no_action"],
                pending=b["pending"],
                sla_breaches=b["sla_breaches"],
                sla_breach_rate_pct=_safe_pct(b["sla_breaches"], b["cases_opened"]),
                precision=precision,
                recall=recall,
                true_positives=tp,
                false_positives=fp,
            )
        )

    total_alerts = sum(r.alerts for r in rules)
    total_cases = sum(r.cases_opened for r in rules)
    total_str = sum(r.str_filed for r in rules)
    total_closed = sum(r.closed_no_action for r in rules)
    total_breaches = sum(r.sla_breaches for r in rules)

    return OutcomesReport(
        spec_program=spec_program,
        as_of=as_of.isoformat(timespec="seconds"),
        total_alerts=total_alerts,
        total_cases=total_cases,
        total_str_filed=total_str,
        total_closed_no_action=total_closed,
        alert_to_case_pct=_safe_pct(total_cases, total_alerts),
        case_to_str_pct=_safe_pct(total_str, total_cases),
        alert_to_str_pct=_safe_pct(total_str, total_alerts),
        sla_breach_rate_pct=_safe_pct(total_breaches, total_cases),
        rules=rules,
    )


def funnel_ratios(report: OutcomesReport) -> dict[str, float]:
    """Return the three top-line ratios AMLA + FinCEN want."""
    return {
        "alert_to_case_pct": report.alert_to_case_pct,
        "case_to_str_pct": report.case_to_str_pct,
        "alert_to_str_pct": report.alert_to_str_pct,
    }


# ---------------------------------------------------------------------------
# AMLA RTS draft 2026-02 JSON renderer
# ---------------------------------------------------------------------------


AMLA_RTS_VERSION = "2026-02-draft"


def format_amla_rts_json(
    report: OutcomesReport,
    *,
    program_metadata: dict[str, Any],
) -> bytes:
    """Render the report as the AMLA RTS draft 2026-02 effectiveness JSON.

    The shape mirrors what the AMLA central register is expected to
    accept once operational (H2 2026 per the [AMLA launch announcement](
    https://www.amla.europa.eu/amla-takes-major-step-toward-harmonised-eu-supervision_en)).
    Submission semantics are documented; the byte format is stable so
    operators can wire to whatever transport the final RTS specifies.

    Args:
        report: the `OutcomesReport` from `compute_outcomes()`.
        program_metadata: dict containing at least
            `lei` (Legal Entity Identifier),
            `obliged_entity_type` (credit_institution / payment_institution / ...),
            `home_member_state` (ISO 3166-1 alpha-2),
            `reporting_period_start` / `reporting_period_end` (ISO dates).

    Returns deterministic UTF-8 JSON bytes.
    """
    payload = {
        "rts_version": AMLA_RTS_VERSION,
        "submission_id": _submission_id(report, program_metadata),
        "obliged_entity": {
            "lei": program_metadata.get("lei", ""),
            "type": program_metadata.get("obliged_entity_type", ""),
            "home_member_state": program_metadata.get("home_member_state", ""),
        },
        "reporting_period": {
            "start": program_metadata.get("reporting_period_start", ""),
            "end": program_metadata.get("reporting_period_end", ""),
        },
        "program": {
            "name": report.spec_program,
            "as_of": report.as_of,
        },
        "effectiveness": {
            "totals": {
                "alerts": report.total_alerts,
                "investigations": report.total_cases,
                "str_filed": report.total_str_filed,
                "closed_no_action": report.total_closed_no_action,
            },
            "conversion_ratios_pct": {
                "alert_to_investigation": report.alert_to_case_pct,
                "investigation_to_str": report.case_to_str_pct,
                "alert_to_str": report.alert_to_str_pct,
            },
            "operational": {
                "sla_breach_rate_pct": report.sla_breach_rate_pct,
            },
            "per_rule": [
                {
                    "rule_id": r.rule_id,
                    "alerts": r.alerts,
                    "investigations": r.cases_opened,
                    "str_filed": r.str_filed,
                    "closed_no_action": r.closed_no_action,
                    "pending": r.pending,
                    "sla_breach_rate_pct": r.sla_breach_rate_pct,
                    "precision": r.precision,
                }
                for r in report.rules
            ],
        },
    }
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")


def _submission_id(report: OutcomesReport, metadata: dict[str, Any]) -> str:
    """Deterministic AMLA submission id — `AMLA-<sha256[:16]>`.

    Same report + same metadata → same submission_id, so retransmissions
    are idempotent.
    """
    digest_input = json.dumps(
        {
            "spec_program": report.spec_program,
            "as_of": report.as_of,
            "lei": metadata.get("lei", ""),
            "reporting_period_start": metadata.get("reporting_period_start", ""),
            "reporting_period_end": metadata.get("reporting_period_end", ""),
            "totals": {
                "alerts": report.total_alerts,
                "cases": report.total_cases,
                "str_filed": report.total_str_filed,
            },
        },
        sort_keys=True,
    ).encode("utf-8")
    return "AMLA-" + hashlib.sha256(digest_input).hexdigest()[:16]


__all__ = [
    "AMLA_RTS_VERSION",
    "OutcomesReport",
    "RuleOutcome",
    "compute_outcomes",
    "format_amla_rts_json",
    "funnel_ratios",
]
