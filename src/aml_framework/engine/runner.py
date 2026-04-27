"""Execute spec rules against an in-memory DuckDB warehouse."""

from __future__ import annotations

import importlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta as _timedelta
from pathlib import Path
from typing import Any, TypedDict

import duckdb

from aml_framework.engine.audit import AuditLedger
from aml_framework.generators.sql import compile_rule_sql
from aml_framework.metrics.engine import MetricResult, evaluate_metrics
from aml_framework.metrics.reports import render_all_reports
from aml_framework.spec.loader import spec_content_hash
from aml_framework.spec.models import AMLSpec, Rule

logger = logging.getLogger("aml.engine.runner")

# python_ref callables must live under one of these module prefixes. Keeps a
# malicious spec author from importing arbitrary code on sys.path. Override
# with AML_PYTHON_REF_PREFIX (comma-separated) for institution-specific
# scorers in a separate package.
_DEFAULT_PYTHON_REF_PREFIXES = ("aml_framework.models.",)


def _allowed_python_ref_prefixes() -> tuple[str, ...]:
    env = os.environ.get("AML_PYTHON_REF_PREFIX", "").strip()
    if not env:
        return _DEFAULT_PYTHON_REF_PREFIXES
    return tuple(p.strip() for p in env.split(",") if p.strip())


def _harden_duckdb(con: duckdb.DuckDBPyConnection) -> None:
    """Lock down a DuckDB connection so a malicious custom_sql rule cannot
    reach the network or filesystem. The reference engine only needs
    in-memory tables and reference-list CSVs (loaded by Python, not DuckDB).
    """
    for stmt in (
        "SET autoinstall_known_extensions=false",
        "SET autoload_known_extensions=false",
        "SET allow_unsigned_extensions=false",
        "SET enable_external_access=false",
    ):
        try:
            con.execute(stmt)
        except Exception:
            # Older DuckDB releases may not support every setting; skip
            # silently. The CI matrix pins a known version.
            pass


class CaseDict(TypedDict):
    case_id: str
    rule_id: str
    rule_name: str
    severity: str
    regulation_refs: list[dict[str, str]]
    queue: str
    alert: dict[str, Any]
    evidence_requested: list[str]
    spec_program: str
    input_hash: dict[str, Any]
    status: str


class DecisionEvent(TypedDict, total=False):
    event: str
    case_id: str
    rule_id: str
    queue: str
    disposition: str
    resolution_hours: float
    within_sla: bool


@dataclass
class RunResult:
    manifest: dict[str, Any]
    alerts: dict[str, list[dict[str, Any]]]
    case_ids: list[str] = field(default_factory=list)
    metrics: list[MetricResult] = field(default_factory=list)
    reports: dict[str, str] = field(default_factory=dict)

    @property
    def total_alerts(self) -> int:
        return sum(len(v) for v in self.alerts.values())


def _build_warehouse(
    con: duckdb.DuckDBPyConnection,
    spec: AMLSpec,
    data: dict[str, list[dict[str, Any]]],
) -> None:
    """Register each data_contract as a DuckDB table called `<id>`.

    The physical table name used in the engine is the contract id, not the
    `source` string — that keeps the reference engine independent of the
    institution's warehouse layout.
    """
    for contract in spec.data_contracts:
        rows = data.get(contract.id, [])
        if not rows:
            con.execute(f"CREATE TABLE {contract.id} AS SELECT NULL WHERE 1=0")
            continue
        # Only insert columns declared in the contract — synthetic data may
        # carry extra fields used by other specs.
        contract_cols = [c.name for c in contract.columns]
        cols = ", ".join(contract_cols)
        placeholders = ", ".join(["?"] * len(contract_cols))
        con.execute(f"CREATE TABLE {contract.id} ({_ddl_for_contract(contract)})")
        con.executemany(
            f"INSERT INTO {contract.id} ({cols}) VALUES ({placeholders})",
            [tuple(r.get(c) for c in contract_cols) for r in rows],
        )


def _ddl_for_contract(contract) -> str:
    dtype = {
        "string": "VARCHAR",
        "integer": "BIGINT",
        "decimal": "DECIMAL(18,2)",
        "boolean": "BOOLEAN",
        "date": "DATE",
        "timestamp": "TIMESTAMP",
    }
    parts = []
    for col in contract.columns:
        null_sql = "" if col.nullable else " NOT NULL"
        parts.append(f"{col.name} {dtype[col.type]}{null_sql}")
    return ", ".join(parts)


