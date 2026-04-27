"""Effectiveness Evidence Pack — FinCEN April 2026 NPRM artifact.

Consumes a finalised run dir (audit ledger + alerts + cases + decisions
+ metrics) and produces a structured artifact mapped to the four pillars
FinCEN's 2026-04-07 Notice of Proposed Rulemaking ("Reform of the AML/CFT
Programs Requirements") names. Examiners are moving from "existence" to
"effectiveness" standards; institutions need to demonstrate, with
evidence, that their programme is working — not just that it exists.

The four pillars
    1. **Risk-assessment alignment** — every rule is tied to a documented
       risk (`regulation_refs`), and severity matches assessed risk.
    2. **AML/CFT priority coverage** — what FinCEN priorities does the
       programme cover (via the new `aml_priority` rule field), and where
       are the gaps?
    3. **Control output quality** — alert volume, false-positive proxy
       (closed_no_action rate from decisions), tuning evidence (precision/
       recall from `tuning_run` events), narrative-review acceptance rate.
    4. **Feedback loop evidence** — recent threshold changes (tuning_run
       events), pKYC trigger rate (responsiveness to risk shifts),
       narrative-review action mix.

Output: a single JSON document. The caller can pretty-print to PDF
downstream or surface in the dashboard. Same determinism contract as
`goaml_xml.py` and `amla_str.py` — same inputs → same bytes.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aml_framework import __version__ as ENGINE_VERSION
from aml_framework.spec.models import AMLSpec

NPRM_VERSION = "FinCEN-NPRM-2026-04-07"
NPRM_DOCKET = "FINCEN-2026-NPRM-001"  # placeholder; final docket published with rule
NPRM_PILLARS = (
    "risk_assessment_alignment",
    "aml_cft_priority_coverage",
    "control_output_quality",
    "feedback_loop_evidence",
)

# Canonical FinCEN AML/CFT priorities (June 2021, reaffirmed by the 2026
# NPRM). Order matters for deterministic JSON output.
FINCEN_PRIORITIES = (
    "corruption",
    "cybercrime",
    "terrorist_financing",
    "fraud",
    "transnational_criminal_organization",
    "drug_trafficking",
    "human_trafficking",
    "proliferation_financing",
)


@dataclass(frozen=True)
class PillarFinding:
    """One finding within a pillar — keyed by `key` for stable lookup."""

    key: str
    label: str
    value: Any  # could be float, int, str, dict
    status: str = "informational"  # informational | satisfied | gap | warning


@dataclass(frozen=True)
class PillarResult:
    pillar: str
    summary: str
    findings: list[PillarFinding] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pillar 1: Risk-assessment alignment
# ---------------------------------------------------------------------------


def _pillar_risk_alignment(spec: AMLSpec) -> PillarResult:
    rules = list(spec.rules)
    total = len(rules)
    with_refs = sum(1 for r in rules if r.regulation_refs)
    with_tags = sum(1 for r in rules if r.tags)
    severity_counts = Counter(r.severity for r in rules)

    # Rule of thumb: every active rule must cite ≥1 regulation_ref.
    gap = total - with_refs
    findings = [
        PillarFinding(
            key="rules_total",
            label="Total active rules",
            value=total,
        ),
        PillarFinding(
            key="rules_with_regulation_refs",
            label="Rules citing ≥1 regulation reference",
            value=with_refs,
            status="satisfied" if gap == 0 else "gap",
        ),
        PillarFinding(
            key="rules_with_tags",
            label="Rules with typology tags",
            value=with_tags,
            status="satisfied" if with_tags >= total * 0.8 else "warning",
        ),
        PillarFinding(
            key="severity_distribution",
            label="Severity distribution",
            value=dict(sorted(severity_counts.items())),
        ),
    ]
    summary = (
        f"{with_refs}/{total} rules cite regulation references. "
        f"Severity mix: {dict(sorted(severity_counts.items()))}."
    )
    return PillarResult(pillar="risk_assessment_alignment", summary=summary, findings=findings)


# ---------------------------------------------------------------------------
# Pillar 2: AML/CFT priority coverage
# ---------------------------------------------------------------------------


def _pillar_priority_coverage(spec: AMLSpec) -> PillarResult:
    by_priority: dict[str, list[str]] = {p: [] for p in FINCEN_PRIORITIES}
    by_priority["other"] = []
    unmapped: list[str] = []
    for rule in spec.rules:
        priority = rule.aml_priority
        if priority is None:
            unmapped.append(rule.id)
            by_priority["other"].append(rule.id)
        else:
            by_priority[priority].append(rule.id)

    coverage_pct = sum(1 for p in FINCEN_PRIORITIES if by_priority[p]) / len(FINCEN_PRIORITIES)

    findings = [
        PillarFinding(
            key="priority_coverage_pct",
            label="FinCEN priorities with at least one rule",
            value=round(coverage_pct, 4),
            status="satisfied" if coverage_pct >= 0.5 else "gap",
        ),
        PillarFinding(
            key="rules_by_priority",
            label="Rules grouped by FinCEN priority",
            value={k: sorted(v) for k, v in by_priority.items()},
        ),
        PillarFinding(
            key="unmapped_rules",
            label="Rules without `aml_priority` field (need MLRO classification)",
            value=sorted(unmapped),
            status="gap" if unmapped else "satisfied",
        ),
    ]
    summary = (
        f"Programme covers {sum(1 for p in FINCEN_PRIORITIES if by_priority[p])}"
        f"/{len(FINCEN_PRIORITIES)} FinCEN priorities. "
        f"{len(unmapped)} rules unmapped."
    )
    return PillarResult(pillar="aml_cft_priority_coverage", summary=summary, findings=findings)


# ---------------------------------------------------------------------------
# Pillar 3: Control output quality
# ---------------------------------------------------------------------------


def _pillar_control_quality(
    alerts_by_rule: dict[str, list[dict[str, Any]]],
    decisions: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
) -> PillarResult:
    total_alerts = sum(len(v) for v in alerts_by_rule.values())

    # False-positive proxy: cases closed_no_action vs total decisions.
    closed_no_action = sum(1 for d in decisions if d.get("disposition") == "closed_no_action")
    closed_with_action = sum(
        1
        for d in decisions
        if d.get("disposition") in ("filed_str", "escalate_to_str", "filed_sar", "escalate")
    )
    total_dispositions = closed_no_action + closed_with_action
    fp_proxy = round(closed_no_action / total_dispositions, 4) if total_dispositions else None

    # Narrative review acceptance: accept / total narrative_review events.
    nr_events = [d for d in decisions if d.get("event") == "narrative_review"]
    nr_accept = sum(1 for d in nr_events if d.get("disposition") == "accept")
    nr_acceptance = round(nr_accept / len(nr_events), 4) if nr_events else None

    # Tuning evidence: count tuning_run events + best F1 if recorded.
    tuning_events = [d for d in decisions if d.get("event") == "tuning_run"]
    best_f1_records = [d.get("best_f1") for d in tuning_events if d.get("best_f1") is not None]

    findings = [
        PillarFinding(
            key="total_alerts",
            label="Alerts produced this run",
            value=total_alerts,
        ),
        PillarFinding(
            key="alerts_by_rule",
            label="Alerts grouped by rule",
            value={k: len(v) for k, v in sorted(alerts_by_rule.items())},
        ),
        PillarFinding(
            key="false_positive_proxy",
            label="closed_no_action / (closed_no_action + filed)",
            value=fp_proxy,
            status="satisfied" if fp_proxy is not None and fp_proxy < 0.95 else "warning",
        ),
        PillarFinding(
            key="narrative_review_acceptance_rate",
            label="Analyst acceptance rate of LLM-drafted narratives",
            value=nr_acceptance,
        ),
        PillarFinding(
            key="tuning_runs_recorded",
            label="Threshold tuning sweeps in audit trail",
            value=len(tuning_events),
            status="satisfied" if tuning_events else "warning",
        ),
        PillarFinding(
            key="best_f1_observed",
            label="Best F1 across recorded tuning runs",
            value=best_f1_records,
        ),
        PillarFinding(
            key="metrics_red_count",
            label="Metrics in RED RAG band (operational health)",
            value=sum(1 for m in metrics if m.get("rag") == "red"),
            status="warning"
            if sum(1 for m in metrics if m.get("rag") == "red") > 0
            else "satisfied",
        ),
    ]
    summary = (
        f"{total_alerts} alerts; FP proxy {fp_proxy}; "
        f"{len(tuning_events)} tuning sweep(s) recorded."
    )
    return PillarResult(pillar="control_output_quality", summary=summary, findings=findings)


# ---------------------------------------------------------------------------
# Pillar 4: Feedback loop evidence
# ---------------------------------------------------------------------------


def _pillar_feedback_loop(decisions: list[dict[str, Any]]) -> PillarResult:
    pkyc_events = [d for d in decisions if d.get("event") == "pkyc_review"]
    tuning_events = [d for d in decisions if d.get("event") == "tuning_run"]
    nr_events = [d for d in decisions if d.get("event") == "narrative_review"]
    escalations = [d for d in decisions if d.get("event") == "escalated_to_str"]

    nr_action_mix = Counter(d.get("disposition") for d in nr_events)

    findings = [
        PillarFinding(
            key="pkyc_review_count",
            label="pKYC re-review actions recorded",
            value=len(pkyc_events),
            status="satisfied" if pkyc_events else "warning",
        ),
        PillarFinding(
            key="tuning_run_count",
            label="Threshold tuning iterations executed",
            value=len(tuning_events),
        ),
        PillarFinding(
            key="narrative_review_action_mix",
            label="Analyst action mix on drafted narratives",
            value=dict(sorted(nr_action_mix.items())),
        ),
        PillarFinding(
            key="str_escalation_count",
            label="Cases escalated to STR/SAR filing",
            value=len(escalations),
        ),
    ]
    summary = (
        f"{len(pkyc_events)} pKYC, {len(tuning_events)} tuning, "
        f"{len(nr_events)} narrative reviews, {len(escalations)} STR escalations."
    )
    return PillarResult(pillar="feedback_loop_evidence", summary=summary, findings=findings)


# ---------------------------------------------------------------------------
# Top-level builders
# ---------------------------------------------------------------------------


def build_effectiveness_pack(
    spec: AMLSpec,
    *,
    alerts_by_rule: dict[str, list[dict[str, Any]]] | None = None,
    decisions: list[dict[str, Any]] | None = None,
    metrics: list[dict[str, Any]] | None = None,
    manifest: dict[str, Any] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build the structured Effectiveness Evidence Pack.

    Every input except `spec` is optional. Missing data degrades gracefully
    — pillars compute what they can and mark gaps with `status="gap"` or
    `status="warning"`. The pack still serialises and is auditable.
    """
    alerts_by_rule = alerts_by_rule or {}
    decisions = decisions or []
    metrics = metrics or []
    manifest = manifest or {}
    generated_at = generated_at or datetime.now(tz=timezone.utc)

    pillars = [
        _pillar_risk_alignment(spec),
        _pillar_priority_coverage(spec),
        _pillar_control_quality(alerts_by_rule, decisions, metrics),
        _pillar_feedback_loop(decisions),
    ]

    overall_gaps = sum(1 for p in pillars for f in p.findings if f.status == "gap")
    overall_warnings = sum(1 for p in pillars for f in p.findings if f.status == "warning")
    overall_satisfied = sum(1 for p in pillars for f in p.findings if f.status == "satisfied")

    return {
        "_schema": NPRM_VERSION,
        "_docket": NPRM_DOCKET,
        "_generated_at": generated_at.isoformat(),
        "_engine_version": ENGINE_VERSION,
        "programme": {
            "name": spec.program.name,
            "jurisdiction": spec.program.jurisdiction,
            "regulator": spec.program.regulator,
            "owner": spec.program.owner,
            "effective_date": spec.program.effective_date.isoformat(),
        },
        "audit_trail_anchor": {
            "spec_content_hash": manifest.get("spec_content_hash"),
            "decisions_hash": manifest.get("decisions_hash"),
            "as_of": manifest.get("as_of"),
            "run_dir": manifest.get("run_dir"),
        },
        "summary": {
            "pillars_evaluated": len(pillars),
            "findings_satisfied": overall_satisfied,
            "findings_warning": overall_warnings,
            "findings_gap": overall_gaps,
        },
        "pillars": [
            {
                "pillar": p.pillar,
                "summary": p.summary,
                "findings": [
                    {
                        "key": f.key,
                        "label": f.label,
                        "value": f.value,
                        "status": f.status,
                    }
                    for f in p.findings
                ],
            }
            for p in pillars
        ],
    }


