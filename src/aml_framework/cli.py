"""`aml` command-line entry point."""

from __future__ import annotations

import re
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
def init(
    target_dir: Path = typer.Argument(
        Path("."), help="Where to write aml.yaml + README.md. Defaults to current directory."
    ),
    program_name: str = typer.Option(
        "", "--program", help="Program name (lowercase a-z / 0-9 / _). Prompted if empty."
    ),
    jurisdiction: str = typer.Option(
        "", "--jurisdiction", help="US / CA / GB / EU / AU / SG. Prompted if empty."
    ),
    archetype: str = typer.Option(
        "", "--archetype", help="community_bank / schedule_i_bank / vasp / fintech."
    ),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="Take all defaults; no prompts. For CI / scripts.",
    ),
    overwrite: bool = typer.Option(
        False, "--overwrite", help="Replace an existing aml.yaml in target_dir."
    ),
) -> None:
    """Scaffold a working starter AML spec in <60 seconds.

    Five questions → one validated aml.yaml + a README that tells a
    developer exactly what to run next. Non-interactive mode takes
    every default so CI / scripts can wrap the wizard.

    The output is a complete spec the engine accepts on day one:
    program metadata, two data contracts (txn + customer), three
    starter rules (structuring, velocity, high-risk jurisdiction), a
    four-queue workflow, and a STR reporting form. Every detector
    cites the FATF recommendation that justifies it — same shape the
    rest of the framework's example specs use.
    """
    from aml_framework.init_wizard import (
        JURISDICTION_DEFAULTS,
        InitConfig,
        normalise_archetype,
        normalise_jurisdiction,
        validate_program_name,
        write_scaffold,
    )

    target_dir = target_dir.resolve()

    # --- Question 1: program name ---
    if not program_name:
        default_name = re.sub(r"[^a-z0-9_]", "_", target_dir.name.lower()) + "_aml"
        if not non_interactive:
            program_name = typer.prompt("Program name", default=default_name)
        else:
            program_name = default_name
    err = validate_program_name(program_name)
    if err:
        console.print(f"[red]{err}[/red]")
        raise typer.Exit(code=2)

    # --- Question 2: jurisdiction ---
    if not jurisdiction:
        if non_interactive:
            jurisdiction = "US"
        else:
            jurisdiction = typer.prompt(
                "Jurisdiction (US / CA / GB / EU / AU / SG / OTHER)",
                default="US",
            )
    jurisdiction = normalise_jurisdiction(jurisdiction)
    regulator, currency = JURISDICTION_DEFAULTS[jurisdiction]

    # --- Question 3: archetype ---
    if not archetype:
        if non_interactive:
            archetype = "community_bank"
        else:
            archetype = typer.prompt(
                "Bank type (community_bank / schedule_i_bank / vasp / fintech)",
                default="community_bank",
            )
    archetype_norm = normalise_archetype(archetype)

    # --- Question 4: confirm + write ---
    config = InitConfig(
        program_name=program_name,
        jurisdiction=jurisdiction,
        regulator=regulator,
        archetype=archetype_norm,
        target_dir=target_dir,
        currency=currency,
    )
    if not non_interactive:
        console.print("\n[bold]About to write:[/bold]")
        console.print(f"  program     : {config.program_name}")
        console.print(f"  jurisdiction: {config.jurisdiction}  (regulator: {config.regulator})")
        console.print(
            f"  archetype   : {config.archetype}  (channels: {', '.join(config.channels)})"
        )
        console.print(f"  target_dir  : {config.target_dir}\n")
        if not typer.confirm("Proceed?", default=True):
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(code=0)

    try:
        scaffold = write_scaffold(config, overwrite=overwrite)
    except FileExistsError as e:
        console.print(f"[red]{e}[/red]\nRe-run with [bold]--overwrite[/bold] to replace.")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]Spec validation failed:[/red] {e}")
        raise typer.Exit(code=1)

    # --- Next-step narration ---
    console.rule(f"[bold cyan]✓ Scaffold written to {scaffold.spec_path.parent}[/bold cyan]")
    console.print(f"\n  [green]→[/green] {scaffold.spec_path}")
    console.print(f"  [green]→[/green] {scaffold.readme_path}\n")
    console.print("[bold]Try it now:[/bold]")
    console.print(f"  [dim]$[/dim] aml validate {scaffold.spec_path}")
    console.print(f"  [dim]$[/dim] aml run {scaffold.spec_path} --seed 42")
    console.print(f"  [dim]$[/dim] aml dashboard {scaffold.spec_path}\n")


@app.command()
def validate(spec_path: Path = typer.Argument(..., exists=True, readable=True)) -> None:
    """Validate aml.yaml against the JSON Schema and cross-reference checks."""
    spec = load_spec(spec_path)
    console.print(
        f"[green]OK[/green] {spec_path} — "
        f"{len(spec.data_contracts)} contract(s), {len(spec.rules)} rule(s), "
        f"{len(spec.workflow.queues)} queue(s)."
    )


