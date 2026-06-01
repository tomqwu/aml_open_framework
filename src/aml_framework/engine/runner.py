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

from aml_framework import __version__ as ENGINE_VERSION
from aml_framework.engine.audit import AuditLedger, rule_version_hash
from aml_framework.engine.constants import Event, Queue
from aml_framework.engine.cost_volume import (
    CostVolumeTimer,
    build_report as build_cost_volume_report,
    summarise_tables,
    write_report as write_cost_volume_report,
)
from aml_framework.engine.defect_log import build_defect_log, derive_run_id, write_defect_log
from aml_framework.engine.dq import DQException, evaluate_contract_checks
from aml_framework.engine.entity_resolution import resolve_entities
from aml_framework.engine.freshness import scan_contract_freshness
from aml_framework.engine.lineage import FieldLineageEntry, derive_field_lineage
from aml_framework.engine.monitoring_digest import (
    build_monitoring_digest,
    lookup_prior_run,
    write_monitoring_digest,
)
from aml_framework.engine.payload_meta import stamp_payload_meta
from aml_framework.engine.promotion import (
    EnvironmentGatingError,
    is_rule_approved_for_environment,
    promotion_audit_event,
)
from aml_framework.engine.reconciliation import (
    build_reconciliation_report,
    write_reconciliation_report,
)
from aml_framework.engine.sla import SLAReport, evaluate_sla
from aml_framework.generators.sql import _compile_filter, compile_rule_sql
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


def _is_strict_python_ref(strict_python_ref: bool | None = None) -> bool:
    """Determine whether python_ref failures should abort the run.

    Resolution order:
    1. Explicit parameter (via CLI or programmatic call)
    2. AML_STRICT_PYTHON_REF environment variable ("0" → permissive)
    3. Default: strict (True)
    """
    if strict_python_ref is not None:
        return strict_python_ref
    env = os.environ.get("AML_STRICT_PYTHON_REF", "1").strip()
    return env != "0"


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
    # PR-PAY-1: spec-derived `rule_version_hash(rule)` — same value the
    # audit ledger stamps on `case_opened` decisions. Surfaced at the
    # case level so the dashboard's "Why this fired" panel reads it
    # without a ledger round-trip.
    rule_version: str
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
    python_ref_failures: dict[str, str] = field(default_factory=dict)

    @property
    def total_alerts(self) -> int:
        return sum(len(v) for v in self.alerts.values())


class PythonRefFailure(Exception):
    """A python_ref scorer failed at execution time.

    In strict mode (default), the engine aborts the run rather than
    silently recording zero alerts.  The audit ledger still captures the
    failure event before the exception propagates.
    """

    def __init__(
        self,
        rule_id: str,
        module_path: str,
        func_name: str,
        message: str = "",
    ):
        self.rule_id = rule_id
        self.module_path = module_path
        self.func_name = func_name
        super().__init__(message or f"python_ref scorer failed for rule '{rule_id}'")


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
        # PR-PAY-1: surface the spec-derived rule_version_hash at the
        # case level so the Case Investigation 'Why this fired' panel
        # can render it without a ledger round-trip. Same hash the audit
        # ledger stamps on `case_opened` decision events
        # (_open_cases_for_alerts below) — pinned by
        # `test_rule_version_stamped_matches_audit_hash`. Lives on the
        # case (not the alert) so alert hashes stay invariant under
        # spec-metadata-only changes such as `evaluation_mode:
        # streaming`, per `test_engine_runs_batch_regardless_of_field`.
        "rule_version": rule_version_hash(rule),
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


def _load_reference_list(list_name: str) -> tuple[list[str], str] | None:
    """Load a reference list CSV, returning `(names+aliases, version)` or None.

    PR-PAY-1 codex pass-5 race fix: the bytes used to build the matcher
    are also the bytes hashed for the alert payload's
    `reference_data_version`. That removes the original two-read race
    (a sanctions-list refresh between the screening read and the
    digest re-read would otherwise produce an alert that cites a
    different list snapshot than the one it was actually matched
    against).
    """
    import csv
    import io

    from aml_framework.engine.payload_meta import reference_data_version_from_bytes
    from aml_framework.paths import REFERENCE_LISTS_DIR

    list_path = REFERENCE_LISTS_DIR / f"{list_name}.csv"
    if not list_path.exists():
        return None
    raw = list_path.read_bytes()
    version = reference_data_version_from_bytes(list_name, raw)
    names: list[str] = []
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
    for row in reader:
        name = row.get("name", "").strip().upper()
        if name:
            names.append(name)
        # #209: include aliases in the matchable set so alias-only
        # entries can trigger list_match while the canonical name
        # and list_id survive in the alert payload.
        aliases_raw = row.get("aliases", "")
        if aliases_raw:
            for alias in aliases_raw.split("|"):
                alias = alias.strip().upper()
                if alias and alias not in names:
                    names.append(alias)
    return names, version


