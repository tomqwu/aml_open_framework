"""Data-contract quality-check evaluator (B4 — DQ visibility).

Backs backlog issue #369 (`[B4][task] DQ exception table`). Option B in the
ticket: **additive observability with no row drops**. The reference engine
previously ignored `quality_checks` entirely at run time — they were
re-evaluated only at display time in `dashboard/pages/14_Data_Quality.py`
and `dashboard/pages/30_Data_Integration.py`. That left no audit trail and
no shippable artifact for DQ failures.

This module adds a pure evaluator that produces `DQException` records.
Callers (the engine runner) accumulate them, write a `dq_exceptions.jsonl`
artifact, and emit one audit-ledger event per exception so the failures
join the existing hash-chain integrity guarantee. Crucially the evaluator
does **NOT** mutate the input rows — observability only. Warehouse row
counts are unchanged.

Supported check types in v1:
- `not_null`: per declared column, one exception per row whose value is
  `None`. `failing_value` is `None`; `row_index` is the position of the
  offending row in the input list.
- `unique`: per declared column, one exception per duplicate occurrence
  (the second and later sightings of the same non-null value).
  `failing_value` is the duplicated value; `row_index` is the position
  of the duplicate occurrence.

Other check shapes the spec allows (e.g. `enum`, `range`) are left for
follow-up; unknown keys are silently skipped here so this evaluator stays
forward-compatible with future quality_checks dialects.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DQCheckType = Literal["not_null", "unique"]


class DQException(BaseModel):
    """One data-quality failure observed against a declared check.

    Frozen + `extra="forbid"` so callers can rely on the shape: a new
    field always means a deliberate schema bump, never an accidental
    dict-spread overflow.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_id: str
    check_id: str  # synthesized: "not_null:<col>" or "unique:<col>"
    check_type: DQCheckType
    column: str
    failing_value: str | None = None
    row_index: int | None = None
    reason: str
    at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


def _format_value(value: Any) -> str | None:
    """Coerce a failing value to a string for ledger storage.

    `None` stays `None` so consumers can distinguish "null violation"
    (failing_value is None on a not_null check) from "the value was the
    literal string 'None'".
    """
    if value is None:
        return None
    return str(value)


def evaluate_contract_checks(
    rows: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    *,
    contract_id: str,
    at: datetime | None = None,
) -> list[DQException]:
    """Evaluate every declared check against `rows` and return exceptions.

    Pure and deterministic. Does **not** mutate `rows`. Returns exceptions
    in a stable order: outer loop = the declared checks (in spec order),
    inner loop = row index ascending. Two runs over the same inputs
    produce the same list.

    `at` lets the runner pin a deterministic timestamp on each exception
    so the JSONL artifact + audit ledger entries are reproducible across
    runs. Defaults to "now" for ad-hoc callers (tests, dashboard).
    """
    if not rows or not checks:
        return []

    timestamp = at if at is not None else datetime.now(tz=timezone.utc)
    exceptions: list[DQException] = []

    for qc in checks:
        for check_type, fields in qc.items():
            if check_type not in ("not_null", "unique"):
                # Forward-compat: unknown check shape, skip silently.
                continue
            if not isinstance(fields, list):
                continue
            for column in fields:
                if check_type == "not_null":
                    exceptions.extend(_eval_not_null(rows, contract_id, column, timestamp))
                elif check_type == "unique":
                    exceptions.extend(_eval_unique(rows, contract_id, column, timestamp))

    return exceptions


def _eval_not_null(
    rows: list[dict[str, Any]],
    contract_id: str,
    column: str,
    at: datetime,
) -> list[DQException]:
    out: list[DQException] = []
    for idx, row in enumerate(rows):
        # Treat a missing key the same as an explicit `None`. `_build_warehouse`
        # materializes declared columns as None when the source row dict
        # doesn't carry the key, and downstream dashboard surfaces already
        # count those as nulls — so the engine-time DQ artifact must too,
        # otherwise sparse input rows under-report. Issue #369 codex pass.
        if column not in row or row[column] is None:
            out.append(
                DQException(
                    contract_id=contract_id,
                    check_id=f"not_null:{column}",
                    check_type="not_null",
                    column=column,
                    failing_value=None,
                    row_index=idx,
                    reason=f"column '{column}' is null on row {idx}",
                    at=at,
                )
            )
    return out


def _eval_unique(
    rows: list[dict[str, Any]],
    contract_id: str,
    column: str,
    at: datetime,
) -> list[DQException]:
    """Flag the *second and later* occurrence of each duplicated value.

    Nulls are ignored — `not_null` is the right check for that, and
    SQL UNIQUE constraints conventionally do not collide on NULL.
    """
    seen: dict[Any, int] = {}
    out: list[DQException] = []
    for idx, row in enumerate(rows):
        if column not in row:
            continue
        value = row[column]
        if value is None:
            continue
        if value in seen:
            first_idx = seen[value]
            out.append(
                DQException(
                    contract_id=contract_id,
                    check_id=f"unique:{column}",
                    check_type="unique",
                    column=column,
                    failing_value=_format_value(value),
                    row_index=idx,
                    reason=(f"column '{column}' value duplicates row {first_idx} at row {idx}"),
                    at=at,
                )
            )
        else:
            seen[value] = idx
    return out
