"""AMLA RTS effectiveness telemetry pack (#528).

The EU AML Authority (AMLA) supervises obliged entities against the
AMLR (Regulation (EU) 2024/1624). Three of its customer-due-diligence
obligations each carry an *effectiveness* expectation that an obliged
entity must be able to evidence from its transaction-monitoring program
(article numbers verified against the EUR-Lex AMLR text, 2026-06):

- **CDD** — AMLR **Art. 28(1)** (RTS on the information necessary to
  perform CDD): the customer-due-diligence measures a rule must reflect.
- **Ongoing monitoring of the business relationship** — AMLR **Art. 26**
  ("Ongoing monitoring of the business relationship and monitoring of
  transactions performed by customers"; listed as a CDD measure in
  Art. 20(1)(f)).
- **Targeted financial sanctions screening** — AMLR **Art. 20(1)(d)**:
  verifying whether the customer or beneficial owners are subject to
  targeted financial sanctions.

This module rolls a run's existing artifacts (cases, decisions, metrics)
into a frozen, deterministic `AmlaEffectivenessReport`:

1. **Funnel + per-rule precision/recall** — reused from
   `metrics.outcomes.compute_outcomes`; nothing reinvented here.
2. **AMLA RTS citation coverage** — which rules carry a citation that
   maps to each of the three AMLR articles, so a supervisor can see at a
   glance whether the CDD / ongoing-monitoring / targeted-financial-
   sanctions obligations are evidenced in the spec.

Everything is *derived* from the run dir — no metric is fabricated. The
run does not track STR *acceptance* (a regulator-feedback event), so
`str_acceptance` is reported as `not_tracked` rather than invented.

Pure + deterministic: same inputs (incl. caller-supplied `as_of`) →
same model. Stdlib + pydantic only. Offline — NEVER in the engine run
path; this is a post-run report like `aml model-inventory`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from aml_framework.metrics.outcomes import OutcomesReport, compute_outcomes


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------------------------------------------------------------------------
# AMLA RTS standard — the three effectiveness-bearing articles (#528).
# Each entry: the canonical citation string an authored rule carries in its
# `regulation_refs`, plus the substring tokens that also count as a match
# (operators cite the same article a few different ways). REAL references:
# AMLR = Regulation (EU) 2024/1624; AMLD6 = Directive (EU) 2024/1640.
# ---------------------------------------------------------------------------


class AmlaRtsArticle(_Base):
    key: str  # stable id, e.g. "cdd"
    title: str
    citation: str  # the canonical citation string
    instrument: str  # "AMLR" | "AMLD6"


AMLA_RTS_ARTICLES: tuple[AmlaRtsArticle, ...] = (
    AmlaRtsArticle(
        key="cdd",
        title="Customer due diligence",
        citation="AMLR Art. 28(1)",
        instrument="AMLR",
    ),
    AmlaRtsArticle(
        key="ongoing_monitoring",
        title="Ongoing monitoring of the business relationship",
        citation="AMLR Art. 26",
        instrument="AMLR",
    ),
    AmlaRtsArticle(
        key="targeted_financial_sanctions",
        title="Targeted financial sanctions screening",
        citation="AMLR Art. 20(1)(d)",
        instrument="AMLR",
    ),
)

# Substring tokens that count as "this rule cites this RTS article". The
# canonical citation always matches; the extra tokens absorb the common
# author variants without false-positiving onto an unrelated article.
_ARTICLE_TOKENS: dict[str, tuple[str, ...]] = {
    "cdd": ("amlr art. 28(1)", "amlr art 28(1)", "amlr article 28(1)", "art. 28(1)"),
    "ongoing_monitoring": (
        "amlr art. 26",
        "amlr art 26",
        "amlr article 26",
    ),
    "targeted_financial_sanctions": (
        "amlr art. 20(1)(d)",
        "amlr art 20(1)(d)",
        "amlr article 20(1)(d)",
        "art. 20(1)(d)",
    ),
}


# ---------------------------------------------------------------------------
# Report shapes
# ---------------------------------------------------------------------------


class RtsCoverage(_Base):
    """Coverage of one AMLA RTS article across the spec's rules."""

    key: str
    title: str
    citation: str
    instrument: str
    # Rule ids that carry a citation mapping to this RTS article, sorted.
    covering_rule_ids: list[str]
    n_covering_rules: int
    # ✓ when >=1 rule cites it; ✗ when none. (No ⚠ here — a citation
    # either maps to the article or it doesn't; the dashboard derives ⚠
    # for the *partial* case where the rule fired no alerts.)
    status: str  # "covered" | "gap"


