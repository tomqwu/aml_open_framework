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

A `malformed_check` synthetic check_type fires when a KNOWN check
type carries the wrong value shape (e.g. `enum: ["currency"]` instead
of `enum: {currency: [...]}`). `quality_checks` is currently untyped
in both the JSON Schema and the Pydantic model, so the misuse passes
`aml validate` cleanly — without this signal a typo would silently
disable a compliance check. Codex review (B1 pass 8). Truly unknown
check_types stay a silent skip for forward-compat with future
dialects.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Numeric types accepted by range checks. `Decimal` is included because
# CSV-backed contract columns of type `decimal` are loaded as
# `decimal.Decimal` (see `data/sources.py`); excluding it would falsely
# flag every monetary amount as `non-numeric`. `bool` is deliberately
# excluded below — `isinstance(True, int)` is True, but a True/False in
# a numeric column is almost certainly a defect.
_NUMERIC_TYPES = (int, float, Decimal)

DQCheckType = Literal["not_null", "unique", "enum", "regex", "range", "malformed_check"]


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
    if not checks:
        # No declared checks → nothing to evaluate at all. Empty `rows`
        # alone is NOT a short-circuit: a malformed spec must surface
        # even on an empty feed (codex review B1 pass 9).
        return []

    timestamp = at if at is not None else datetime.now(tz=timezone.utc)
    exceptions: list[DQException] = []

    for qc in checks:
        for check_type, fields in qc.items():
            if check_type in ("not_null", "unique"):
                # Existing shape: list of column names.
                if not isinstance(fields, list):
                    # Fail closed (B1 codex pass 8): a known check_type
                    # with a wrong-shaped value would otherwise be a
                    # silently-ignored compliance check. Emit a
                    # malformed-spec DQ exception so the audit ledger
                    # records the missed coverage.
                    exceptions.append(
                        _malformed_check_exception(
                            contract_id,
                            check_type,
                            fields,
                            timestamp,
                            expected="list of column names",
                        )
                    )
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
                # (range).
                if not isinstance(fields, dict):
                    # Same fail-closed posture: a spec carrying
                    # `enum: [currency]` (list, not dict) would silently
                    # do nothing. Surface it as a malformed-spec event.
                    exceptions.append(
                        _malformed_check_exception(
                            contract_id,
                            check_type,
                            fields,
                            timestamp,
                            expected="dict of {column: check_spec}",
                        )
                    )
                    continue
                for column, spec in fields.items():
                    if check_type == "enum":
                        exceptions.extend(_eval_enum(rows, contract_id, column, spec, timestamp))
                    elif check_type == "regex":
                        exceptions.extend(_eval_regex(rows, contract_id, column, spec, timestamp))
                    else:
                        exceptions.extend(_eval_range(rows, contract_id, column, spec, timestamp))
            else:
                # Forward-compat: unknown check shape (a future dialect)
                # stays a silent skip — only KNOWN types fail closed.
                continue

    return exceptions


