"""Pillar-4 reconciliation stage tracker (PR-B3 — closes #368).

A regulator opening a run dir needs to answer: *"did we lose rows between
ingestion and detection?"* The framework already emits per-stage evidence
(input manifest row counts, DQ exceptions, alerts), but no single
artifact rolls them up into the row-count survival story across the
medallion stages **bronze → silver → gold → alert**.

This module writes ``reconciliation_report.json`` next to ``manifest.json``.
For every input data contract the report records:

- ``stage_counts``: the row count observed at the contract's declared
  ``layer`` plus the alert-stage row count for any rule that consumed
  the contract via ``rule.logic.source``;
- ``drop_breakdown``: per-stage signed row deltas vs the prior stage,
  with a short attribution string. Attribution vocabulary:
  ``dq_exceptions`` (rows removed because at least one row-level DQ
  check failed on them), ``alert_surface`` (gold→alert leg — alerts
  fire from N candidate rows), ``no_drop`` (zero delta or no causal
  signal), ``missing_layer`` (upstream stage carries no count because
  no contract was anchored there). A negative drop is survival
  shrinkage; a positive value means the stage *amplified* (e.g. an
  aggregation rule emitting one alert per group breaks 1:1 row
  equivalence — the artifact records the count rather than asserting
  equality).

The evaluator is **pure** — no I/O, no ledger writes, no DuckDB. The
runner is the single caller that persists the report via
:func:`write_reconciliation_report`. Always emitted (empty payloads
remain shape-stable) — same posture as ``dq_exceptions.jsonl`` /
``field_lineage.jsonl`` / ``sla_report.json`` / ``run_cost_volume.json``.

Determinism note: stage counts depend on the input data + rules only;
no wall-clock fields. The artifact's SHA-256 is pinned in the manifest
(``reconciliation_report_hash``) so post-finalize tampering surfaces
the same way it does for the other Pillar-6 / Pillar-4 evidence.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from aml_framework.engine.dq import DQException
from aml_framework.spec.models import AMLSpec


class ReconciliationStage(str, Enum):
    """Medallion stages the reconciliation tracker walks per contract.

    `BRONZE`/`SILVER`/`GOLD` mirror the optional ``data_contract.layer``
    hint introduced in PR-D1 (#374). `ALERT` is the terminal stage — the
    rule-fire population is tracked separately so the regulator can read
    "rows in → rows alerted" as one line per contract.
    """

    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    ALERT = "alert"


_LAYER_ORDER: tuple[str, ...] = ("bronze", "silver", "gold")


class _ReconBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StageDrop(_ReconBase):
    """One stage-to-stage delta with attribution.

    `from_stage` → `to_stage` records the signed row delta plus a
    short attribution string: one of ``"dq_exceptions"``,
    ``"alert_surface"``, ``"no_drop"``, ``"missing_layer"``. Frozen so
    the artifact shape can be relied on by dashboards reading the JSON
    without a Pydantic schema round-trip.
    """

    from_stage: ReconciliationStage
    to_stage: ReconciliationStage
    delta: int
    attribution: str


class ContractReconciliation(_ReconBase):
    """Per-contract stage counts + drop breakdown.

    `stage_counts` keys are the four ``ReconciliationStage`` values;
    missing stages (e.g. a contract whose `layer` is None, or one that
    no rule consumes) carry ``None`` rather than zero so the regulator
    can tell "no data" apart from "zero rows".
    """

    contract_id: str
    layer: str | None
    stage_counts: dict[ReconciliationStage, int | None]
    drop_breakdown: list[StageDrop]


class ReconciliationReport(_ReconBase):
    """Run-level reconciliation artifact persisted as
    ``reconciliation_report.json``.

    Always written. `contracts` is a list (not dict) so JSON ordering
    is stable across re-runs without relying on dict-insertion order.
    """

    total_contracts: int = 0
    total_input_rows: int = 0
    total_alerts: int = 0
    contracts: list[ContractReconciliation] = Field(default_factory=list)


def _rule_source_to_contract(spec: AMLSpec) -> dict[str, str]:
    """Build a {rule_id: contract_id} map for **active** rules whose
    logic carries a `source` field (aggregation_window / list_match /
    network_pattern).

    `custom_sql` and `python_ref` rules don't declare a single contract
    source — they're omitted from the contract-level alert tally. The
    aggregate `total_alerts` on the report still counts those alerts so
    the run-wide total matches the monitoring digest. Non-active rules
    (status experimental/deprecated/inactive) are also omitted — the
    runner skips them at `runner.py::run_spec`, so attributing a zero
    alert count to their source contract would falsely claim the
    contract reached the alert surface in this run.
    """
    out: dict[str, str] = {}
    for rule in spec.rules:
        if rule.status != "active":
            continue
        logic = rule.logic
        source = getattr(logic, "source", None)
        if isinstance(source, str) and source:
            out[rule.id] = source
    return out


def _stage_counts_for_contract(
    *,
    contract_id: str,
    layer: str | None,
    input_row_count: int,
    dq_drops: int,
    alert_count: int | None,
) -> dict[ReconciliationStage, int | None]:
    """Project the (layer, row_count) signal across the four stages.

    The medallion ladder is monotone — a contract at `silver` carries
    its own row count there AND propagates downstream to `gold`. The
    upstream stage (`bronze` for a silver contract) is `None` because
    no row count was observed at that earlier stage in the current run.

    DQ drops reduce the row count from the declared layer to the next
    layer down: e.g. a `bronze` contract with 100 input rows + 3 DQ
    exceptions reports `bronze=100`, `silver=97`. A `silver` contract
    skips bronze entirely (`bronze=None`) and reports `silver=100`,
    `gold=97`. A `gold` contract starts at `gold` with no DQ drop
    propagation (the regulator-facing view is "this came in clean").
    `layer=None` (no medallion hint declared on the contract) keeps
    every stage `None` except `alert` so the artifact still records
    rule-fire counts.
    """
    counts: dict[ReconciliationStage, int | None] = {
        ReconciliationStage.BRONZE: None,
        ReconciliationStage.SILVER: None,
        ReconciliationStage.GOLD: None,
        ReconciliationStage.ALERT: alert_count,
    }
    if layer == "bronze":
        counts[ReconciliationStage.BRONZE] = input_row_count
        counts[ReconciliationStage.SILVER] = max(input_row_count - dq_drops, 0)
        counts[ReconciliationStage.GOLD] = max(input_row_count - dq_drops, 0)
    elif layer == "silver":
        counts[ReconciliationStage.SILVER] = input_row_count
        counts[ReconciliationStage.GOLD] = max(input_row_count - dq_drops, 0)
    elif layer == "gold":
        counts[ReconciliationStage.GOLD] = input_row_count
    return counts


def _drop_breakdown_for_contract(
    counts: dict[ReconciliationStage, int | None],
    *,
    dq_drops: int,
) -> list[StageDrop]:
    """Compute the signed stage-to-stage deltas.

    Walks the ordered stage list and emits one ``StageDrop`` per
    adjacent pair where the upstream stage has a known count. Missing
    upstream counts surface as ``attribution="missing_layer"`` with
    ``delta=0`` so a dashboard can show "no signal at this stage"
    instead of dropping the row silently. The alert leg is always
    emitted when a gold count is present, so the regulator can read
    the gold→alert ratio without scanning rule outputs.
    """
    breakdown: list[StageDrop] = []
    stages = (
        ReconciliationStage.BRONZE,
        ReconciliationStage.SILVER,
        ReconciliationStage.GOLD,
        ReconciliationStage.ALERT,
    )
    for upstream, downstream in zip(stages[:-1], stages[1:]):
        upstream_count = counts[upstream]
        downstream_count = counts[downstream]
        if upstream_count is None and downstream_count is None:
            continue
        if upstream_count is None:
            breakdown.append(
                StageDrop(
                    from_stage=upstream,
                    to_stage=downstream,
                    delta=0,
                    attribution="missing_layer",
                )
            )
            continue
        if downstream_count is None:
            # Downstream stage has no count — the contract didn't reach
            # this layer (e.g. gold→alert when no rule consumes the
            # contract). Record as no_drop with delta=0 so the row is
            # still emitted for shape stability.
            breakdown.append(
                StageDrop(
                    from_stage=upstream,
                    to_stage=downstream,
                    delta=0,
                    attribution="no_drop",
                )
            )
            continue
        delta = downstream_count - upstream_count
        if delta == 0:
            attribution = "no_drop"
        elif downstream == ReconciliationStage.SILVER:
            # bronze→silver: DQ exception removal is the canonical cause.
            attribution = "dq_exceptions" if dq_drops > 0 else "no_drop"
        elif downstream == ReconciliationStage.GOLD:
            # silver→gold: silver-anchored contracts surface their DQ
            # removal here. Bronze-anchored contracts already absorbed
            # the DQ delta on the upstream leg, so this leg is a
            # zero-delta no_drop and the branch is unreached in that
            # path.
            attribution = "dq_exceptions" if dq_drops > 0 and delta < 0 else "no_drop"
        else:
            # gold→alert: any non-zero delta is the rule-fire surface.
            attribution = "alert_surface"
        breakdown.append(
            StageDrop(
                from_stage=upstream,
                to_stage=downstream,
                delta=delta,
                attribution=attribution,
            )
        )
    return breakdown


def build_reconciliation_report(
    spec: AMLSpec,
    data: dict[str, list[dict[str, Any]]],
    dq_exceptions: list[DQException],
    alerts_by_rule: dict[str, list[dict[str, Any]]],
) -> ReconciliationReport:
    """Aggregate row-count survival across bronze→silver→gold→alert.

    Pure function: no I/O, no clock reads. Caller is responsible for
    sourcing the inputs from the runner state and persisting the result
    via :func:`write_reconciliation_report`.

    Contracts are listed in their declared spec order so the artifact
    matches the readable layout of ``aml.yaml``. The aggregate
    ``total_alerts`` matches the monitoring digest's ``total_alerts``
    (counts every alert regardless of whether the firing rule carries a
    ``source`` attribution).
    """
    rule_to_contract = _rule_source_to_contract(spec)

    # Roll DQ drops up by contract. The reconciliation surface counts
    # *rows* that failed at least one check, not the raw exception
    # count — one row can fail multiple checks (e.g. null AND
    # out-of-range), and inflating the DQ delta by exception count
    # would understate silver/gold survival.
    #
    # Exceptions whose `row_index` is None (synthetic
    # `malformed_check` events that don't bind to a specific row)
    # don't contribute to row-level survival arithmetic. They still
    # show up on `dq_exceptions.jsonl` so the regulator sees the
    # control gap, but they can't reduce a row count.
    dq_row_indices: dict[str, set[int]] = {}
    for exc in dq_exceptions:
        if exc.row_index is None:
            continue
        dq_row_indices.setdefault(exc.contract_id, set()).add(exc.row_index)
    dq_per_contract: dict[str, int] = {cid: len(rows) for cid, rows in dq_row_indices.items()}

    # Roll alert counts up by contract — every rule contributes via its
    # source-contract attribution; rules with no source are dropped from
    # the contract roll-up but still counted in the run-wide total.
    alerts_per_contract: dict[str, int] = {}
    total_alerts = 0
    for rule_id, alerts in alerts_by_rule.items():
        count = len(alerts)
        total_alerts += count
        contract_id = rule_to_contract.get(rule_id)
        if contract_id is not None:
            alerts_per_contract[contract_id] = alerts_per_contract.get(contract_id, 0) + count

    contracts: list[ContractReconciliation] = []
    total_input_rows = 0
    for contract in spec.data_contracts:
        contract_id = contract.id
        rows = data.get(contract_id, [])
        input_row_count = len(rows)
        total_input_rows += input_row_count
        dq_drops = dq_per_contract.get(contract_id, 0)
        # `alert_count` is None when no rule references this contract —
        # records "no alert surface" distinctly from "zero alerts".
        alert_count = alerts_per_contract.get(contract_id)
        if alert_count is None and contract_id in {v for v in rule_to_contract.values()}:
            # Defensive: a rule references this contract but no alerts
            # fired → zero, not None.
            alert_count = 0
        counts = _stage_counts_for_contract(
            contract_id=contract_id,
            layer=contract.layer,
            input_row_count=input_row_count,
            dq_drops=dq_drops,
            alert_count=alert_count,
        )
        drop_breakdown = _drop_breakdown_for_contract(counts, dq_drops=dq_drops)
        contracts.append(
            ContractReconciliation(
                contract_id=contract_id,
                layer=contract.layer,
                stage_counts=counts,
                drop_breakdown=drop_breakdown,
            )
        )

    return ReconciliationReport(
        total_contracts=len(contracts),
        total_input_rows=total_input_rows,
        total_alerts=total_alerts,
        contracts=contracts,
    )


def write_reconciliation_report(run_dir: Path, report: ReconciliationReport) -> Path:
    """Persist the report as ``reconciliation_report.json`` under
    ``run_dir``.

    ``sort_keys=True`` so the file is byte-stable across re-runs — the
    manifest-hash pin in ``audit.finalize()`` would otherwise drift on
    every run. Returns the written path so callers can hash it without
    re-deriving the location (parallel to ``write_monitoring_digest``).
    """
    path = run_dir / "reconciliation_report.json"
    payload = report.model_dump(mode="json")
    path.write_bytes(json.dumps(payload, indent=2, sort_keys=True, default=str).encode("utf-8"))
    return path