class RuleEffectiveness(_Base):
    """One rule's funnel + quality numbers + AMLA RTS mapping."""

    rule_id: str
    alerts: int
    cases_opened: int
    str_filed: int
    closed_no_action: int
    pending: int
    precision: float | None  # None when no labels supplied
    recall: float | None  # None — needs the ground-truth positive population
    true_positives: int | None
    false_positives: int | None
    amla_rts_articles: list[str]  # keys of the RTS articles this rule cites


class AmlaEffectivenessReport(_Base):
    """Frozen AMLA RTS effectiveness telemetry for one engine run."""

    spec_program: str
    generated_at: datetime
    # Funnel totals (reused from compute_outcomes).
    total_alerts: int
    total_cases: int
    total_str_filed: int
    total_closed_no_action: int
    alert_to_case_pct: float
    case_to_str_pct: float
    alert_to_str_pct: float
    # STR acceptance is a regulator-feedback event the run does not record.
    # Reported as not-tracked rather than fabricated.
    str_acceptance_rate_pct: float | None
    str_acceptance_status: str  # always "not_tracked" for a stock run
    # AMLA RTS citation coverage.
    rts_coverage: list[RtsCoverage]
    n_rts_articles: int
    n_rts_covered: int
    # Per-rule detail.
    rules: list[RuleEffectiveness]


# ---------------------------------------------------------------------------
# Citation mapping
# ---------------------------------------------------------------------------


def _articles_for_citations(citations: list[str]) -> list[str]:
    """Return the AMLA RTS article keys a rule's citation strings map to.

    Deterministic, order = `AMLA_RTS_ARTICLES` order. A citation matches an
    article when its lower-cased form contains one of that article's tokens.
    """
    lowered = [c.lower() for c in citations]
    keys: list[str] = []
    for art in AMLA_RTS_ARTICLES:
        tokens = _ARTICLE_TOKENS[art.key]
        if any(any(tok in c for tok in tokens) for c in lowered):
            keys.append(art.key)
    return keys


def build_rts_coverage(
    rule_citations: dict[str, list[str]],
) -> tuple[list[RtsCoverage], dict[str, list[str]]]:
    """Map every rule's citations onto the three AMLA RTS articles.

    Args:
        rule_citations: `{rule_id: [citation, ...]}` from the spec.

    Returns:
        `(coverage, per_rule_keys)` where `coverage` is one `RtsCoverage`
        per RTS article (in `AMLA_RTS_ARTICLES` order) and `per_rule_keys`
        is `{rule_id: [article_key, ...]}`.
    """
    per_rule_keys: dict[str, list[str]] = {
        rid: _articles_for_citations(cits) for rid, cits in rule_citations.items()
    }
    coverage: list[RtsCoverage] = []
    for art in AMLA_RTS_ARTICLES:
        covering = sorted(rid for rid, keys in per_rule_keys.items() if art.key in keys)
        coverage.append(
            RtsCoverage(
                key=art.key,
                title=art.title,
                citation=art.citation,
                instrument=art.instrument,
                covering_rule_ids=covering,
                n_covering_rules=len(covering),
                status="covered" if covering else "gap",
            )
        )
    return coverage, per_rule_keys


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_amla_effectiveness_report(
    *,
    cases: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    rule_citations: dict[str, list[str]],
    spec_program: str,
    generated_at: datetime,
    labels: dict[str, bool] | None = None,
) -> AmlaEffectivenessReport:
    """Build the frozen AMLA RTS effectiveness report from a run's artifacts.

    Args:
        cases: case dicts (from `cases/<id>.json`).
        decisions: decision events (from `decisions.jsonl`).
        rule_citations: `{rule_id: [citation, ...]}` from the spec's rules.
        spec_program: `spec.program.name`.
        generated_at: report timestamp — supply the run's manifest `as_of`
            so the report is deterministic (no wall-clock read).
        labels: optional `{case_id: true_positive}` for precision.

    Pure + deterministic. Reuses `compute_outcomes` for the funnel so the
    AMLA pack and the existing outcomes pack never diverge.
    """
    outcomes: OutcomesReport = compute_outcomes(
        cases=cases,
        decisions=decisions,
        spec_program=spec_program,
        labels=labels,
        as_of=generated_at,
    )

    coverage, per_rule_keys = build_rts_coverage(rule_citations)

    rules: list[RuleEffectiveness] = []
    for r in outcomes.rules:
        rules.append(
            RuleEffectiveness(
                rule_id=r.rule_id,
                alerts=r.alerts,
                cases_opened=r.cases_opened,
                str_filed=r.str_filed,
                closed_no_action=r.closed_no_action,
                pending=r.pending,
                precision=r.precision,
                recall=r.recall,
                true_positives=r.true_positives,
                false_positives=r.false_positives,
                amla_rts_articles=per_rule_keys.get(r.rule_id, []),
            )
        )

    return AmlaEffectivenessReport(
        spec_program=spec_program,
        generated_at=generated_at,
        total_alerts=outcomes.total_alerts,
        total_cases=outcomes.total_cases,
        total_str_filed=outcomes.total_str_filed,
        total_closed_no_action=outcomes.total_closed_no_action,
        alert_to_case_pct=outcomes.alert_to_case_pct,
        case_to_str_pct=outcomes.case_to_str_pct,
        alert_to_str_pct=outcomes.alert_to_str_pct,
        # The run records STR *filing* (escalated_to_str) but no regulator
        # acceptance feedback. Report it as not-tracked — never fabricated.
        str_acceptance_rate_pct=None,
        str_acceptance_status="not_tracked",
        rts_coverage=coverage,
        n_rts_articles=len(coverage),
        n_rts_covered=sum(1 for c in coverage if c.status == "covered"),
        rules=rules,
    )


