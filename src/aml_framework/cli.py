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


def _resolve_run_dir(run_dir: Path | None, artifacts: Path) -> Path:
    """Pick `run_dir` or fall back to the newest `run-*` under `artifacts`.
    Exits with a clear message if no run directories exist.
    """
    if run_dir is not None:
        return run_dir
    candidates = sorted(artifacts.glob("run-*"), reverse=True)
    if not candidates:
        console.print("[red]No run directories found.[/red] Run `aml run` first.")
        raise typer.Exit(code=1)
    return candidates[0]


@app.command()
def validate(spec_path: Path = typer.Argument(..., exists=True, readable=True)) -> None:
    """Validate aml.yaml against the JSON Schema and cross-reference checks."""
    spec = load_spec(spec_path)
    console.print(
        f"[green]OK[/green] {spec_path} — "
        f"{len(spec.data_contracts)} contract(s), {len(spec.rules)} rule(s), "
        f"{len(spec.workflow.queues)} queue(s)."
    )


@app.command(name="validate-data")
def validate_data(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    data_dir: Path = typer.Argument(..., exists=True, help="Directory with CSV files."),
) -> None:
    """Validate CSV data files against spec data contracts."""
    from aml_framework.data.sources import validate_csv

    spec = load_spec(spec_path)
    all_errors: list[str] = []
    for contract in spec.data_contracts:
        csv_path = data_dir / f"{contract.id}.csv"
        errors = validate_csv(csv_path, spec, contract.id)
        if errors:
            for e in errors:
                console.print(f"  [red]{contract.id}[/red]: {e}")
                all_errors.append(e)
        else:
            console.print(f"  [green]{contract.id}[/green]: OK")

    if all_errors:
        console.print(f"\n[red]{len(all_errors)} error(s)[/red] found.")
        raise typer.Exit(code=1)
    else:
        console.print("\n[green]All contracts valid.[/green]")