@app.command(name="outcomes-pack")
def outcomes_pack_cmd(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    run_dir: Path = typer.Option(
        None, "--run-dir", help="Run directory; defaults to newest under artifacts/."
    ),
    artifacts: Path = typer.Option(
        Path("artifacts"), "--artifacts", help="Where engine runs are written."
    ),
    out: Path = typer.Option(
        Path("amla-outcomes.json"),
        "--out",
        help="Output AMLA RTS draft 2026-02 JSON file.",
    ),
    lei: str = typer.Option("", "--lei", help="Legal Entity Identifier (20 chars)."),
    entity_type: str = typer.Option(
        "credit_institution",
        "--entity-type",
        help="AMLA obliged-entity type.",
    ),
    home_state: str = typer.Option(
        "", "--home-state", help="ISO 3166-1 alpha-2 home Member State."
    ),
    period_start: str = typer.Option(
        "", "--period-start", help="Reporting period start (YYYY-MM-DD)."
    ),
    period_end: str = typer.Option("", "--period-end", help="Reporting period end (YYYY-MM-DD)."),
    labels_csv: Path | None = typer.Option(
        None,
        "--labels",
        help="Optional CSV: case_id,is_true_positive (1/0) for precision.",
    ),
) -> None:
    """Generate AMLA RTS effectiveness pack (alert→case→STR funnel)."""
    import csv as _csv
    import json as _json

    from aml_framework.metrics.outcomes import compute_outcomes, format_amla_rts_json

    spec = load_spec(spec_path)
    run = _resolve_run_dir(run_dir, artifacts)

    cases = []
    cases_dir = run / "cases"
    if cases_dir.exists():
        for f in sorted(cases_dir.glob("*.json")):
            cases.append(_json.loads(f.read_text()))
    decisions = []
    dec_path = run / "decisions.jsonl"
    if dec_path.exists():
        for line in dec_path.read_text().splitlines():
            line = line.strip()
            if line:
                decisions.append(_json.loads(line))

    labels: dict[str, bool] | None = None
    if labels_csv is not None:
        labels = {}
        with labels_csv.open() as f:
            for row in _csv.DictReader(f):
                labels[row["case_id"]] = row.get("is_true_positive", "0") in (
                    "1",
                    "true",
                    "True",
                    "yes",
                )

    report = compute_outcomes(
        cases=cases,
        decisions=decisions,
        spec_program=spec.program.name,
        labels=labels,
    )
    payload = format_amla_rts_json(
        report,
        program_metadata={
            "lei": lei,
            "obliged_entity_type": entity_type,
            "home_member_state": home_state,
            "reporting_period_start": period_start,
            "reporting_period_end": period_end,
        },
    )
    out.write_bytes(payload)
    console.print(
        f"[green]Outcomes pack written[/green] {out}\n"
        f"  total_alerts: {report.total_alerts}\n"
        f"  total_cases: {report.total_cases}\n"
        f"  total_str_filed: {report.total_str_filed}\n"
        f"  alert_to_str: {report.alert_to_str_pct}%"
    )


@app.command(name="regwatch")
def regwatch_cmd(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    baseline: Path = typer.Option(
        Path(".regwatch.json"),
        "--baseline",
        help="Path to the baseline JSON file (default: ./.regwatch.json).",
    ),
    update: bool = typer.Option(
        False,
        "--update",
        help="Write the current scan as the new baseline instead of comparing.",
    ),
    offline: bool = typer.Option(
        False,
        "--offline",
        help="Skip network fetches; only verify the baseline file's internal consistency.",
    ),
) -> None:
    """Detect drift in cited regulation URLs.

    Hashes the content of every URL referenced by `regulation_refs` in
    the spec and compares against a saved baseline. Run with `--update`
    to refresh the baseline after acknowledging drift.

    Closes the gap from FinCEN BOI Mar 2025 narrowing — when a regulator
    silently rewrites a page, the spec's citation goes stale without any
    signal to the operator. Run weekly via cron.
    """
    from aml_framework.compliance.regwatch import (
        check_drift,
        fetch_current,
        load_baseline,
        save_baseline,
        scan_spec,
    )

    spec = load_spec(spec_path)
    citations = scan_spec(spec)

    if update:
        if offline:
            console.print("[red]ERROR[/red] cannot --update in --offline mode")
            raise typer.Exit(code=2)
        entries, unreachable = fetch_current(citations)
        save_baseline(entries, baseline)
        console.print(
            f"[green]Baseline written[/green] {baseline} — "
            f"{len(entries)} citation(s) hashed, {len(unreachable)} unreachable."
        )
        for u in unreachable:
            console.print(f"  [yellow]!{u['citation']}[/yellow] {u['reason']}")
        raise typer.Exit(code=0)

    if offline:
        baseline_entries = load_baseline(baseline)
        console.print(
            f"[green]Offline check[/green] {baseline} — "
            f"{len(baseline_entries)} entries in baseline, no network calls made."
        )
        raise typer.Exit(code=0)

    baseline_entries = load_baseline(baseline)
    if not baseline_entries:
        console.print(f"[yellow]No baseline at {baseline}[/yellow] — run with --update first.")
        raise typer.Exit(code=1)

    report = check_drift(spec, baseline_entries)
    if report.unchanged_count:
        console.print(f"[green]✓[/green] {report.unchanged_count} unchanged")
    for d in report.drifted:
        console.print(
            f"[red]DRIFTED[/red] {d['citation']}\n"
            f"        url: {d['url']}\n"
            f"        baseline: {d['baseline_hash'][:16]}... ({d['baseline_fetched_at']})\n"
            f"        current:  {d['current_hash'][:16]}... ({d['current_fetched_at']})"
        )
    for u in report.unreachable:
        console.print(f"[yellow]UNREACHABLE[/yellow] {u['citation']}: {u['reason']}")
    for n in report.new:
        console.print(f"[blue]NEW[/blue] {n['citation']} → {n['url']}")
    for r in report.removed:
        console.print(f"[magenta]REMOVED[/magenta] {r['citation']} → {r['url']}")
    raise typer.Exit(code=1 if report.has_findings else 0)


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