def build_effectiveness_pack_json(spec: AMLSpec, **kwargs: Any) -> bytes:
    """Convenience: build pack and serialise to JSON bytes."""
    pack = build_effectiveness_pack(spec, **kwargs)
    return json.dumps(pack, indent=2, sort_keys=True, default=str).encode("utf-8")


def render_effectiveness_markdown(pack: dict[str, Any]) -> str:
    """Render the pack as a Markdown report — the artifact a regulator
    or board member actually reads. Pure formatting, no IO."""
    lines: list[str] = []
    prog = pack.get("programme", {})
    lines.append(f"# Effectiveness Evidence Pack — {prog.get('name', '?')}")
    lines.append("")
    lines.append(f"**Schema**: `{pack['_schema']}`  ·  **Docket**: `{pack['_docket']}`")
    lines.append(f"**Generated at**: {pack['_generated_at']}")
    lines.append(f"**Engine version**: `{pack['_engine_version']}`")
    lines.append("")
    lines.append(
        f"**Programme**: {prog.get('name')}  ·  "
        f"jurisdiction: {prog.get('jurisdiction')}  ·  "
        f"regulator: {prog.get('regulator')}  ·  "
        f"owner: {prog.get('owner')}"
    )
    lines.append("")

    summary = pack.get("summary", {})
    lines.append("## Summary")
    lines.append(f"- {summary.get('pillars_evaluated', 0)} pillars evaluated")
    lines.append(f"- ✅ {summary.get('findings_satisfied', 0)} satisfied")
    lines.append(f"- ⚠️ {summary.get('findings_warning', 0)} warnings")
    lines.append(f"- ❌ {summary.get('findings_gap', 0)} gaps requiring action")
    lines.append("")

    anchor = pack.get("audit_trail_anchor", {})
    lines.append("## Audit-trail anchor")
    lines.append(f"- spec_content_hash: `{anchor.get('spec_content_hash')}`")
    lines.append(f"- decisions_hash: `{anchor.get('decisions_hash')}`")
    lines.append(f"- as_of: {anchor.get('as_of')}")
    lines.append(f"- run_dir: `{anchor.get('run_dir')}`")
    lines.append("")

    for p in pack.get("pillars", []):
        lines.append(f"## Pillar: {p['pillar'].replace('_', ' ').title()}")
        lines.append("")
        lines.append(p["summary"])
        lines.append("")
        for f in p.get("findings", []):
            icon = {"satisfied": "✅", "warning": "⚠️", "gap": "❌"}.get(f["status"], "•")
            lines.append(f"- {icon} **{f['label']}** — `{f['value']}`")
        lines.append("")

    return "\n".join(lines)


def export_pack_from_run_dir(
    spec: AMLSpec,
    run_dir: Path,
    *,
    generated_at: datetime | None = None,
) -> bytes:
    """Read alerts + decisions + manifest from a finalised run dir and
    build the pack JSON bytes."""
    if not run_dir.exists():
        raise FileNotFoundError(f"Run dir not found: {run_dir}")

    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes()) if manifest_path.exists() else {}

    alerts_by_rule: dict[str, list[dict[str, Any]]] = {}
    alerts_dir = run_dir / "alerts"
    if alerts_dir.exists():
        for jsonl in sorted(alerts_dir.glob("*.jsonl")):
            rule_id = jsonl.stem
            rows: list[dict[str, Any]] = []
            for line in jsonl.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.append(json.loads(line))
            alerts_by_rule[rule_id] = rows

    decisions: list[dict[str, Any]] = []
    decisions_path = run_dir / "decisions.jsonl"
    if decisions_path.exists():
        for line in decisions_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                decisions.append(json.loads(line))

    metrics = manifest.get("metrics", []) or []

    return build_effectiveness_pack_json(
        spec,
        alerts_by_rule=alerts_by_rule,
        decisions=decisions,
        metrics=metrics,
        manifest=manifest,
        generated_at=generated_at,
    )
