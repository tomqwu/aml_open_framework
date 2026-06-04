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


@app.command(name="auditor-pack")
def auditor_pack_cmd(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    run_dir: Path = typer.Option(
        None, "--run-dir", help="Run directory; defaults to newest under artifacts/."
    ),
    artifacts: Path = typer.Option(
        Path("artifacts"), "--artifacts", help="Where engine runs are written."
    ),
    out: Path = typer.Option(
        Path("auditor-pack.zip"),
        "--out",
        help="Where to write the bundle ZIP.",
    ),
    print_link: bool = typer.Option(
        False,
        "--print-link",
        help="Print a dashboard deep-link the auditor can open in a browser.",
    ),
) -> None:
    """One ZIP, one command, no IT call — auditor self-service bundle.

    Builds a single ZIP containing the chain-verified audit ledger, the
    regulator examination pack, the effectiveness pack (when supported),
    the raw manifest + decisions.jsonl, and a one-page MANIFEST.txt
    index the auditor opens first.

    Use `--print-link` to also print a dashboard URL that lands the
    auditor on the Audit & Evidence page in auditor-persona mode — for
    when they want to drill in before downloading the ZIP.
    """
    from aml_framework.auditor import auditor_dashboard_url, build_auditor_pack

    spec = load_spec(spec_path)
    run = _resolve_run_dir(run_dir, artifacts)
    result = build_auditor_pack(spec, run, out=out)

    table = Table(title=f"Auditor pack · {spec.program.name}")
    table.add_column("Component")
    table.add_column("Status")
    for c in result.components:
        table.add_row(c, "[green]✓[/green]")
    console.print(table)

    if result.chain_verified:
        console.print(f"\n[green]✓ Hash chain verified.[/green] {result.chain_message}")
    else:
        console.print(f"\n[red]✗ Chain integrity issue.[/red] {result.chain_message}")

    console.print(f"\n[green]Auditor pack written[/green] {result.zip_path}")

    if print_link:
        url = auditor_dashboard_url(spec_path)
        console.print(f"\n[bold]Auditor dashboard URL:[/bold]\n  {url}")


@app.command(name="add-rule")
def add_rule_cmd(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    pattern: str = typer.Option(
        "structuring",
        "--pattern",
        help="structuring | velocity_burst | high_risk_jurisdiction",
    ),
    rule_id: str = typer.Option("", "--id", help="Rule id (lowercase a-z / 0-9 / _)."),
    name: str = typer.Option("", "--name", help="Human-readable rule name."),
    severity: str = typer.Option("high", "--severity", help="low/medium/high/critical."),
    threshold: float = typer.Option(0.0, "--threshold", help="Amount threshold (structuring)."),
    window: int = typer.Option(
        0, "--window", help="Window in days (structuring) or hours (velocity_burst)."
    ),
    min_count: int = typer.Option(0, "--min-count", help="Minimum transaction count."),
    channel: str = typer.Option("cash", "--channel", help="Channel filter (structuring)."),
    direction: str = typer.Option("in", "--direction", help="in | out."),
    countries: str = typer.Option(
        "",
        "--countries",
        help="ISO 3166-1 alpha-2 codes (high_risk_jurisdiction), comma-separated.",
    ),
    citation: str = typer.Option("", "--citation", help="Regulation citation."),
    citation_description: str = typer.Option("", "--citation-description"),
    escalate_to: str = typer.Option("l2_review", "--escalate-to", help="Queue id."),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="Take all defaults / flags; no prompts. For CI / scripts.",
    ),
) -> None:
    """Add a new detection rule to an existing spec — 60 seconds, not 60 minutes.

    Three patterns supported:
      structuring             — N txns of channel X summing to ≥ A in W days
      velocity_burst          — N txns of any kind in H hours
      high_risk_jurisdiction  — country list × amount floor

    Other patterns (python_ref, network_pattern) need a coded scorer or
    graph-shape parameter respectively — those are out of wizard scope;
    edit the spec by hand for now.
    """
    from aml_framework.add_rule_wizard import (
        HighRiskJurisdictionConfig,
        StructuringConfig,
        VelocityBurstConfig,
        render_high_risk_jurisdiction,
        render_structuring,
        render_velocity_burst,
        splice_rule,
        validate_country_codes,
        validate_rule_id,
    )

    spec = load_spec(spec_path)
    existing_ids = {r.id for r in spec.rules}
    queue_ids = [q.id for q in spec.workflow.queues]

    # Pick a sensible escalate_to default if the user took the literal
    # "l2_review" default and that queue doesn't exist in this spec.
    if escalate_to == "l2_review" and "l2_review" not in queue_ids:
        # Prefer a queue with "l2", "investigator", or "review" in the
        # id; else pick the second queue (typical 1LoD → 2LoD shape);
        # else the first.
        preferred = [q for q in queue_ids if any(k in q for k in ("l2", "investigator", "review"))]
        if preferred:
            escalate_to = preferred[0]
        elif len(queue_ids) >= 2:
            escalate_to = queue_ids[1]
        elif queue_ids:
            escalate_to = queue_ids[0]
        # else leave as l2_review and let the loader fail with a clear
        # message — this spec has no queues at all.

    # Resolve rule_id (prompt if missing).
    if not rule_id:
        if non_interactive:
            console.print("[red]--id is required in --non-interactive mode.[/red]")
            raise typer.Exit(code=2)
        rule_id = typer.prompt("Rule id (lowercase a-z / 0-9 / _)")
    err = validate_rule_id(rule_id, existing_ids)
    if err:
        console.print(f"[red]{err}[/red]")
        raise typer.Exit(code=2)

    if not name:
        name = (
            rule_id.replace("_", " ").title()
            if non_interactive
            else typer.prompt("Rule name", default=rule_id.replace("_", " ").title())
        )

    if not citation and not non_interactive:
        citation = typer.prompt("Regulation citation", default="FATF R.20")
    citation = citation or "FATF R.20"
    if not citation_description and not non_interactive:
        citation_description = typer.prompt(
            "Citation description",
            default="Reporting suspicious activity.",
        )
    citation_description = citation_description or "Reporting suspicious activity."

    # Build the pattern-specific config + render YAML.
    pattern = pattern.strip().lower().replace("-", "_")
    if pattern == "structuring":
        if threshold == 0.0:
            threshold = (
                9500.0
                if non_interactive
                else float(typer.prompt("Sum-amount threshold", default="9500"))
            )
        if window == 0:
            window = 30 if non_interactive else int(typer.prompt("Window (days)", default="30"))
        if min_count == 0:
            min_count = 3 if non_interactive else int(typer.prompt("Minimum count", default="3"))
        cfg = StructuringConfig(
            rule_id=rule_id,
            name=name,
            severity=severity,  # type: ignore[arg-type]
            threshold_amount=threshold,
            window_days=window,
            min_count=min_count,
            channel=channel,
            direction=direction,  # type: ignore[arg-type]
            citation=citation,
            citation_description=citation_description,
            escalate_to=escalate_to,
        )
        rule_yaml = render_structuring(cfg)
    elif pattern == "velocity_burst":
        if window == 0:
            window = 1 if non_interactive else int(typer.prompt("Window (hours)", default="1"))
        if min_count == 0:
            min_count = 5 if non_interactive else int(typer.prompt("Minimum count", default="5"))
        cfg_v = VelocityBurstConfig(
            rule_id=rule_id,
            name=name,
            severity=severity,  # type: ignore[arg-type]
            min_count=min_count,
            window_hours=window,
            direction=direction,  # type: ignore[arg-type]
            citation=citation,
            citation_description=citation_description,
            escalate_to=escalate_to,
        )
        rule_yaml = render_velocity_burst(cfg_v)
    elif pattern == "high_risk_jurisdiction":
        if not countries and non_interactive:
            countries = "IR,KP,RU,SY"
        elif not countries:
            countries = typer.prompt(
                "High-risk countries (ISO alpha-2, comma-separated)",
                default="IR,KP,RU,SY",
            )
        country_list = validate_country_codes(countries.split(","))
        if not country_list:
            console.print(
                "[red]No valid ISO 3166-1 alpha-2 country codes parsed. "
                "Pass --countries 'IR,KP,RU'.[/red]"
            )
            raise typer.Exit(code=2)
        if threshold == 0.0:
            threshold = (
                1000.0 if non_interactive else float(typer.prompt("Amount floor", default="1000"))
            )
        cfg_j = HighRiskJurisdictionConfig(
            rule_id=rule_id,
            name=name,
            severity=severity,  # type: ignore[arg-type]
            countries=country_list,
            amount_floor=threshold,
            citation=citation,
            citation_description=citation_description,
            escalate_to=escalate_to,
        )
        rule_yaml = render_high_risk_jurisdiction(cfg_j)
    else:
        console.print(
            f"[red]Unknown pattern {pattern!r}.[/red] "
            "Choose: structuring | velocity_burst | high_risk_jurisdiction"
        )
        raise typer.Exit(code=2)

    if not non_interactive:
        console.print("\n[bold]About to insert this rule into[/bold] " + str(spec_path))
        console.print(rule_yaml)
        if not typer.confirm("Splice it in?", default=True):
            console.print("[yellow]Aborted — spec unchanged.[/yellow]")
            raise typer.Exit(code=0)

    try:
        result = splice_rule(spec_path, rule_yaml, rule_id)
    except Exception as e:
        console.print(f"[red]Splice failed:[/red] {e}")
        raise typer.Exit(code=1)

    console.rule(f"[bold cyan]✓ Rule {rule_id!r} added[/bold cyan]")
    console.print(f"  spec: {result.spec_path}")
    console.print(f"  inserted near line {result.line_number}\n")
    console.print("[bold]Try it now:[/bold]")
    console.print(f"  $ aml validate {spec_path}")
    console.print(f"  $ aml run {spec_path} --seed 42")