def _build_case(
    rule: Rule, alert: dict[str, Any], spec: AMLSpec, input_hash: dict[str, Any]
) -> CaseDict:
    # Minimal case file: enough for a reviewer to act, enough for an auditor
    # to trace the alert back to a spec clause.
    case_id = f"{rule.id}__{alert.get('customer_id', 'unknown')}__{alert.get('window_end', '')}"
    case_id = case_id.replace(" ", "T").replace(":", "")
    return {
        "case_id": case_id,
        "rule_id": rule.id,
        "rule_name": rule.name,
        "severity": rule.severity,
        "regulation_refs": [r.model_dump() for r in rule.regulation_refs],
        "queue": rule.escalate_to,
        "alert": alert,
        "evidence_requested": rule.evidence,
        "spec_program": spec.program.name,
        "input_hash": input_hash,
        "status": "open",
    }


def _open_cases_for_alerts(
    rule: Rule,
    alerts: list[dict[str, Any]],
    spec: AMLSpec,
    ledger: AuditLedger,
    case_ids: list[str],
) -> None:
    """Create a case for each alert, record to ledger, and append to case_ids."""
    for alert in alerts:
        case = _build_case(rule, alert, spec, ledger.input_manifest)
        ledger.record_case(case["case_id"], case)
        case_ids.append(case["case_id"])
        ledger.append_decision(
            {
                "event": "case_opened",
                "case_id": case["case_id"],
                "rule_id": rule.id,
                "queue": rule.escalate_to,
            }
        )


def _normalize_for_match(s: str) -> str:
    """ASCII-fold + uppercase + collapse whitespace.

    `Müller` → `MULLER`. Sanctions / PEP lists are typically transliterated
    Latin even when source data is not, so folding accents catches the
    common diacritic-vs-no-diacritic mismatch that the previous token-set
    matcher missed.
    """
    import unicodedata

    folded = unicodedata.normalize("NFKD", s)
    ascii_only = "".join(c for c in folded if not unicodedata.combining(c))
    return " ".join(ascii_only.upper().split())


def _fuzzy_match(value: str, list_entries: list[str], threshold: float) -> tuple[str, float] | None:
    """Return (best_entry, score) if any entry scores >= threshold.

    Score is the max of:
        - token-overlap (handles transposed tokens: "MARIA MUELLER" vs
          "MUELLER MARIA" still match)
        - SequenceMatcher ratio (handles edit-distance: "MUELLER" vs
          "MUELLERS" or "VOLKOV" vs "VOLKOVA" no longer slip through)

    Accents are folded to ASCII before scoring so "MÜLLER" matches "MUELLER"
    and "MUELLER".
    """
    from difflib import SequenceMatcher

    value_norm = _normalize_for_match(value)
    if not value_norm:
        return None
    value_tokens = set(value_norm.split())

    best: tuple[str, float] | None = None
    for entry in list_entries:
        entry_norm = _normalize_for_match(entry)
        if not entry_norm:
            continue
        entry_tokens = set(entry_norm.split())
        overlap = len(value_tokens & entry_tokens)
        token_score = overlap / max(len(value_tokens), len(entry_tokens))
        seq_score = SequenceMatcher(None, value_norm, entry_norm).ratio()
        score = max(token_score, seq_score)
        if score >= threshold and (best is None or score > best[1]):
            best = (entry, round(score, 3))
    return best


def _load_reference_list(list_name: str) -> list[str] | None:
    """Load a reference list CSV, returning uppercased names or None if missing."""
    import csv

    lists_dir = Path(__file__).resolve().parents[1] / "data" / "lists"
    list_path = lists_dir / f"{list_name}.csv"
    if not list_path.exists():
        return None
    with list_path.open("r", encoding="utf-8") as f:
        return [row["name"].strip().upper() for row in csv.DictReader(f)]


def _execute_list_match(
    rule: Rule,
    con: duckdb.DuckDBPyConnection,
    as_of: datetime,
) -> list[dict[str, Any]]:
    """Screen a data source field against a reference list (sanctions, PEP, etc.)."""
    logic = rule.logic
    list_name = logic.list
    field = logic.field
    match_type = logic.match
    threshold = logic.threshold or 0.8

    list_entries = _load_reference_list(list_name)
    if list_entries is None:
        return []

    # Get source data.
    source_table = logic.source
    try:
        rows = con.execute(f"SELECT * FROM {source_table}").fetchall()
        cols = [d[0] for d in con.description] if con.description else []
    except Exception:
        logger.warning("list_match: table '%s' not found for rule '%s'", source_table, rule.id)
        return []

    source_rows = [dict(zip(cols, r)) for r in rows]
    alerts: list[dict[str, Any]] = []
    base_alert = {
        "rule_id": rule.id,
        "list_name": list_name,
        "window_start": as_of,
        "window_end": as_of,
    }

    for row in source_rows:
        value = str(row.get(field, "")).strip().upper()
        if not value:
            continue
        customer_id = row.get("customer_id", "")

        if match_type == "exact" and value in list_entries:
            alerts.append(
                {
                    **base_alert,
                    "customer_id": customer_id,
                    "matched_name": value,
                    "match_type": "exact",
                    "match_score": 1.0,
                }
            )
        elif match_type == "fuzzy":
            result = _fuzzy_match(value, list_entries, threshold)
            if result:
                entry, score = result
                alerts.append(
                    {
                        **base_alert,
                        "customer_id": customer_id,
                        "matched_name": value,
                        "list_entry": entry,
                        "match_type": "fuzzy",
                        "match_score": score,
                    }
                )
    return alerts