@app.command(name="tune")
def tune_cmd(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    rule_id: str = typer.Option(..., "--rule", help="Rule id to sweep."),
    seed: int = typer.Option(42, help="Synthetic data seed (matches `aml run`)."),
    as_of: str | None = typer.Option(None, help="ISO timestamp used as the rule 'now'."),
    data_source: str = typer.Option(
        "synthetic", help="Data source: synthetic, csv, parquet, duckdb."
    ),
    data_dir: str | None = typer.Option(None, help="Directory with CSV/Parquet files."),
    labels_file: Path | None = typer.Option(
        None,
        "--labels",
        help="CSV with columns customer_id,is_true_positive (1/0). "
        "Enables precision/recall scoring.",
    ),
    out: Path | None = typer.Option(None, help="Write JSON result; otherwise summary printed."),
    audit_run_dir: Path | None = typer.Option(
        None,
        help="Append a `tuning_run` event to this run dir's decisions.jsonl.",
    ),
) -> None:
    """Sweep a rule's `tuning_grid` over fixed data and report alert deltas."""
    import csv as _csv
    import json as _json

    from aml_framework.data.sources import resolve_source
    from aml_framework.engine.tuning import sweep_rule

    spec = load_spec(spec_path)
    as_of_dt = _parse_as_of(as_of)
    data = resolve_source(
        source_type=data_source, spec=spec, as_of=as_of_dt, seed=seed, data_dir=data_dir
    )

    labels: dict[str, bool] | None = None
    if labels_file is not None:
        labels = {}
        with labels_file.open() as f:
            for row in _csv.DictReader(f):
                cid = row.get("customer_id", "").strip()
                if not cid:
                    continue
                flag = str(row.get("is_true_positive", "")).strip().lower()
                labels[cid] = flag in ("1", "true", "yes", "y", "t")

    run = sweep_rule(
        spec, rule_id, data, as_of=as_of_dt, labels=labels, audit_run_dir=audit_run_dir
    )

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_json.dumps(run.to_dict(), indent=2, default=str))
        console.print(
            f"[green]tuning[/green] {out} (rule={rule_id}, "
            f"baseline={run.baseline.alert_count}, scenarios={run.grid_size})"
        )
        return

    console.print(
        f"[bold]Tuning sweep[/bold] for rule [cyan]{rule_id}[/cyan]: "
        f"{run.grid_size} scenarios, baseline alerts = {run.baseline.alert_count}"
    )
    table = Table(title="Scenarios")
    table.add_column("Parameters")
    table.add_column("Alerts", justify="right")
    table.add_column("+/- vs baseline")
    if labels is not None:
        table.add_column("Precision", justify="right")
        table.add_column("Recall", justify="right")
        table.add_column("F1", justify="right")
    for s in run.scenarios:
        delta = f"+{s.added_vs_baseline} / -{s.removed_vs_baseline}"
        params_str = ", ".join(f"{k}={v}" for k, v in s.parameters.items())
        row = [params_str, str(s.alert_count), delta]
        if labels is not None:
            row += [
                f"{s.precision:.3f}" if s.precision is not None else "—",
                f"{s.recall:.3f}" if s.recall is not None else "—",
                f"{s.f1:.3f}" if s.f1 is not None else "—",
            ]
        table.add_row(*row)
    console.print(table)

    if labels is not None:
        best = run.best_by("f1")
        if best is not None:
            params_str = ", ".join(f"{k}={v}" for k, v in best.parameters.items())
            console.print(
                f"[bold green]Best F1[/bold green]: {params_str} "
                f"(precision={best.precision:.3f}, recall={best.recall:.3f}, f1={best.f1:.3f})"
            )


@app.command(name="effectiveness-pack")
def effectiveness_pack_cmd(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    run_dir: Path | None = typer.Option(None, help="Run dir; defaults to latest."),
    out: Path = typer.Option(Path(".artifacts/effectiveness_pack.json"), help="Output JSON path."),
    markdown_out: Path | None = typer.Option(
        None, help="Optional Markdown rendering of the same pack."
    ),
    artifacts: Path = typer.Option(Path(".artifacts")),
) -> None:
    """Build an Effectiveness Evidence Pack (FinCEN April 2026 NPRM artifact).

    Composes the audit ledger, alerts, decisions, and metrics from a
    finalised run into one structured JSON document mapped to the four
    pillars FinCEN's Reform NPRM names: risk-assessment alignment,
    AML/CFT priority coverage, control output quality, feedback-loop
    evidence.
    """
    import json as _json

    from aml_framework.generators.effectiveness import (
        export_pack_from_run_dir,
        render_effectiveness_markdown,
    )

    run_dir = _resolve_run_dir(run_dir, artifacts)
    spec = load_spec(spec_path)

    pack_bytes = export_pack_from_run_dir(spec, run_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pack_bytes)

    pack = _json.loads(pack_bytes)
    summary = pack["summary"]
    console.print(
        f"[green]Effectiveness Pack[/green] {out} "
        f"({len(pack_bytes):,} bytes) — "
        f"✅ {summary['findings_satisfied']} satisfied · "
        f"⚠️ {summary['findings_warning']} warnings · "
        f"❌ {summary['findings_gap']} gaps"
    )

    if markdown_out is not None:
        markdown_out.parent.mkdir(parents=True, exist_ok=True)
        markdown_out.write_text(render_effectiveness_markdown(pack), encoding="utf-8")
        console.print(f"[green]Markdown[/green] {markdown_out}")