def _execute_list_match(
    rule: Rule,
    con: duckdb.DuckDBPyConnection,
    as_of: datetime,
    cost_timer: CostVolumeTimer | None = None,
) -> list[dict[str, Any]]:
    """Screen a data source field against a reference list (sanctions, PEP, etc.).

    The companion `_execute_list_match_with_version` returns the same
    alerts AND the content fingerprint of the bytes that drove the
    match, so the runner can stamp a race-free `reference_data_version`
    on the alert payload. This thin wrapper preserves the
    previous public signature for older callers (unit tests, the
    `_execute_list_match` import in tests/test_engine.py) that only
    care about the alerts list.
    """
    alerts, _version = _execute_list_match_with_version(rule, con, as_of, cost_timer)
    return alerts


def _execute_list_match_with_version(
    rule: Rule,
    con: duckdb.DuckDBPyConnection,
    as_of: datetime,
    cost_timer: CostVolumeTimer | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Same as `_execute_list_match` but also returns the version of the
    reference list bytes that were actually matched against.

    Returns `(alerts, version)` where `version` is `None` when the
    reference list was missing (alerts is also empty in that case).
    Used by `run_spec` to pin the `reference_data_version` stamped on
    each alert to the exact bytes the matcher saw, eliminating the
    race window codex pass-5 flagged on the two-read original.
    """
    logic = rule.logic
    list_name = logic.list
    field = logic.field
    match_type = logic.match
    # Default only on None (omitted in spec); honour an explicit 0.0
    # because the spec YAML is the source of truth — silently rewriting
    # a schema-valid value would lie about what fired. Mirror of
    # `payload_meta.alert_threshold_snapshot` so the alert payload and
    # the executor agree on the effective threshold.
    from aml_framework.engine.payload_meta import DEFAULT_FUZZY_THRESHOLD

    threshold = DEFAULT_FUZZY_THRESHOLD if logic.threshold is None else logic.threshold

    loaded = _load_reference_list(list_name)
    if loaded is None:
        return [], None
    list_entries, list_version = loaded

    # Get source data — pull rowid alongside so each alert can carry
    # `matched_row_ids` (PR-LIN-4) for the dashboard's "show me which
    # rows fired this" affordance.
    source_table = logic.source
    try:
        rows = con.execute(f"SELECT rowid AS __row_id, * FROM {source_table}").fetchall()
        if cost_timer is not None:
            cost_timer.increment_queries()
        cols = [d[0] for d in con.description] if con.description else []
    except Exception:
        logger.warning("list_match: table '%s' not found for rule '%s'", source_table, rule.id)
        return [], list_version

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
        row_id = row.get("__row_id")
        matched_row_ids = [int(row_id)] if row_id is not None else []

        if match_type == "exact" and value in list_entries:
            alerts.append(
                {
                    **base_alert,
                    "customer_id": customer_id,
                    "matched_name": value,
                    "match_type": "exact",
                    "match_score": 1.0,
                    "matched_row_ids": matched_row_ids,
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
                        "matched_row_ids": matched_row_ids,
                    }
                )
    return alerts, list_version


def _execute_network_pattern(
    rule: Rule,
    con: duckdb.DuckDBPyConnection,
    as_of: datetime,
    cost_timer: CostVolumeTimer | None = None,
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
        if cost_timer is not None:
            cost_timer.increment_queries()
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
            subgraph = _capture_subgraph(con, record["customer_id"], max_hops, cost_timer)
            # PR-LIN-4: matched_row_ids for network_pattern is the
            # customer-table rowid of every entity in the reached
            # subgraph (the "evidence" rows for component_size /
            # counterparty_count). Empty list rather than None when
            # the lookup fails so callers don't need a special case.
            customer_ids = [n["id"] for n in subgraph.get("nodes", [])]
            matched_row_ids: list[int] = []
            if customer_ids:
                try:
                    placeholders = ",".join(["?"] * len(customer_ids))
                    rid_rows = con.execute(
                        f"SELECT rowid FROM customer WHERE customer_id IN ({placeholders})",
                        customer_ids,
                    ).fetchall()
                    if cost_timer is not None:
                        cost_timer.increment_queries()
                    matched_row_ids = [int(r[0]) for r in rid_rows]
                except Exception:
                    matched_row_ids = []
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
                    "matched_row_ids": matched_row_ids,
                }
            )
    return alerts


def _capture_subgraph(
    con: duckdb.DuckDBPyConnection,
    seed_id: str,
    max_hops: int,
    cost_timer: CostVolumeTimer | None = None,
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
        if cost_timer is not None:
            cost_timer.increment_queries()
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
            if cost_timer is not None:
                cost_timer.increment_queries()
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
    # PR-LIN-3: precompute rule_version per rule_id so resolution events
    # carry the same `rule_version` that case_opened events do. Lets
    # walk_lineage answer "did this case escalate under the same rule
    # version it opened under?" — relevant when a spec edit lands
    # mid-investigation.
    rule_version_by_id = {r.id: rule_version_hash(r) for r in spec.rules}

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
        rule_id = case.get("rule_id", "")
        ledger.append_decision(
            {
                "event": event,
                "case_id": case_id,
                "rule_id": rule_id,
                "rule_version": rule_version_by_id.get(rule_id),
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


def _maybe_mask_dq_exception(exc: DQException, ledger: AuditLedger) -> DQException:
    """Return a copy of `exc` with `failing_value` PII-masked if applicable.

    `_mask_alert` masks alert payload fields by key name. Here the
    sensitive content lives under a generic `failing_value` field on the
    DQ exception, so the standard masker can't help — we look up the
    *source column* on the contract and, when it's a `pii: true` column
    and masking is enabled (`ledger.pii_columns` is non-empty), hash
    the failing_value with the run's PII salt. Same HMAC-SHA256 / 16-hex
    posture as `_pii_mask_value`, so a PII-aware reader can dedupe
    across alert + DQ artifacts.

    Issue #369 — codex review pass 3.
    """
    if not ledger.pii_columns or exc.column not in ledger.pii_columns:
        return exc
    if exc.failing_value is None:
        return exc
    from aml_framework.engine.audit import _pii_mask_value

    return exc.model_copy(
        update={"failing_value": _pii_mask_value(exc.failing_value, ledger.pii_salt)}
    )


def _write_dq_exceptions(run_dir: Path, exceptions: list[DQException]) -> None:
    """Persist DQ exceptions as one JSON object per line under the run dir.

    Always writes the file, even when `exceptions` is empty, so downstream
    consumers (exporters, dashboard surfacers in a follow-up PR) can rely
    on the artifact's existence rather than guarding on `exists()`. Stdlib
    `json` only — no new dependency. Per-line ordering follows
    `evaluate_contract_checks`'s deterministic order so the JSONL diff is
    stable across re-runs.
    """
    path = run_dir / "dq_exceptions.jsonl"
    if not exceptions:
        path.write_bytes(b"")
        return
    lines = [
        json.dumps(exc.model_dump(mode="json"), sort_keys=True, default=str).encode("utf-8")
        for exc in exceptions
    ]
    path.write_bytes(b"\n".join(lines) + b"\n")


def _write_sla_report(run_dir: Path, report: SLAReport) -> None:
    """Persist the Pillar-6 SLA-monitor report as `sla_report.json`.

    Always writes the file (possibly an empty / disabled report) so
    downstream consumers — audit-bundle exporter, dashboard follow-up
    surface — can rely on its presence rather than guarding on
    `exists()`. Same audit-integrity posture as `dq_exceptions.jsonl`
    and `field_lineage.jsonl`. JSON shape is byte-stable
    (`sort_keys=True`) so the run reproducibility contract holds:
    same spec + same data + same as_of = identical artifact hash.
    """
    path = run_dir / "sla_report.json"
    payload = report.model_dump(mode="json")
    path.write_bytes(json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8"))


def _write_defect_log_snapshot(
    ledger: AuditLedger,
    *,
    dq_exceptions: list[DQException],
    python_ref_failures: dict[str, str],
) -> None:
    """Emit `defect_log.jsonl` from the current accumulator state.

    Single canonical writer used by `run_spec`, the strict-mode
    python_ref abort, and `_finalize_run`. Centralising the call
    keeps the `derive_run_id` argument tuple (spec_content_hash,
    as_of, input_manifest) in one place — codex pass-3 P2 on PR-C1.
    """
    defects = build_defect_log(
        run_id=derive_run_id(
            ledger.spec_content_hash,
            ledger.as_of,
            ledger.input_manifest,
        ),
        dq_exceptions=dq_exceptions,
        python_ref_failures=python_ref_failures,
        created_at=ledger.as_of,
    )
    write_defect_log(ledger.run_dir, defects)


def _write_field_lineage(run_dir: Path, entries: list[FieldLineageEntry]) -> None:
    """Persist field lineage entries as one JSON object per line under the run dir.

    Always writes the file, even when `entries` is empty (e.g. an empty
    spec), so downstream consumers can rely on its presence rather than
    guarding on `exists()` — same audit-integrity posture as
    `dq_exceptions.jsonl`. Ordering is deterministic (set by
    `derive_field_lineage`) so the JSONL diff is byte-stable across
    re-runs — required for the run reproducibility contract.
    """
    path = run_dir / "field_lineage.jsonl"
    if not entries:
        path.write_bytes(b"")
        return
    lines = [
        json.dumps(entry.model_dump(mode="json"), sort_keys=True, default=str).encode("utf-8")
        for entry in entries
    ]
    path.write_bytes(b"\n".join(lines) + b"\n")


def run_spec(
    spec: AMLSpec,
    spec_path: Path,
    data: dict[str, list[dict[str, Any]]],
    as_of: datetime,
    artifacts_root: Path,
    strict_python_ref: bool | None = None,
    data_sources: dict[str, str] | None = None,
) -> RunResult:
    """Execute every active rule, persist alerts + cases + audit ledger.

    `data_sources` (optional) maps contract_id → logical source path so
    the lineage walk-back can answer "this alert came from row N of
    /data/input/txn.csv on snapshot X" rather than just "the txn
    contract". Pass file paths for csv/parquet, connection strings for
    duckdb/snowflake/bigquery, or `"synthetic"` for the in-tree
    generator. None entries are recorded as None — backward-compatible
    with callers (tests, older API surfaces) that don't track source.
    """
    # PR-LF2 (#384) — Pillar-6 run cost + data volume artefact. Timer
    # is created BEFORE the ledger so `wall_clock_seconds` covers the
    # full runner cost, including ledger directory setup and warehouse
    # build. The timer is intentionally non-deterministic (wall clock,
    # memory) — see `engine/cost_volume.py` for the determinism caveat.
    cost_timer = CostVolumeTimer()
    ledger = AuditLedger.create(
        artifacts_root=artifacts_root,
        spec_path=spec_path,
        spec_hash=spec_content_hash(spec_path),
        as_of=as_of,
        spec=spec,
    )

    contract_by_id = {c.id: c for c in spec.data_contracts}
    sources = data_sources or {}
    for contract_id, rows in data.items():
        contract = contract_by_id.get(contract_id)
        schema_columns = [c.name for c in contract.columns] if contract else None
        ledger.record_input(
            contract_id,
            rows,
            source_path=sources.get(contract_id),
            schema_columns=schema_columns,
        )

    # B4 (#369) — Data Quality visibility. MUST run before `_build_warehouse`
    # because DuckDB tables are declared with `NOT NULL` for `nullable: false`
    # columns (see `_build_warehouse` DDL); a not_null check failing on
    # such a column would otherwise crash the warehouse insert before the
    # evaluator ever runs, and no `dq_exception` ledger event would land.
    # Evaluating the raw `data` dict here catches every check on the input
    # rows, regardless of DuckDB constraints. Observability only — no rows
    # are dropped or mutated. Specs are clean by design — most runs produce
    # zero exceptions — but `dq_exceptions.jsonl` is still emitted (possibly
    # empty) so downstream consumers can rely on its presence.
    #
    # PII masking — when `AML_PII_MASKING=1` and the failing column is
    # marked `pii: true` on its contract, the `failing_value` on a
    # `unique` violation would otherwise leak raw plaintext PII
    # (customer_id, email, etc.) into both `decisions.jsonl` and
    # `dq_exceptions.jsonl`. The audit ledger already hashes alert
    # payload PII via `_mask_alert`; mirror that posture here by
    # hashing `failing_value` with the same salt before persisting.
    dq_exceptions: list[DQException] = []
    # PR-B2 (#367): build the FK-lookup map from *declared* contracts only.
    # `data` can carry undeclared tables (the synthetic generator does this
    # for several specs); passing the raw map would let a `foreign_key`
    # check resolve against a parent table the spec doesn't actually
    # declare, silently passing on synthetic/dashboard runs while the
    # same spec correctly fails under CSV sources. Codex review pass 1.
    declared_data: dict[str, list[dict[str, Any]]] = {
        c.id: data.get(c.id, []) for c in spec.data_contracts
    }
    for contract in spec.data_contracts:
        rows = data.get(contract.id, [])
        # `all_data` enables `foreign_key` checks to look up the
        # referenced contract's column values without a DuckDB
        # roundtrip. Every other check ignores it.
        contract_exceptions = evaluate_contract_checks(
            rows,
            contract.quality_checks,
            contract_id=contract.id,
            at=as_of,
            all_data=declared_data,
        )
        for raw_exc in contract_exceptions:
            exc = _maybe_mask_dq_exception(raw_exc, ledger)
            dq_exceptions.append(exc)
            ledger.append_decision(
                {
                    "event": Event.DQ_EXCEPTION,
                    # `queue` is None for DQ events — these are not
                    # queue-routed work items. Included explicitly so the
                    # dashboard's `df_decisions["queue"]` indexer (My Queue
                    # page) finds a column on zero-alert / DQ-only runs.
                    "queue": None,
                    "contract_id": exc.contract_id,
                    "check_id": exc.check_id,
                    "check_type": exc.check_type,
                    "column": exc.column,
                    "failing_value": exc.failing_value,
                    "row_index": exc.row_index,
                    "reason": exc.reason,
                }
            )
    _write_dq_exceptions(ledger.run_dir, dq_exceptions)

    # PR-C1 (#371) codex pass-3 P2: write `defect_log.jsonl` HERE,
    # immediately after `dq_exceptions.jsonl`, so the artifact lands
    # on disk before any downstream abort (ContractViolation,
    # DuckDB's NOT NULL constraint, an unexpected rule-execution
    # exception). The one-ticket-per-DQ-exception contract holds
    # across every abort path, not just the ones we explicitly
    # wrapped. `_finalize_run` re-emits the file later with the full
    # defect list including python_ref failures — idempotent for the
    # happy path, additive for the rule-loop strict-abort path.
    _write_defect_log_snapshot(
        ledger,
        dq_exceptions=dq_exceptions,
        python_ref_failures={},
    )

    # PR-A3 (#364) — field lineage is pure-spec derivation, so it can be
    # written any time after `run_dir` exists. Doing it here (before the
    # warehouse build) means an early ContractViolation that aborts the
    # run still leaves a field_lineage.jsonl behind, which keeps the
    # artifact-always-present invariant the manifest-hash code relies on.
    _write_field_lineage(ledger.run_dir, derive_field_lineage(spec, as_of))

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
        # PR-C1 (#371): the defect log was already written before
        # `_build_warehouse`, so this re-raise leaves the artifact
        # on disk regardless of which warehouse-build path failed
        # (ContractViolation, DuckDB NOT NULL, etc.).
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
    python_ref_failures: dict[str, str] = {}

    for rule in spec.rules:
        if rule.status != "active":
            continue

        # PR-D3 (#376): environment promotion gate. The audit event is
        # ALWAYS recorded — even on approval — so the regulator pack can
        # prove the gate was consulted, not just that blocked rules
        # existed. When the program declares `strict_environment_gating`
        # and the rule is not approved for the current lane, raise
        # `EnvironmentGatingError` to abort the run. Otherwise emit a
        # WARN and let the rule fire (the WARN-only default lets
        # institutions stage the gate before flipping it to enforce).
        approved = is_rule_approved_for_environment(rule, spec.program)
        ledger.append_decision(promotion_audit_event(rule, spec.program, approved=approved))
        if not approved:
            if spec.program.strict_environment_gating:
                raise EnvironmentGatingError(
                    rule_id=rule.id,
                    environment=spec.program.environment,
                    approved=list(rule.environments),
                )
            logger.warning(
                "rule '%s' fired in environment '%s' but is only approved for %s — "
                "WARN only (set program.strict_environment_gating: true to block)",
                rule.id,
                spec.program.environment,
                list(rule.environments),
            )

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
                with cost_timer.rule(rule.id):
                    alerts = scorer(con, as_of)
                # python_ref scorers may issue arbitrary numbers of
                # DuckDB queries internally; count the call as 1 since
                # we can't introspect without wrapping the connection.
                # Captures *that* a scorer ran, not how chatty it was.
                cost_timer.increment_queries()
                # Opt-in matched-row lineage hook: if the scorer module
                # exposes `_inspect_context(con, alerts, as_of)`, call
                # it for richer audit attribution. Returns a list of
                # (table, rowid) tuples per alert (parallel to
                # `alerts`) — stored on each alert as `matched_row_ids`
                # so dashboards / lineage walks see what evidence the
                # python_ref scorer used. PR #225 deferred this
                # because the callable contract was unscoped; this
                # opt-in protocol keeps existing scorers working while
                # letting new ones surface evidence rows.
                inspect = getattr(mod, "_inspect_context", None)
                if callable(inspect) and alerts:
                    try:
                        attrib = inspect(con, alerts, as_of)
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "python_ref rule '%s' _inspect_context() raised — "
                            "alerts kept, matched_row_ids left empty",
                            rule.id,
                        )
                    else:
                        if attrib and len(attrib) == len(alerts):
                            for alert, rowids in zip(alerts, attrib, strict=True):
                                # Normalise — each entry should be a
                                # list of (table_name, rowid) tuples or
                                # plain rowids; both shapes welcome.
                                alert["matched_row_ids"] = list(rowids or [])
            except Exception as exc:
                # Always record the failure in the audit ledger so the
                # run directory documents what went wrong regardless of
                # whether the engine aborts.
                logger.exception(
                    "python_ref rule '%s' failed: %s — recording zero alerts",
                    rule.id,
                    exc,
                )
                error_msg = f"{type(exc).__name__}: {exc}"
                alerts = []
                alerts_by_rule[rule.id] = alerts
                ledger.record_alerts(rule.id, alerts)
                ledger.append_decision(
                    {
                        "event": Event.RULE_FAILED,
                        "rule_id": rule.id,
                        "rule_version": rule_version_hash(rule),
                        "logic_type": "python_ref",
                        "error": error_msg,
                    }
                )
                python_ref_failures[rule.id] = error_msg
                # PR-C1 (#371) codex pass-4 P2: re-emit the defect
                # log every time a python_ref failure is recorded,
                # not just on the strict-abort path. Under permissive
                # mode (`AML_STRICT_PYTHON_REF=0`), a later rule
                # (e.g. an invalid `custom_sql`) or finalize step
                # might abort before `_finalize_run()` overwrites the
                # snapshot. Re-emitting here keeps every recorded
                # `rule_failed` event paired with a RULE_LOGIC defect
                # on disk.
                _write_defect_log_snapshot(
                    ledger,
                    dq_exceptions=dq_exceptions or [],
                    python_ref_failures=python_ref_failures,
                )
                if _is_strict_python_ref(strict_python_ref):
                    # Strict mode aborts before `_finalize_run()`;
                    # the re-emit above already covered the artifact,
                    # so just raise.
                    raise PythonRefFailure(
                        rule_id=rule.id,
                        module_path=module_path,
                        func_name=func_name,
                        message=error_msg,
                    ) from exc
                continue
            stamp_payload_meta(rule, alerts, as_of=as_of)
            alerts_by_rule[rule.id] = alerts
            ledger.record_alerts(rule.id, alerts)
            _open_cases_for_alerts(rule, alerts, spec, ledger, case_ids)
            continue

        # --- list_match: screen against a reference list ---
        if rule.logic.type == "list_match":
            # `_execute_list_match` increments the SQL counter only
            # after the SELECT against the source table runs, so the
            # missing-reference-list path returns 0 queries instead
            # of phantom-1 (codex pass-2 P3 on PR-LF2).
            with cost_timer.rule(rule.id):
                alerts, list_version = _execute_list_match_with_version(
                    rule, con, as_of, cost_timer
                )
            # PR-PAY-1 codex pass-5 race fix: pin the alert payload's
            # `reference_data_version` to the EXACT bytes
            # `_load_reference_list` just read. Without the override,
            # `stamp_payload_meta` would re-read the list file; a
            # mid-run refresh between the screening read and the
            # digest re-read would mean the alert cites a snapshot
            # different from the one it was actually matched against.
            stamp_payload_meta(
                rule,
                alerts,
                as_of=as_of,
                reference_data_version_override=list_version,
            )
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
            # `_execute_network_pattern` + `_capture_subgraph` increment
            # the SQL counter internally — the main CTE + per-alert
            # rowid lookup + per-alert subgraph walk + per-alert edge
            # query are all counted (codex pass-1 P2 on PR-LF2).
            with cost_timer.rule(rule.id):
                alerts = _execute_network_pattern(rule, con, as_of, cost_timer)
            stamp_payload_meta(rule, alerts, as_of=as_of)
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

        # PR-LF2: time the rule's SQL execution + count the query. The
        # follow-up matched-row-id replay queries are counted below
        # (one per alert).
        with cost_timer.rule(rule.id):
            rows = con.execute(sql).fetchall()
        cost_timer.increment_queries()
        cols = [d[0] for d in con.description] if con.description else []
        alerts = [dict(zip(cols, r)) for r in rows]
        # PR-LIN-4: for each alert produced by an aggregation_window /
        # custom_sql rule, look up the source rowids that contributed
        # to it. One follow-up SELECT per alert; the alert sample is
        # bounded so this is fine for FI-scale runs. Fails silently
        # per-alert (matched_row_ids stays []) when the source table
        # doesn't expose the expected customer_id / booked_at shape —
        # better than crashing the whole run.
        #
        # #21: the lookup must reproduce what the rule actually matched,
        # else STR/lineage evidence is misleading:
        #  - aggregation_window rules: replay `rule.logic.filter` (reuse
        #    the same `_compile_filter` the rule SQL is built from), so
        #    only the filtered rows (e.g. channel='cash', purpose_code=
        #    'INVS') are attributed — not every customer row in the
        #    window. custom_sql keeps the customer+window best-effort
        #    heuristic (its WHERE is hand-written; not generically
        #    reconstructable).
        #  - `booked_at <= window_end`: window_end is MAX(booked_at) of
        #    the contributing rows, so a strict `<` dropped the latest
        #    qualifying transaction from the evidence. Inclusive is
        #    correct for both rule types.
        if source_table:
            filter_preds: list[str] = []
            if rule.logic.type == "aggregation_window":
                filter_preds = _compile_filter(getattr(rule.logic, "filter", None))
            extra_where = (" AND " + " AND ".join(filter_preds)) if filter_preds else ""
            for alert in alerts:
                cid = alert.get("customer_id")
                w_start = alert.get("window_start")
                w_end = alert.get("window_end")
                alert["matched_row_ids"] = []
                if cid and w_start and w_end:
                    try:
                        with cost_timer.rule(rule.id):
                            rid_rows = con.execute(
                                f"SELECT rowid FROM {source_table} "
                                f"WHERE customer_id = ? AND booked_at >= ? "
                                f"AND booked_at <= ?{extra_where}",
                                [cid, w_start, w_end],
                            ).fetchall()
                        cost_timer.increment_queries()
                        alert["matched_row_ids"] = [int(r[0]) for r in rid_rows]
                    except Exception:
                        # Don't fail the alert on a lineage-lookup miss, but
                        # don't swallow it silently either — an empty
                        # matched_row_ids with no trace looks identical to a
                        # rule that genuinely matched zero evidence rows. Log
                        # by rule only — customer_id is PII and would leak into
                        # CI/container logs when AML_PII_MASKING=1 (the alert
                        # itself is masked later by record_alerts()).
                        logger.exception(
                            "rule '%s' matched_row_ids lookup failed — "
                            "alert kept, matched_row_ids left empty",
                            rule.id,
                        )
        stamp_payload_meta(rule, alerts, as_of=as_of)
        alerts_by_rule[rule.id] = alerts
        ledger.record_alerts(rule.id, alerts)

        _open_cases_for_alerts(rule, alerts, spec, ledger, case_ids)

    # --- Simulate case resolution ---
    # Walk each case through the workflow queues to generate realistic
    # decision events, resolution times, and SLA compliance data.
    _simulate_case_resolution(spec, case_ids, ledger, as_of)

    return _finalize_run(
        spec,
        ledger,
        alerts_by_rule,
        case_ids,
        data,
        python_ref_failures,
        cost_timer=cost_timer,
        dq_exceptions=dq_exceptions,
    )


def _finalize_run(
    spec: AMLSpec,
    ledger: AuditLedger,
    alerts_by_rule: dict[str, list[dict[str, Any]]],
    case_ids: list[str],
    data: dict[str, list[dict[str, Any]]],
    python_ref_failures: dict[str, str] | None = None,
    *,
    cost_timer: CostVolumeTimer | None = None,
    dq_exceptions: list[DQException] | None = None,
) -> RunResult:
    """Evaluate metrics, render reports, and write the final manifest.

    `cost_timer` (PR-LF2) is optional so existing tests / callers that
    invoke `_finalize_run` directly don't break. When provided, a
    `run_cost_volume.json` artifact is written BEFORE `ledger.finalize()`
    so its SHA-256 can be pinned in the manifest by the audit module.
    """
    cases_rows: list[dict[str, Any]] = []
    for case_file in sorted((ledger.run_dir / "cases").glob("*.json")):
        cases_rows.append(json.loads(case_file.read_bytes()))
    decisions_rows: list[dict[str, Any]] = []
    decisions_path = ledger.run_dir / "decisions.jsonl"
    if decisions_path.exists():
        for line in decisions_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                decisions_rows.append(json.loads(line))

    # PR-LF1 (#383): emit `sla_report.json` before metrics so the report
    # is available to downstream readers even if metric rendering fails.
    # The report is pure — no I/O beyond writing this one file — and
    # always written (possibly disabled/empty when `program.sla` is
    # absent), matching the artifact-always-present posture set by
    # `dq_exceptions.jsonl` and `field_lineage.jsonl`.
    _write_sla_report(
        ledger.run_dir,
        evaluate_sla(spec, decisions_rows, data, ledger.as_of),
    )

    metric_results = evaluate_metrics(
        spec=spec,
        alerts=alerts_by_rule,
        cases=cases_rows,
        decisions=decisions_rows,
        data=data,
        run_dir=ledger.run_dir,
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

    # PR-LF2 (#384) — write `run_cost_volume.json` BEFORE finalize so
    # `AuditLedger.finalize()` can pin its SHA-256 in the manifest.
    # `cost_timer` is None for legacy callers that bypass `run_spec`;
    # in that case we still emit an artifact with zero seconds and an
    # empty per-rule map so the always-present contract holds.
    if cost_timer is None:
        cost_timer = CostVolumeTimer()
    cost_report = build_cost_volume_report(
        wall_clock_seconds=cost_timer.wall_clock(),
        tables=summarise_tables(data),
        total_sql_queries=cost_timer.total_sql_queries,
        per_rule_seconds=dict(cost_timer.per_rule_seconds),
    )
    write_cost_volume_report(ledger.run_dir, cost_report)

    # PR-LF4 (#386): write the post-run monitoring digest BEFORE
    # `ledger.finalize()` so the manifest can pin its SHA-256 — the
    # finalize() step hashes whichever artifacts already exist on disk.
    # The prior-run lookup is best-effort: missing persistence layer or
    # any exception below returns None and the diff degrades gracefully
    # to an empty dict.
    prior_run = lookup_prior_run(
        str(ledger.spec_path),
        current_run_dir=str(ledger.run_dir),
    )
    digest = build_monitoring_digest(
        spec,
        run_dir=ledger.run_dir,
        spec_path=ledger.spec_path,
        spec_content_hash=ledger.spec_content_hash,
        engine_version=ENGINE_VERSION,
        as_of=ledger.as_of,
        alerts_by_rule=alerts_by_rule,
        dq_exceptions=dq_exceptions or [],
        prior_run=prior_run,
    )
    write_monitoring_digest(ledger.run_dir, digest)

    # PR-C1 (#371) — Pillar-2 defect log. Re-emit with the full
    # accumulator state (DQ exceptions + permissive-mode python_ref
    # failures); the snapshot written pre-warehouse already covered
    # the abort paths. Written BEFORE `ledger.finalize()` so the
    # manifest can pin `defect_log_hash`.
    _write_defect_log_snapshot(
        ledger,
        dq_exceptions=dq_exceptions or [],
        python_ref_failures=python_ref_failures or {},
    )

    # PR-B3 (#368): write the Pillar-4 reconciliation report BEFORE
    # `ledger.finalize()` so the manifest can pin its SHA-256. Always
    # emitted (possibly empty `contracts` for an empty-spec run) so
    # downstream readers can rely on its presence — same posture as
    # `monitoring_digest.json` / `sla_report.json` / `dq_exceptions.jsonl`.
    reconciliation = build_reconciliation_report(
        spec,
        data,
        dq_exceptions or [],
        alerts_by_rule,
    )
    write_reconciliation_report(ledger.run_dir, reconciliation)

    manifest = ledger.finalize()
    manifest["metrics"] = [m.to_dict() for m in metric_results]
    manifest["reports"] = sorted(reports.keys())
    # PR-LF4 (#386) codex pass-1 P2: persist `alerts_per_rule` + the
    # prior_run_id on the manifest so a future run loading THIS one
    # via `db.get_run()` can compute a real diff instead of falling
    # back to a zero-count baseline. Counts only — full digest body
    # stays on disk to keep the manifest small.
    manifest["monitoring_digest"] = {
        "alerts_per_rule": dict(digest.alerts_per_rule),
        "prior_run_id": digest.prior_run_id,
    }
    if python_ref_failures:
        manifest["python_ref_failures"] = python_ref_failures
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
        python_ref_failures=python_ref_failures or {},
    )