@app.command(name="sanctions-sync")
def sanctions_sync(
    source: str = typer.Argument(..., help="Feed source: ofac, eu, complyadvantage."),
    payload_file: Path | None = typer.Option(
        None,
        "--from-file",
        help="Parse a local XML/JSON payload instead of fetching upstream.",
    ),
    url: str | None = typer.Option(None, help="Override default upstream URL."),
    lists_dir: Path | None = typer.Option(
        None, help="Lists directory; defaults to bundled aml_framework/data/lists/."
    ),
    list_name: str | None = typer.Option(
        None, help="Filename to write under lists_dir (default: source name)."
    ),
    show_diff: bool = typer.Option(
        True, help="Print added/removed entries vs the previous cached payload."
    ),
) -> None:
    """Pull a sanctions list, hash-cache, and write the CSV used by `list_match`."""
    from aml_framework.paths import REFERENCE_LISTS_DIR
    from aml_framework.sanctions import (
        ComplyAdvantageWebhookSource,
        EUConsolidatedSource,
        OFACAdvancedXMLSource,
        sync_source,
    )

    sources_by_name = {
        "ofac": OFACAdvancedXMLSource(),
        "eu": EUConsolidatedSource(),
        "complyadvantage": ComplyAdvantageWebhookSource(),
    }
    src = sources_by_name.get(source.lower())
    if src is None:
        console.print(
            f"[red]Unknown source[/red] {source!r}. Choose one of: {', '.join(sources_by_name)}."
        )
        raise typer.Exit(code=1)

    payload: bytes | None = None
    if payload_file is not None:
        payload = payload_file.read_bytes()

    target_dir = lists_dir or REFERENCE_LISTS_DIR
    result = sync_source(
        src,
        lists_dir=target_dir,
        list_name=list_name,
        url=url,
        payload=payload,
    )

    if result.unchanged:
        console.print(
            f"[dim]unchanged[/dim] {result.list_name} "
            f"({result.row_count} rows, sha256={result.sha256[:12]}…)"
        )
        return

    console.print(
        f"[green]synced[/green] {result.list_name} → {result.csv_path} "
        f"({result.row_count} rows, +{len(result.added)} -{len(result.removed)})"
    )
    if show_diff:
        for entry in result.added[:25]:
            console.print(f"  [green]+[/green] {entry.name} ({entry.country})")
        if len(result.added) > 25:
            console.print(f"  [green]+[/green] … {len(result.added) - 25} more")
        for entry in result.removed[:25]:
            console.print(f"  [red]-[/red] {entry.name} ({entry.country})")
        if len(result.removed) > 25:
            console.print(f"  [red]-[/red] … {len(result.removed) - 25} more")


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
    data_source: str = typer.Option(
        "synthetic", help="Data source: synthetic, csv, parquet, duckdb."
    ),
    data_dir: str | None = typer.Option(
        None, help="Directory with CSV/Parquet files. Default: data/input/"
    ),
) -> None:
    """End-to-end: load data, execute rules, emit cases + audit bundle."""
    from aml_framework.data.sources import resolve_source

    spec = load_spec(spec_path)
    as_of_dt = _parse_as_of(as_of)
    data = resolve_source(
        source_type=data_source,
        spec=spec,
        as_of=as_of_dt,
        seed=seed,
        data_dir=data_dir,
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
    audience: str | None = typer.Option(
        None, help="Filter reports by audience (e.g. svp, vp, director)."
    ),
    report_id: str | None = typer.Option(None, "--report", help="Render a specific report id."),
    run_dir: Path | None = typer.Option(None, help="Specific run dir; defaults to latest."),
    artifacts: Path = typer.Option(Path(".artifacts")),
    stdout: bool = typer.Option(
        False, help="Print the first matching report to stdout instead of listing."
    ),
) -> None:
    """Show or print role-specific reports from a completed run."""
    spec = load_spec(spec_path)
    run_dir = _resolve_run_dir(run_dir, artifacts)

    reports_dir = run_dir / "reports"
    if not reports_dir.exists():
        console.print(f"[red]No reports/[/red] in {run_dir}. Re-run `aml run` on the updated spec.")
        raise typer.Exit(code=1)

    selected = [
        r
        for r in spec.reports
        if (audience is None or r.audience == audience) and (report_id is None or r.id == report_id)
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
    run_dir = _resolve_run_dir(run_dir, artifacts)
    out_path = export_bundle(run_dir, out, spec_path=spec_path)
    console.print(f"[green]Bundle[/green] {out_path} (from {run_dir})")


@app.command(name="export-goaml")
def export_goaml_cmd(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    run_dir: Path | None = typer.Option(None, help="Run dir; defaults to latest."),
    out: Path = typer.Option(Path(".artifacts/goaml.xml"), help="Output XML path."),
    artifacts: Path = typer.Option(Path(".artifacts")),
    seed: int = typer.Option(42, help="Synthetic data seed (matches `aml run`)."),
    data_source: str = typer.Option(
        "synthetic", help="Data source: synthetic, csv, parquet, duckdb."
    ),
    data_dir: str | None = typer.Option(None, help="Directory with CSV/Parquet files."),
    rentity_id: str = typer.Option("0", help="FIU-assigned reporting entity ID."),
    rentity_branch: str = typer.Option("HEAD_OFFICE", help="Reporting branch code."),
    submission_date: str | None = typer.Option(
        None, help="ISO 8601 submission date; defaults to now (UTC)."
    ),
    report_code: str = typer.Option("STR", help="goAML report code: STR, SAR, ATR…"),
) -> None:
    """Export finalised cases as goAML 5.0.2 XML for FIU submission.

    The exporter reads cases from a finalised run directory, re-resolves
    customer + transaction data from the spec's data sources (so PII never
    needs to be persisted in the audit ledger), and produces a single XML
    document with one <report> element per case.
    """
    from aml_framework.data.sources import resolve_source
    from aml_framework.generators.goaml_xml import (
        ReportingEntity,
        export_goaml_from_run_dir,
    )

    run_dir = _resolve_run_dir(run_dir, artifacts)
    spec = load_spec(spec_path)

    # Use the run's as_of for source resolution so synthetic data lines up
    # with the cases we're exporting.
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        console.print(f"[red]No manifest.json in {run_dir}[/red]")
        raise typer.Exit(code=1)
    import json as _json

    manifest = _json.loads(manifest_path.read_bytes())
    as_of_dt = datetime.fromisoformat(manifest["as_of"])

    data = resolve_source(
        source_type=data_source,
        spec=spec,
        as_of=as_of_dt,
        seed=seed,
        data_dir=data_dir,
    )

    submit_dt = (
        datetime.fromisoformat(submission_date)
        if submission_date
        else datetime.now(tz=timezone.utc)
    )

    xml_bytes = export_goaml_from_run_dir(
        run_dir,
        spec,
        customers=data.get("customer", []),
        transactions=data.get("txn", []),
        entity=ReportingEntity(
            rentity_id=rentity_id,
            rentity_branch=rentity_branch,
            name=spec.program.name,
        ),
        submission_date=submit_dt,
        report_code=report_code,
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(xml_bytes)
    console.print(f"[green]goAML[/green] {out} ({len(xml_bytes):,} bytes from {run_dir})")


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
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(dashboard_app),
            "--server.port",
            str(port),
            "--server.headless",
            "true",
            "--",
            str(spec_path.resolve()),
            str(seed),
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

    run_dir = _resolve_run_dir(run_dir, artifacts)
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
        spec=spec,
        spec_path=spec_path,
        data=data,
        as_of=as_of_dt,
        artifacts_root=replay_root,
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
                rule_id,
                orig[:16] + "...",
                repl[:16] + "...",
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
def schedule(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    interval: str = typer.Option("1h", help="Run interval: 1h, 6h, 24h, etc."),
    data_source: str = typer.Option("csv", help="Data source: synthetic, csv, parquet."),
    data_dir: str | None = typer.Option("data/input", help="Data directory."),
    artifacts: Path = typer.Option(Path(".artifacts"), help="Artifacts root."),
) -> None:
    """Run the engine on a schedule (press Ctrl+C to stop)."""
    import time

    from aml_framework.data.sources import resolve_source
    from aml_framework.generators.sql import parse_window

    interval_td = parse_window(interval)
    interval_seconds = interval_td.total_seconds()

    console.print(
        f"[green]Scheduled[/green] every {interval} for {spec_path.name} "
        f"(data_source={data_source}). Press Ctrl+C to stop."
    )

    run_count = 0
    while True:
        run_count += 1
        try:
            spec = load_spec(spec_path)
            as_of_dt = _parse_as_of(None)
            data = resolve_source(
                source_type=data_source,
                spec=spec,
                as_of=as_of_dt,
                seed=run_count,
                data_dir=data_dir,
            )
            result = run_spec(
                spec=spec,
                spec_path=spec_path,
                data=data,
                as_of=as_of_dt,
                artifacts_root=artifacts,
            )
            console.print(
                f"[green]Run #{run_count}[/green] {result.total_alerts} alerts, "
                f"{len(result.case_ids)} cases. Next in {interval}."
            )
        except KeyboardInterrupt:
            console.print(f"\n[yellow]Stopped[/yellow] after {run_count} runs.")
            break
        except Exception as e:
            console.print(f"[red]Error[/red] in run #{run_count}: {e}")

        try:
            time.sleep(interval_seconds)
        except KeyboardInterrupt:
            console.print(f"\n[yellow]Stopped[/yellow] after {run_count} runs.")
            break


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
            sys.executable,
            "-m",
            "uvicorn",
            "aml_framework.api.main:app",
            "--host",
            host,
            "--port",
            str(port),
        ],
        check=False,
    )