@app.command(name="mrm-bundle")
def mrm_bundle_cmd(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    rule: list[str] = typer.Option(
        [], "--rule", help="Rule id(s) to dossier; repeat for multiple. Default: all rules."
    ),
    out_dir: Path = typer.Option(
        Path(".artifacts/mrm"), help="Output directory for per-rule dossiers + inventory."
    ),
    run_dir: Path | None = typer.Option(None, help="Run dir; defaults to latest."),
    artifacts: Path = typer.Option(Path(".artifacts")),
) -> None:
    """Build per-rule MRM dossiers (SR 26-2 / OCC Bulletin 2026-13) + inventory.

    Composes the audit ledger, alerts, decisions (including any
    `tuning_run` events from `aml tune --audit-run-dir …`), and the
    spec's model_tier / validation_cadence_months fields into per-rule
    Markdown + JSON dossiers the bank's second-line model-validation
    team reads. Also writes a spec-wide `inventory.json` aggregating
    every rule's tier + cadence + classification status.
    """
    from aml_framework.generators.mrm import export_bundle_from_run_dir

    run_dir = _resolve_run_dir(run_dir, artifacts)
    spec = load_spec(spec_path)

    result = export_bundle_from_run_dir(spec, run_dir, out_dir, rule_ids=rule or None)

    summary = result["summary"]
    console.print(
        f"[green]MRM bundle[/green] {result['out_dir']} — "
        f"{len(result['rules_written'])} dossier(s); "
        f"tiers high={summary['by_tier']['high']} "
        f"medium={summary['by_tier']['medium']} "
        f"low={summary['by_tier']['low']}"
    )
    classification = summary.get("by_classification_status", {})
    if classification.get("defaulted_to_low"):
        console.print(
            f"[yellow]⚠️  {classification['defaulted_to_low']} rule(s) defaulted to "
            "tier 'low' — second-line should classify explicitly via Rule.model_tier.[/yellow]"
        )


@app.command(name="audit-pack")
def audit_pack_cmd(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    jurisdiction: str = typer.Option(
        "CA-FINTRAC",
        "--jurisdiction",
        help="Regulator-specific pack template. Currently: CA-FINTRAC.",
    ),
    out: Path = typer.Option(
        Path("audit-pack.zip"),
        "--out",
        help="Output ZIP file path.",
    ),
    run_dir: Path | None = typer.Option(
        None, "--run-dir", help="Run directory; defaults to newest under artifacts/."
    ),
    artifacts: Path = typer.Option(
        Path("artifacts"), "--artifacts", help="Where engine runs are written."
    ),
) -> None:
    """Build a regulator pre-examination audit pack.

    Bundles the spec inventory + alerts summary + cases summary +
    audit-trail integrity proof + sanctions evidence + jurisdiction-
    specific section maps into one deterministic ZIP. Hand to
    examiners on arrival.

    Closes the gap from FINTRAC's January 2026 examination manual
    update which made the pre-exam evidence demand explicit.
    """
    from aml_framework.generators.audit_pack import build_audit_pack_from_run_dir

    spec = load_spec(spec_path)
    run = _resolve_run_dir(run_dir, artifacts)
    payload = build_audit_pack_from_run_dir(spec, run, jurisdiction=jurisdiction)
    out.write_bytes(payload)
    console.print(
        f"[green]Audit pack written[/green] {out} "
        f"({len(payload):,} bytes, jurisdiction={jurisdiction})"
    )