@app.command(name="today")
def today_cmd(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    persona: str = typer.Option(
        "cco",
        "--persona",
        help="cco | mlro | director | manager | analyst | auditor | cto | svp",
    ),
    run_dir: Path = typer.Option(
        None, "--run-dir", help="Run dir; defaults to newest under artifacts/."
    ),
    artifacts: Path = typer.Option(
        Path("artifacts"), "--artifacts", help="Where engine runs are written."
    ),
    no_run: bool = typer.Option(
        False,
        "--no-run",
        help="Skip the run-dir lookup; show only always-applicable hints.",
    ),
) -> None:
    """Per-persona morning checklist — what needs your attention today.

    Walks the latest run's audit ledger + cases and produces a one-page
    checklist tailored to the asker's role. CCO sees board-relevant
    signal; MLRO sees model-challenge work; analyst sees their own
    queue. Quiet defaults: when nothing's on fire, the checklist is a
    one-line "all clear" rather than empty.

    Process problem: leaders read 4 dashboards every morning to assemble
    a unified picture. This is that unified picture in 1 command.
    """
    from aml_framework.today_checklist import (
        PERSONA_SIGNALS,
        build_checklist,
        render_checklist_text,
    )

    persona = persona.strip().lower()
    if persona not in PERSONA_SIGNALS:
        console.print(
            f"[red]Unknown persona {persona!r}.[/red] Choose: {', '.join(sorted(PERSONA_SIGNALS))}"
        )
        raise typer.Exit(code=2)

    spec = load_spec(spec_path)
    if no_run:
        run = None
    else:
        try:
            run = _resolve_run_dir(run_dir, artifacts)
        except typer.Exit:
            # No run dir → silently fall back to "no-run" mode rather than
            # crashing the new-bank case.
            run = None

    checklist = build_checklist(persona=persona, spec=spec, run_dir=run)
    console.print(render_checklist_text(checklist))


@app.command(name="propose-change")
def propose_change_cmd(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    rule_id: str = typer.Option(..., "--rule", help="Rule id whose threshold is changing."),
    proposed_yaml_path: Path = typer.Option(
        ...,
        "--proposed-yaml",
        exists=True,
        readable=True,
        help="File containing the proposed rule YAML (replaces the current rule block).",
    ),
    rationale: str = typer.Option(..., "--rationale", help="One-paragraph what + why."),
    proposer: str = typer.Option("", "--proposer", help="1LoD name (defaults to git user.name)."),
    expected_impact: str = typer.Option(
        "", "--expected-impact", help="One-line prediction (optional)."
    ),
    out: Path = typer.Option(
        Path("mlro-review-packet.md"),
        "--out",
        help="Where to write the Markdown packet.",
    ),
) -> None:
    """Package a threshold change as a 2LoD review packet (Markdown).

    Process problem: today, when 1LoD wants to lower a structuring
    threshold, the 2LoD review ritual happens in email or Word — not
    archived with the spec PR. When OSFI walks in 18 months later
    asking "who decided?", the answer is in an Outlook thread.

    This command produces a Markdown packet 1LoD attaches to their
    spec PR. 2LoD reads it in-line, fills the sign-off block, the
    MLRO countersigns. The packet + spec PR commit history together
    are the audit-trail artifact.
    """
    import subprocess

    from aml_framework.propose_change import ProposedChange, build_review_packet

    if not proposer:
        try:
            proposer = subprocess.check_output(
                ["git", "config", "--get", "user.name"], text=True
            ).strip()
        except Exception:
            proposer = "(unknown — set with --proposer)"

    proposed_yaml = proposed_yaml_path.read_text(encoding="utf-8")
    change = ProposedChange(
        spec_path=spec_path,
        rule_id=rule_id,
        proposed_yaml=proposed_yaml,
        proposer=proposer,
        rationale=rationale,
        expected_impact=expected_impact,
    )
    packet = build_review_packet(change=change)
    out.write_text(packet, encoding="utf-8")

    console.print(f"[green]Review packet written[/green] {out}")
    console.print(f"  proposer: {proposer}")
    console.print(f"  rule:     {rule_id}")
    console.print(
        "\n[bold]Next:[/bold] paste this Markdown into the spec PR description,\n"
        "or commit it next to your spec change so the audit trail keeps both."
    )


@app.command(name="notify-digest")
def notify_digest_cmd(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    run_dir: Path = typer.Option(
        None, "--run-dir", help="Run directory; defaults to newest under artifacts/."
    ),
    artifacts: Path = typer.Option(
        Path("artifacts"), "--artifacts", help="Where engine runs are written."
    ),
    window_hours: int = typer.Option(24, "--since-hours", help="Lookback window."),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Print the rendered Slack message; don't POST to webhooks.",
    ),
    suppress_empty: bool = typer.Option(
        False,
        "--suppress-empty",
        help="Skip the send when nothing crossed the line in the window.",
    ),
) -> None:
    """Roll up escalations + SLA breaches + critical alerts into one Slack/Teams message.

    Cron this every 4-24 hours into your team's compliance channel.
    Without it, the only way the supervisor finds out about a breach
    is by opening the dashboard — so they don't, until end-of-day.

    Configure via env:
      SLACK_WEBHOOK_URL — Slack incoming webhook
      TEAMS_WEBHOOK_URL — Teams incoming webhook
    """
    from aml_framework.integrations.digest import build_digest, post_digest, render_slack_text

    spec = load_spec(spec_path)
    run = _resolve_run_dir(run_dir, artifacts)
    payload = build_digest(run, program_name=spec.program.name, window_hours=window_hours)

    text = render_slack_text(payload)
    console.rule("[bold]Digest preview[/bold]")
    console.print(text)
    console.rule()

    if dry_run:
        console.print("[yellow]Dry run — not posting to webhooks.[/yellow]")
        return

    sent = post_digest(payload, suppress_when_empty=suppress_empty)
    if not any(sent.values()):
        if suppress_empty and payload.total == 0:
            console.print(
                "[dim]Suppressed (no events in window). Re-run without "
                "--suppress-empty to send a heartbeat anyway.[/dim]"
            )
        else:
            console.print(
                "[yellow]No webhooks reachable.[/yellow] Set SLACK_WEBHOOK_URL "
                "or TEAMS_WEBHOOK_URL in env. Use --dry-run to preview without posting."
            )
    else:
        for platform, ok in sent.items():
            mark = "[green]✓[/green]" if ok else "[red]✗[/red]"
            console.print(f"  {mark} {platform}")


