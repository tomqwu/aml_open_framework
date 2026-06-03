"""Field-level lineage derivation (A3 — #364).

Backs backlog issue #364 (`[A3][task] field_lineage artifact in run_dir`).
This module computes a pure, spec-derived mapping from each rule's
`alert_field` to the source `(contract_id, column)` it traces back to,
along with the SQL/Python transform that produced it. The engine runner
writes the resulting list as `field_lineage.jsonl` under the run dir —
one JSON object per line — so a regulator can answer "where did
`sum_amount` on this alert come from?" by reading a hash-pinned artifact
rather than re-walking the spec at dashboard time.

Pillar 2 (Evidence-as-a-product) work. `walk_lineage()` in
`engine/audit.py` already surfaces per-case lineage at READ time; this
module makes the same information a first-class WRITE artifact so it's
part of the regulator-shippable evidence bundle.

Rule-logic coverage:

- **Every active rule (PR-PAY-1)**: traces the engine-owned
  `threshold` + `reference_data_version` alert fields that
  `stamp_payload_meta` stamps on every alert. `threshold` derives from
  the spec rule's logic (no data contract); `reference_data_version`
  derives from the reference-list content hash for `list_match` rules
  and is "not_applicable" for the other 4 shapes. Both rows use
  `source_contract_id="*"` because the spec itself (not a data
  contract) is the source.

- `aggregation_window`: traces each `group_by` column (transform=GROUP_BY),
  each `having` metric to its underlying source column via the
  `_HAVING_AGGREGATES` map mirrored from `generators.sql`, and the two
  emitted window fields (`window_start = MIN(booked_at)`,
  `window_end = MAX(booked_at)`) that `compile_rule_sql` writes on every
  alert. `count` is modeled as a transform over `*` (no single column)
  so it stays honest about its semantics.
- `list_match`: traces every derived alert key the executor produces:
  `matched_name` → (source, field), `customer_id` → (source,
  customer_id), `match_score` → (`*`, list_name); fuzzy alerts also
  trace `list_entry` → (`*`, list_name). The reference list itself is
  not a declared contract, so list-derived fields use `source_contract_id="*"`
  with the list name captured in `source_column`.
- `custom_sql`: best-effort — emits one synthetic row per rule with
  `source_column="*"` and `transform="custom_sql"`. Parsing the SQL is
  intentionally out of scope (it would re-implement a SQL parser); the
  gap is documented so downstream consumers know not to expect more.
- `python_ref`: best-effort — `source_column="*"`,
  `transform="python_ref:<callable>"`.
- `network_pattern`: traces seed `customer_id` to the hard-coded
  `customer` seed table (the executor ignores `logic.source` and seeds
  from `FROM customer`), and emits both `component_size` AND
  `counterparty_count` rows because the executor always populates both
  alert keys regardless of which the rule thresholds on. Both metrics
  trace back to the `customer` contract with `source_column="*"`
  (the underlying `resolved_entity_link` table is an in-memory derived
  artifact, NOT a declared contract — pointing there would leave an
  auditor with no resolvable source).

Only `status="active"` rules contribute lineage rows — `experimental`
and `deprecated` rules are skipped by `run_spec` and therefore have
no alerts in `rule_outputs`; emitting lineage for them would
misrepresent the evidence bundle.

The output is sorted deterministically so two calls on the same spec
produce byte-identical artifacts (pinned by `test_determinism_two_calls_match`
+ the engine's reproducibility contract).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from aml_framework.spec.models import AMLSpec

# Mirrors `generators.sql._HAVING_AGGREGATES`. Kept local rather than
# imported so this module stays a pure spec-derivation utility — no
# transitive dependency on the SQL generator. If the generator grows a
# new having metric, this table needs the same row.
#
# Each entry maps a having key → (source_column, transform). `count`
# aggregates rows rather than a column, so its source is the wildcard
# "*" and its transform is COUNT. Other metrics are SUM/AVG/MIN/MAX
# over the `amount` column.
_HAVING_LINEAGE: dict[str, tuple[str, str]] = {
    "count": ("*", "COUNT"),
    "sum_amount": ("amount", "SUM"),
    "max_amount": ("amount", "MAX"),
    "min_amount": ("amount", "MIN"),
    "avg_amount": ("amount", "AVG"),
}


class FieldLineageEntry(BaseModel):
    """One (rule, alert_field) → (source_contract, source_column, transform) triple.

    Frozen + `extra="forbid"` so the artifact shape is locked: a new
    field is a deliberate schema bump, never an accidental dict-spread
    overflow. Same posture as `DQException` from PR-B4.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str
    alert_field: str
    source_contract_id: str
    source_column: str
    transform: str
    at: datetime