@app.command(name="export-amla-str")
def export_amla_str_cmd(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    run_dir: Path | None = typer.Option(None, help="Run dir; defaults to latest."),
    out: Path = typer.Option(Path(".artifacts/amla_str.json"), help="Output JSON path."),
    artifacts: Path = typer.Option(Path(".artifacts")),
    seed: int = typer.Option(42, help="Synthetic data seed (matches `aml run`)."),
    data_source: str = typer.Option(
        "synthetic", help="Data source: synthetic, csv, parquet, duckdb."
    ),
    data_dir: str | None = typer.Option(None, help="Directory with CSV/Parquet files."),
    lei: str = typer.Option(
        "00000000000000000000",
        help="ISO 17442 Legal Entity Identifier of the obliged entity.",
    ),
    sector: str = typer.Option(
        "CREDIT_INSTITUTION",
        help="Obliged entity sector code (CREDIT_INSTITUTION, VASP, EMI, etc.).",
    ),
    submission_date: str | None = typer.Option(
        None, help="ISO 8601 submission date; defaults to now (UTC)."
    ),
) -> None:
    """Export finalised cases as an AMLA RTS-aligned STR payload (JSON).

    ⚠️  AMLA RTS is in consultation (draft 2026-02). Field names and
    typology codes will change before the 2026-07-10 final-RTS deadline.
    The output payload is marked with `_draft_warning` — do NOT submit
    to a regulator without first updating this generator against the
    final RTS.
    """
    from aml_framework.data.sources import resolve_source
    from aml_framework.generators.amla_str import (
        DRAFT_WARNING,
        ObligedEntity,
        export_amla_str_from_run_dir,
    )

    run_dir = _resolve_run_dir(run_dir, artifacts)
    spec = load_spec(spec_path)

    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        console.print(f"[red]No manifest.json in {run_dir}[/red]")
        raise typer.Exit(code=1)
    import json as _json

    manifest = _json.loads(manifest_path.read_bytes())
    as_of_dt = datetime.fromisoformat(manifest["as_of"])

    data = resolve_source(
        source_type=data_source, spec=spec, as_of=as_of_dt, seed=seed, data_dir=data_dir
    )

    submit_dt = (
        datetime.fromisoformat(submission_date)
        if submission_date
        else datetime.now(tz=timezone.utc)
    )

    payload_bytes = export_amla_str_from_run_dir(
        run_dir,
        spec,
        customers=data.get("customer", []),
        transactions=data.get("txn", []),
        obliged_entity=ObligedEntity(
            lei=lei,
            name=spec.program.name,
            sector=sector,  # type: ignore[arg-type]
            jurisdiction=spec.program.jurisdiction,
            programme_name=spec.program.name,
        ),
        submission_date=submit_dt,
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(payload_bytes)

    payload = _json.loads(payload_bytes)
    conformance = payload.get("conformance", {})
    console.print(f"[yellow]⚠️  {DRAFT_WARNING}[/yellow]")
    console.print(
        f"[green]AMLA STR[/green] {out} "
        f"({len(payload_bytes):,} bytes, {len(payload.get('reports', []))} report(s), "
        f"conformance {conformance.get('mandatory_fields_populated')}/"
        f"{conformance.get('mandatory_fields_total')} mandatory fields populated)"
    )
    if conformance.get("unmapped_required"):
        console.print("[yellow]Unmapped mandatory fields (need analyst fill-in):[/yellow]")
        for field_name in conformance["unmapped_required"]:
            console.print(f"  - {field_name}")


@app.command(name="pkyc-scan")
def pkyc_scan_cmd(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    seed: int = typer.Option(42, help="Synthetic data seed (matches `aml run`)."),
    data_source: str = typer.Option(
        "synthetic", help="Data source: synthetic, csv, parquet, duckdb."
    ),
    data_dir: str | None = typer.Option(None, help="Directory with CSV/Parquet files."),
    high_risk_countries: str = typer.Option(
        "",
        help="Comma-separated ISO-2 country codes treated as high-risk (e.g. RU,KP,IR).",
    ),
    sanctions_added_file: Path | None = typer.Option(
        None,
        help="Path to a SyncResult JSON whose `added` entries seed the sanctions detector.",
    ),
    alert_lookback_days: int = typer.Option(
        90, help="How far back to count alerts for the transaction-pattern detector."
    ),
    alert_threshold: int = typer.Option(
        3, help="Minimum alerts to fire the transaction-pattern trigger."
    ),
    run_dir: Path | None = typer.Option(
        None, help="Run dir whose alerts seed the pattern detector; defaults to latest."
    ),
    artifacts: Path = typer.Option(Path(".artifacts")),
    out: Path | None = typer.Option(
        None, help="Write the scan result as JSON; otherwise summary printed."
    ),
) -> None:
    """Run pKYC trigger scan over current customers — flag re-reviews."""
    import json as _json
    from datetime import timedelta

    from aml_framework.data.sources import resolve_source
    from aml_framework.pkyc import (
        ScanContext,
        TransactionPatternDetector,
        run_scan,
    )
    from aml_framework.pkyc.detectors import (
        AdverseMediaDetector,
        CountryRiskDetector,
        SanctionsHitDetector,
        StaleKYCDetector,
    )
    from aml_framework.sanctions.base import SanctionEntry

    spec = load_spec(spec_path)
    as_of_dt = _parse_as_of(None)
    data = resolve_source(
        source_type=data_source,
        spec=spec,
        as_of=as_of_dt,
        seed=seed,
        data_dir=data_dir,
    )
    customers = data.get("customer", [])

    sanctions_added: list[SanctionEntry] = []
    if sanctions_added_file is not None:
        sync_payload = _json.loads(sanctions_added_file.read_text())
        for row in sync_payload.get("added", []):
            sanctions_added.append(
                SanctionEntry(
                    name=row.get("name", ""),
                    list_source=row.get("list_source", ""),
                    country=row.get("country", ""),
                    type=row.get("type", "individual"),
                )
            )

    recent_alerts: dict[str, int] = {}
    try:
        rd = _resolve_run_dir(run_dir, artifacts)
        alerts_dir = rd / "alerts"
        if alerts_dir.exists():
            cutoff = as_of_dt - timedelta(days=alert_lookback_days)
            for jsonl in alerts_dir.glob("*.jsonl"):
                for line in jsonl.read_text().splitlines():
                    if not line.strip():
                        continue
                    a = _json.loads(line)
                    cid = a.get("customer_id")
                    if not cid:
                        continue
                    ts = a.get("window_end") or a.get("window_start")
                    if ts:
                        try:
                            t = datetime.fromisoformat(str(ts).replace(" ", "T", 1))
                            if t < cutoff:
                                continue
                        except ValueError:
                            pass
                    recent_alerts[cid] = recent_alerts.get(cid, 0) + 1
    except typer.Exit:
        # No prior run; transaction-pattern detector simply gets empty input.
        pass

    countries = {c.strip().upper() for c in high_risk_countries.split(",") if c.strip()}

    context = ScanContext(
        as_of=as_of_dt,
        sanctions_added=sanctions_added,
        adverse_media_entries=[],
        high_risk_countries=countries,
        recent_alerts_by_customer=recent_alerts,
        lookback_days=alert_lookback_days,
    )

    detectors = [
        SanctionsHitDetector(),
        AdverseMediaDetector(),
        CountryRiskDetector(),
        TransactionPatternDetector(threshold=alert_threshold),
        StaleKYCDetector(),
    ]
    scan = run_scan(customers, context, detectors=detectors)

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_json.dumps(scan.to_dict(), indent=2, default=str))
        console.print(
            f"[green]pkyc[/green] {out} "
            f"(triggers={len(scan.triggers)}, rating_changes={len(scan.rating_changes)})"
        )
        return

    table = Table(title="pKYC scan result")
    table.add_column("Customer")
    table.add_column("Trigger")
    table.add_column("Severity")
    table.add_column("Action")
    table.add_column("Detector")
    for t in scan.triggers[:50]:
        table.add_row(t.customer_id, t.kind, t.severity, t.recommended_action, t.detector)
    console.print(table)

    if scan.rating_changes:
        ctable = Table(title="Risk rating changes")
        ctable.add_column("Customer")
        ctable.add_column("Old")
        ctable.add_column("New")
        ctable.add_column("Triggers", justify="right")
        for rc in scan.rating_changes:
            ctable.add_row(rc.customer_id, rc.old_rating, rc.new_rating, str(len(rc.triggers)))
        console.print(ctable)
    console.print(
        f"Scanned {scan.customers_scanned} customers, "
        f"fired {len(scan.triggers)} trigger(s), "
        f"{len(scan.rating_changes)} rating change(s)."
    )


