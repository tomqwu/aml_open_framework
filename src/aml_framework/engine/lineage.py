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

- `aggregation_window`: traces each `group_by` column (transform=GROUP_BY)
  and each `having` metric to its underlying source column via the
  `_HAVING_AGGREGATES` map mirrored from `generators.sql`. `count` is
  modeled as a transform over `*` (no single column) so it stays
  honest about its semantics.
- `list_match`: traces the rule's `field` to the source contract with
  transform=list_match.
- `custom_sql`: best-effort — emits one synthetic row per rule with
  `source_column="*"` and `transform="custom_sql"`. Parsing the SQL is
  intentionally out of scope (it would re-implement a SQL parser); the
  gap is documented so downstream consumers know not to expect more.
- `python_ref`: best-effort — `source_column="*"`,
  `transform="python_ref:<callable>"`.
- `network_pattern`: traces seed `customer_id` + each having metric
  (`component_size`, `counterparty_count`) — the rule consumes the
  resolved_entity_link graph, so source columns are best-effort `*`
  with a graph-walk transform tag.

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
        logic = rule.logic
        logic_type = getattr(logic, "type", None)

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
        elif logic_type == "list_match":
            # `_execute_list_match` emits `matched_name` (the value of
            # the screened field, upper-cased) and `customer_id` (carried
            # from the source row) on every alert. Map both back to the
            # source contract so the artifact answers lineage questions
            # for sanctions/PEP alerts. Mapping `logic.field` directly
            # would point at a non-existent alert key — codex caught
            # this on PR-A3.
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
            # seed entity is customer_id on the configured source contract.
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
            for metric in logic.having.keys():
                entries.append(
                    FieldLineageEntry(
                        rule_id=rule.id,
                        alert_field=metric,
                        source_contract_id="resolved_entity_link",
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
