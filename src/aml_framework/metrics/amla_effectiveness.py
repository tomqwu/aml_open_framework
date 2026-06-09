"""AMLA RTS effectiveness report — citation coverage + alert→case→STR funnel.

Composes:
- `metrics/outcomes.py:OutcomesReport` (alert→case→STR funnel per rule)
- per-rule AMLA RTS citation coverage (scanned from spec.rules[*].regulation_refs)

The three RTS the Authority must submit to the Commission by 2026-07-10:
  CDD RTS            — AMLR Article 28(1) — effectiveness demonstration obligation
  Business-rels RTS  — AMLR Article 19(9) — ongoing monitoring of business relationships
  Pecuniary-sanctions — AMLD6 Article 53(10) — administrative sanctions framework

Running `aml amla-effectiveness-report` emits `amla_effectiveness_report.json` so
EU obliged entities can demonstrate AMLA RTS readiness in one command.

Design
- Pure + deterministic: same spec + same run data → byte-identical JSON output.
- Stdlib + pydantic only (no new deps).
- Composes with, does not duplicate, `metrics/outcomes.py`.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from aml_framework.metrics.outcomes import OutcomesReport

# ---------------------------------------------------------------------------
# Tracked AMLA RTS articles — three standards due 2026-07-10
# ---------------------------------------------------------------------------

AMLA_RTS_VERSION = "2026-07-draft"

# Each entry: (article_id, match_pattern, full_citation, rts_name, title).
# match_pattern is matched against regulation_refs[*].citation via substring.
_AMLA_RTS_DEFS: list[tuple[str, str, str, str, str]] = [
    (
        "AMLR_28_1",
        "AMLR Art. 28",
        "AMLR Art. 28(1)",
        "CDD RTS",
        "Customer due diligence — effectiveness demonstration (AMLR Art. 28(1))",
    ),
    (
        "AMLR_19_9",
        "AMLR Art. 19",
        "AMLR Art. 19(9)",
        "Business-relationships RTS",
        "Ongoing monitoring of business relationships (AMLR Art. 19(9))",
    ),
    (
        "AMLD6_53_10",
        "AMLD6 Art. 53",
        "AMLD6 Art. 53(10)",
        "Pecuniary-sanctions RTS",
        "Administrative pecuniary sanctions (AMLD6 Art. 53(10))",
    ),
]


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RtsArticleCoverage:
    """Coverage of one AMLA RTS article by the spec's rules."""

    article_id: str
    citation: str  # canonical display string
    rts_name: str
    title: str
    rule_count: int
    rule_ids: tuple[str, ...]  # sorted
    status: str  # "covered" | "partial" | "gap"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["rule_ids"] = list(self.rule_ids)
        return d


@dataclass
class AMLAEffectivenessReport:
    """Combined AMLA RTS effectiveness report."""

    spec_program: str
    as_of: str  # ISO 8601 UTC
    rts_version: str
    rts_coverage: list[RtsArticleCoverage] = field(default_factory=list)
    # Optional funnel metrics — None when no run directory was supplied.
    funnel: OutcomesReport | None = None

    def to_dict(self) -> dict[str, Any]:
        coverage = [c.to_dict() for c in self.rts_coverage]
        d: dict[str, Any] = {
            "spec_program": self.spec_program,
            "as_of": self.as_of,
            "rts_version": self.rts_version,
            "rts_coverage": coverage,
        }
        if self.funnel is not None:
            d["funnel"] = self.funnel.to_dict()
        return d


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def build_rts_coverage(rules: list[Any]) -> list[RtsArticleCoverage]:
    """Scan rule regulation_refs and return per-article coverage status.

    Args:
        rules: list of `spec.models.Rule` objects (each has `id` and
               `regulation_refs: list[RegulationRef]`).

    Returns a list of `RtsArticleCoverage` sorted by article_id.
    """
    # article_id → list of matching rule_ids
    buckets: dict[str, list[str]] = {aid: [] for aid, *_ in _AMLA_RTS_DEFS}

    for rule in rules:
        citations = [ref.citation for ref in (rule.regulation_refs or [])]
        for article_id, pattern, _citation, _rts, _title in _AMLA_RTS_DEFS:
            if any(pattern in c for c in citations):
                buckets[article_id].append(rule.id)

    coverage: list[RtsArticleCoverage] = []
    for article_id, _pattern, citation, rts_name, title in _AMLA_RTS_DEFS:
        rule_ids = sorted(buckets[article_id])
        count = len(rule_ids)
        if count >= 2:
            status = "covered"
        elif count == 1:
            status = "partial"
        else:
            status = "gap"
        coverage.append(
            RtsArticleCoverage(
                article_id=article_id,
                citation=citation,
                rts_name=rts_name,
                title=title,
                rule_count=count,
                rule_ids=tuple(rule_ids),
                status=status,
            )
        )
    return coverage


