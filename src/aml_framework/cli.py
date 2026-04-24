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
    data_source: str = typer.Option("synthetic", help="Data source: synthetic, csv, parquet, duckdb."),
    data_dir: str | None = typer.Option(None, help="Directory with CSV/Parquet files. Default: data/input/"),
) -> None:
    """End-to-end: load data, execute rules, emit cases + audit bundle."""
    from aml_framework.data.sources import resolve_source

    spec = load_spec(spec_path)
    as_of_dt = _parse_as_of(as_of)
    data = resolve_source(
        source_type=data_source, spec=spec, as_of=as_of_dt,
        seed=seed, data_dir=data_dir,
    )

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


@app.command()
def dashboard(
    spec_path: Path = typer.Argument(
        Path("examples/community_bank/aml.yaml"), exists=True, readable=True
    ),
    port: int = typer.Option(8501, help="Streamlit server port."),
    seed: int = typer.Option(42, help="Synthetic data seed."),
) -> None:
    """Launch the interactive Streamlit demo dashboard."""
    import subprocess
    import sys

    dashboard_app = Path(__file__).parent / "dashboard" / "app.py"
    subprocess.run(
        [
            sys.executable, "-m", "streamlit", "run", str(dashboard_app),
            "--server.port", str(port),
            "--server.headless", "true",
            "--", str(spec_path.resolve()), str(seed),
        ],
        check=False,
    )


@app.command(name="export-alerts")
def export_alerts(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    run_dir: Path | None = typer.Option(None, help="Specific run dir; defaults to latest."),
    out: Path = typer.Option(Path(".artifacts/alerts.csv"), help="Output CSV path."),
    artifacts: Path = typer.Option(Path(".artifacts")),
) -> None:
    """Export alerts from a completed run as CSV."""
    import csv
    import json

    if run_dir is None:
        candidates = sorted(artifacts.glob("run-*"), reverse=True)
        if not candidates:
            console.print("[red]No run directories found.[/red] Run `aml run` first.")
            raise typer.Exit(code=1)
        run_dir = candidates[0]

    alerts_dir = run_dir / "alerts"
    if not alerts_dir.exists():
        console.print(f"[red]No alerts/[/red] in {run_dir}.")
        raise typer.Exit(code=1)

    all_alerts: list[dict] = []
    for jsonl_file in sorted(alerts_dir.glob("*.jsonl")):
        rule_id = jsonl_file.stem
        for line in jsonl_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                alert = json.loads(line)
                alert["rule_id"] = rule_id
                all_alerts.append(alert)

    if not all_alerts:
        console.print("[yellow]No alerts to export.[/yellow]")
        raise typer.Exit(code=0)

    out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(all_alerts[0].keys())
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_alerts)

    console.print(f"[green]Exported[/green] {len(all_alerts)} alerts to {out}")


@app.command()
def replay(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    run_dir: Path = typer.Argument(..., exists=True, help="Original run directory to replay."),
    seed: int = typer.Option(42, help="Synthetic data seed."),
    artifacts: Path = typer.Option(Path(".artifacts")),
) -> None:
    """Re-execute a run and compare output hashes to verify determinism."""
    import json

    spec = load_spec(spec_path)
    as_of_str = None
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_bytes())
        as_of_str = manifest.get("as_of")

    as_of_dt = _parse_as_of(as_of_str)
    data = generate_dataset(as_of=as_of_dt, seed=seed)

    replay_root = artifacts / "replay"
    result = run_spec(
        spec=spec, spec_path=spec_path, data=data, as_of=as_of_dt, artifacts_root=replay_root,
    )

    # Compare hashes.
    if manifest_path.exists():
        original = json.loads(manifest_path.read_bytes())
        orig_hashes = original.get("rule_outputs", {})
        replay_hashes = result.manifest.get("rule_outputs", {})

        table = Table(title="Hash Comparison")
        table.add_column("Rule")
        table.add_column("Original")
        table.add_column("Replay")
        table.add_column("Match")

        all_match = True
        for rule_id in sorted(set(orig_hashes) | set(replay_hashes)):
            orig = orig_hashes.get(rule_id, "N/A")
            repl = replay_hashes.get(rule_id, "N/A")
            match = orig == repl
            if not match:
                all_match = False
            table.add_row(
                rule_id, orig[:16] + "...", repl[:16] + "...",
                "[green]YES[/green]" if match else "[red]NO[/red]",
            )
        console.print(table)

        if all_match:
            console.print("[green]All hashes match.[/green] Run is deterministic.")
        else:
            console.print("[red]Hash mismatch detected.[/red] Non-deterministic output.")
    else:
        console.print(f"[yellow]No manifest.json in {run_dir}.[/yellow] Cannot compare.")
        console.print(f"Replay completed. Results in {result.manifest['run_dir']}")


@app.command()
def diff(
    spec_a: Path = typer.Argument(..., exists=True, readable=True, help="First spec."),
    spec_b: Path = typer.Argument(..., exists=True, readable=True, help="Second spec."),
) -> None:
    """Compare two aml.yaml specs and show differences."""
    from aml_framework.diff import diff_specs

    diff_specs(spec_a, spec_b)


@app.command()
def api(
    port: int = typer.Option(8000, help="API server port."),
    host: str = typer.Option("0.0.0.0", help="Bind address."),
) -> None:
    """Launch the FastAPI REST server."""
    import subprocess
    import sys

    subprocess.run(
        [
            sys.executable, "-m", "uvicorn",
            "aml_framework.api.main:app",
            "--host", host,
            "--port", str(port),
        ],
        check=False,
    )


if __name__ == "__main__":
    app()