def derive_field_lineage(spec: "AMLSpec", at: datetime) -> list[FieldLineageEntry]:
    """Return one entry per (rule, alert_field, source) triple.

    Pure function over the spec — no I/O, no DuckDB, no run state. The
    runner calls this once per run and persists the result as a
    hash-pinned artifact. Ordering is deterministic: rules in spec
    order, then alphabetical alert_field within each rule.
    """
    entries: list[FieldLineageEntry] = []

    for rule in spec.rules:
        # Match `run_spec`'s skip rule: only `status="active"` rules run,
        # so only active rules should claim lineage in the regulator-
        # facing artifact. Codex P2 on PR-A3 caught the misrepresentation
        # — a deprecated rule with no alerts in `rule_outputs` would
        # otherwise still appear in field_lineage.jsonl.
        if getattr(rule, "status", "active") != "active":
            continue
        logic = rule.logic
        logic_type = getattr(logic, "type", None)

        # PR-PAY-1: `threshold` + `reference_data_version` are
        # engine-owned alert fields, stamped by `stamp_payload_meta` on
        # every alert across all 5 rule shapes regardless of executor.
        # Both trace back to the spec rule itself (not a data contract):
        # `threshold` is `rule.logic.having` / `match`+threshold /
        # `pattern`+`max_hops`+`having` — derived purely from the spec —
        # and `reference_data_version` is the content-hash of the
        # reference list for `list_match` rules (or None for everything
        # else). Add lineage rows for them so `field_lineage.jsonl`
        # matches the real alert shape; the spec itself is named as the
        # source via `source_contract_id="*"` + `source_column="<spec
        # location>"`.
        entries.append(
            FieldLineageEntry(
                rule_id=rule.id,
                alert_field="threshold",
                source_contract_id="*",
                source_column=f"spec.rules.{rule.id}.logic",
                transform="payload_meta:threshold_snapshot",
                at=at,
            )
        )
        # N1: when governed prioritization is enabled, every alert (all rule
        # shapes) gains `priority_score` + `priority_explanation`, stamped by
        # `stamp_priority`. Trace them to `program.prioritization` + the scorer
        # so the lineage artifact matches the real persisted alert shape and an
        # auditor can follow the advisory score back to its config + logic.
        prioritization = getattr(spec.program, "prioritization", None)
        if prioritization is not None and prioritization.enabled:
            for _priority_field in ("priority_explanation", "priority_score"):
                entries.append(
                    FieldLineageEntry(
                        rule_id=rule.id,
                        alert_field=_priority_field,
                        source_contract_id="*",
                        source_column="spec.program.prioritization",
                        transform="prioritization:advisory_score",
                        at=at,
                    )
                )
        if logic_type == "list_match":
            entries.append(
                FieldLineageEntry(
                    rule_id=rule.id,
                    alert_field="reference_data_version",
                    source_contract_id="*",
                    source_column=logic.list,
                    transform="payload_meta:sha256_content_hash",
                    at=at,
                )
            )
        else:
            entries.append(
                FieldLineageEntry(
                    rule_id=rule.id,
                    alert_field="reference_data_version",
                    source_contract_id="*",
                    source_column="*",
                    transform="payload_meta:not_applicable",
                    at=at,
                )
            )

        if logic_type == "aggregation_window":
            # group_by columns trace 1:1 to the source contract's column
            # of the same name with no transform (they're the partition
            # keys, not aggregated).
            for gb_col in logic.group_by:
                entries.append(
                    FieldLineageEntry(
                        rule_id=rule.id,
                        alert_field=gb_col,
                        source_contract_id=logic.source,
                        source_column=gb_col,
                        transform="GROUP_BY",
                        at=at,
                    )
                )
            # having metrics: each becomes an alert_field with the
            # mirrored aggregate. Unknown metrics fall back to a
            # best-effort row with source_column="*" rather than
            # silently disappearing — the artifact should never hide
            # a derived alert field.
            for metric in logic.having.keys():
                src_col, transform = _HAVING_LINEAGE.get(metric, ("*", "UNKNOWN_AGGREGATE"))
                entries.append(
                    FieldLineageEntry(
                        rule_id=rule.id,
                        alert_field=metric,
                        source_contract_id=logic.source,
                        source_column=src_col,
                        transform=transform,
                        at=at,
                    )
                )
            # `compile_rule_sql` always emits `window_start = MIN(booked_at)`
            # and `window_end = MAX(booked_at)` on every aggregation
            # alert — these are source-derived fields too and must have
            # a lineage row, or the artifact under-represents the alert
            # shape. Codex P2 on PR-A3 caught the omission.
            for window_field, agg in (("window_start", "MIN"), ("window_end", "MAX")):
                entries.append(
                    FieldLineageEntry(
                        rule_id=rule.id,
                        alert_field=window_field,
                        source_contract_id=logic.source,
                        source_column="booked_at",
                        transform=agg,
                        at=at,
                    )
                )
        elif logic_type == "list_match":
            # `_execute_list_match` emits on every alert:
            #   - `matched_name` (the upper-cased value of the screened
            #     source field)
            #   - `customer_id` (carried from the source row)
            #   - `match_score` (1.0 for exact, fuzzy ratio otherwise)
            # Plus, on fuzzy alerts only:
            #   - `list_entry` (the reference-list value that matched)
            # All four are derived alert fields a regulator needs to
            # explain "why did this alert fire?" — codex P2 on PR-A3
            # caught the original under-coverage. `match_score` and
            # `list_entry` reference the configured reference list
            # rather than a contract column, so source_column captures
            # the list name and source_contract_id is a wildcard.
            entries.append(
                FieldLineageEntry(
                    rule_id=rule.id,
                    alert_field="matched_name",
                    source_contract_id=logic.source,
                    source_column=logic.field,
                    transform="list_match",
                    at=at,
                )
            )
            entries.append(
                FieldLineageEntry(
                    rule_id=rule.id,
                    alert_field="customer_id",
                    source_contract_id=logic.source,
                    source_column="customer_id",
                    transform="GROUP_BY",
                    at=at,
                )
            )
            entries.append(
                FieldLineageEntry(
                    rule_id=rule.id,
                    alert_field="match_score",
                    source_contract_id="*",
                    source_column=logic.list,
                    transform=f"list_match:{logic.match}",
                    at=at,
                )
            )
            if logic.match == "fuzzy":
                entries.append(
                    FieldLineageEntry(
                        rule_id=rule.id,
                        alert_field="list_entry",
                        source_contract_id="*",
                        source_column=logic.list,
                        transform="list_match:fuzzy",
                        at=at,
                    )
                )
        elif logic_type == "custom_sql":
            # Parsing arbitrary SQL is out of scope (a real implementation
            # would need a SQL AST library and dialect awareness). Emit a
            # single best-effort row per rule so the artifact still
            # references every rule; downstream consumers can treat
            # source_column="*" as "see the rendered .sql file under
            # rules/<rule_id>.sql for the full query".
            entries.append(
                FieldLineageEntry(
                    rule_id=rule.id,
                    alert_field="*",
                    source_contract_id="*",
                    source_column="*",
                    transform="custom_sql",
                    at=at,
                )
            )
        elif logic_type == "python_ref":
            entries.append(
                FieldLineageEntry(
                    rule_id=rule.id,
                    alert_field="*",
                    source_contract_id="*",
                    source_column="*",
                    transform=f"python_ref:{logic.callable}",
                    at=at,
                )
            )
        elif logic_type == "network_pattern":
            # `_execute_network_pattern` hard-codes the seed table to
            # `customer` (regardless of `logic.source`) — see the
            # `FROM customer` line in the recursive CTE — and always
            # emits BOTH `component_size` and `counterparty_count` on
            # every alert (not just the metrics named in `having`).
            # Mirror that exactly so the artifact tells the truth about
            # the executor: seed_contract=customer, both metrics
            # present. Codex P2 on PR-A3 caught the divergence.
            entries.append(
                FieldLineageEntry(
                    rule_id=rule.id,
                    alert_field="customer_id",
                    source_contract_id="customer",
                    source_column="customer_id",
                    transform="GROUP_BY",
                    at=at,
                )
            )
            # `resolved_entity_link` is a derived in-memory DuckDB
            # table built by `resolve_entities` from declared linking
            # attributes on the `customer` contract. It is not itself
            # a declared data contract, so naming it as the source
            # would point auditors at an unresolvable contract id.
            # Point at the underlying `customer` contract with
            # `source_column="*"` so the chain back to a declared
            # input is preserved. Codex P2 on PR-A3.
            for metric in ("component_size", "counterparty_count"):
                entries.append(
                    FieldLineageEntry(
                        rule_id=rule.id,
                        alert_field=metric,
                        source_contract_id="customer",
                        source_column="*",
                        transform=f"network_pattern:{logic.pattern}",
                        at=at,
                    )
                )
        # Unknown logic types: skip silently — forward-compat. A future
        # rule shape that lands without a lineage author is better
        # surfaced via a downstream gap-check than by crashing the run.

    # Deterministic order: by (rule_id, alert_field, source_contract_id,
    # source_column, transform). `at` is constant for the whole spec so
    # excluding it from the sort key is safe — adding it would just
    # break the tie deterministically anyway.
    entries.sort(
        key=lambda e: (
            e.rule_id,
            e.alert_field,
            e.source_contract_id,
            e.source_column,
            e.transform,
        )
    )
    return entries