@app.command(name="draft-narrative")
def draft_narrative_cmd(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    case_id: str = typer.Argument(..., help="Case ID to draft a narrative for."),
    backend: str = typer.Option("template", help="Drafter backend: template, ollama, openai."),
    run_dir: Path | None = typer.Option(None, help="Run dir; defaults to latest."),
    artifacts: Path = typer.Option(Path(".artifacts")),
    seed: int = typer.Option(42, help="Synthetic data seed (matches `aml run`)."),
    data_source: str = typer.Option(
        "synthetic", help="Data source: synthetic, csv, parquet, duckdb."
    ),
    data_dir: str | None = typer.Option(None, help="Directory with CSV/Parquet files."),
    out: Path | None = typer.Option(
        None, help="Write JSON output to file; otherwise print to stdout."
    ),
) -> None:
    """Draft a structured STR/SAR narrative for one case using a pluggable backend."""
    import json as _json

    from aml_framework.data.sources import resolve_source
    from aml_framework.narratives import get_drafter, load_case_evidence_from_run_dir

    run_dir = _resolve_run_dir(run_dir, artifacts)
    spec = load_spec(spec_path)

    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        console.print(f"[red]No manifest.json in {run_dir}[/red]")
        raise typer.Exit(code=1)
    manifest = _json.loads(manifest_path.read_bytes())
    as_of_dt = datetime.fromisoformat(manifest["as_of"])

    data = resolve_source(
        source_type=data_source, spec=spec, as_of=as_of_dt, seed=seed, data_dir=data_dir
    )
    evidence = load_case_evidence_from_run_dir(
        run_dir,
        case_id,
        customers=data.get("customer", []),
        transactions=data.get("txn", []),
        jurisdiction=spec.program.jurisdiction,
    )

    drafter = get_drafter(backend)
    drafted = drafter.draft(evidence)
    payload = drafted.model_dump_json(indent=2)

    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload, encoding="utf-8")
        console.print(f"[green]drafted[/green] {out} (backend={drafter.name})")
    else:
        console.print(payload)


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