@app.command(name="email-digest")
def email_digest(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    audience: str = typer.Option("svp", help="Report audience (svp, vp, director, etc.)."),
    to: str = typer.Option(..., help="Recipient email address."),
    smtp_host: str = typer.Option("localhost", help="SMTP server host."),
    smtp_port: int = typer.Option(587, help="SMTP server port."),
    seed: int = typer.Option(42, help="Synthetic data seed."),
) -> None:
    """Generate and email a role-specific report digest."""
    from aml_framework.data.sources import resolve_source

    spec = load_spec(spec_path)
    as_of_dt = _parse_as_of(None)
    data = resolve_source(source_type="synthetic", spec=spec, as_of=as_of_dt, seed=seed)

    result = run_spec(
        spec=spec,
        spec_path=spec_path,
        data=data,
        as_of=as_of_dt,
        artifacts_root=Path(".artifacts"),
    )

    # Find the report for the audience.
    matching = [r for r in result.reports.items() if audience in r[0]]
    if not matching:
        console.print(f"[red]No report found for audience '{audience}'.[/red]")
        raise typer.Exit(code=1)

    report_id, markdown = matching[0]

    # Send via SMTP.
    import smtplib
    from email.mime.text import MIMEText

    msg = MIMEText(markdown, "plain", "utf-8")
    msg["Subject"] = f"AML Report: {report_id} ({spec.program.name})"
    msg["From"] = f"aml-framework@{spec.program.name}"
    msg["To"] = to

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.send_message(msg)
        console.print(f"[green]Sent[/green] {report_id} to {to}")
    except Exception as e:
        console.print(f"[red]SMTP error:[/red] {e}")
        console.print("Report content saved to stdout:")
        console.print(markdown)


if __name__ == "__main__":
    app()