def _decide_disposition(severity: str, queue_next: list[str], idx: int) -> tuple[str, str]:
    """Return (event, disposition) for a case based on severity and queue config."""
    if severity in ("high", "critical"):
        filing_queues = [q for q in queue_next if "str" in q or "sar" in q or "filing" in q]
        if filing_queues:
            return "escalated_to_str", filing_queues[0]
        if queue_next:
            return "escalated", queue_next[0]
        return "closed", "closed_no_action"

    # Medium/low — escalate every 3rd case, close the rest.
    if idx % 3 == 0:
        non_close = [q for q in queue_next if "closed" not in q]
        if non_close:
            return "escalated", non_close[0]
    return "closed", "closed_no_action"


def _simulate_case_resolution(
    spec: AMLSpec,
    case_ids: list[str],
    ledger: AuditLedger,
    as_of: datetime,
) -> None:
    """Walk cases through workflow queues to generate resolution events.

    This simulates an analyst team processing the alert queue so metrics
    like SLA compliance and average resolution time produce real values.
    The simulation uses deterministic timing based on case index.
    """
    from aml_framework.generators.sql import parse_window

    queue_map = {q.id: q for q in spec.workflow.queues}

    for idx, case_id in enumerate(case_ids):
        case_path = ledger.run_dir / "cases" / f"{case_id}.json"
        if not case_path.exists():
            continue
        case = json.loads(case_path.read_bytes())
        current_queue = case.get("queue", "")
        queue_obj = queue_map.get(current_queue)
        if not queue_obj:
            continue

        # Parse SLA to get hours for timing.
        sla_td = parse_window(queue_obj.sla)
        sla_hours = sla_td.total_seconds() / 3600

        # Deterministic resolution: most cases resolve within SLA,
        # a few (every 5th) take longer to create realistic SLA metrics.
        if idx % 5 == 4:
            resolution_hours = sla_hours * 1.3  # Over SLA
        else:
            resolution_hours = sla_hours * (0.3 + (idx % 4) * 0.15)

        resolved_at = as_of + _timedelta(hours=resolution_hours)

        severity = case.get("severity", "medium")
        event, disposition = _decide_disposition(severity, queue_obj.next or [], idx)

        # Record the resolution decision. `ts` is derived from `as_of` so the
        # decisions_hash is deterministic for a given (spec, data, as_of).
        ledger.append_decision(
            {
                "event": event,
                "case_id": case_id,
                "rule_id": case.get("rule_id", ""),
                "queue": current_queue,
                "disposition": disposition,
                "resolution_hours": round(resolution_hours, 2),
                "within_sla": resolution_hours <= sla_hours,
            },
            ts=resolved_at,
        )

        # Update case status on disk.
        case["status"] = disposition
        case["resolved_at"] = resolved_at.isoformat()
        case["resolution_hours"] = round(resolution_hours, 2)
        case_path.write_bytes(
            json.dumps(case, indent=2, sort_keys=True, default=str).encode("utf-8")
        )