@app.command()
def backtest(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    rule_id: str = typer.Option(..., "--rule", help="Which rule to backtest."),
    quarters: int = typer.Option(
        4, "--quarters", help="Number of 90-day windows ending at --as-of."
    ),
    as_of: str | None = typer.Option(
        None, "--as-of", help="ISO timestamp of the most-recent window. Defaults to now."
    ),
    seed: int = typer.Option(42, "--seed", help="Synthetic data seed."),
    labels_csv: Path | None = typer.Option(
        None,
        "--labels",
        help="CSV with header 'customer_id,is_true_positive,period' (period optional). "
        "When 'period' is present, rows are filtered to the matching period label.",
    ),
    out: Path = typer.Option(
        Path(".artifacts/backtest_report.json"),
        "--out",
        help="Where to write the BacktestReport JSON.",
    ),
) -> None:
    """Backtest one rule across N historical quarters.

    Built for 2LoD model-risk: answers "is rule X still earning its
    keep, or is precision/recall trending down?" without commissioning
    a vendor study. The output JSON drops straight into a per-rule
    SR 26-2 / OCC 2026-13 dossier.

    The default quarter generator steps back 90 days from --as-of; pass
    your own period list via the Python API when your fiscal calendar
    is non-standard.
    """
    import csv as _csv
    import json as _json

    from aml_framework.engine.backtest import (
        BacktestPeriod,
        backtest_rule,
        quarters as _quarters_helper,
    )

    spec = load_spec(spec_path)
    end_dt = _parse_as_of(as_of)
    periods: list[BacktestPeriod] = [
        BacktestPeriod(label=p.label, as_of=p.as_of, seed=seed)
        for p in _quarters_helper(end=end_dt, n=quarters)
    ]

    labels_loader = None
    if labels_csv is not None:
        per_period_labels: dict[str | None, dict[str, bool]] = {}
        with labels_csv.open(encoding="utf-8") as f:
            for row in _csv.DictReader(f):
                period_key = row.get("period") or None
                bucket = per_period_labels.setdefault(period_key, {})
                bucket[row["customer_id"]] = row.get("is_true_positive", "0") in (
                    "1",
                    "true",
                    "True",
                    "yes",
                )

        def labels_loader(period: BacktestPeriod) -> dict[str, bool] | None:
            if period.label in per_period_labels:
                return per_period_labels[period.label]
            return per_period_labels.get(None)

    report = backtest_rule(spec, rule_id, periods, labels_loader=labels_loader)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_json.dumps(report.to_dict(), indent=2), encoding="utf-8")

    table = Table(title=f"Backtest · {rule_id}")
    table.add_column("Period")
    table.add_column("As-of")
    table.add_column("Alerts", justify="right")
    table.add_column("Precision", justify="right")
    table.add_column("Recall", justify="right")
    table.add_column("F1", justify="right")
    for p in report.periods:
        table.add_row(
            p.period,
            p.as_of[:10],
            str(p.alert_count),
            f"{p.precision:.2%}" if p.precision is not None else "—",
            f"{p.recall:.2%}" if p.recall is not None else "—",
            f"{p.f1:.2%}" if p.f1 is not None else "—",
        )
    console.print(table)

    if report.drift_summary:
        console.print("\n[bold]Drift summary:[/bold]")
        for k, v in report.drift_summary.items():
            colour = "green"
            if any(metric in k for metric in ("precision", "recall", "f1")):
                colour = "red" if (isinstance(v, (int, float)) and v < 0) else "green"
            console.print(f"  [{colour}]{k}[/{colour}] = {v}")
    console.print(f"\n[green]Backtest written[/green] {out}")


_DEMO_PERSONA_NEXT_STEPS: dict[str, list[tuple[str, str, str]]] = {
    "cco": [
        (
            "See the audit pack you'd hand a regulator.",
            "open {artifacts}/audit-pack.zip",
            "audit-pack.zip",
        ),
        (
            "Walk the dashboard at the CCO landing page.",
            "aml dashboard {spec}",
            "",
        ),
        (
            "Read the FinCEN-aligned effectiveness pack.",
            "open {artifacts}/effectiveness.json",
            "effectiveness.json",
        ),
    ],
    "mlro": [
        (
            "Open the spec — every rule, every threshold, every regulation citation.",
            "less {spec}",
            "",
        ),
        (
            "Inspect the per-rule MRM dossier (SR 26-2 / OCC 2026-13).",
            "aml mrm-bundle {spec} --out {artifacts}/mrm",
            "",
        ),
        (
            "Tune a threshold and see the precision/recall trade-off.",
            "aml dashboard {spec}   # → Tuning Lab",
            "",
        ),
    ],
    "analyst": [
        (
            "Open the alert queue with pre-attached evidence.",
            "aml dashboard {spec}   # → Alert Queue",
            "",
        ),
        (
            "Draft a STR narrative from any alert.",
            "aml draft-narrative {spec} --alert-id <id>",
            "",
        ),
        (
            "Export alerts as CSV for offline review.",
            "aml export-alerts {spec}",
            "",
        ),
    ],
    "auditor": [
        (
            "Verify the SHA-256 hash chain — tampering is reportable.",
            "ls {artifacts}/run-*/decisions.jsonl",
            "",
        ),
        (
            "Replay this run and prove byte-for-byte determinism.",
            "aml replay {spec} {artifacts}/run-*",
            "",
        ),
        (
            "Pull the FINTRAC examination ZIP.",
            "open {artifacts}/audit-pack.zip",
            "audit-pack.zip",
        ),
    ],
}