def render_markdown(report: AmlaEffectivenessReport) -> str:
    """Render the report as pipe-formatted markdown tables for an MRC pack.

    Deterministic; mirrors the model-inventory markdown shape.
    """
    lines: list[str] = []
    lines.append(f"# AMLA RTS effectiveness pack — {report.spec_program}")
    lines.append("")
    lines.append(f"_Generated at: {report.generated_at.isoformat()}_")
    lines.append("")

    lines.append("## Effectiveness funnel")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| Alerts | {report.total_alerts} |")
    lines.append(f"| Cases opened | {report.total_cases} |")
    lines.append(f"| STR filed | {report.total_str_filed} |")
    lines.append(f"| Closed no action | {report.total_closed_no_action} |")
    lines.append(f"| Alert → case % | {report.alert_to_case_pct} |")
    lines.append(f"| Case → STR % | {report.case_to_str_pct} |")
    lines.append(f"| Alert → STR % | {report.alert_to_str_pct} |")
    accept = (
        "not tracked in run"
        if report.str_acceptance_status == "not_tracked"
        else str(report.str_acceptance_rate_pct)
    )
    lines.append(f"| STR acceptance rate | {accept} |")
    lines.append("")

    lines.append("## AMLA RTS citation coverage")
    lines.append("")
    lines.append("| Status | RTS article | Citation | Instrument | Covering rules |")
    lines.append("|---|---|---|---|---|")
    for c in report.rts_coverage:
        mark = "✓" if c.status == "covered" else "✗"
        rules_cell = ", ".join(c.covering_rule_ids) if c.covering_rule_ids else "—"
        lines.append(f"| {mark} | {c.title} | {c.citation} | {c.instrument} | {rules_cell} |")
    lines.append("")
    lines.append(
        f"_{report.n_rts_covered} of {report.n_rts_articles} AMLA RTS articles "
        f"evidenced by at least one rule._"
    )
    lines.append("")

    lines.append("## Per-rule effectiveness")
    lines.append("")
    lines.append(
        "| Rule | Alerts | Cases | STR filed | Closed | Pending | Precision | RTS articles |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in report.rules:
        prec = "—" if r.precision is None else f"{r.precision}"
        arts = ", ".join(r.amla_rts_articles) if r.amla_rts_articles else "—"
        lines.append(
            f"| {r.rule_id} | {r.alerts} | {r.cases_opened} | {r.str_filed} | "
            f"{r.closed_no_action} | {r.pending} | {prec} | {arts} |"
        )
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "AMLA_RTS_ARTICLES",
    "AmlaEffectivenessReport",
    "AmlaRtsArticle",
    "RtsCoverage",
    "RuleEffectiveness",
    "build_amla_effectiveness_report",
    "build_rts_coverage",
    "render_markdown",
]
