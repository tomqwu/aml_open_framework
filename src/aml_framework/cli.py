"""`aml` command-line entry point."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from aml_framework.data import generate_dataset
from aml_framework.engine import run_spec
from aml_framework.export import export_bundle
from aml_framework.generators import render_control_matrix, render_dag_stub
from aml_framework.spec import load_spec

app = typer.Typer(help="Spec-driven AML automation framework.", add_completion=False)
console = Console()


def _parse_as_of(value: str | None) -> datetime:
    if value is None:
        return datetime.now(tz=timezone.utc).replace(tzinfo=None)
    return datetime.fromisoformat(value)


@app.command()
def validate(spec_path: Path = typer.Argument(..., exists=True, readable=True)) -> None:
    """Validate aml.yaml against the JSON Schema and cross-reference checks."""
    spec = load_spec(spec_path)
    console.print(
        f"[green]OK[/green] {spec_path} — "
        f"{len(spec.data_contracts)} contract(s), {len(spec.rules)} rule(s), "
        f"{len(spec.workflow.queues)} queue(s)."
    )


@app.command()
def generate(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    out_dir: Path = typer.Option(Path(".artifacts/generated"), help="Output directory."),
) -> None:
    """Emit SQL stubs, control matrix, and DAG skeleton from the spec."""
    spec = load_spec(spec_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "control_matrix.md").write_text(render_control_matrix(spec), encoding="utf-8")
    (out_dir / "dag.py").write_text(render_dag_stub(spec), encoding="utf-8")

    console.print(f"[green]Generated[/green] artifacts in {out_dir}/")


@app.command()
def run(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    seed: int = typer.Option(42, help="Synthetic data seed."),
    as_of: str | None = typer.Option(None, help="ISO timestamp used as the rule 'now'."),
    artifacts: Path = typer.Option(Path(".artifacts"), help="Artifacts root."),
) -> None:
    """End-to-end demo: synthesize data, execute rules, emit cases + audit bundle."""
    spec = load_spec(spec_path)
    as_of_dt = _parse_as_of(as_of)
    data = generate_dataset(as_of=as_of_dt, seed=seed)

    result = run_spec(
        spec=spec,
        spec_path=spec_path,
        data=data,
        as_of=as_of_dt,
        artifacts_root=artifacts,
    )

    table = Table(title="Alerts by rule")
    table.add_column("Rule")
    table.add_column("Severity")
    table.add_column("Alerts", justify="right")
    for rule in spec.rules:
        count = len(result.alerts.get(rule.id, []))
        table.add_row(rule.id, rule.severity, str(count))
    console.print(table)

    if result.metrics:
        mtable = Table(title="Metrics")
        mtable.add_column("RAG")
        mtable.add_column("Metric")
        mtable.add_column("Category")
        mtable.add_column("Value", justify="right")
        mtable.add_column("Audience")
        rag_style = {"green": "green", "amber": "yellow", "red": "red", "unset": "dim"}
        for m in result.metrics:
            mtable.add_row(
                f"[{rag_style[m.rag]}]{m.rag.upper()}[/{rag_style[m.rag]}]",
                m.name,
                m.category,
                str(m.value),
                ", ".join(m.audience),
            )
        console.print(mtable)

    console.print(
        f"[green]Done.[/green] {result.total_alerts} alert(s), "
        f"{len(result.case_ids)} case(s), "
        f"{len(result.metrics)} metric(s), "
        f"{len(result.reports)} report(s). "
        f"Run dir: {result.manifest['run_dir']}"
    )


@app.command()
def report(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    audience: str | None = typer.Option(None, help="Filter reports by audience (e.g. svp, vp, director)."),
    report_id: str | None = typer.Option(None, "--report", help="Render a specific report id."),
    run_dir: Path | None = typer.Option(None, help="Specific run dir; defaults to latest."),
    artifacts: Path = typer.Option(Path(".artifacts")),
    stdout: bool = typer.Option(False, help="Print the first matching report to stdout instead of listing."),
) -> None:
    """Show or print role-specific reports from a completed run."""
    spec = load_spec(spec_path)
    if run_dir is None:
        candidates = sorted(artifacts.glob("run-*"), reverse=True)
        if not candidates:
            console.print("[red]No run directories found.[/red] Run `aml run` first.")
            raise typer.Exit(code=1)
        run_dir = candidates[0]

    reports_dir = run_dir / "reports"
    if not reports_dir.exists():
        console.print(f"[red]No reports/[/red] in {run_dir}. Re-run `aml run` on the updated spec.")
        raise typer.Exit(code=1)

    selected = [
        r for r in spec.reports
        if (audience is None or r.audience == audience)
        and (report_id is None or r.id == report_id)
    ]
    if not selected:
        console.print("[yellow]No reports match the filter.[/yellow]")
        raise typer.Exit(code=1)

    if stdout:
        md = (reports_dir / f"{selected[0].id}.md").read_text(encoding="utf-8")
        console.print(md)
        return

    table = Table(title=f"Reports in {run_dir}")
    table.add_column("ID")
    table.add_column("Title")
    table.add_column("Audience")
    table.add_column("Cadence")
    table.add_column("Path")
    for r in selected:
        table.add_row(r.id, r.title or "", r.audience, r.cadence, str(reports_dir / f"{r.id}.md"))
    console.print(table)


@app.command()
def export(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    run_dir: Path | None = typer.Option(None, help="Specific run dir; defaults to latest."),
    out: Path = typer.Option(Path(".artifacts/evidence.zip")),
    artifacts: Path = typer.Option(Path(".artifacts")),
) -> None:
    """Zip a run directory into a regulator-ready evidence bundle."""
    if run_dir is None:
        candidates = sorted(artifacts.glob("run-*"), reverse=True)
        if not candidates:
            console.print("[red]No run directories found.[/red] Run `aml run` first.")
            raise typer.Exit(code=1)
        run_dir = candidates[0]

    out_path = export_bundle(run_dir, out)
    console.print(f"[green]Bundle[/green] {out_path} (from {run_dir})")


if __name__ == "__main__":
    app()
