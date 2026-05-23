"""Spec comparison tool — show what changed between two aml.yaml specs.

Internal layout: `compute_spec_diff` does the comparison and returns a
structured `SpecDiffResult`. `diff_specs` is the CLI entry point — it
calls `compute_spec_diff` and prints the result via Rich tables. The
API exposes `compute_spec_diff` directly via `/api/v1/diff` so callers
get the structured form without having to parse Rich-formatted text.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict
from rich.console import Console
from rich.table import Table

from aml_framework.spec import load_spec

console = Console()


# ---------------------------------------------------------------------------
# Structured result models
# ---------------------------------------------------------------------------


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FieldChange(_Base):
    field: str
    before: str
    after: str


class RuleAdded(_Base):
    id: str
    name: str
    severity: str


class RuleRemoved(_Base):
    id: str
    name: str
    severity: str


class RuleModified(_Base):
    id: str
    changes: list[str]


class MetricAdded(_Base):
    id: str
    name: str


class MetricRemoved(_Base):
    id: str
    name: str


class MetricModified(_Base):
    id: str
    changes: list[str]


# PR-D1 (#374): structured diff entries for DataContract changes. The
# spec_diff path didn't surface contract-level edits before this PR, so
# a layer re-tier (or any future additive contract field) would slip
# through `aml diff` silently. Mirrors the Rule equivalents.
class DataContractAdded(_Base):
    id: str
    source: str


class DataContractRemoved(_Base):
    id: str
    source: str


class DataContractModified(_Base):
    id: str
    changes: list[str]


class SpecDiffSummary(_Base):
    rules_total_a: int
    rules_total_b: int
    rules_added: int
    rules_removed: int
    metrics_total_a: int
    metrics_total_b: int
    metrics_added: int
    metrics_removed: int
    queues_total_a: int
    queues_total_b: int
    # PR-D1 (#374): contract-level totals + deltas for symmetry with the
    # rules / metrics roll-up so a `compute_spec_diff` consumer can spot
    # contract churn without iterating the full list.
    data_contracts_total_a: int
    data_contracts_total_b: int
    data_contracts_added: int
    data_contracts_removed: int


class SpecDiffResult(_Base):
    spec_a_name: str
    spec_b_name: str
    program_changes: list[FieldChange]
    rules_added: list[RuleAdded]
    rules_removed: list[RuleRemoved]
    rules_modified: list[RuleModified]
    metrics_added: list[MetricAdded]
    metrics_removed: list[MetricRemoved]
    metrics_modified: list[MetricModified]
    queues_added: list[str]
    queues_removed: list[str]
    # PR-D1 (#374): contract-level added/removed/modified lists. Added
    # alongside the rule/metric equivalents so the API surface stays
    # symmetrical. `data_contracts_modified` surfaces per-attribute
    # transitions (currently `layer`) for an `aml diff` reviewer.
    data_contracts_added: list[DataContractAdded]
    data_contracts_removed: list[DataContractRemoved]
    data_contracts_modified: list[DataContractModified]
    summary: SpecDiffSummary


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def compute_spec_diff(path_a: Path, path_b: Path) -> SpecDiffResult:
    """Compare two specs and return a structured result.

    The CLI (`aml diff`) wraps this with Rich rendering; the REST API
    surfaces it directly. Loading is best-effort — if either spec fails
    Pydantic validation, the underlying loader's exception bubbles up so
    the caller can decide how to surface it.
    """
    spec_a = load_spec(path_a)
    spec_b = load_spec(path_b)

    program_changes: list[FieldChange] = []
    if spec_a.program != spec_b.program:
        for field in ("name", "jurisdiction", "regulator", "owner", "effective_date"):
            va = getattr(spec_a.program, field)
            vb = getattr(spec_b.program, field)
            if va != vb:
                program_changes.append(FieldChange(field=field, before=str(va), after=str(vb)))
        # PR-D2 (#375): surface nfrs changes per-attribute so an NFR-only
        # update (e.g. rto_minutes 60 → 30) doesn't slip through audit
        # review with no program_changes recorded. Codex pass on PR-D2.
        nfrs_a = spec_a.program.nfrs
        nfrs_b = spec_b.program.nfrs
        if nfrs_a != nfrs_b:
            for field in (
                "rto_minutes",
                "rpo_minutes",
                "sla_p95_ms",
                "throughput_per_min",
                "retention_days",
                "notes",
            ):
                va = getattr(nfrs_a, field, None) if nfrs_a is not None else None
                vb = getattr(nfrs_b, field, None) if nfrs_b is not None else None
                before = "" if va is None else str(va)
                after = "" if vb is None else str(vb)
                # Skip when the rendered strings match — `notes` defaults
                # to "" on a fresh NFR block, so adding `nfrs: {rto: 60}`
                # would otherwise emit a bogus `nfrs.notes` row with
                # identical before/after empty strings. Codex pass 2.
                if before == after:
                    continue
                program_changes.append(
                    FieldChange(field=f"nfrs.{field}", before=before, after=after)
                )
        # PR-LF1 (#383): same posture for `program.sla` — an SLA-only
        # change (e.g. alert_disposition_days 30 → 15) is regulator-
        # facing and must land in `program_changes` so the audit diff
        # reflects it. Mirrors the NFRs handling above.
        sla_a = spec_a.program.sla
        sla_b = spec_b.program.sla
        if sla_a != sla_b:
            for field in (
                "alert_disposition_days",
                "batch_cadence_days",
                "batch_lateness_grace_days",
            ):
                va = getattr(sla_a, field, None) if sla_a is not None else None
                vb = getattr(sla_b, field, None) if sla_b is not None else None
                before = "" if va is None else str(va)
                after = "" if vb is None else str(vb)
                if before == after:
                    continue
                program_changes.append(
                    FieldChange(field=f"sla.{field}", before=before, after=after)
                )

    rules_a = {r.id: r for r in spec_a.rules}
    rules_b = {r.id: r for r in spec_b.rules}
    added_ids = sorted(set(rules_b) - set(rules_a))
    removed_ids = sorted(set(rules_a) - set(rules_b))
    common_ids = sorted(set(rules_a) & set(rules_b))

    rules_added = [
        RuleAdded(id=rid, name=rules_b[rid].name, severity=rules_b[rid].severity)
        for rid in added_ids
    ]
    rules_removed = [
        RuleRemoved(id=rid, name=rules_a[rid].name, severity=rules_a[rid].severity)
        for rid in removed_ids
    ]

    rules_modified: list[RuleModified] = []
    for rid in common_ids:
        ra, rb = rules_a[rid], rules_b[rid]
        changes: list[str] = []
        if ra.severity != rb.severity:
            changes.append(f"severity: {ra.severity} -> {rb.severity}")
        if ra.status != rb.status:
            changes.append(f"status: {ra.status} -> {rb.status}")
        if ra.logic != rb.logic:
            changes.append("logic changed")
        if ra.escalate_to != rb.escalate_to:
            changes.append(f"queue: {ra.escalate_to} -> {rb.escalate_to}")
        # PR-A2: surface authored-rationale + explicit-scope changes
        # so an examiner reviewing `aml diff` sees changes to the
        # rule's documented intent, not just its mechanical fields.
        if ra.business_intent != rb.business_intent:
            changes.append("business_intent changed")
        if ra.out_of_scope != rb.out_of_scope:
            changes.append("out_of_scope changed")
        # PR-RISK-1: surface risk_tier changes so a risk-based-controls
        # reviewer sees re-tiering events in `aml diff`. Rendered as a
        # value transition (mirrors severity / status / queue lines)
        # because the field is a small enum, not free-text/list.
        if ra.risk_tier != rb.risk_tier:
            changes.append(f"risk_tier: {ra.risk_tier} -> {rb.risk_tier}")
        if changes:
            rules_modified.append(RuleModified(id=rid, changes=changes))

    metrics_a = {m.id: m for m in spec_a.metrics}
    metrics_b = {m.id: m for m in spec_b.metrics}
    m_added_ids = sorted(set(metrics_b) - set(metrics_a))
    m_removed_ids = sorted(set(metrics_a) - set(metrics_b))
    m_common_ids = sorted(set(metrics_a) & set(metrics_b))

    metrics_added = [MetricAdded(id=mid, name=metrics_b[mid].name) for mid in m_added_ids]
    metrics_removed = [MetricRemoved(id=mid, name=metrics_a[mid].name) for mid in m_removed_ids]

    metrics_modified: list[MetricModified] = []
    for mid in m_common_ids:
        ma, mb = metrics_a[mid], metrics_b[mid]
        changes = []
        if ma.thresholds != mb.thresholds:
            changes.append("thresholds changed")
        if ma.target != mb.target:
            changes.append("target changed")
        if ma.audience != mb.audience:
            changes.append("audience changed")
        if changes:
            metrics_modified.append(MetricModified(id=mid, changes=changes))

    queues_a = {q.id for q in spec_a.workflow.queues}
    queues_b = {q.id for q in spec_b.workflow.queues}
    queues_added = sorted(queues_b - queues_a)
    queues_removed = sorted(queues_a - queues_b)

    # PR-D1 (#374): contract-level diff. Surfaces added/removed contracts
    # and per-attribute transitions on common contracts (currently
    # `layer`). The pre-D1 spec_diff path didn't track contracts at all,
    # so any contract edit was invisible to an `aml diff` reviewer.
    contracts_a = {c.id: c for c in spec_a.data_contracts}
    contracts_b = {c.id: c for c in spec_b.data_contracts}
    c_added_ids = sorted(set(contracts_b) - set(contracts_a))
    c_removed_ids = sorted(set(contracts_a) - set(contracts_b))
    c_common_ids = sorted(set(contracts_a) & set(contracts_b))

    data_contracts_added = [
        DataContractAdded(id=cid, source=contracts_b[cid].source) for cid in c_added_ids
    ]
    data_contracts_removed = [
        DataContractRemoved(id=cid, source=contracts_a[cid].source) for cid in c_removed_ids
    ]

    data_contracts_modified: list[DataContractModified] = []
    for cid in c_common_ids:
        ca, cb = contracts_a[cid], contracts_b[cid]
        changes: list[str] = []
        if ca.layer != cb.layer:
            changes.append(f"layer: {ca.layer} -> {cb.layer}")
        if changes:
            data_contracts_modified.append(DataContractModified(id=cid, changes=changes))

    summary = SpecDiffSummary(
        rules_total_a=len(spec_a.rules),
        rules_total_b=len(spec_b.rules),
        rules_added=len(added_ids),
        rules_removed=len(removed_ids),
        metrics_total_a=len(spec_a.metrics),
        metrics_total_b=len(spec_b.metrics),
        metrics_added=len(m_added_ids),
        metrics_removed=len(m_removed_ids),
        queues_total_a=len(spec_a.workflow.queues),
        queues_total_b=len(spec_b.workflow.queues),
        data_contracts_total_a=len(spec_a.data_contracts),
        data_contracts_total_b=len(spec_b.data_contracts),
        data_contracts_added=len(c_added_ids),
        data_contracts_removed=len(c_removed_ids),
    )

    return SpecDiffResult(
        spec_a_name=path_a.name,
        spec_b_name=path_b.name,
        program_changes=program_changes,
        rules_added=rules_added,
        rules_removed=rules_removed,
        rules_modified=rules_modified,
        metrics_added=metrics_added,
        metrics_removed=metrics_removed,
        metrics_modified=metrics_modified,
        queues_added=queues_added,
        queues_removed=queues_removed,
        data_contracts_added=data_contracts_added,
        data_contracts_removed=data_contracts_removed,
        data_contracts_modified=data_contracts_modified,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# CLI rendering
# ---------------------------------------------------------------------------


def diff_specs(path_a: Path, path_b: Path) -> None:
    """Compare two specs and print the differences (CLI entry point)."""
    result = compute_spec_diff(path_a, path_b)
    _render(result)


def _render(result: SpecDiffResult) -> None:
    console.print(f"\n[bold]Comparing[/bold] {result.spec_a_name} vs {result.spec_b_name}\n")

    if result.program_changes:
        table = Table(title="Program Changes")
        table.add_column("Field")
        table.add_column(result.spec_a_name)
        table.add_column(result.spec_b_name)
        for ch in result.program_changes:
            table.add_row(ch.field, ch.before, ch.after)
        console.print(table)

    if result.rules_added or result.rules_removed or result.rules_modified:
        table = Table(title="Rule Changes")
        table.add_column("Change")
        table.add_column("Rule ID")
        table.add_column("Details")
        for r in result.rules_added:
            table.add_row("[green]+ added[/green]", r.id, f"{r.name} ({r.severity})")
        for r in result.rules_removed:
            table.add_row("[red]- removed[/red]", r.id, f"{r.name} ({r.severity})")
        for r in result.rules_modified:
            table.add_row("[yellow]~ modified[/yellow]", r.id, "; ".join(r.changes))
        console.print(table)

    metrics_changed = result.metrics_added or result.metrics_removed or result.metrics_modified
    if metrics_changed:
        table = Table(title="Metric Changes")
        table.add_column("Change")
        table.add_column("Metric ID")
        table.add_column("Details")
        for m in result.metrics_added:
            table.add_row("[green]+ added[/green]", m.id, m.name)
        for m in result.metrics_removed:
            table.add_row("[red]- removed[/red]", m.id, m.name)
        for m in result.metrics_modified:
            table.add_row("[yellow]~ modified[/yellow]", m.id, "; ".join(m.changes))
        console.print(table)

    if result.queues_added or result.queues_removed:
        table = Table(title="Workflow Queue Changes")
        table.add_column("Change")
        table.add_column("Queue ID")
        for qid in result.queues_added:
            table.add_row("[green]+ added[/green]", qid)
        for qid in result.queues_removed:
            table.add_row("[red]- removed[/red]", qid)
        console.print(table)

    # PR-D1 (#374): print contract changes so an `aml diff` reviewer
    # sees added/removed contracts and `layer` transitions.
    contracts_changed = (
        result.data_contracts_added
        or result.data_contracts_removed
        or result.data_contracts_modified
    )
    if contracts_changed:
        table = Table(title="Data Contract Changes")
        table.add_column("Change")
        table.add_column("Contract ID")
        table.add_column("Details")
        for c in result.data_contracts_added:
            table.add_row("[green]+ added[/green]", c.id, c.source)
        for c in result.data_contracts_removed:
            table.add_row("[red]- removed[/red]", c.id, c.source)
        for c in result.data_contracts_modified:
            table.add_row("[yellow]~ modified[/yellow]", c.id, "; ".join(c.changes))
        console.print(table)

    console.print("\n[bold]Summary:[/bold]")
    s = result.summary
    console.print(
        f"  Rules: {s.rules_total_a} -> {s.rules_total_b} "
        f"({s.rules_added} added, {s.rules_removed} removed)"
    )
    console.print(
        f"  Metrics: {s.metrics_total_a} -> {s.metrics_total_b} "
        f"({s.metrics_added} added, {s.metrics_removed} removed)"
    )
    console.print(f"  Queues: {s.queues_total_a} -> {s.queues_total_b}")
    console.print(
        f"  Data Contracts: {s.data_contracts_total_a} -> {s.data_contracts_total_b} "
        f"({s.data_contracts_added} added, {s.data_contracts_removed} removed)"
    )
    console.print()