def build_effectiveness_report(
    spec: Any,
    *,
    funnel: OutcomesReport | None = None,
    as_of: str,
) -> AMLAEffectivenessReport:
    """Build an AMLA effectiveness report from a spec (and optional funnel data).

    Args:
        spec: loaded `AMLSpec` object.
        funnel: `OutcomesReport` from `compute_outcomes()`; pass `None` when
                no run directory is available (citation-coverage only).
        as_of: ISO 8601 timestamp string for the report.
    """
    rts_coverage = build_rts_coverage(spec.rules or [])
    return AMLAEffectivenessReport(
        spec_program=spec.program.name,
        as_of=as_of,
        rts_version=AMLA_RTS_VERSION,
        rts_coverage=rts_coverage,
        funnel=funnel,
    )


def format_effectiveness_json(report: AMLAEffectivenessReport) -> bytes:
    """Serialize the report to deterministic UTF-8 JSON bytes."""
    return json.dumps(report.to_dict(), indent=2, sort_keys=True).encode("utf-8")


def format_effectiveness_markdown(report: AMLAEffectivenessReport) -> str:
    """Render the report as a GitHub-flavoured Markdown table.

    Returns a string suitable for inclusion in model-risk committee reports or
    a `--markdown` file output.
    """
    lines: list[str] = []
    lines.append(f"## AMLA RTS Effectiveness Report — {report.spec_program}")
    lines.append(f"*As of: {report.as_of} · RTS version: {report.rts_version}*")
    lines.append("")

    # --- RTS article coverage table ---
    lines.append("### RTS Article Coverage")
    lines.append("")
    lines.append("| Status | Article | RTS Name | Rules Covered |")
    lines.append("|--------|---------|----------|---------------|")
    status_icon = {"covered": "✓", "partial": "⚠", "gap": "✗"}
    for cov in report.rts_coverage:
        icon = status_icon.get(cov.status, "?")
        rule_list = ", ".join(cov.rule_ids) if cov.rule_ids else "—"
        lines.append(f"| {icon} {cov.status} | {cov.citation} | {cov.rts_name} | {rule_list} |")
    lines.append("")

    # --- Funnel metrics table (when a run was provided) ---
    if report.funnel is not None and report.funnel.rules:
        f = report.funnel
        lines.append("### Alert → Case → STR Funnel")
        lines.append("")
        lines.append("| Rule | Alerts | Cases | STR Filed | Alert→STR % | SLA Breach % |")
        lines.append("|------|--------|-------|-----------|-------------|--------------|")
        for r in f.rules:
            lines.append(
                f"| {r.rule_id} | {r.alerts} | {r.cases_opened} | {r.str_filed}"
                f" | {r.sla_breach_rate_pct:.1f}% | {r.sla_breach_rate_pct:.1f}% |"
            )
        lines.append("")
        lines.append(
            f"**Totals** — alerts: {f.total_alerts}, cases: {f.total_cases}, "
            f"STR filed: {f.total_str_filed}, alert→STR: {f.alert_to_str_pct}%, "
            f"SLA breach: {f.sla_breach_rate_pct}%"
        )
        lines.append("")

    return "\n".join(lines)


__all__ = [
    "AMLA_RTS_VERSION",
    "AMLAEffectivenessReport",
    "RtsArticleCoverage",
    "build_effectiveness_report",
    "build_rts_coverage",
    "format_effectiveness_json",
    "format_effectiveness_markdown",
]