def _malformed_check_exception(
    contract_id: str,
    check_type: str,
    fields: Any,
    at: datetime,
    *,
    expected: str,
) -> DQException:
    """Build a DQ exception for a known check_type with a wrong-shaped value.

    Codex review (B1 pass 8): `quality_checks` is untyped in the JSON
    Schema and Pydantic, so a spec like `quality_checks: [{enum: [currency]}]`
    (list where the engine expects a dict) survives `aml validate`. Without
    this signal the misuse silently disables a compliance check. Emitting a
    `dq_exception` with `check_type="malformed_check"` and a synthetic
    `check_id` keeps the malfeasance visible in `dq_exceptions.jsonl`,
    `decisions.jsonl`, and the manifest hash chain.

    `row_index` is `None` because the violation is about the spec, not a row.
    The actual `check_type` (enum/regex/range/etc.) is encoded into `column`
    and `reason` so consumers can attribute it without us having to widen
    the `DQCheckType` Literal.
    """
    # `failing_value` summarises the offending shape — class name + length
    # hint where it helps. Do NOT include the raw `fields` value: it may
    # contain plaintext that hasn't been masked (column names declared
    # `pii: true` would still surface here).
    shape_hint = type(fields).__name__
    if isinstance(fields, (list, tuple, dict, set)):
        shape_hint = f"{shape_hint}(len={len(fields)})"
    return DQException(
        contract_id=contract_id,
        check_id=f"malformed_check:{check_type}",
        check_type="malformed_check",
        column=check_type,
        failing_value=shape_hint,
        row_index=None,
        reason=(
            f"malformed quality_check: '{check_type}' expects {expected}, "
            f"got {shape_hint} — check is silently disabled until fixed"
        ),
        at=at,
    )


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
    enum's. `allowed` must be a list/tuple; a non-list allow-list is
    a spec typo and surfaces as a `malformed_check` event so the
    misuse isn't a silent compliance gap (codex B1 pass 9).
    """
    if not isinstance(allowed, (list, tuple)):
        return [
            _malformed_check_exception(
                contract_id,
                f"enum:{column}",
                allowed,
                at,
                expected="list of allowed values",
            )
        ]
    allowed_set = list(allowed)  # preserve list semantics for reason text
    out: list[DQException] = []
    for idx, row in enumerate(rows):
        if column not in row:
            continue
        value = row[column]
        if value is None:
            continue
        if value not in allowed_set:
            # PII-safety: do NOT embed the raw `value` in `reason`. The
            # runner's `_maybe_mask_dq_exception` only masks
            # `failing_value`; a raw value in `reason` would still leak
            # to `dq_exceptions.jsonl` and `decisions.jsonl` when the
            # column is `pii: true` and `AML_PII_MASKING=1`. The
            # allowed-set is config, not data, so embedding it is safe.
            out.append(
                DQException(
                    contract_id=contract_id,
                    check_id=f"enum:{column}",
                    check_type="enum",
                    column=column,
                    failing_value=_format_value(value),
                    row_index=idx,
                    reason=(
                        f"column '{column}' value not in allowed set {allowed_set!r} at row {idx}"
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
        return [
            _malformed_check_exception(
                contract_id,
                f"regex:{column}",
                pattern,
                at,
                expected="regex pattern string",
            )
        ]
    try:
        compiled = re.compile(pattern)
    except re.error:
        # Malformed pattern in spec — surface as a `malformed_check`
        # event rather than crash the whole run. Spec-loader-side
        # validation is a separate concern, but the audit ledger must
        # at least record the silent disablement (codex B1 pass 9).
        return [
            _malformed_check_exception(
                contract_id,
                f"regex:{column}",
                pattern,
                at,
                expected="valid Python regex pattern",
            )
        ]
    out: list[DQException] = []
    for idx, row in enumerate(rows):
        if column not in row:
            continue
        value = row[column]
        if value is None:
            continue
        if not isinstance(value, str) or compiled.fullmatch(value) is None:
            # PII-safety: do NOT embed raw `value` in `reason` — the
            # runner masks `failing_value` for `pii: true` columns but
            # not the reason text. Pattern is config, safe to include.
            out.append(
                DQException(
                    contract_id=contract_id,
                    check_id=f"regex:{column}",
                    check_type="regex",
                    column=column,
                    failing_value=_format_value(value),
                    row_index=idx,
                    reason=(
                        f"column '{column}' value does not fullmatch "
                        f"pattern {pattern!r} at row {idx}"
                    ),
                    at=at,
                )
            )
    return out


def _coerce_bound(bound: Any) -> Decimal | None:
    """Coerce a spec-declared range bound to a `Decimal` for comparison.

    `quality_checks` entries are untyped in both the JSON Schema and
    Pydantic at this revision, so a spec can carry a quoted bound like
    `range: {amount: {min: "0"}}` and validate cleanly. Comparing a
    numeric row value against a string bound raises `TypeError` at
    `<`/`>` time and aborts the whole `aml run`. Coerce here so a
    malformed bound becomes "no bound that side" rather than a crash.

    Returns `None` when the bound is `None` (not provided), can't be
    coerced to a number, or coerces to a non-finite Decimal
    (`NaN`/`Inf` — e.g. `min: .nan` in YAML or `min: "NaN"`). Non-
    finite bounds would otherwise still raise `decimal.InvalidOperation`
    at compare time and abort `aml run`. Codex review (B1 pass 3).
    """
    if bound is None:
        return None
    if isinstance(bound, bool):
        # Reject bools the same way we reject them as values — almost
        # certainly a contract defect, not a real bound.
        return None
    if isinstance(bound, Decimal):
        result = bound
    elif isinstance(bound, (int, float)):
        try:
            result = Decimal(str(bound))
        except Exception:
            return None
    elif isinstance(bound, str):
        try:
            result = Decimal(bound)
        except Exception:
            return None
    else:
        return None
    # Filter non-finite (`NaN`, `Inf`, `-Inf`) — these bounds are
    # uncomparable and would crash the `<`/`>` step.
    if not result.is_finite():
        return None
    return result


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

    `Decimal` IS accepted as numeric — CSV-backed contract columns of
    `type: decimal` are loaded as `decimal.Decimal` (see
    `data/sources.py`), so excluding it would falsely flag every
    monetary amount as `non-numeric` in real runs.
    """
    if not isinstance(bounds, dict):
        return [
            _malformed_check_exception(
                contract_id,
                f"range:{column}",
                bounds,
                at,
                expected="dict with optional 'min' / 'max' numeric bounds",
            )
        ]
    # Detect typoed bound keys (`minimum`/`maximum`/`lo`/etc.) — a
    # non-empty bounds dict that carries NO recognised key is almost
    # certainly a spec typo, not an intentional no-op. The
    # `quality_checks` shape is untyped at the spec layer so the
    # misuse passes `aml validate`; surfacing a `malformed_check`
    # event keeps it out of the silent-disablement category. Codex
    # review (B1 pass 11).
    recognised_keys = {"min", "max"}
    unknown_keys = set(bounds.keys()) - recognised_keys
    if bounds and not (recognised_keys & bounds.keys()):
        return [
            _malformed_check_exception(
                contract_id,
                f"range:{column}",
                bounds,
                at,
                expected=f"'min' and/or 'max' keys (got {sorted(unknown_keys)!r})",
            )
        ]
    raw_lo = bounds.get("min")
    raw_hi = bounds.get("max")
    lo = _coerce_bound(raw_lo)
    hi = _coerce_bound(raw_hi)
    # Surface the inner-spec malformed case: at least one bound was
    # declared but neither coerces. A truly bound-less `range: {}`
    # (`raw_lo is None and raw_hi is None`) is still a silent no-op
    # — there's nothing to check (codex B1 pass 9).
    if lo is None and hi is None:
        if raw_lo is None and raw_hi is None:
            return []
        return [
            _malformed_check_exception(
                contract_id,
                f"range:{column}",
                bounds,
                at,
                expected="at least one finite numeric bound (min and/or max)",
            )
        ]
    out: list[DQException] = []
    for idx, row in enumerate(rows):
        if column not in row:
            continue
        value = row[column]
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, _NUMERIC_TYPES):
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
        # Cross-type compare via `Decimal` so int/float/Decimal all play
        # together without a `decimal.InvalidOperation` or surprise
        # precision skew. `Decimal(str(float))` is the safe path.
        if isinstance(value, Decimal):
            value_dec = value
        else:
            value_dec = Decimal(str(value))
        # Non-finite values (`float('nan')` / `Decimal('NaN')` / `Inf`)
        # pass the numeric type check but raise `decimal.InvalidOperation`
        # on `<`/`>` for NaN — aborting the whole DQ scan and `aml run`.
        # Treat them as a range violation: clearly the row carries no
        # comparable numeric, so the spec author should see it in the
        # exception table rather than have the run crash. Codex review
        # (B1 pass 2).
        if not value_dec.is_finite():
            out.append(
                DQException(
                    contract_id=contract_id,
                    check_id=f"range:{column}",
                    check_type="range",
                    column=column,
                    failing_value=_format_value(value),
                    row_index=idx,
                    reason="non-finite value cannot be range-checked",
                    at=at,
                )
            )
            continue
        # PII-safety: do NOT embed raw `value` in `reason` — runner
        # masks `failing_value` for `pii: true` columns. Bounds are
        # config, safe to include.
        if lo is not None and value_dec < lo:
            out.append(
                DQException(
                    contract_id=contract_id,
                    check_id=f"range:{column}",
                    check_type="range",
                    column=column,
                    failing_value=_format_value(value),
                    row_index=idx,
                    reason=(f"column '{column}' value below min {lo!r} at row {idx}"),
                    at=at,
                )
            )
            continue
        if hi is not None and value_dec > hi:
            out.append(
                DQException(
                    contract_id=contract_id,
                    check_id=f"range:{column}",
                    check_type="range",
                    column=column,
                    failing_value=_format_value(value),
                    row_index=idx,
                    reason=(f"column '{column}' value above max {hi!r} at row {idx}"),
                    at=at,
                )
            )
    return out
