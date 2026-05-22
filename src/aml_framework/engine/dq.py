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

Supported check types:
- `not_null`: per declared column, one exception per row whose value is
  `None`. `failing_value` is `None`; `row_index` is the position of the
  offending row in the input list.
- `unique`: per declared column, one exception per duplicate occurrence
  (the second and later sightings of the same non-null value).
  `failing_value` is the duplicated value; `row_index` is the position
  of the duplicate occurrence.
- `enum` (PR-B1 / #366): per declared column, one exception per row
  whose value is present but NOT in the declared allowed-values list.
  Missing keys / None values are skipped — `not_null` is the right check
  for absence; enum is a validity check on values that *are* present.
- `regex` (PR-B1 / #366): per declared column, one exception per row
  whose value is present but does not `re.fullmatch` the declared
  pattern. Full-match semantics so a partial match like "abc" against
  "[a-z]" + " junk" trailing fails. Callers embed inline flags
  (`(?i)`, `(?s)`, etc.) — no separate flag option.
- `range` (PR-B1 / #366): per declared column, one exception per row
  whose numeric value is outside `[min, max]`. Both bounds are
  optional. Non-numeric values produce a `range` violation with reason
  "non-numeric value cannot be range-checked".

Unknown check shapes are silently skipped so this evaluator stays
forward-compatible with future quality_checks dialects.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from numbers import Real
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DQCheckType = Literal["not_null", "unique", "enum", "regex", "range"]


class DQException(BaseModel):
    """One data-quality failure observed against a declared check.

    Frozen + `extra="forbid"` so callers can rely on the shape: a new
    field always means a deliberate schema bump, never an accidental
    dict-spread overflow.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_id: str
    check_id: str  # synthesized: "<check_type>:<col>" (e.g. "not_null:email")
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
            if check_type in ("not_null", "unique"):
                # Existing shape: list of column names.
                if not isinstance(fields, list):
                    continue
                for column in fields:
                    if check_type == "not_null":
                        exceptions.extend(_eval_not_null(rows, contract_id, column, timestamp))
                    else:
                        exceptions.extend(_eval_unique(rows, contract_id, column, timestamp))
            elif check_type in ("enum", "regex", "range"):
                # PR-B1 (#366): dict-shaped checks — `{col: spec}` per
                # declared column. `spec` is the allowed-values list
                # (enum), the pattern string (regex), or the bounds dict
                # (range). Anything else is skipped silently for
                # forward-compat.
                if not isinstance(fields, dict):
                    continue
                for column, spec in fields.items():
                    if check_type == "enum":
                        exceptions.extend(_eval_enum(rows, contract_id, column, spec, timestamp))
                    elif check_type == "regex":
                        exceptions.extend(_eval_regex(rows, contract_id, column, spec, timestamp))
                    else:
                        exceptions.extend(_eval_range(rows, contract_id, column, spec, timestamp))
            else:
                # Forward-compat: unknown check shape, skip silently.
                continue

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


def _eval_enum(
    rows: list[dict[str, Any]],
    contract_id: str,
    column: str,
    allowed: Any,
    at: datetime,
) -> list[DQException]:
    """Flag any row whose value for `column` is not in `allowed`.

    Missing keys / None are SKIPPED — absence is `not_null`'s job, not
    enum's. `allowed` must be a list/tuple; if the spec carries a
    non-iterable, the whole check is skipped (forward-compat).
    """
    if not isinstance(allowed, (list, tuple)):
        return []
    allowed_set = list(allowed)  # preserve list semantics for reason text
    out: list[DQException] = []
    for idx, row in enumerate(rows):
        if column not in row:
            continue
        value = row[column]
        if value is None:
            continue
        if value not in allowed_set:
            out.append(
                DQException(
                    contract_id=contract_id,
                    check_id=f"enum:{column}",
                    check_type="enum",
                    column=column,
                    failing_value=_format_value(value),
                    row_index=idx,
                    reason=(
                        f"column '{column}' value {value!r} not in allowed set "
                        f"{allowed_set!r} at row {idx}"
                    ),
                    at=at,
                )
            )
    return out


def _eval_regex(
    rows: list[dict[str, Any]],
    contract_id: str,
    column: str,
    pattern: Any,
    at: datetime,
) -> list[DQException]:
    """Flag any row whose value for `column` does not `re.fullmatch(pattern)`.

    Missing keys / None are SKIPPED — `not_null` covers absence. A
    non-string pattern, or a value that isn't a string, is treated as
    "cannot be regex-checked" and produces a violation only when the
    value is present and non-string (the regex check applies to strings;
    a stray int in a regex-checked column is a defect worth surfacing).
    """
    if not isinstance(pattern, str):
        return []
    try:
        compiled = re.compile(pattern)
    except re.error:
        # Malformed pattern in spec — skip silently rather than crash the
        # whole run. Spec-loader-side validation is a separate concern.
        return []
    out: list[DQException] = []
    for idx, row in enumerate(rows):
        if column not in row:
            continue
        value = row[column]
        if value is None:
            continue
        if not isinstance(value, str) or compiled.fullmatch(value) is None:
            out.append(
                DQException(
                    contract_id=contract_id,
                    check_id=f"regex:{column}",
                    check_type="regex",
                    column=column,
                    failing_value=_format_value(value),
                    row_index=idx,
                    reason=(
                        f"column '{column}' value {value!r} does not fullmatch "
                        f"pattern {pattern!r} at row {idx}"
                    ),
                    at=at,
                )
            )
    return out


def _eval_range(
    rows: list[dict[str, Any]],
    contract_id: str,
    column: str,
    bounds: Any,
    at: datetime,
) -> list[DQException]:
    """Flag any row whose numeric value for `column` is outside [min, max].

    Both `min` and `max` are optional — omitted means "no bound that
    side". Missing keys / None are SKIPPED. Non-numeric values produce
    a range violation with a "non-numeric" reason — the spec author
    declared the column numeric-checkable, so a string there is a
    defect worth surfacing as a DQ event.

    `bool` is excluded from the numeric path on purpose: Python's
    `isinstance(True, int)` is True, but a True/False in a numeric
    column is almost always a contract defect, not a 1/0 to be range-
    checked. Treat it as non-numeric so it surfaces as a violation.
    """
    if not isinstance(bounds, dict):
        return []
    lo = bounds.get("min")
    hi = bounds.get("max")
    # If neither bound is provided the check is a no-op; emit nothing.
    if lo is None and hi is None:
        return []
    out: list[DQException] = []
    for idx, row in enumerate(rows):
        if column not in row:
            continue
        value = row[column]
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, Real):
            out.append(
                DQException(
                    contract_id=contract_id,
                    check_id=f"range:{column}",
                    check_type="range",
                    column=column,
                    failing_value=_format_value(value),
                    row_index=idx,
                    reason="non-numeric value cannot be range-checked",
                    at=at,
                )
            )
            continue
        if lo is not None and value < lo:
            out.append(
                DQException(
                    contract_id=contract_id,
                    check_id=f"range:{column}",
                    check_type="range",
                    column=column,
                    failing_value=_format_value(value),
                    row_index=idx,
                    reason=(f"column '{column}' value {value!r} below min {lo!r} at row {idx}"),
                    at=at,
                )
            )
            continue
        if hi is not None and value > hi:
            out.append(
                DQException(
                    contract_id=contract_id,
                    check_id=f"range:{column}",
                    check_type="range",
                    column=column,
                    failing_value=_format_value(value),
                    row_index=idx,
                    reason=(f"column '{column}' value {value!r} above max {hi!r} at row {idx}"),
                    at=at,
                )
            )
    return out