@app.command(name="queue-rank")
def queue_rank_cmd(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    top: int = typer.Option(5, "--top", help="Top N cases to return."),
    run_dir: Path | None = typer.Option(
        None,
        "--run-dir",
        help="Run dir to read cases from. Defaults to the most recent under .artifacts/.",
    ),
    artifacts: Path = typer.Option(
        Path(".artifacts"),
        "--artifacts",
        help="Artifacts root; only used when --run-dir is unset.",
    ),
    seed: int = typer.Option(
        42,
        "--seed",
        help="Synthetic-data seed (used to load customers when --run-dir is unset).",
    ),
) -> None:
    """Rank open cases by composite triage score (PR-PROC-2 / PROC-1).

    Reads cases from a run dir (or the most recent .artifacts run if none
    specified), composes SLA breach / severity / customer-risk / rule
    precision into a single 0-100 urgency score, and prints the top N
    with one-line "why this case first" justifications.

    Same inputs always produce the same ranking — the score is
    deterministic, so two analysts running the same command see the
    same queue order.
    """
    import json as _json
    from datetime import datetime as _dt
    from datetime import timezone as _tz

    from aml_framework.cases.triage import rank_queue
    from aml_framework.data.sources import resolve_source

    spec = load_spec(spec_path)

    # Resolve run_dir: use --run-dir if given, otherwise newest under
    # --artifacts. Refuse if no run dirs exist (operator should run
    # `aml run` first).
    if run_dir is None:
        candidates = sorted(artifacts.glob("run-*"), reverse=True)
        if not candidates:
            console.print(
                f"[red]No run dirs under {artifacts}/.[/red] "
                f"Run [cyan]aml run {spec_path}[/cyan] first."
            )
            raise typer.Exit(code=1)
        run_dir = candidates[0]
    cases_dir = run_dir / "cases"
    if not cases_dir.exists():
        console.print(f"[red]No cases dir under {run_dir}.[/red]")
        raise typer.Exit(code=1)

    cases = []
    for path in sorted(cases_dir.glob("*.json")):
        if path.name.endswith("__filing.jsonl"):
            continue  # PR-DATA-9 sidecars; not cases
        try:
            cases.append(_json.loads(path.read_text(encoding="utf-8")))
        except _json.JSONDecodeError:
            continue

    if not cases:
        console.print(f"[yellow]No cases in {run_dir}.[/yellow] Nothing to rank.")
        return

    # Customers are needed for risk_rating lookup. Use the same data
    # source the run was built from (synthetic with the given seed
    # gives deterministic customers; real-data runs require the same
    # source files to still be present).
    #
    # Engine-emitted cases serialise timestamps as naive ISO strings
    # (no tz suffix). Use a naive UTC clock so SLA arithmetic doesn't
    # crash on aware/naive subtraction. Mirrors dashboard pages 21 and 24.
    as_of = _dt.now(tz=_tz.utc).replace(tzinfo=None)
    try:
        data = resolve_source(
            source_type="synthetic",
            spec=spec,
            as_of=as_of,
            seed=seed,
            data_dir=None,
        )
        customers = data.get("customer", [])
    except Exception:  # noqa: BLE001
        customers = []

    ranked = rank_queue(cases, spec, customers, as_of=as_of, top_n=top)

    table = Table(title=f"Triage rank — top {len(ranked)} of {len(cases)} cases")
    table.add_column("#", style="dim", width=3)
    table.add_column("Score", justify="right")
    table.add_column("case_id")
    table.add_column("Severity")
    table.add_column("SLA")
    table.add_column("Customer")
    table.add_column("Why")

    sla_style = {
        "breached": "red",
        "red": "red",
        "amber": "yellow",
        "green": "green",
        "unknown": "dim",
    }
    for i, r in enumerate(ranked, start=1):
        table.add_row(
            str(i),
            f"{r.score:.1f}",
            r.case_id,
            r.severity,
            f"[{sla_style.get(r.sla_state, 'white')}]{r.sla_state}[/]",
            f"{r.customer_id} ({r.customer_risk_rating})",
            r.why,
        )
    console.print(table)