def run_spec(
    spec: AMLSpec,
    spec_path: Path,
    data: dict[str, list[dict[str, Any]]],
    as_of: datetime,
    artifacts_root: Path,
) -> RunResult:
    """Execute every active rule, persist alerts + cases + audit ledger."""
    ledger = AuditLedger.create(
        artifacts_root=artifacts_root,
        spec_path=spec_path,
        spec_hash=spec_content_hash(spec_path),
        as_of=as_of,
    )

    for contract_id, rows in data.items():
        ledger.record_input(contract_id, rows)

    con = duckdb.connect(":memory:")
    _harden_duckdb(con)
    _build_warehouse(con, spec, data)

    alerts_by_rule: dict[str, list[dict[str, Any]]] = {}
    case_ids: list[str] = []

    for rule in spec.rules:
        if rule.status != "active":
            continue

        # --- python_ref: dynamically load and call the scorer ---
        if rule.logic.type == "python_ref":
            module_path, func_name = rule.logic.callable.split(":")
            allowed = _allowed_python_ref_prefixes()
            if not any(module_path == p.rstrip(".") or module_path.startswith(p) for p in allowed):
                raise ValueError(
                    f"python_ref module '{module_path}' is not under an allowed prefix "
                    f"({', '.join(allowed)}). Set AML_PYTHON_REF_PREFIX to extend."
                )
            mod = importlib.import_module(module_path)
            scorer = getattr(mod, func_name)
            ledger.record_rule_sql(
                rule.id,
                f"-- rule '{rule.id}' executed via python_ref\n"
                f"-- callable: {rule.logic.callable}\n"
                f"-- model_id: {rule.logic.model_id}\n"
                f"-- model_version: {rule.logic.model_version}\n",
            )
            alerts = scorer(con, as_of)
            alerts_by_rule[rule.id] = alerts
            ledger.record_alerts(rule.id, alerts)
            _open_cases_for_alerts(rule, alerts, spec, ledger, case_ids)
            continue

        # --- list_match: screen against a reference list ---
        if rule.logic.type == "list_match":
            alerts = _execute_list_match(rule, con, as_of)
            alerts_by_rule[rule.id] = alerts
            ledger.record_rule_sql(
                rule.id,
                f"-- rule '{rule.id}' executed via list_match\n"
                f"-- list: {rule.logic.list}\n"
                f"-- field: {rule.logic.field}\n"
                f"-- match: {rule.logic.match}\n",
            )
            ledger.record_alerts(rule.id, alerts)
            _open_cases_for_alerts(rule, alerts, spec, ledger, case_ids)
            continue

        if rule.logic.type not in ("aggregation_window", "custom_sql"):
            # pragma: no cover — not executable in reference engine.
            ledger.record_rule_sql(
                rule.id,
                f"-- rule '{rule.id}' logic type '{rule.logic.type}' "
                f"is not executable in the reference engine.\n",
            )
            alerts_by_rule[rule.id] = []
            ledger.record_alerts(rule.id, [])
            continue

        source_table = rule.logic.source if hasattr(rule.logic, "source") else ""
        sql = compile_rule_sql(rule, as_of=as_of, source_table=source_table)
        ledger.record_rule_sql(rule.id, sql)

        rows = con.execute(sql).fetchall()
        cols = [d[0] for d in con.description] if con.description else []
        alerts = [dict(zip(cols, r)) for r in rows]
        alerts_by_rule[rule.id] = alerts
        ledger.record_alerts(rule.id, alerts)

        _open_cases_for_alerts(rule, alerts, spec, ledger, case_ids)

    # --- Simulate case resolution ---
    # Walk each case through the workflow queues to generate realistic
    # decision events, resolution times, and SLA compliance data.
    _simulate_case_resolution(spec, case_ids, ledger, as_of)

    return _finalize_run(spec, ledger, alerts_by_rule, case_ids, data)


def _finalize_run(
    spec: AMLSpec,
    ledger: AuditLedger,
    alerts_by_rule: dict[str, list[dict[str, Any]]],
    case_ids: list[str],
    data: dict[str, list[dict[str, Any]]],
) -> RunResult:
    """Evaluate metrics, render reports, and write the final manifest."""
    cases_rows: list[dict[str, Any]] = []
    for case_file in sorted((ledger.run_dir / "cases").glob("*.json")):
        cases_rows.append(json.loads(case_file.read_bytes()))
    decisions_rows: list[dict[str, Any]] = []
    decisions_path = ledger.run_dir / "decisions.jsonl"
    if decisions_path.exists():
        for line in decisions_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                decisions_rows.append(json.loads(line))

    metric_results = evaluate_metrics(
        spec=spec,
        alerts=alerts_by_rule,
        cases=cases_rows,
        decisions=decisions_rows,
        data=data,
    )
    metrics_dir = ledger.run_dir / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    (metrics_dir / "metrics.json").write_bytes(
        json.dumps([m.to_dict() for m in metric_results], indent=2, sort_keys=True).encode("utf-8")
    )

    reports = render_all_reports(spec, metric_results)
    reports_dir = ledger.run_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    for report_id, markdown in reports.items():
        (reports_dir / f"{report_id}.md").write_text(markdown, encoding="utf-8")

    manifest = ledger.finalize()
    manifest["metrics"] = [m.to_dict() for m in metric_results]
    manifest["reports"] = sorted(reports.keys())
    (ledger.run_dir / "manifest.json").write_bytes(
        json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    )
    return RunResult(
        manifest=manifest,
        alerts=alerts_by_rule,
        case_ids=case_ids,
        metrics=metric_results,
        reports=reports,
    )