@app.command()
def demo(
    spec_path: Path = typer.Argument(
        Path("examples/canadian_schedule_i_bank/aml.yaml"),
        exists=True,
        readable=True,
        help="Spec to demo. Defaults to the Canadian Schedule-I bank example.",
    ),
    persona: str = typer.Option(
        "cco",
        "--persona",
        help="Whose first 5 minutes is this? cco | mlro | analyst | auditor.",
    ),
    artifacts: Path = typer.Option(
        Path(".artifacts/demo"),
        "--artifacts",
        help="Where to write demo outputs (separate from real runs).",
    ),
    seed: int = typer.Option(42, "--seed", help="Synthetic data seed."),
    launch: bool = typer.Option(
        False,
        "--launch/--no-launch",
        help="If set, start the dashboard at the end. Otherwise, print the command.",
    ),
) -> None:
    """Five-minute guided demo for a non-technical buyer.

    Runs validate → engine → audit pack → effectiveness pack against the
    canonical example spec, narrated for a chosen persona. Designed so a
    CCO who has 5 minutes between meetings can self-serve a real audit
    pack without booking a vendor demo.

    The story we tell:
      1. The spec exists and is valid.
      2. The engine ran. Here are the alerts and cases.
      3. The audit chain is intact. Here's the proof.
      4. Here's the regulator-ready ZIP. Open it.
      5. Here's where to look next, tailored to who you are.
    """
    persona = persona.lower().strip()
    if persona not in _DEMO_PERSONA_NEXT_STEPS:
        console.print(
            f"[red]Unknown persona '{persona}'.[/red] "
            f"Choose one of: {', '.join(sorted(_DEMO_PERSONA_NEXT_STEPS))}"
        )
        raise typer.Exit(code=1)

    artifacts.mkdir(parents=True, exist_ok=True)

    console.rule("[bold cyan]AML Open Framework — 5-minute demo[/bold cyan]")
    console.print(
        f"Persona: [bold]{persona.upper()}[/bold]    "
        f"Spec: [dim]{spec_path}[/dim]    "
        f"Artifacts: [dim]{artifacts}/[/dim]\n"
    )

    # Step 1 — validate.
    console.print("[bold]1.[/bold] Reading the spec…")
    spec = load_spec(spec_path)
    console.print(
        f"   [green]✓[/green] {len(spec.rules)} detection rule(s), "
        f"{len(spec.data_contracts)} data contract(s), "
        f"{len(spec.workflow.queues)} queue(s). "
        f"Plain YAML — readable by 1LoD, 2LoD, and the regulator."
    )

    # Step 2 — run engine.
    console.print("\n[bold]2.[/bold] Running the engine on synthetic data…")
    as_of_dt = _parse_as_of(None)
    data = generate_dataset(as_of=as_of_dt, seed=seed)
    result = run_spec(
        spec=spec,
        spec_path=spec_path,
        data=data,
        as_of=as_of_dt,
        artifacts_root=artifacts,
    )
    console.print(
        f"   [green]✓[/green] {result.total_alerts} alert(s) across "
        f"{len(spec.rules)} rule(s); "
        f"{len(result.case_ids)} case(s) opened; "
        f"{len(result.metrics)} metric(s) computed."
    )

    # Step 3 — audit chain.
    run_dir = Path(result.manifest["run_dir"])
    decisions_path = run_dir / "decisions.jsonl"
    if decisions_path.exists():
        n_decisions = sum(1 for _ in decisions_path.open(encoding="utf-8"))
    else:
        n_decisions = 0
    console.print("\n[bold]3.[/bold] Sealing the audit chain…")
    console.print(
        f"   [green]✓[/green] {n_decisions} decision(s) hash-chained in "
        f"[dim]{decisions_path.relative_to(artifacts.parent) if decisions_path.exists() else 'decisions.jsonl'}[/dim]. "
        f"Tampering would break verify_decisions()."
    )

    # Step 4 — audit pack.
    console.print("\n[bold]4.[/bold] Building the regulator pack (FINTRAC-aligned)…")
    from aml_framework.generators.audit_pack import build_audit_pack_from_run_dir

    audit_zip = artifacts / "audit-pack.zip"
    payload = build_audit_pack_from_run_dir(spec, run_dir, jurisdiction="CA-FINTRAC")
    audit_zip.write_bytes(payload)
    console.print(
        f"   [green]✓[/green] {audit_zip} ({len(payload):,} bytes). "
        f"This is what an examiner would receive on day one of an exam."
    )

    # Step 4b — effectiveness pack (optional, only if rules carry aml_priority).
    has_priority = any(getattr(r, "aml_priority", None) for r in spec.rules)
    if has_priority:
        console.print("\n[bold]4b.[/bold] Building the FinCEN effectiveness pack…")
        from aml_framework.generators.effectiveness import (
            export_pack_from_run_dir as _export_eff_pack,
        )

        eff_path = artifacts / "effectiveness.json"
        eff_path.write_bytes(_export_eff_pack(spec, run_dir))
        console.print(f"   [green]✓[/green] {eff_path} — mapped to the four FinCEN NPRM pillars.")
    else:
        console.print("\n[dim]4b. (skipped — this spec has no aml_priority fields yet)[/dim]")

    # Step 5 — persona-specific next steps. Skip steps whose target file
    # was not produced by this run (e.g. effectiveness pack on a spec
    # without aml_priority).
    console.rule(f"[bold]Next 5 minutes for a {persona.upper()}[/bold]")
    for human, command, requires in _DEMO_PERSONA_NEXT_STEPS[persona]:
        if requires and not (artifacts / requires).exists():
            continue
        console.print(f"  [cyan]▸[/cyan] {human}")
        rendered = command.format(spec=spec_path, artifacts=artifacts)
        console.print(f"    [dim]$ {rendered}[/dim]\n")

    if launch:
        console.print("[bold]Launching dashboard…[/bold]\n")
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
                "--server.headless",
                "true",
                "--",
                str(spec_path.resolve()),
                str(seed),
            ],
            check=False,
        )
    else:
        console.print("[dim]Add [/dim][bold]--launch[/bold][dim] to open the dashboard now.[/dim]")


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
