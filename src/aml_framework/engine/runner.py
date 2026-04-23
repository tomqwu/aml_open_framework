"""Execute spec rules against an in-memory DuckDB warehouse."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb

from aml_framework.engine.audit import AuditLedger
from aml_framework.generators.sql import compile_rule_sql
from aml_framework.spec.loader import spec_content_hash
from aml_framework.spec.models import AMLSpec, Rule


@dataclass
class RunResult:
    manifest: dict[str, Any]
    alerts: dict[str, list[dict[str, Any]]]
    case_ids: list[str] = field(default_factory=list)

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
        cols = ", ".join(rows[0].keys())
        placeholders = ", ".join(["?"] * len(rows[0]))
        con.execute(f"CREATE TABLE {contract.id} ({_ddl_for_contract(contract)})")
        con.executemany(
            f"INSERT INTO {contract.id} ({cols}) VALUES ({placeholders})",
            [tuple(r.values()) for r in rows],
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


def _build_case(rule: Rule, alert: dict[str, Any], spec: AMLSpec, input_hash: dict[str, Any]) -> dict[str, Any]:
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
    _build_warehouse(con, spec, data)

    alerts_by_rule: dict[str, list[dict[str, Any]]] = {}
    case_ids: list[str] = []

    for rule in spec.rules:
        if rule.status != "active":
            continue
        if rule.logic.type not in ("aggregation_window", "custom_sql"):
            # Parseable but not executable in the reference slice.
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

        for alert in alerts:
            case = _build_case(rule, alert, spec, ledger.input_manifest)
            ledger.record_case(case["case_id"], case)
            case_ids.append(case["case_id"])
            ledger.append_decision({
                "event": "case_opened",
                "case_id": case["case_id"],
                "rule_id": rule.id,
                "queue": rule.escalate_to,
            })

    manifest = ledger.finalize()
    return RunResult(manifest=manifest, alerts=alerts_by_rule, case_ids=case_ids)