@app.command(name="share-pattern")
def share_pattern_cmd(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    partner: str = typer.Option(
        ..., "--partner", help="Partner FI ID from spec.information_sharing.partners[].fi_id."
    ),
    rule_family: str = typer.Option(
        "network_pattern",
        "--rule-family",
        help="Taxonomy slug for the pattern family being shared (e.g. rtp_mule_cluster).",
    ),
    salt: str = typer.Option(
        ...,
        "--salt",
        help="Per-pair, per-period salt agreed with the partner FI out-of-band.",
    ),
    salt_period: str = typer.Option(
        "",
        "--salt-period",
        help="Salt period label, e.g. '2026-04'. Receiving FI checks parity.",
    ),
    out: Path = typer.Option(
        Path("share-pattern.json"),
        "--out",
        help="Where to write the partner-scoped JSON.",
    ),
) -> None:
    """Emit a partner-scoped obfuscated-pattern JSON for cross-bank info sharing (DATA-10).

    The spec must declare `information_sharing.partners[].fi_id == partner`
    or the command refuses to write — the spec is the policy boundary.
    Production cross-FI exchange is out of scope; this command produces
    a reference artifact the partner can compare against.
    """
    import json as _json
    from datetime import datetime, timezone

    from aml_framework.compliance.sandbox import obfuscate_pattern_match

    spec = load_spec(spec_path)
    if not spec.information_sharing or not spec.information_sharing.enabled:
        console.print("[red]Refused:[/red] spec has no enabled `information_sharing` block.")
        raise typer.Exit(code=1)
    declared = {p.fi_id for p in spec.information_sharing.partners}
    if partner not in declared:
        console.print(
            f"[red]Refused:[/red] partner '{partner}' is not in the spec's "
            f"information_sharing.partners (declared: {sorted(declared) or 'none'})."
        )
        raise typer.Exit(code=1)

    obfuscated = obfuscate_pattern_match(
        fi_id=spec.program.regulator,
        rule_family=rule_family,
        detected_at=datetime.now(tz=timezone.utc),
        pattern_kind="component_size",
        structural_fingerprint={"node_count": 0, "edge_count": 0, "max_hop": 0},
        subject_ids=[],
        neighbour_ids=[],
        salt=salt.encode("utf-8"),
        salt_period=salt_period,
    )
    out.write_text(_json.dumps(obfuscated.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    console.print(f"[green]Wrote[/green] partner-scoped pattern to {out}")
    console.print(f"  partner: {partner}")
    console.print(f"  salt_period: {salt_period or '(unset)'}")


@app.command(name="verify-pattern")
def verify_pattern_cmd(
    local_file: Path = typer.Argument(
        ..., exists=True, readable=True, help="Local obfuscated-pattern JSON."
    ),
    partner_file: Path = typer.Argument(
        ..., exists=True, readable=True, help="Partner-FI obfuscated-pattern JSON."
    ),
) -> None:
    """Compare two obfuscated patterns from different FIs (DATA-10).

    Both files should have been emitted by `aml share-pattern` against
    the same salt + salt_period. Returns a structural-match flag plus
    any obfuscated-id overlap.
    """
    import json as _json
    from datetime import datetime

    from aml_framework.compliance.sandbox import (
        ObfuscatedPattern,
        verify_pattern_overlap,
    )

    def _load(path: Path) -> ObfuscatedPattern:
        d = _json.loads(path.read_text(encoding="utf-8"))
        return ObfuscatedPattern(
            fi_id=d["fi_id"],
            rule_family=d["rule_family"],
            detected_at=datetime.fromisoformat(d["detected_at"].replace("Z", "+00:00")),
            pattern_kind=d["pattern_kind"],
            structural_fingerprint=d["structural_fingerprint"],
            obfuscated_subject_ids=list(d.get("obfuscated_subject_ids", [])),
            obfuscated_neighbour_ids=list(d.get("obfuscated_neighbour_ids", [])),
            salt_period=d.get("salt_period", ""),
        )

    local = _load(local_file)
    partner = _load(partner_file)
    report = verify_pattern_overlap(local, partner)

    console.print("[bold]Overlap report[/bold]")
    console.print(f"  structural_match: {report.structural_match}")
    console.print(f"  structural_distance: {report.structural_distance}")
    console.print(f"  has_identifier_overlap: {report.has_identifier_overlap}")
    if report.has_identifier_overlap:
        console.print(
            f"  overlapping_obfuscated_ids ({len(report.overlapping_obfuscated_ids)}): "
            f"{report.overlapping_obfuscated_ids[:5]}…"
        )
    if report.note:
        console.print(f"  note: {report.note}")


@app.command(name="attest")
def attest_cmd(
    spec_path: Path = typer.Argument(..., exists=True, readable=True, help="Spec to attest."),
    officer: str = typer.Option(
        ..., "--officer", help="MLRO / officer ID signing the attestation."
    ),
    notes: str = typer.Option("", "--notes", help="Optional sign-off notes."),
    attestations_dir: Path = typer.Option(
        Path(".attestations"),
        "--attestations-dir",
        help="Where to write the hash-chained attestations.jsonl ledger.",
    ),
) -> None:
    """Record an MLRO attestation against the spec's current content hash (DATA-8).

    Writes an entry to a hash-chained `attestations.jsonl` ledger,
    chained for tamper detection. Use `aml run --strict` afterwards to
    enforce attestation as a precondition for execution.
    """
    from aml_framework.attestations import AttestationLedger
    from aml_framework.spec.loader import spec_content_hash

    spec_hash = spec_content_hash(spec_path)
    ledger = AttestationLedger(dir=attestations_dir)
    attestation = ledger.append(
        officer_id=officer,
        spec_content_hash=spec_hash,
        notes=notes,
    )
    console.print(
        f"[green]Attestation recorded[/green] for spec hash [cyan]{spec_hash[:16]}…[/cyan]"
    )
    console.print(f"  officer: {attestation.officer_id}")
    console.print(f"  ts:      {attestation.ts.isoformat()}")
    console.print(f"  ledger:  {ledger.path}")
    if notes:
        console.print(f"  notes:   {notes}")


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


def _load_legacy_inventory(legacy_path: Path):
    """Dispatch by suffix to the right legacy parser. Returns ParseResult."""
    from aml_framework.generators.legacy_import import (
        parse_legacy_csv_with_warnings,
        parse_legacy_json_with_warnings,
    )

    suffix = legacy_path.suffix.lower()
    if suffix == ".csv":
        return parse_legacy_csv_with_warnings(legacy_path)
    if suffix == ".json":
        return parse_legacy_json_with_warnings(legacy_path)
    raise typer.BadParameter(f"Unsupported legacy file format '{suffix}' — expected .csv or .json.")


@app.command(name="inventory")
def inventory_cmd(
    legacy_path: Path = typer.Argument(..., exists=True, readable=True),
) -> None:
    """Read-only summary of a legacy rule export.

    Counts rules by shape (SQL / threshold / narrative / empty), flags
    duplicate rule IDs, and reports how many rules are ready to import
    vs how many need manual conversion. Use this before
    `aml import-legacy` to size the migration.
    """
    from aml_framework.generators.legacy_import import inventory_summary

    result = _load_legacy_inventory(legacy_path)
    summary = inventory_summary(result.rows)

    console.rule(f"[bold cyan]Legacy rule inventory — {legacy_path.name}[/bold cyan]")
    console.print(f"  Total rules parsed : [bold]{summary['total']}[/bold]")
    console.print(f"  Ready to import    : [green]{summary['ready_to_import']}[/green]")
    console.print(f"  Needs manual work  : [yellow]{summary['needs_manual']}[/yellow]")
    console.print(f"  Missing reg refs   : {summary['missing_regulator_refs']}")
    if summary["duplicate_rule_ids"]:
        console.print(
            f"  [red]Duplicate rule_ids[/red]: {', '.join(summary['duplicate_rule_ids'])}"
        )
    table = Table(title="By shape")
    table.add_column("Shape")
    table.add_column("Count", justify="right")
    for shape, count in summary["by_shape"].items():
        table.add_row(shape, str(count))
    console.print(table)
    if result.warnings:
        console.print(f"\n[yellow]{len(result.warnings)} parse warning(s):[/yellow]")
        for warning in result.warnings[:20]:
            rid = warning.rule_id or "—"
            console.print(f"  row {warning.row_index} ({rid}): {warning.reason}")
        if len(result.warnings) > 20:
            console.print(f"  …and {len(result.warnings) - 20} more")


@app.command(name="import-legacy")
def import_legacy_cmd(
    legacy_path: Path = typer.Argument(..., exists=True, readable=True),
    output: Path = typer.Option(
        Path("spec_skeleton.yaml"),
        "--output",
        "-o",
        help="Where to write the starter spec skeleton.",
    ),
    overwrite: bool = typer.Option(
        False, "--overwrite", help="Replace the output file if it already exists."
    ),
) -> None:
    """Convert a legacy SAS / Actimize / Mantas / IMS rule export into a spec skeleton.

    The output is a *starter* `aml.yaml` block — every legacy rule
    becomes a stub the operator iterates on. SQL-bearing rules become
    `logic.type: custom_sql`; threshold-bearing rules become
    `aggregation_window` stubs with the legacy threshold tucked into
    `having`; narrative-only rules emit a TODO placeholder so the
    operator can find them with `grep TODO`.

    The skeleton intentionally fails `aml validate` if used as-is —
    that's the design. The operator must merge it into their real
    spec, fill in regulation_refs / escalate_to / severity, and tune
    thresholds against the institution's data contracts.
    """
    import yaml

    from aml_framework.generators.legacy_import import build_spec_skeleton, inventory_summary

    if output.exists() and not overwrite:
        console.print(f"[red]{output} already exists.[/red]\nRe-run with [bold]--overwrite[/bold].")
        raise typer.Exit(code=1)

    result = _load_legacy_inventory(legacy_path)
    summary = inventory_summary(result.rows)
    # Abort before writing an empty `rules: []` skeleton — otherwise
    # an unrecognised export (e.g. wrong-shape JSON or CSV with no
    # known headers) would look "imported" while silently hiding the
    # migration workload. Surface the warnings + exit so the operator
    # can fix the input.
    if not result.rows:
        console.print(
            "[red]No legacy rules parsed from "
            f"{legacy_path.name}[/red] — refusing to write an empty skeleton."
        )
        if result.warnings:
            console.print(f"[yellow]{len(result.warnings)} parse warning(s):[/yellow]")
            for warning in result.warnings[:10]:
                rid = warning.rule_id or "—"
                console.print(f"  row {warning.row_index} ({rid}): {warning.reason}")
            if len(result.warnings) > 10:
                console.print(f"  …and {len(result.warnings) - 10} more")
        console.print("Run [bold]aml inventory[/bold] for the full diagnostic.")
        raise typer.Exit(code=1)
    skeleton = build_spec_skeleton(result.rows)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump(skeleton, sort_keys=False), encoding="utf-8")

    console.rule(f"[bold cyan]✓ Wrote {output}[/bold cyan]")
    console.print(
        f"  {summary['total']} rule(s) — "
        f"[green]{summary['ready_to_import']} ready[/green], "
        f"[yellow]{summary['needs_manual']} need manual work[/yellow]"
    )
    if result.warnings:
        console.print(
            f"  [yellow]{len(result.warnings)} parse warning(s) — run `aml inventory` to see them.[/yellow]"
        )
    console.print("\n[bold]Next steps:[/bold]")
    console.print(f"  1. Open {output} and search for [bold]TODO[/bold] markers.")
    console.print("  2. Fill in regulation_refs, escalate_to, severity per rule.")
    console.print("  3. Merge into your real aml.yaml + run `aml validate`.")


@app.command()
def byod(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    data_dir: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
    out: Path = typer.Option(
        Path("data_mapping.yaml"),
        "--out",
        help="Where to write the mapping YAML the developer edits.",
    ),
) -> None:
    """Bring-your-own-data wizard — map a real warehouse to spec contracts.

    Walks every data contract in `aml.yaml`, finds the matching CSV in
    `data_dir` (by contract id), profiles each column (type + nullness +
    sample values), and suggests a likely mapping for every column the
    spec declares. Output is a `data_mapping.yaml` the developer
    reviews + edits — then `aml validate-data` checks completeness.

    Decision order for each suggestion (highest-confidence first):
      1. Exact name match (confidence 1.00)
      2. Known alias (e.g. `cust_id` ↔ `customer_id`) — confidence 0.85
      3. Substring match — confidence 0.60
      4. Single matching declared type, no name signal — confidence 0.30
         (flagged for human review)
      5. No suggestion — fill in manually
    """
    from aml_framework.byod import map_spec_to_data_dir, render_mapping_yaml

    spec = load_spec(spec_path)
    reports = map_spec_to_data_dir(spec, data_dir)
    out.write_text(render_mapping_yaml(reports), encoding="utf-8")

    table = Table(title=f"Mapping report · {spec_path.name}")
    table.add_column("Contract")
    table.add_column("Source")
    table.add_column("Total", justify="right")
    table.add_column("Mapped", justify="right")
    table.add_column("Low conf", justify="right")
    table.add_column("Unmapped", justify="right")
    n_mapped = 0
    n_low = 0
    n_unmapped = 0
    for r in reports:
        mapped = sum(1 for m in r.mappings if m.suggested_source_column is not None)
        low = len(r.low_confidence)
        unmapped = len(r.unmapped_required)
        n_mapped += mapped
        n_low += low
        n_unmapped += unmapped
        table.add_row(
            r.contract_id,
            r.source_file.name,
            str(len(r.mappings)),
            str(mapped),
            str(low),
            str(unmapped),
        )
    console.print(table)

    if n_unmapped:
        console.print(
            f"\n[yellow]⚠ {n_unmapped} column(s) have no suggestion — "
            "fill them in manually.[/yellow]"
        )
    if n_low:
        console.print(
            f"[yellow]⚠ {n_low} column(s) are low-confidence — please verify "
            "before running the engine.[/yellow]"
        )

    console.print(f"\n[green]Mapping written[/green] {out}")
    console.print(
        f"\n[bold]Try it next:[/bold]\n  $ {out}  # review + edit\n"
        f"  $ aml validate-data {spec_path} --data-dir {data_dir}"
    )


@app.command()
def validate(spec_path: Path = typer.Argument(..., exists=True, readable=True)) -> None:
    """Validate aml.yaml against the JSON Schema and cross-reference checks."""
    spec = load_spec(spec_path)
    console.print(
        f"[green]OK[/green] {spec_path} — "
        f"{len(spec.data_contracts)} contract(s), {len(spec.rules)} rule(s), "
        f"{len(spec.workflow.queues)} queue(s)."
    )


@app.command(name="generate-dbt")
def generate_dbt_cmd(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    output_dir: Path = typer.Option(
        Path("dbt_aml"),
        "-o",
        "--output-dir",
        help="Directory to write the dbt project into. Created if absent.",
    ),
    as_of: str | None = typer.Option(
        None,
        help="ISO timestamp used as the rule 'now'. Defaults to current time.",
    ),
) -> None:
    """Emit a dbt project from the spec.

    Each `custom_sql` and `aggregation_window` rule becomes one dbt
    model under `<output_dir>/models/aml/<rule_id>.sql`. The output
    is drop-in for a bank's existing dbt project — `dbt run
    --select tag:aml` runs every emitted model.

    Rules using `python_ref` / `list_match` / `network_pattern`
    are skipped with a note in the emitted README (they need
    warehouse-side wiring beyond plain SQL).
    """
    from datetime import datetime

    from aml_framework.generators.dbt import generate_dbt_project

    spec = load_spec(spec_path)
    as_of_dt = datetime.fromisoformat(as_of) if as_of else datetime.now().replace(microsecond=0)
    written = generate_dbt_project(spec, spec_path, output_dir, as_of=as_of_dt)
    console.print(f"[green]Generated[/green] {len(written)} files into {output_dir}/")
    for name in sorted(written):
        console.print(f"  - {name}")


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
    notify: bool = typer.Option(
        False,
        "--notify",
        help="On drift findings, also post a summary to SLACK_WEBHOOK_URL / TEAMS_WEBHOOK_URL (no-op when neither is set).",
    ),
    export: Path | None = typer.Option(
        None,
        "--export",
        help="On drift findings, write the DriftReport as JSON to this path. Useful for downstream tooling (Jira tickets, regulator-summary docs).",
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

    if report.has_findings:
        if export is not None:
            import json as _json

            export.write_text(_json.dumps(report.to_dict(), indent=2), encoding="utf-8")
            console.print(f"[blue]Exported[/blue] drift report → {export}")
        if notify:
            from aml_framework.integrations.notifications import notify_regwatch_drift

            notify_regwatch_drift(report.to_dict())

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


@app.command(name="model-inventory")
def model_inventory_cmd(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    out: Path | None = typer.Option(None, "--out", help="Write the inventory JSON here."),
    markdown: Path | None = typer.Option(
        None, "--markdown", help="Write an MRM-review markdown table here."
    ),
) -> None:
    """Emit the SR-26-2 model-population inventory (rules + python_ref models +
    the N1 prioritization scorer) from the spec alone. Deterministic."""
    import json as _json

    from aml_framework.generators.model_inventory import (
        build_model_inventory,
        render_model_inventory_markdown,
    )
    from aml_framework.spec import load_spec

    spec = load_spec(spec_path)
    inv = build_model_inventory(spec)

    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_json.dumps(inv, indent=2, sort_keys=True) + "\n")
        typer.echo(f"Wrote model inventory JSON -> {out}")
    if markdown is not None:
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(render_model_inventory_markdown(inv))
        typer.echo(f"Wrote model inventory markdown -> {markdown}")

    s = inv["summary"]
    typer.echo(
        f"{s['total_models']} models "
        f"(by kind: {dict(sorted(s['by_kind'].items()))}; by tier: {s['by_tier']})"
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


@app.command(name="export-case")
def export_case_cmd(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    run_dir: Path = typer.Argument(..., exists=True, file_okay=False, readable=True),
    case_id: str = typer.Argument(..., help="case_id (basename of cases/<id>.json)."),
    out: Path = typer.Option(
        None,
        "--out",
        help="Output ZIP path; defaults to ./case-<case_id>.zip.",
    ),
    signing_key: str | None = typer.Option(
        None,
        "--signing-key",
        envvar="AML_CASE_PACK_SIGNING_KEY",
        help="Optional HMAC-SHA256 signing key for the manifest.",
    ),
) -> None:
    """Build a per-case evidence pack (PR-D4).

    The single-case subset of `audit-pack` — spec snapshot, the one case
    file, decisions sub-chain, lineage, the rule SQL and the alert
    payload. Smaller than a full-run pack; suitable for handing a
    regulator/auditor exactly the evidence for one alert.
    """
    from aml_framework.generators.audit_pack import (
        _load_pii_map,
        _mask_compound_string,
        build_case_pack,
    )

    spec = load_spec(spec_path)
    case_path = run_dir / "cases" / f"{case_id}.json"
    if not case_path.exists():
        console.print(f"[red]Case file not found:[/red] {case_path}")
        raise typer.Exit(code=1)
    # Codex P1 fix: when the run is masked, the engine case_id embeds
    # plaintext PII (e.g. ``<rule>__C0001__<ts>``). Mask the case_id
    # before using it in the default --out filename and in the console
    # log so PII never leaks into shell history / a CI artifact name.
    pii_map = _load_pii_map(run_dir)
    display_case_id = _mask_compound_string(case_id, pii_map) if pii_map else case_id
    target = out or Path(f"case-{display_case_id}.zip")
    payload = build_case_pack(spec, case_path, run_dir, signing_key=signing_key)
    target.write_bytes(payload)
    signed = " (signed)" if signing_key else ""
    console.print(
        f"[green]Case pack written[/green] {target} "
        f"({len(payload):,} bytes, case_id={display_case_id}){signed}"
    )


@app.command(name="export-batch")
def export_batch_cmd(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    run_dir: Path = typer.Argument(..., exists=True, file_okay=False, readable=True),
    cases: str = typer.Option(
        ...,
        "--cases",
        help="Comma-separated case_ids to bundle.",
    ),
    out: Path = typer.Option(
        Path("batch-pack.zip"),
        "--out",
        help="Output ZIP path.",
    ),
    signing_key: str | None = typer.Option(
        None,
        "--signing-key",
        envvar="AML_CASE_PACK_SIGNING_KEY",
        help="Optional HMAC-SHA256 signing key for the manifest.",
    ),
) -> None:
    """Build a multi-case evidence pack (PR-D4).

    For when a regulator requests evidence on a hand-picked batch of
    alerts — bundles every requested case's spec snapshot, decisions
    sub-chain, lineage, rule SQL and alert payload into one ZIP. Missing
    case ids fail loudly so the investigator never ships a half-empty pack.
    """
    from aml_framework.generators.audit_pack import build_batch_pack

    spec = load_spec(spec_path)
    case_ids = [c.strip() for c in cases.split(",") if c.strip()]
    if not case_ids:
        console.print("[red]--cases must contain at least one case_id.[/red]")
        raise typer.Exit(code=1)
    try:
        payload = build_batch_pack(spec, run_dir, case_ids, signing_key=signing_key)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    out.write_bytes(payload)
    signed = " (signed)" if signing_key else ""
    console.print(
        f"[green]Batch pack written[/green] {out} "
        f"({len(payload):,} bytes, {len(case_ids)} cases){signed}"
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
    strict: bool = typer.Option(
        False,
        "--strict",
        help=(
            "Refuse to run unless the current spec_content_hash has an MLRO "
            "attestation on file (DATA-8). Use `aml attest` to record one. "
            "Opt-in; default behaviour unchanged."
        ),
    ),
    labels: Path | None = typer.Option(
        None,
        "--labels",
        exists=True,
        readable=True,
        help=(
            "Ground-truth CSV (customer_id,is_true_positive). When given + "
            "prioritization enabled, writes a champion-challenger "
            "priority_outcome.json (precision@k / recall)."
        ),
    ),
    challenger_weights: str | None = typer.Option(
        None,
        "--challenger-weights",
        help="JSON weight overrides for the challenger scorer, e.g. '{\"amount\": 5.0}'.",
    ),
) -> None:
    """End-to-end: load data, execute rules, emit cases + audit bundle."""
    from aml_framework.data.sources import resolve_source
    from aml_framework.spec.loader import spec_content_hash as _spec_hash

    spec = load_spec(spec_path)
    as_of_dt = _parse_as_of(as_of)

    # PR-DATA-8: --strict gate. If the spec hasn't been signed by an
    # MLRO at this exact content hash, refuse to run. Run "aml attest"
    # first; or drop --strict if the gate isn't appropriate yet.
    if strict:
        from aml_framework.attestations import AttestationLedger

        spec_hash_now = _spec_hash(spec_path)
        ledger = AttestationLedger()
        latest = ledger.latest_for_spec(spec_hash_now)
        if latest is None:
            console.print(
                f"[red]--strict refused:[/red] no attestation on file for spec "
                f"hash {spec_hash_now[:16]}…\n"
                f"  Run [cyan]aml attest --officer <name> --spec {spec_path}[/cyan] first."
            )
            raise typer.Exit(code=1)
        console.print(
            f"[green]--strict passed:[/green] attested by "
            f"[cyan]{latest.officer_id}[/cyan] at {latest.ts.isoformat()}"
        )

    data = resolve_source(
        source_type=data_source,
        spec=spec,
        as_of=as_of_dt,
        seed=seed,
        data_dir=data_dir,
    )
    from aml_framework.data.sources import infer_source_paths

    data_sources = infer_source_paths(data_source, spec, data_dir=data_dir)

    _labels = None
    if labels is not None:
        from aml_framework.engine.priority_outcome import load_labels_csv

        _labels = load_labels_csv(labels)
    if challenger_weights:
        import json as _json

        _challenger = _json.loads(challenger_weights)
    else:
        _challenger = None

    result = run_spec(
        spec=spec,
        spec_path=spec_path,
        data=data,
        as_of=as_of_dt,
        artifacts_root=artifacts,
        data_sources=data_sources,
        labels=_labels,
        challenger_weights=_challenger,
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


@app.command(name="lineage")
def lineage_cmd(
    case_id: str = typer.Argument(..., help="case_id to walk back."),
    run_dir: Path | None = typer.Option(None, help="Specific run dir; defaults to latest."),
    artifacts: Path = typer.Option(Path(".artifacts")),
    format: str = typer.Option(
        "json",
        help="Output format: 'json' (default, machine-readable) or 'table' (human-readable).",
    ),
) -> None:
    """Walk the lineage chain for one case_id (PR-LIN-19).

    Wraps `walk_lineage()` so the chain (rule_sql + source_path +
    schema_hash + rule_version + matched_row_ids + decisions) is
    scriptable from CLI. Pipe to `jq` for ad-hoc queries:

        aml lineage C0042-cash_structuring-001 | jq '.matched_row_ids | length'
    """
    import json as _json

    from aml_framework.engine.audit import walk_lineage

    run_dir = _resolve_run_dir(run_dir, artifacts)
    chain = walk_lineage(run_dir, case_id)
    if chain.get("case") is None:
        console.print(f"[yellow]No case file found for {case_id!r} in {run_dir}.[/yellow]")
        raise typer.Exit(code=1)

    if format == "json":
        console.print_json(_json.dumps(chain, default=str))
        return

    # Human-readable table mode.
    console.print(f"[bold]Lineage chain for[/bold] [cyan]{case_id}[/cyan]")
    console.print(f"  rule_id            : {chain.get('rule_id') or '—'}")
    console.print(f"  rule_version       : {chain.get('rule_version') or '—'}")
    console.print(f"  spec_content_hash  : {(chain.get('spec_content_hash') or '—')[:16]}…")
    console.print(f"  engine_version     : {chain.get('engine_version') or '—'}")
    console.print(f"  as_of              : {chain.get('as_of') or '—'}")
    matched = (chain.get("case") or {}).get("alert", {}).get("matched_row_ids") or []
    console.print(f"  matched source rows: {len(matched)}")
    if chain.get("input_files"):
        console.print("  input_files:")
        for inp in chain["input_files"]:
            console.print(
                f"    - {inp.get('contract_id')} ← {inp.get('source_path') or '—'} "
                f"({inp.get('row_count') or 0:,} rows, schema {(inp.get('schema_hash') or '—')[:16]})"
            )
    console.print(f"  decisions: {len(chain.get('decisions') or [])}")


@app.command(name="verify-decisions")
def verify_decisions_cmd(
    run_dir: Path | None = typer.Option(None, help="Specific run dir; defaults to latest."),
    artifacts: Path = typer.Option(Path(".artifacts")),
    expected_hash: str | None = typer.Option(
        None,
        help=(
            "Out-of-band hash to verify against. If omitted, compares against "
            "the manifest.json's decisions_hash (catches partial tampering only)."
        ),
    ),
) -> None:
    """Verify the decisions.jsonl hash chain hasn't been tampered with (PR-LIN-19).

    Wraps `AuditLedger.verify_decisions()` so an examiner can run
    integrity checks from CLI. Exits 0 on a clean chain, 1 on tamper
    detection. The recommended path passes `--expected-hash` from a
    trusted out-of-band store (database, signed log, WORM bucket).
    """
    from aml_framework.engine.audit import AuditLedger

    run_dir = _resolve_run_dir(run_dir, artifacts)
    valid, msg = AuditLedger.verify_decisions(run_dir, expected_hash)
    color = "green" if valid else "red"
    console.print(f"[{color}]{msg}[/{color}]")
    if not valid:
        raise typer.Exit(code=1)


@app.command(name="equivalence")
def equivalence_cmd(
    run_dir: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        help="Run directory containing alerts/*.jsonl (the new-side alert export).",
    ),
    legacy: Path = typer.Option(
        ...,
        "--legacy",
        exists=True,
        readable=True,
        help="CSV of legacy-system alerts. Required columns: customer_id, "
        "period_start, period_end, rule_id_legacy. Optional: severity. "
        "Any extra columns become `payload`.",
    ),
    rule_map: Path | None = typer.Option(
        None,
        "--rule-map",
        exists=True,
        readable=True,
        help="YAML mapping of new_rule_id → legacy_rule_id. When absent, "
        "MATCH is computed against the identity mapping (new == legacy).",
    ),
    out: Path | None = typer.Option(
        None,
        "--out",
        help="Write the full classification report as JSON (array of cell records).",
    ),
    markdown: Path | None = typer.Option(
        None,
        "--markdown",
        help="Render a Markdown report (counts table + top-20 of each decision class). "
        "Useful for regulator-pack evidence.",
    ),
    spec_path: Path | None = typer.Option(
        None,
        "--spec",
        exists=True,
        readable=True,
        help="Optional spec path. When given, per-rule severities are passed to the "
        "classifier so DIFF detection works even when the alert payload lacks severity.",
    ),
    max_severity_diff: int | None = typer.Option(
        None,
        "--max-severity-diff",
        help="Exit non-zero if the DIFF count (severity-mismatch cells) exceeds this "
        "threshold. Default: no threshold (warn-only).",
    ),
) -> None:
    """Classify legacy↔new alert divergence as MATCH / NEW_ONLY / LEGACY_ONLY / DIFF.

    Wraps `engine.equivalence.classify_alerts()` so the 5-year-lookback
    runbook can produce a regulator-pack divergence report from the CLI
    without spinning up the dashboard. Reads the new-side alerts from
    `<run_dir>/alerts/*.jsonl` and the legacy alerts from `--legacy <csv>`.

    With `--max-severity-diff N`, exits non-zero when the DIFF count
    exceeds N — wire this into a CI gate to keep severity drift in check.
    Without it, the command always exits 0 (warn-only).
    """
    import json as _json
    from datetime import datetime as _datetime
    from datetime import timezone as _timezone

    from aml_framework.engine.audit import unmask_alerts
    from aml_framework.engine.equivalence import (
        EquivalenceClass,
        classify_alerts,
        load_legacy_alerts_csv,
    )

    # Load new-side alerts. Codex P2 review on PR-LOOKBACK-3: when the
    # run was produced with `AML_PII_MASKING=1`, `alerts/*.jsonl` stores
    # 16-hex-char hashes for `customer_id`, while a typical legacy CSV
    # carries plaintext IDs. Joining hashed vs plaintext keys would
    # report every true MATCH as NEW_ONLY + LEGACY_ONLY — misleading
    # evidence under SR 11-7 / OSFI E-23 scrutiny. `unmask_alerts()`
    # is a no-op when the run isn't masked (returns the raw alerts as
    # written), so this path is safe for both modes.
    alerts_dir = run_dir / "alerts"
    if not alerts_dir.exists():
        console.print(f"[red]No alerts/ in {run_dir}.[/red] Run `aml run` first.")
        raise typer.Exit(code=1)

    new_alerts = unmask_alerts(run_dir)

    # Resolve the source-of-truth spec early so we can pull per-rule
    # severities (DIFF detection), `program.legacy_reference.rule_map`
    # (correct join keys), and the legacy export's declared
    # `key_columns` (CSV column-name translation) from it. Default to
    # the run's `spec_snapshot.yaml` so the CLI always reproduces the
    # rule mapping that produced the alerts; `--spec` overrides for
    # the case where the operator is testing a proposed-spec change
    # against an existing run.
    rule_severities: dict[str, str] | None = None
    spec_rule_map: dict[str, str] = {}
    legacy_key_columns: list[str] = []
    effective_spec_path: Path | None = spec_path
    if effective_spec_path is None:
        snapshot = run_dir / "spec_snapshot.yaml"
        if snapshot.exists():
            effective_spec_path = snapshot
    if effective_spec_path is not None:
        spec = load_spec(effective_spec_path)
        rule_severities = {r.id: r.severity for r in spec.rules}
        legacy_ref = getattr(spec.program, "legacy_reference", None)
        if legacy_ref is not None:
            if legacy_ref.rule_map:
                spec_rule_map = {str(k): str(v) for k, v in legacy_ref.rule_map.items()}
            if legacy_ref.key_columns:
                legacy_key_columns = list(legacy_ref.key_columns)

    # Resolve the new→legacy rule map. Precedence (highest first):
    #   1. `--rule-map <yaml>` if passed (explicit operator override).
    #   2. `program.legacy_reference.rule_map` from the spec — codex
    #      pass 3 P2: this is the source-of-truth mapping captured
    #      alongside the spec, so the CLI must use it before falling
    #      back to identity. Without this step, runs whose legacy
    #      system uses different rule_ids report every true MATCH as
    #      NEW_ONLY + LEGACY_ONLY.
    #   3. Identity mapping over the rule_ids the new-side alerts
    #      carry (only safe when new_rule_id == legacy_rule_id).
    rule_map_dict: dict[str, str] = {}
    if rule_map is not None:
        import yaml as _yaml

        loaded = _yaml.safe_load(rule_map.read_text(encoding="utf-8"))
        # Codex pass 4 P2: an empty `--rule-map` YAML (or any non-dict
        # value) used to silently fall through to identity mapping,
        # which would BYPASS the spec's `legacy_reference.rule_map`
        # even when the spec carried a correct mapping. An explicit
        # override that's malformed should error, not degrade.
        if loaded is None or loaded == {}:
            console.print(
                f"[red]--rule-map is empty[/red] ({rule_map}). "
                "Either remove the flag (the CLI will use the spec's "
                "`program.legacy_reference.rule_map`, or identity mapping "
                "when no spec map exists) or populate the YAML."
            )
            raise typer.Exit(code=2)
        if not isinstance(loaded, dict):
            console.print(
                f"[red]--rule-map must be a YAML mapping[/red] "
                f"({type(loaded).__name__} parsed from {rule_map})."
            )
            raise typer.Exit(code=2)
        # Stringify keys/values so a YAML `1: 2` doesn't sneak ints in.
        rule_map_dict = {str(k): str(v) for k, v in loaded.items()}
    elif spec_rule_map:
        rule_map_dict = spec_rule_map

    if not rule_map_dict:
        rule_map_dict = {rid: rid for rid in new_alerts}

    # Translate the legacy CSV's spec-declared column names to the
    # canonical names `load_legacy_alerts_csv` expects (codex pass 4
    # P2). Mirrors the dashboard's `_derive_column_mapping` in
    # `pages/48_Equivalence.py` so the CLI accepts the same legacy
    # exports the dashboard already loads without forcing the operator
    # to rename columns. When the spec declares `key_columns:
    # [rule_id, customer_id, window_start]` (the CA example's spelling),
    # we translate `rule_id → rule_id_legacy`, `window_start →
    # period_start`, etc. When the CSV already uses canonical names,
    # the mapping is empty and the loader reads it directly.
    column_mapping = _derive_legacy_column_mapping(legacy, legacy_key_columns)

    # Surface loader failures (missing header / required column / malformed
    # datetime) as a user-readable CLI error instead of a Python traceback.
    # The loader's messages already name the file and the offending column.
    try:
        legacy_alerts = load_legacy_alerts_csv(legacy, column_mapping=column_mapping or None)
    except ValueError as exc:
        console.print(f"[red]Could not parse --legacy CSV[/red] {legacy}: {exc}")
        raise typer.Exit(code=2) from exc

    # Filter alerts that lack the comparison-required fields so the
    # classifier doesn't raise on a custom_sql / python_ref payload
    # missing canonical cell keys. Mirrors the page-side filter.
    _REQUIRED_FIELDS = ("customer_id", "window_start", "window_end")
    filtered_alerts: dict[str, list[dict]] = {}
    dropped_per_rule: dict[str, int] = {}
    for rule_id, alerts in new_alerts.items():
        keep: list[dict] = []
        dropped = 0
        for a in alerts:
            if all(a.get(k) is not None for k in _REQUIRED_FIELDS):
                keep.append(a)
            else:
                dropped += 1
        if keep:
            filtered_alerts[rule_id] = keep
        if dropped:
            dropped_per_rule[rule_id] = dropped

    if dropped_per_rule:
        total_dropped = sum(dropped_per_rule.values())
        console.print(
            f"[yellow]⚠ {total_dropped} alert(s) across "
            f"{len(dropped_per_rule)} rule(s) excluded — missing "
            f"customer_id / window_start / window_end.[/yellow]"
        )

    # Codex P2 review on PR-LOOKBACK-3: pass a real wall-clock timestamp
    # so the Markdown evidence pack carries an honest `Generated at` line
    # instead of the classifier's deterministic `datetime.min` sentinel
    # (`0001-01-01T00:00:00`). The sentinel is the right default for
    # equivalence-of-equivalence library tests, but a regulator-facing
    # CLI report needs a true generation time.
    generated_at = _datetime.now(tz=_timezone.utc).replace(tzinfo=None)

    report = classify_alerts(
        new_alerts=filtered_alerts,
        legacy_alerts=legacy_alerts,
        rule_map=rule_map_dict,
        rule_severities=rule_severities,
        generated_at=generated_at,
    )

    # KPI roll-up.
    table = Table(title=f"Equivalence — {run_dir.name}")
    table.add_column("Class")
    table.add_column("Count", justify="right")
    for cls in (
        EquivalenceClass.MATCH,
        EquivalenceClass.NEW_ONLY,
        EquivalenceClass.LEGACY_ONLY,
        EquivalenceClass.DIFF,
    ):
        table.add_row(cls.value, str(report.counts[cls]))
    console.print(table)
    console.print(
        f"  cells: {sum(report.counts.values())} · "
        f"rules: {len(report.by_rule)} · "
        f"legacy: {len(legacy_alerts)} rows · "
        f"new-side: {sum(len(v) for v in filtered_alerts.values())} alerts"
    )

    # JSON output (full cell list).
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        cells_json = [
            {
                "customer_id": c.customer_id,
                "period_start": c.period_start.isoformat(),
                "period_end": c.period_end.isoformat(),
                "rule_id_new": c.rule_id_new,
                "rule_id_legacy": c.rule_id_legacy,
                "classification": c.classification.value,
                "new_severity": c.new_severity,
                "legacy_severity": c.legacy_severity,
                "diff_reason": c.diff_reason,
            }
            for c in report.cells
        ]
        out.write_text(_json.dumps(cells_json, indent=2), encoding="utf-8")
        console.print(f"[green]JSON[/green] {out} ({len(cells_json)} cell(s))")

    # Markdown report (counts + top 20 of each decision class).
    if markdown is not None:
        markdown.parent.mkdir(parents=True, exist_ok=True)
        md = _render_equivalence_markdown(report, run_dir=run_dir, legacy_path=legacy)
        markdown.write_text(md, encoding="utf-8")
        console.print(f"[green]Markdown[/green] {markdown}")

    # Optional gate: exit non-zero when DIFF count exceeds the threshold.
    diff_count = report.counts[EquivalenceClass.DIFF]
    if max_severity_diff is not None and diff_count > max_severity_diff:
        console.print(
            f"[red]DIFF count {diff_count} exceeds --max-severity-diff {max_severity_diff}.[/red]"
        )
        raise typer.Exit(code=1)


# Canonical CSV column names → well-known legacy-system synonyms,
# mirroring `_LEGACY_SYNONYMS` in `pages/48_Equivalence.py`. The CLI
# uses these to translate spec-declared `key_columns` (e.g. CA's
# `[rule_id, customer_id, window_start]`) to the canonical names the
# loader expects (`rule_id_legacy`, `period_start`, etc.), so a CSV
# exported with native legacy column names loads without renames.
_EQUIVALENCE_LEGACY_SYNONYMS: dict[str, str] = {
    # legacy-system column name → canonical loader name
    "rule_id": "rule_id_legacy",
    "window_start": "period_start",
    "window_end": "period_end",
}


def _derive_legacy_column_mapping(
    legacy_path: Path,
    key_columns: list[str],
) -> dict[str, str]:
    """Build `{canonical: csv_column}` for `load_legacy_alerts_csv`.

    Strategy (matches `pages/48_Equivalence.py::_derive_column_mapping`):

    1. Honor explicit `legacy_reference.key_columns` synonyms first —
       when the spec declares `key_columns: [rule_id, customer_id,
       window_start]`, those are the operator's declared legacy
       column names.
    2. For any canonical column not yet mapped AND absent from the
       CSV header, fall back to the well-known synonym if present.
    3. If the canonical column is in the CSV header, do nothing —
       the loader's default mapping reads it directly.

    Returns `{}` when no translation is needed; the loader treats that
    as "use canonical names verbatim".
    """
    import csv as _csv

    canonical_cols = ("customer_id", "period_start", "period_end", "rule_id_legacy")
    try:
        with legacy_path.open(newline="", encoding="utf-8") as _fh:
            _reader = _csv.reader(_fh)
            csv_header = next(_reader, []) or []
    except OSError:
        return {}

    mapping: dict[str, str] = {}
    header_set = set(csv_header)
    # Step 1: explicit operator declarations from key_columns. Only
    # apply when (a) the legacy name from key_columns is in the CSV
    # header AND (b) the canonical name is NOT — preserves the
    # canonical-header export case.
    for col in key_columns:
        canonical = _EQUIVALENCE_LEGACY_SYNONYMS.get(col)
        if canonical is None or canonical in header_set or col not in header_set:
            continue
        mapping[canonical] = col
    # Step 2: fill gaps with well-known synonyms when the canonical
    # name is absent and the synonym is present.
    legacy_for_canonical = {v: k for k, v in _EQUIVALENCE_LEGACY_SYNONYMS.items()}
    for canonical in canonical_cols:
        if canonical in mapping or canonical in header_set:
            continue
        synonym = legacy_for_canonical.get(canonical)
        if synonym is not None and synonym in header_set:
            mapping[canonical] = synonym
    return mapping


def _render_equivalence_markdown(
    report,
    *,
    run_dir: Path,
    legacy_path: Path,
) -> str:
    """Render an EquivalenceReport as a Markdown evidence-pack snippet.

    Counts table + top 20 cells per class. Kept module-local because
    every other Markdown renderer in the CLI is also inline — the
    snippet is short and changes with the CLI flag set, not the
    classifier API.
    """
    from aml_framework.engine.equivalence import EquivalenceClass

    lines: list[str] = []
    lines.append(f"# Equivalence report — `{run_dir.name}`")
    lines.append("")
    lines.append(f"- Run directory: `{run_dir}`")
    lines.append(f"- Legacy alerts: `{legacy_path}`")
    lines.append(f"- Generated at: `{report.generated_at.isoformat()}`")
    lines.append("")
    lines.append("## Counts")
    lines.append("")
    lines.append("| Classification | Count |")
    lines.append("| --- | ---: |")
    for cls in (
        EquivalenceClass.MATCH,
        EquivalenceClass.NEW_ONLY,
        EquivalenceClass.LEGACY_ONLY,
        EquivalenceClass.DIFF,
    ):
        lines.append(f"| {cls.value} | {report.counts[cls]} |")
    lines.append("")

    lines.append("## By rule")
    lines.append("")
    if report.by_rule:
        lines.append("| Rule | MATCH | NEW_ONLY | LEGACY_ONLY | DIFF |")
        lines.append("| --- | ---: | ---: | ---: | ---: |")
        for rule_id, bucket in sorted(report.by_rule.items()):
            lines.append(
                f"| `{rule_id}` | "
                f"{bucket[EquivalenceClass.MATCH]} | "
                f"{bucket[EquivalenceClass.NEW_ONLY]} | "
                f"{bucket[EquivalenceClass.LEGACY_ONLY]} | "
                f"{bucket[EquivalenceClass.DIFF]} |"
            )
    else:
        lines.append("_No rules classified._")
    lines.append("")

    # Divergence clusters (NEW_ONLY / LEGACY_ONLY grouped by shape).
    # A triage lens — the four-way classification above is authoritative.
    from aml_framework.engine.equivalence_clustering import cluster_divergences

    cluster_report = cluster_divergences(report)
    lines.append("## Divergence clusters")
    lines.append("")
    lines.append(
        "_Shape-signature grouping of NEW_ONLY / LEGACY_ONLY cells "
        "(a triage lens; the four-way classification above is authoritative)._"
    )
    lines.append("")
    if cluster_report.clusters:
        lines.append("| Classification | Rule | Severity | Window (days) | Size |")
        lines.append("| --- | --- | --- | ---: | ---: |")
        for cl in cluster_report.clusters:
            lines.append(
                f"| {cl.classification.value} | `{cl.rule_id}` | {cl.severity} | "
                f"{cl.window_days} | {cl.size} |"
            )
    else:
        lines.append("_No divergences to cluster._")
    lines.append("")

    # Top 20 of each class (deterministic — cells are already sorted by
    # (customer, period, rule) so the head is stable across runs).
    by_class: dict[EquivalenceClass, list] = {cls: [] for cls in EquivalenceClass}
    for cell in report.cells:
        by_class[cell.classification].append(cell)

    for cls in (
        EquivalenceClass.MATCH,
        EquivalenceClass.NEW_ONLY,
        EquivalenceClass.LEGACY_ONLY,
        EquivalenceClass.DIFF,
    ):
        bucket = by_class[cls]
        lines.append(f"## {cls.value} — first 20 of {len(bucket)}")
        lines.append("")
        if not bucket:
            lines.append("_None._")
            lines.append("")
            continue
        lines.append(
            "| customer_id | period_start | period_end | rule_id_new | "
            "rule_id_legacy | new_severity | legacy_severity | diff_reason |"
        )
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for cell in bucket[:20]:
            lines.append(
                f"| {cell.customer_id} | "
                f"{cell.period_start.isoformat()} | "
                f"{cell.period_end.isoformat()} | "
                f"{cell.rule_id_new or ''} | "
                f"{cell.rule_id_legacy or ''} | "
                f"{cell.new_severity or ''} | "
                f"{cell.legacy_severity or ''} | "
                f"{cell.diff_reason or ''} |"
            )
        lines.append("")

    return "\n".join(lines)


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


@app.command(name="typology-list")
def typology_list_cmd(
    jurisdiction: str | None = typer.Option(
        None,
        "--jurisdiction",
        help="Filter to typologies that apply in this jurisdiction (e.g. US, CA, GB).",
    ),
) -> None:
    """List curated typologies available for `aml typology-import`."""
    from aml_framework.typology_library import list_typologies

    items = list_typologies()
    if jurisdiction:
        juris_upper = jurisdiction.upper()
        items = [t for t in items if juris_upper in {j.upper() for j in t.jurisdictions}]

    if not items:
        console.print(
            "[yellow]No typologies match.[/yellow] "
            "Drop a YAML file into src/aml_framework/spec/library/typologies/."
        )
        return

    table = Table(title="Curated typology catalogue", show_lines=False)
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("severity", style="magenta")
    table.add_column("jurisdictions", style="green")
    table.add_column("source", style="dim")
    table.add_column("description")

    for t in items:
        table.add_row(
            t.id,
            t.recommended_severity,
            ", ".join(t.jurisdictions),
            t.source,
            t.description_short,
        )

    console.print(table)
    console.print(
        f"\n[dim]{len(items)} typolog{'y' if len(items) == 1 else 'ies'} listed. "
        "Install with `aml typology-import <id> <spec-path>`.[/dim]"
    )


@app.command(name="typology-import")
def typology_import_cmd(
    typology_id: str = typer.Argument(..., help="Typology id (see `aml typology-list`)."),
    spec_path: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        writable=True,
        help="Path to the aml.yaml spec to splice the typology into.",
    ),
    allow_duplicate: bool = typer.Option(
        False,
        "--allow-duplicate",
        help="Skip the rule-id collision check (advanced).",
    ),
    escalate_to: str | None = typer.Option(
        None,
        "--escalate-to",
        help="Override the typology's preferred escalation queue id.",
    ),
) -> None:
    """Splice a curated typology rule into an existing aml.yaml.

    Atomic: validates the post-splice spec; rolls back on any failure.
    """
    from aml_framework.typology_library import import_typology

    try:
        result = import_typology(
            typology_id=typology_id,
            spec_path=spec_path,
            allow_duplicate_rule_id=allow_duplicate,
            escalate_to_override=escalate_to,
        )
    except KeyError as e:
        console.print(f"[red]Typology not found:[/red] {e}")
        raise typer.Exit(code=1) from e
    except ValueError as e:
        console.print(f"[red]Install failed:[/red] {e}")
        raise typer.Exit(code=1) from e

    console.print(
        f"[green]Installed[/green] typology [cyan]{result.typology_id}[/cyan] "
        f"as rule [cyan]{result.rule_id}[/cyan] "
        f"(line ~{result.line_number}) in {result.spec_path}."
    )
    if result.escalate_to_remapped_from:
        console.print(
            f"[yellow]Note:[/yellow] escalate_to remapped from "
            f"[cyan]{result.escalate_to_remapped_from}[/cyan] "
            f"to [cyan]{result.escalate_to}[/cyan] (queue does not exist in your spec)."
        )
    if result.source:
        console.print(f"[dim]Source: {result.source}[/dim]")
    console.print(
        "[dim]Next:[/dim] review the diff, run [cyan]aml validate[/cyan], "
        "then [cyan]aml run[/cyan] to see it fire."
    )


if __name__ == "__main__":
    app()
