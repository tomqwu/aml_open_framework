"""Spec comparison tool — show what changed between two aml.yaml specs."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.table import Table

from aml_framework.spec import load_spec

console = Console()


def diff_specs(path_a: Path, path_b: Path) -> None:
    """Compare two specs and print the differences."""
    spec_a = load_spec(path_a)
    spec_b = load_spec(path_b)

    console.print(f"\n[bold]Comparing[/bold] {path_a.name} vs {path_b.name}\n")

    # Program.
    if spec_a.program != spec_b.program:
        table = Table(title="Program Changes")
        table.add_column("Field")
        table.add_column(path_a.name)
        table.add_column(path_b.name)
        for field in ("name", "jurisdiction", "regulator", "owner", "effective_date"):
            va = getattr(spec_a.program, field)
            vb = getattr(spec_b.program, field)
            if va != vb:
                table.add_row(field, str(va), str(vb))
        console.print(table)

    # Rules.
    rules_a = {r.id: r for r in spec_a.rules}
    rules_b = {r.id: r for r in spec_b.rules}
    added = set(rules_b) - set(rules_a)
    removed = set(rules_a) - set(rules_b)
    common = set(rules_a) & set(rules_b)

    if added or removed:
        table = Table(title="Rule Changes")
        table.add_column("Change")
        table.add_column("Rule ID")
        table.add_column("Details")
        for rid in sorted(added):
            r = rules_b[rid]
            table.add_row("[green]+ added[/green]", rid, f"{r.name} ({r.severity})")
        for rid in sorted(removed):
            r = rules_a[rid]
            table.add_row("[red]- removed[/red]", rid, f"{r.name} ({r.severity})")
        for rid in sorted(common):
            ra, rb = rules_a[rid], rules_b[rid]
            changes = []
            if ra.severity != rb.severity:
                changes.append(f"severity: {ra.severity} -> {rb.severity}")
            if ra.status != rb.status:
                changes.append(f"status: {ra.status} -> {rb.status}")
            if ra.logic != rb.logic:
                changes.append("logic changed")
            if ra.escalate_to != rb.escalate_to:
                changes.append(f"queue: {ra.escalate_to} -> {rb.escalate_to}")
            if changes:
                table.add_row("[yellow]~ modified[/yellow]", rid, "; ".join(changes))
        console.print(table)

    # Metrics.
    metrics_a = {m.id: m for m in spec_a.metrics}
    metrics_b = {m.id: m for m in spec_b.metrics}
    m_added = set(metrics_b) - set(metrics_a)
    m_removed = set(metrics_a) - set(metrics_b)
    m_common = set(metrics_a) & set(metrics_b)

    if (
        m_added
        or m_removed
        or any(metrics_a[m].thresholds != metrics_b[m].thresholds for m in m_common)
    ):
        table = Table(title="Metric Changes")
        table.add_column("Change")
        table.add_column("Metric ID")
        table.add_column("Details")
        for mid in sorted(m_added):
            table.add_row("[green]+ added[/green]", mid, metrics_b[mid].name)
        for mid in sorted(m_removed):
            table.add_row("[red]- removed[/red]", mid, metrics_a[mid].name)
        for mid in sorted(m_common):
            ma, mb = metrics_a[mid], metrics_b[mid]
            changes = []
            if ma.thresholds != mb.thresholds:
                changes.append("thresholds changed")
            if ma.target != mb.target:
                changes.append("target changed")
            if ma.audience != mb.audience:
                changes.append("audience changed")
            if changes:
                table.add_row("[yellow]~ modified[/yellow]", mid, "; ".join(changes))
        console.print(table)

    # Workflow queues.
    queues_a = {q.id for q in spec_a.workflow.queues}
    queues_b = {q.id for q in spec_b.workflow.queues}
    q_added = queues_b - queues_a
    q_removed = queues_a - queues_b
    if q_added or q_removed:
        table = Table(title="Workflow Queue Changes")
        table.add_column("Change")
        table.add_column("Queue ID")
        for qid in sorted(q_added):
            table.add_row("[green]+ added[/green]", qid)
        for qid in sorted(q_removed):
            table.add_row("[red]- removed[/red]", qid)
        console.print(table)

    # Summary.
    console.print("\n[bold]Summary:[/bold]")
    console.print(
        f"  Rules: {len(spec_a.rules)} -> {len(spec_b.rules)} "
        f"({len(added)} added, {len(removed)} removed)"
    )
    console.print(
        f"  Metrics: {len(spec_a.metrics)} -> {len(spec_b.metrics)} "
        f"({len(m_added)} added, {len(m_removed)} removed)"
    )
    console.print(f"  Queues: {len(spec_a.workflow.queues)} -> {len(spec_b.workflow.queues)}")
    console.print()
