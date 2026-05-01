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

from aml_framework.engine.audit import AuditLedger, rule_version_hash
from aml_framework.engine.constants import Event, Queue
from aml_framework.engine.entity_resolution import resolve_entities
from aml_framework.engine.freshness import scan_contract_freshness
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


class ContractViolation(Exception):
    """Input data does not satisfy a `data_contract`'s required-column constraints.

    Raised by `_build_warehouse` when a non-nullable contract column is
    missing from input data (i.e. the engine cannot fire any rule that
    depends on that column). Callers in `run_spec` catch this, emit a
    `contract_violation` event to the audit ledger, and re-raise so the
    CLI exits non-zero.

    This is the engine-side enforcement of the data-contract claim in the
    "Data is the AML problem" whitepaper (DATA-1): the validator fails
    closed, rather than firing a rule against NULLs and producing
    misleading-zero alerts.
    """

    def __init__(self, contract_id: str, missing_columns: list[str], detail: str = ""):
        self.contract_id = contract_id
        self.missing_columns = sorted(missing_columns)
        msg = (
            f"contract '{contract_id}' violation: required column(s) "
            f"{self.missing_columns} missing from input data"
        )
        if detail:
            msg = f"{msg}. {detail}"
        super().__init__(msg)


def _build_warehouse(
    con: duckdb.DuckDBPyConnection,
    spec: AMLSpec,
    data: dict[str, list[dict[str, Any]]],
) -> None:
    """Register each data_contract as a DuckDB table called `<id>`.

    The physical table name used in the engine is the contract id, not the
    `source` string — that keeps the reference engine independent of the
    institution's warehouse layout.

    Fail-closed semantics: if any non-nullable contract column is absent
    from the input rows for that contract, raise `ContractViolation`. This
    runs *before* DuckDB's NOT NULL constraint would fire, so the error
    message names the contract + missing columns rather than surfacing a
    raw "Constraint Error" from the driver.
    """
    for contract in spec.data_contracts:
        rows = data.get(contract.id, [])
        if not rows:
            con.execute(f"CREATE TABLE {contract.id} AS SELECT NULL WHERE 1=0")
            continue
        # Pre-flight: every non-nullable column declared in the contract
        # must be present as a key in the input rows. Sample the first row
        # — input data is uniform within a single contract by convention
        # (every row has the same keys, even if values are None).
        required = [c.name for c in contract.columns if not c.nullable]
        sample_keys = set(rows[0].keys())
        missing = [c for c in required if c not in sample_keys]
        if missing:
            raise ContractViolation(
                contract_id=contract.id,
                missing_columns=missing,
                detail=(
                    f"input rows expose columns {sorted(sample_keys)}; "
                    f"contract requires {sorted(required)}"
                ),
            )
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
        # Drop None-valued fields (e.g. unresolved `url`) so downstream
        # consumers expecting dict[str, str] don't choke. Round-7 #1
        # added the optional `url` field; pre-Round-7 narrative models
        # don't tolerate None values.
        "regulation_refs": [
            {k: v for k, v in r.model_dump().items() if v is not None} for r in rule.regulation_refs
        ],
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
    rule_version = rule_version_hash(rule)
    for alert in alerts:
        case = _build_case(rule, alert, spec, ledger.input_manifest)
        ledger.record_case(case["case_id"], case)
        case_ids.append(case["case_id"])
        # PR-DATA-4: stamp rule_version on every case-opened decision so a
        # 2LoD reviewer can answer "which version of this rule fired?" by
        # reading the ledger alone — no spec-snapshot diff required.
        ledger.append_decision(
            {
                "event": Event.CASE_OPENED,
                "case_id": case["case_id"],
                "rule_id": rule.id,
                "rule_version": rule_version,
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

    from aml_framework.paths import REFERENCE_LISTS_DIR

    list_path = REFERENCE_LISTS_DIR / f"{list_name}.csv"
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


def _execute_network_pattern(
    rule: Rule,
    con: duckdb.DuckDBPyConnection,
    as_of: datetime,
) -> list[dict[str, Any]]:
    """Walk `resolved_entity_link` to find customers whose ego-network
    satisfies a `having` condition.

    Patterns supported in v1:
    - `component_size`: count of distinct customers reachable within
      `max_hops` (including self). Catches mule herds and nested-account
      rings.
    - `common_counterparty`: count of distinct linking attributes shared
      with neighbours. High value = the entity is sharing many of phone /
      email / device / address with others — classic synthetic-identity
      pattern.
    """
    logic = rule.logic
    max_hops = int(logic.max_hops or 2)
    having = logic.having or {}

    # Recursive CTE walks the link table up to max_hops away from each seed.
    # DuckDB recursive CTE syntax: WITH RECURSIVE walk(...) AS (base UNION ALL step)
    walk_sql = f"""
    WITH RECURSIVE walk(seed_id, reached_id, hops) AS (
        SELECT customer_id AS seed_id,
               customer_id AS reached_id,
               0           AS hops
        FROM customer
        UNION ALL
        SELECT w.seed_id,
               CASE WHEN l.left_customer_id = w.reached_id
                    THEN l.right_customer_id
                    ELSE l.left_customer_id END AS reached_id,
               w.hops + 1
        FROM walk w
        JOIN resolved_entity_link l
          ON w.reached_id IN (l.left_customer_id, l.right_customer_id)
        WHERE w.hops < {max_hops}
    )
    SELECT seed_id AS customer_id,
           COUNT(DISTINCT reached_id)        AS component_size,
           COUNT(DISTINCT
                 CASE WHEN reached_id != seed_id THEN reached_id END
                ) AS counterparty_count
    FROM walk
    GROUP BY seed_id
    """
    try:
        rows = con.execute(walk_sql).fetchall()
        cols = [d[0] for d in con.description] if con.description else []
    except Exception as e:
        logger.warning("network_pattern '%s' failed: %s", rule.id, e)
        return []

    alerts: list[dict[str, Any]] = []
    for row in rows:
        record = dict(zip(cols, row))
        # Apply the having condition. Supports {gte, lte, gt, lt, eq}.
        passes = True
        for metric, cond in having.items():
            value = record.get(metric)
            if value is None:
                passes = False
                break
            if isinstance(cond, dict):
                for op, arg in cond.items():
                    if op == "gte" and not value >= arg:
                        passes = False
                    elif op == "lte" and not value <= arg:
                        passes = False
                    elif op == "gt" and not value > arg:
                        passes = False
                    elif op == "lt" and not value < arg:
                        passes = False
                    elif op == "eq" and not value == arg:
                        passes = False
                    if not passes:
                        break
            else:
                if value != cond:
                    passes = False
            if not passes:
                break
        if passes:
            subgraph = _capture_subgraph(con, record["customer_id"], max_hops)
            alerts.append(
                {
                    "rule_id": rule.id,
                    "customer_id": record["customer_id"],
                    "component_size": record["component_size"],
                    "counterparty_count": record["counterparty_count"],
                    "max_hops": max_hops,
                    "pattern": logic.pattern,
                    "window_start": as_of,
                    "window_end": as_of,
                    "subgraph": subgraph,
                }
            )
    return alerts


def _capture_subgraph(
    con: duckdb.DuckDBPyConnection,
    seed_id: str,
    max_hops: int,
) -> dict[str, Any]:
    """Re-walk the link table for one seed and return the matched subgraph.

    Returns nodes (deduped, with hop distance), edges (linking attribute +
    weight), and a `topology_hash` — SHA-256 over the canonicalised
    edge list so two alerts on the same subgraph share the same hash
    even if they fire from different seeds. The hash lets the dashboard
    cluster duplicate detections without re-rendering.

    The reachability walk runs again because we discarded per-edge
    attribution in the aggregation phase. Cost is bounded: max_hops ≤ 5
    by the spec's pydantic constraint, and each call is O(degree^max_hops)
    on the link graph — fine for the alert sample, never run on the
    whole dataset.
    """
    import hashlib
    import json as _json

    # Walk that *carries the linking edge* (left_id, right_id, attr) so
    # we can render the actual subgraph rather than just node sets.
    edge_walk_sql = f"""
    WITH RECURSIVE walk(seed_id, reached_id, hops, path_edges) AS (
        SELECT customer_id AS seed_id,
               customer_id AS reached_id,
               0           AS hops,
               '[]'        AS path_edges
        FROM customer
        WHERE customer_id = ?
        UNION ALL
        SELECT w.seed_id,
               CASE WHEN l.left_customer_id = w.reached_id
                    THEN l.right_customer_id
                    ELSE l.left_customer_id END AS reached_id,
               w.hops + 1,
               CONCAT(
                   w.path_edges, '|',
                   l.left_customer_id, '->', l.right_customer_id,
                   ':', COALESCE(l.attribute, '?')
               )
        FROM walk w
        JOIN resolved_entity_link l
          ON w.reached_id IN (l.left_customer_id, l.right_customer_id)
        WHERE w.hops < {max_hops}
    )
    SELECT seed_id, reached_id, hops, path_edges
    FROM walk
    """
    try:
        rows = con.execute(edge_walk_sql, [seed_id]).fetchall()
        cols = [d[0] for d in con.description] if con.description else []
    except Exception as e:
        logger.warning("subgraph capture failed for seed '%s': %s", seed_id, e)
        return {"seed": seed_id, "nodes": [{"id": seed_id, "hops": 0}], "edges": []}

    walk_rows = [dict(zip(cols, r)) for r in rows]

    # Nodes: dedup by reached_id, keep min hops.
    node_hops: dict[str, int] = {}
    for r in walk_rows:
        nid = r["reached_id"]
        h = int(r["hops"])
        if nid not in node_hops or h < node_hops[nid]:
            node_hops[nid] = h
    nodes = [{"id": nid, "hops": h} for nid, h in sorted(node_hops.items())]

    # Edges: pull the unique link rows that touch any node in the subgraph.
    node_ids = list(node_hops.keys())
    edges: list[dict[str, Any]] = []
    if node_ids:
        # Query links where both endpoints are in the discovered subgraph.
        placeholders = ", ".join(["?"] * len(node_ids))
        edge_sql = f"""
        SELECT left_customer_id, right_customer_id, attribute, weight
        FROM resolved_entity_link
        WHERE left_customer_id IN ({placeholders})
          AND right_customer_id IN ({placeholders})
        """
        try:
            erows = con.execute(edge_sql, node_ids + node_ids).fetchall()
            ecols = [d[0] for d in con.description] if con.description else []
        except Exception as e:
            logger.warning("edge query failed for subgraph '%s': %s", seed_id, e)
            erows, ecols = [], []
        seen: set[tuple] = set()
        for er in erows:
            row = dict(zip(ecols, er))
            l_id = row["left_customer_id"]
            r_id = row["right_customer_id"]
            # Canonicalise direction so (A,B) and (B,A) are deduped.
            key = tuple(sorted([l_id, r_id])) + (row.get("attribute"),)
            if key in seen:
                continue
            seen.add(key)
            edges.append(
                {
                    "source": l_id,
                    "target": r_id,
                    "attribute": row.get("attribute") or "",
                    "weight": float(row.get("weight") or 1.0),
                }
            )

    # Stable topology hash: sort edges canonically and hash.
    canonical = sorted(
        (tuple(sorted([e["source"], e["target"]])) + (e["attribute"],) for e in edges)
    )
    topology_hash = hashlib.sha256(
        _json.dumps(canonical, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()

    return {
        "seed": seed_id,
        "max_hops": max_hops,
        "nodes": nodes,
        "edges": edges,
        "topology_hash": topology_hash,
    }


def _decide_disposition(severity: str, queue_next: list[str], idx: int) -> tuple[str, str]:
    """Return (event, disposition) for a case based on severity and queue config."""
    if severity in ("high", "critical"):
        filing_queues = [q for q in queue_next if "str" in q or "sar" in q or "filing" in q]
        if filing_queues:
            return Event.ESCALATED_TO_STR, filing_queues[0]
        if queue_next:
            return Event.ESCALATED, queue_next[0]
        return Event.CLOSED, Queue.CLOSED_NO_ACTION

    # Medium/low — escalate every 3rd case, close the rest.
    if idx % 3 == 0:
        non_close = [q for q in queue_next if "closed" not in q]
        if non_close:
            return Event.ESCALATED, non_close[0]
    return Event.CLOSED, Queue.CLOSED_NO_ACTION


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
    try:
        _build_warehouse(con, spec, data)
    except ContractViolation as exc:
        # DATA-1 whitepaper claim: the validator fails closed. Emit a
        # decision-ledger event so the run dir documents *why* the engine
        # refused to fire any rule, then re-raise so the CLI exits non-zero.
        ledger.append_decision(
            {
                "event": "contract_violation",
                "contract_id": exc.contract_id,
                "missing_columns": exc.missing_columns,
                "detail": str(exc),
            }
        )
        raise

    # DATA-2 whitepaper claim: per-attribute freshness pinning. After
    # warehouse build, scan each contract for rows whose
    # `last_refreshed_at_column` is older than `max_staleness_days`.
    # Emit one `pkyc_trigger` event per violation. The run continues
    # — staleness is informational, not blocking — but the events land
    # in `decisions.jsonl` so the audit trail names what was stale, when.
    for contract in spec.data_contracts:
        rows = data.get(contract.id, [])
        violations = scan_contract_freshness(contract, rows, as_of)
        for v in violations:
            ledger.append_decision(v.to_event())

    resolve_entities(con, spec)

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
                # Spec-level violation — fail fast, this isn't a runtime fault.
                raise ValueError(
                    f"python_ref module '{module_path}' is not under an allowed prefix "
                    f"({', '.join(allowed)}). Set AML_PYTHON_REF_PREFIX to extend."
                )
            ledger.record_rule_sql(
                rule.id,
                f"-- rule '{rule.id}' executed via python_ref\n"
                f"-- callable: {rule.logic.callable}\n"
                f"-- model_id: {rule.logic.model_id}\n"
                f"-- model_version: {rule.logic.model_version}\n",
            )
            try:
                mod = importlib.import_module(module_path)
                scorer = getattr(mod, func_name)
                alerts = scorer(con, as_of)
            except Exception as exc:
                # A scorer that raises (missing module, missing attr, runtime
                # error inside the model) must not abort the whole run — that
                # would leave the audit ledger half-written. Log, record zero
                # alerts, emit a rule_failed event, continue.
                logger.exception(
                    "python_ref rule '%s' failed: %s — recording zero alerts",
                    rule.id,
                    exc,
                )
                alerts = []
                alerts_by_rule[rule.id] = alerts
                ledger.record_alerts(rule.id, alerts)
                ledger.append_decision(
                    {
                        "event": Event.RULE_FAILED,
                        "rule_id": rule.id,
                        "logic_type": "python_ref",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                continue
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

        # --- network_pattern: walk resolved_entity_link via recursive CTE ---
        if rule.logic.type == "network_pattern":
            alerts = _execute_network_pattern(rule, con, as_of)
            alerts_by_rule[rule.id] = alerts
            ledger.record_rule_sql(
                rule.id,
                f"-- rule '{rule.id}' executed via network_pattern\n"
                f"-- pattern: {rule.logic.pattern}\n"
                f"-- max_hops: {rule.logic.max_hops}\n"
                f"-- having: {rule.logic.having}\n",
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
    # All writes complete — snapshot files become read-only on POSIX.
    ledger.freeze()
    return RunResult(
        manifest=manifest,
        alerts=alerts_by_rule,
        case_ids=case_ids,
        metrics=metric_results,
        reports=reports,
    )
