"""Engine-time data-quality exception evaluator (B4 — #369).

Covers:
- pure evaluator (`evaluate_contract_checks`) for `not_null` + `unique`;
- empty inputs degrade gracefully;
- the runner writes `dq_exceptions.jsonl` to the run dir;
- determinism: same inputs produce identical exception list;
- **observability-only contract**: rows in the warehouse after
  `_build_warehouse` match input row count exactly — no drops;
- audit-ledger hash chain stays valid after `dq_exception` events
  land in `decisions.jsonl`.
"""

from __future__ import annotations

import json
from datetime import date as _date, datetime, timezone
from pathlib import Path

import duckdb

from aml_framework.engine.audit import AuditLedger
from aml_framework.engine.dq import DQException, evaluate_contract_checks
from aml_framework.engine.runner import _build_warehouse, run_spec
from aml_framework.spec.loader import load_spec
from aml_framework.spec.models import (
    AggregationWindowLogic,
    AMLSpec,
    Column,
    DataContract,
    Program,
    Queue,
    RegulationRef,
    Rule,
    Workflow,
)


_AS_OF = datetime(2026, 5, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Pure evaluator unit tests
# ---------------------------------------------------------------------------


class TestEvaluateContractChecksPure:
    def test_not_null_flags_single_none(self):
        rows = [
            {"email": "a@example.com"},
            {"email": None},
            {"email": "c@example.com"},
        ]
        checks = [{"not_null": ["email"]}]

        excs = evaluate_contract_checks(rows, checks, contract_id="customer", at=_AS_OF)

        assert len(excs) == 1
        exc = excs[0]
        assert exc.check_type == "not_null"
        assert exc.column == "email"
        assert exc.row_index == 1
        assert exc.failing_value is None
        assert exc.check_id == "not_null:email"
        assert "email" in exc.reason
        assert exc.contract_id == "customer"

    def test_unique_flags_second_occurrence_only(self):
        rows = [
            {"txn_id": "T0001"},
            {"txn_id": "T0002"},
            {"txn_id": "T0001"},  # duplicate of row 0
        ]
        checks = [{"unique": ["txn_id"]}]

        excs = evaluate_contract_checks(rows, checks, contract_id="txn", at=_AS_OF)

        # Only one exception — the SECOND occurrence is the duplicate.
        assert len(excs) == 1
        exc = excs[0]
        assert exc.check_type == "unique"
        assert exc.column == "txn_id"
        assert exc.row_index == 2
        assert exc.failing_value == "T0001"
        assert exc.check_id == "unique:txn_id"

    def test_empty_rows_and_checks_yields_no_exceptions(self):
        # Both empty.
        assert evaluate_contract_checks([], [], contract_id="x", at=_AS_OF) == []
        # Empty rows, non-empty checks.
        assert (
            evaluate_contract_checks([], [{"not_null": ["foo"]}], contract_id="x", at=_AS_OF) == []
        )
        # Non-empty rows, empty checks.
        assert evaluate_contract_checks([{"foo": 1}], [], contract_id="x", at=_AS_OF) == []

    def test_does_not_mutate_input_rows(self):
        # Defensive sentinel: the evaluator must NEVER touch the rows
        # list (Option B in #369 — observability only).
        rows = [{"email": None}, {"email": "ok"}]
        snapshot = [dict(r) for r in rows]
        evaluate_contract_checks(rows, [{"not_null": ["email"]}], contract_id="c", at=_AS_OF)
        assert rows == snapshot

    def test_determinism_two_evaluations_match(self):
        rows = [{"txn_id": "T1"}, {"txn_id": "T1"}, {"txn_id": "T2"}, {"txn_id": "T2"}]
        checks = [{"unique": ["txn_id"]}]
        a = evaluate_contract_checks(rows, checks, contract_id="t", at=_AS_OF)
        b = evaluate_contract_checks(rows, checks, contract_id="t", at=_AS_OF)
        assert [e.model_dump() for e in a] == [e.model_dump() for e in b]

    def test_unknown_check_type_is_skipped_silently(self):
        # Forward-compat: spec dialect may grow new check shapes; the
        # evaluator should not crash on unknown keys. After PR-B1
        # (#366) `enum` and `range` are known shapes, so we use a
        # truly unknown key here. The inputs to the known checks are
        # valid (value `1` is in `[1, 2]` and >= `0`) and would emit
        # no exceptions anyway.
        rows = [{"x": 1}]
        checks = [
            {"future_check_type_we_dont_know_yet": ["x"]},
            {"enum": {"x": [1, 2]}},
            {"range": {"x": {"min": 0}}},
        ]
        assert evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF) == []

    def test_unique_ignores_nulls(self):
        # Multiple null values must not collide on the unique check —
        # nulls are not equal under SQL UNIQUE semantics.
        rows = [{"x": None}, {"x": None}, {"x": "a"}]
        checks = [{"unique": ["x"]}]
        assert evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF) == []

    def test_not_null_treats_missing_key_as_null(self):
        # A row dict that omits the checked column entirely must report
        # a not_null violation (not a silent skip). `_build_warehouse`
        # materializes the column as None in DuckDB and dashboard surfaces
        # already count `isna()` rows; the engine-time artifact must
        # match. Issue #369 codex pass.
        rows = [
            {"email": "a@example.com"},
            {},  # missing key entirely
            {"email": None},  # explicit None
            {"email": "d@example.com"},
        ]
        checks = [{"not_null": ["email"]}]
        excs = evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF)
        assert [(e.row_index, e.failing_value) for e in excs] == [(1, None), (2, None)]

    # -----------------------------------------------------------------
    # PR-B1 (#366) — enum / regex / range validity checks
    # -----------------------------------------------------------------

    def test_enum_flags_value_not_in_list(self):
        rows = [
            {"currency": "USD"},
            {"currency": "XYZ"},  # not allowed
            {"currency": "CAD"},
        ]
        checks = [{"enum": {"currency": ["USD", "CAD", "EUR"]}}]
        excs = evaluate_contract_checks(rows, checks, contract_id="txn", at=_AS_OF)
        assert len(excs) == 1
        exc = excs[0]
        assert exc.check_type == "enum"
        assert exc.column == "currency"
        assert exc.row_index == 1
        assert exc.failing_value == "XYZ"
        assert exc.check_id == "enum:currency"

    def test_enum_passes_when_value_in_list(self):
        rows = [{"currency": "USD"}, {"currency": "CAD"}, {"currency": "EUR"}]
        checks = [{"enum": {"currency": ["USD", "CAD", "EUR"]}}]
        assert evaluate_contract_checks(rows, checks, contract_id="txn", at=_AS_OF) == []

    def test_enum_skips_missing_key(self):
        # Missing key is NOT an enum violation — that's `not_null`'s job.
        # Same posture for an explicit `None`.
        rows = [
            {"currency": "USD"},
            {},  # missing entirely
            {"currency": None},  # explicit None
        ]
        checks = [{"enum": {"currency": ["USD", "CAD"]}}]
        assert evaluate_contract_checks(rows, checks, contract_id="txn", at=_AS_OF) == []

    def test_regex_flags_pattern_mismatch(self):
        rows = [
            {"email": "ok@example.com"},
            {"email": "not-an-email"},
        ]
        checks = [{"regex": {"email": r"^[^@]+@[^@]+\.[^@]+$"}}]
        excs = evaluate_contract_checks(rows, checks, contract_id="customer", at=_AS_OF)
        assert len(excs) == 1
        exc = excs[0]
        assert exc.check_type == "regex"
        assert exc.column == "email"
        assert exc.row_index == 1
        assert exc.failing_value == "not-an-email"
        assert exc.check_id == "regex:email"

    def test_regex_uses_fullmatch_semantics(self):
        # Partial match must FAIL — a value that satisfies `re.search`
        # but not `re.fullmatch` is a violation. Pattern is "must be 3
        # lowercase letters"; the second row has trailing junk that
        # `search` would let through but `fullmatch` rejects.
        rows = [
            {"code": "abc"},
            {"code": "abc-trailing-junk"},
        ]
        checks = [{"regex": {"code": r"[a-z]{3}"}}]
        excs = evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF)
        assert len(excs) == 1
        assert excs[0].row_index == 1
        assert excs[0].failing_value == "abc-trailing-junk"

    def test_range_flags_below_min(self):
        rows = [{"amount": 50.0}, {"amount": -1.0}]
        checks = [{"range": {"amount": {"min": 0, "max": 1000000}}}]
        excs = evaluate_contract_checks(rows, checks, contract_id="txn", at=_AS_OF)
        assert len(excs) == 1
        exc = excs[0]
        assert exc.check_type == "range"
        assert exc.column == "amount"
        assert exc.row_index == 1
        assert exc.failing_value == "-1.0"
        assert "below min" in exc.reason
        assert exc.check_id == "range:amount"

    def test_range_flags_above_max(self):
        rows = [{"amount": 50.0}, {"amount": 2_000_000.0}]
        checks = [{"range": {"amount": {"min": 0, "max": 1000000}}}]
        excs = evaluate_contract_checks(rows, checks, contract_id="txn", at=_AS_OF)
        assert len(excs) == 1
        exc = excs[0]
        assert exc.row_index == 1
        assert "above max" in exc.reason

    def test_range_min_only_allows_above(self):
        # `{min: 0}` means "value >= 0, no upper bound" — a very large
        # value must pass.
        rows = [{"amount": -5.0}, {"amount": 10.0}, {"amount": 10_000_000_000.0}]
        checks = [{"range": {"amount": {"min": 0}}}]
        excs = evaluate_contract_checks(rows, checks, contract_id="txn", at=_AS_OF)
        assert len(excs) == 1
        assert excs[0].row_index == 0  # only the negative violates

    def test_range_max_only_allows_below(self):
        # `{max: 100}` means "value <= 100, no lower bound" — a very
        # negative value must pass.
        rows = [{"amount": -1_000_000.0}, {"amount": 50.0}, {"amount": 1000.0}]
        checks = [{"range": {"amount": {"max": 100}}}]
        excs = evaluate_contract_checks(rows, checks, contract_id="txn", at=_AS_OF)
        assert len(excs) == 1
        assert excs[0].row_index == 2  # only the 1000.0 > 100 violates

    def test_range_flags_non_numeric_value(self):
        rows = [{"amount": 50.0}, {"amount": "not-a-number"}]
        checks = [{"range": {"amount": {"min": 0, "max": 1000000}}}]
        excs = evaluate_contract_checks(rows, checks, contract_id="txn", at=_AS_OF)
        assert len(excs) == 1
        exc = excs[0]
        assert exc.check_type == "range"
        assert exc.row_index == 1
        assert exc.failing_value == "not-a-number"
        assert exc.reason == "non-numeric value cannot be range-checked"

    def test_range_accepts_decimal_values(self):
        # CSV-backed contract columns of `type: decimal` are loaded as
        # `decimal.Decimal` via `data/sources.py`; the range evaluator
        # must accept them as numeric, not mis-flag them as non-numeric.
        # Codex review (B1 pass 1).
        from decimal import Decimal

        rows = [
            {"amount": Decimal("50.00")},  # in range
            {"amount": Decimal("-1.00")},  # below min
            {"amount": Decimal("2000000.00")},  # above max
        ]
        checks = [{"range": {"amount": {"min": 0, "max": 1000000}}}]
        excs = evaluate_contract_checks(rows, checks, contract_id="txn", at=_AS_OF)
        # In-range Decimal must NOT fire; below-min and above-max must.
        types_and_indices = sorted((e.row_index, e.reason) for e in excs)
        assert len(excs) == 2
        assert types_and_indices[0][0] == 1
        assert "below min" in types_and_indices[0][1]
        assert types_and_indices[1][0] == 2
        assert "above max" in types_and_indices[1][1]
        # And the in-range Decimal must NOT have been mis-flagged as non-numeric.
        for exc in excs:
            assert exc.reason != "non-numeric value cannot be range-checked"

    def test_range_string_bound_does_not_crash(self):
        # `quality_checks` is untyped at the spec layer — a careless
        # spec can carry a quoted bound like `{"min": "0"}`. The
        # evaluator must coerce it (or skip the bound), never raise
        # `TypeError` from `<`/`>` against an int row value and abort
        # the whole `aml run`. Codex review (B1 pass 1).
        rows = [{"amount": 5}, {"amount": -1}]
        checks = [{"range": {"amount": {"min": "0", "max": "1000000"}}}]
        # Must not raise.
        excs = evaluate_contract_checks(rows, checks, contract_id="txn", at=_AS_OF)
        # And the coerced bound must still work: -1 < 0 → below min.
        assert len(excs) == 1
        assert excs[0].row_index == 1
        assert "below min" in excs[0].reason

    def test_range_garbage_bound_is_treated_as_no_bound(self):
        # An uncoerceable bound (e.g. a dict where a number was
        # expected) is treated as "no bound that side" — the check
        # silently becomes a no-op for that side rather than crashing.
        rows = [{"amount": -1}, {"amount": 5}]
        # `min` is garbage → only the `max` side is enforced; nothing
        # exceeds 100, so no violations.
        checks = [{"range": {"amount": {"min": {"nope": True}, "max": 100}}}]
        assert evaluate_contract_checks(rows, checks, contract_id="txn", at=_AS_OF) == []

    def test_enum_reason_does_not_embed_failing_value(self):
        # PII-safety: `reason` must NOT carry the raw failing value;
        # the runner only masks `failing_value`, not `reason`. Codex
        # review (B1 pass 1).
        rows = [{"currency": "SECRET-VALUE"}]
        checks = [{"enum": {"currency": ["USD", "CAD"]}}]
        excs = evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF)
        assert len(excs) == 1
        assert "SECRET-VALUE" not in excs[0].reason
        # The masked-side carrier is `failing_value`, which is still
        # populated (runner masks it when the column is PII).
        assert excs[0].failing_value == "SECRET-VALUE"

    def test_regex_reason_does_not_embed_failing_value(self):
        # PII-safety: same posture as enum — pattern is config, safe;
        # raw value must not appear in `reason`. Codex review (B1 pass 1).
        rows = [{"email": "secret-pii-value"}]
        checks = [{"regex": {"email": r"^[^@]+@[^@]+\.[^@]+$"}}]
        excs = evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF)
        assert len(excs) == 1
        assert "secret-pii-value" not in excs[0].reason
        assert excs[0].failing_value == "secret-pii-value"

    def test_range_reason_does_not_embed_failing_value(self):
        # PII-safety: bounds in `reason` are config, safe; the raw
        # numeric value must not appear in `reason` so it can't slip
        # past the runner's `failing_value`-only mask on a `pii: true`
        # numeric column. Codex review (B1 pass 1).
        rows = [{"amount": 999999.42}]
        checks = [{"range": {"amount": {"min": 0, "max": 100}}}]
        excs = evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF)
        assert len(excs) == 1
        assert "999999.42" not in excs[0].reason
        assert excs[0].failing_value == "999999.42"

    def test_range_rejects_non_finite_bound_without_crashing(self):
        # A spec with `min: "NaN"` or `min: .nan` (YAML) would survive
        # the untyped quality_checks shape; the previous coercion
        # returned `Decimal('NaN')` which then raised
        # `decimal.InvalidOperation` against any real numeric row.
        # Filter non-finite bounds back to None so the malformed side
        # becomes unbounded rather than crashing the run. Codex review
        # (B1 pass 3).
        rows = [{"amount": 50.0}, {"amount": -100.0}, {"amount": 1_000_000.0}]
        # String-NaN min, real max → only the max side enforces.
        checks = [{"range": {"amount": {"min": "NaN", "max": 100}}}]
        excs = evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF)
        # Only the 1_000_000 row exceeds 100; the -100 row would have
        # violated a real min but the NaN bound was rejected.
        assert len(excs) == 1
        assert excs[0].row_index == 2
        assert "above max" in excs[0].reason

    def test_range_rejects_infinity_bound_without_crashing(self):
        # `Inf` / `-Inf` bounds are uncomparable too — also treat as
        # unusable. Codex review (B1 pass 3 + pass 9): the run must
        # not crash, AND it must surface the all-uncoerceable bounds
        # as a `malformed_check` event so the silent disablement
        # lands in the audit ledger.
        from decimal import Decimal

        rows = [{"amount": 50.0}, {"amount": -100.0}]
        checks = [{"range": {"amount": {"min": Decimal("-Infinity"), "max": Decimal("Infinity")}}}]
        excs = evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF)
        # Both bounds were DECLARED (raw_lo/raw_hi non-None) but
        # neither coerces — that's a spec bug, not a no-op. Engine
        # emits one malformed_check event for the column.
        assert len(excs) == 1
        assert excs[0].check_type == "malformed_check"
        assert excs[0].check_id == "malformed_check:range:amount"

    def test_malformed_enum_shape_emits_dq_exception(self):
        # `quality_checks: [{enum: [currency]}]` is a real footgun:
        # spec author meant `{enum: {currency: [...]}}`. The list shape
        # would silently disable the enum check. Engine must surface it
        # as a `malformed_check` DQ exception so the audit ledger
        # records the missed coverage. Codex review (B1 pass 8).
        rows = [{"currency": "USD"}, {"currency": "XYZ"}]
        # WRONG: enum value is a list (should be a dict).
        checks = [{"enum": ["currency"]}]
        excs = evaluate_contract_checks(rows, checks, contract_id="txn", at=_AS_OF)
        assert len(excs) == 1
        exc = excs[0]
        assert exc.check_type == "malformed_check"
        assert exc.check_id == "malformed_check:enum"
        assert exc.column == "enum"
        assert exc.row_index is None
        assert "malformed" in exc.reason
        assert "enum" in exc.reason

    def test_malformed_not_null_shape_emits_dq_exception(self):
        # `quality_checks: [{not_null: {email: True}}]` — meant a list.
        rows = [{"email": None}, {"email": "a@example.com"}]
        checks = [{"not_null": {"email": True}}]
        excs = evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF)
        assert len(excs) == 1
        exc = excs[0]
        assert exc.check_type == "malformed_check"
        assert exc.check_id == "malformed_check:not_null"

    def test_malformed_range_shape_emits_dq_exception(self):
        # `quality_checks: [{range: ["amount"]}]` — meant a dict.
        rows = [{"amount": -5}, {"amount": 1_000_000_000}]
        checks = [{"range": ["amount"]}]
        excs = evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF)
        assert len(excs) == 1
        assert excs[0].check_type == "malformed_check"
        assert excs[0].check_id == "malformed_check:range"

    def test_truly_unknown_check_type_still_silently_skipped(self):
        # A check_type the engine doesn't recognise (future dialect)
        # stays a silent skip — only KNOWN-but-malformed shapes fail
        # closed. Codex review (B1 pass 8) confirms this posture.
        rows = [{"x": 1}]
        checks = [{"some_future_check": ["x"]}]
        assert evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF) == []

    def test_malformed_check_surfaces_even_on_empty_feed(self):
        # An empty feed must NOT silently disable malformed-spec
        # detection — the spec bug is in the spec, not the data, and
        # a regulator-facing compliance check that silently does
        # nothing is the worst kind of false assurance. Codex review
        # (B1 pass 9).
        rows = []  # zero rows
        # Outer-shape malformed (list where dict expected):
        checks = [{"enum": ["currency"]}]
        excs = evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF)
        assert len(excs) == 1
        assert excs[0].check_type == "malformed_check"
        assert excs[0].check_id == "malformed_check:enum"

    def test_inner_malformed_enum_spec_emits_event(self):
        # Inner-spec malformed: `enum: {currency: "USD"}` — the value
        # should be a list, not a string. Without the codex pass-9
        # fix the engine would silently emit no exceptions and the
        # dashboard would show PASS for a disabled check. Now we get
        # a malformed_check event that surfaces in the audit ledger
        # and gives the dashboard something to render as FAIL.
        rows = [{"currency": "USD"}]
        checks = [{"enum": {"currency": "USD"}}]  # string, not list
        excs = evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF)
        assert len(excs) == 1
        assert excs[0].check_type == "malformed_check"
        assert excs[0].check_id == "malformed_check:enum:currency"

    def test_inner_malformed_regex_pattern_emits_event(self):
        # Non-string pattern.
        rows = [{"email": "a@example.com"}]
        checks = [{"regex": {"email": 42}}]  # int, not str
        excs = evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF)
        assert len(excs) == 1
        assert excs[0].check_type == "malformed_check"
        assert excs[0].check_id == "malformed_check:regex:email"

    def test_inner_malformed_regex_invalid_pattern_emits_event(self):
        # Syntactically invalid regex.
        rows = [{"email": "a@example.com"}]
        checks = [{"regex": {"email": "[unclosed"}}]
        excs = evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF)
        assert len(excs) == 1
        assert excs[0].check_type == "malformed_check"
        assert excs[0].check_id == "malformed_check:regex:email"

    def test_inner_malformed_range_bounds_emits_event(self):
        # Non-dict bounds.
        rows = [{"amount": 50}]
        checks = [{"range": {"amount": "0-100"}}]  # string, not dict
        excs = evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF)
        assert len(excs) == 1
        assert excs[0].check_type == "malformed_check"
        assert excs[0].check_id == "malformed_check:range:amount"

    def test_inner_malformed_range_typoed_bound_keys_emits_event(self):
        # Typoed bound keys like `minimum`/`maximum` would silently
        # disable a range check before pass 11 — bounds dict has no
        # recognised key so both raw_lo/raw_hi are None and the path
        # exited as a no-op. Surface the typo via `malformed_check`.
        # Codex review (B1 pass 11).
        rows = [{"amount": 50}, {"amount": -100}]
        checks = [{"range": {"amount": {"minimum": 0, "maximum": 1000000}}}]
        excs = evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF)
        assert len(excs) == 1
        assert excs[0].check_type == "malformed_check"
        assert excs[0].check_id == "malformed_check:range:amount"
        # Reason mentions the unknown keys so operators see the typo.
        assert "minimum" in excs[0].reason and "maximum" in excs[0].reason

    def test_inner_range_empty_bounds_dict_is_silent_noop(self):
        # `range: {amount: {}}` carries NO bound at all — this is the
        # "intentional no-op" path, not a typo. No malformed_check
        # event, no row violations.
        rows = [{"amount": 50}, {"amount": -100}]
        checks = [{"range": {"amount": {}}}]
        assert evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF) == []

    def test_range_handles_nan_and_infinity_without_crashing(self):
        # `float('nan')` and `Decimal('NaN')` pass the type guard but
        # raise `decimal.InvalidOperation` on `<`/`>` — that would abort
        # the whole DQ scan and `aml run`. Codex review (B1 pass 2).
        # Treat non-finite as a range violation, never an exception.
        from decimal import Decimal

        rows = [
            {"amount": float("nan")},
            {"amount": Decimal("NaN")},
            {"amount": float("inf")},
            {"amount": 50.0},  # clean baseline
        ]
        checks = [{"range": {"amount": {"min": 0, "max": 100}}}]
        # Must not raise.
        excs = evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF)
        # Three non-finite values → three range violations; clean row
        # produces nothing.
        assert len(excs) == 3
        reasons = {e.reason for e in excs}
        assert reasons == {"non-finite value cannot be range-checked"}


# ---------------------------------------------------------------------------
# `_build_warehouse` is unchanged: row counts match input
# ---------------------------------------------------------------------------


class TestBuildWarehouseRowCountUnchanged:
    """B4 contract: no row drops, no mutation. The DQ scan runs *after*
    `_build_warehouse`; the warehouse table must contain exactly the
    rows we fed in, even when DQ violations exist."""

    def _spec_with_txn_contract(self) -> AMLSpec:
        return AMLSpec(
            version=1,
            program=Program(
                name="T",
                jurisdiction="US",
                regulator="FinCEN",
                owner="MLRO",
                effective_date=_date(2026, 1, 1),
            ),
            data_contracts=[
                DataContract(
                    id="txn",
                    source="t",
                    columns=[
                        Column(name="txn_id", type="string", nullable=False),
                        Column(name="customer_id", type="string", nullable=False),
                        Column(name="amount", type="decimal", nullable=False),
                        Column(name="booked_at", type="timestamp", nullable=False),
                    ],
                    quality_checks=[{"unique": ["txn_id"]}],
                ),
            ],
            rules=[
                Rule(
                    id="r",
                    name="R",
                    severity="low",
                    regulation_refs=[RegulationRef(citation="x", description="x")],
                    logic=AggregationWindowLogic(
                        type="aggregation_window",
                        source="txn",
                        group_by=["customer_id"],
                        window="7d",
                        having={"count": {"gte": 1}},
                    ),
                    escalate_to="q1",
                    evidence=[],
                )
            ],
            workflow=Workflow(queues=[Queue(id="q1", sla="24h")]),
        )

    def test_warehouse_row_count_equals_input_count_with_dq_violations(self):
        spec = self._spec_with_txn_contract()
        # Two duplicates on txn_id; warehouse must still hold all 4 rows.
        data = {
            "txn": [
                {"txn_id": "T1", "customer_id": "C1", "amount": 10.0, "booked_at": _AS_OF},
                {"txn_id": "T1", "customer_id": "C2", "amount": 20.0, "booked_at": _AS_OF},
                {"txn_id": "T2", "customer_id": "C3", "amount": 30.0, "booked_at": _AS_OF},
                {"txn_id": "T2", "customer_id": "C4", "amount": 40.0, "booked_at": _AS_OF},
            ],
        }
        con = duckdb.connect(":memory:")
        _build_warehouse(con, spec, data)
        (count,) = con.execute("SELECT COUNT(*) FROM txn").fetchone()
        assert count == 4, "build_warehouse must not drop rows even with DQ failures"

        # Sanity check the evaluator agrees those duplicates exist.
        excs = evaluate_contract_checks(
            data["txn"],
            spec.data_contracts[0].quality_checks,
            contract_id="txn",
            at=_AS_OF,
        )
        assert len(excs) == 2, "expected 2 duplicate exceptions for txn_id"


# ---------------------------------------------------------------------------
# Engine integration: artifact + ledger entries
# ---------------------------------------------------------------------------


class TestEngineEmitsDQExceptions:
    def _spec_with_unique_violation(self) -> AMLSpec:
        return AMLSpec(
            version=1,
            program=Program(
                name="T",
                jurisdiction="US",
                regulator="FinCEN",
                owner="MLRO",
                effective_date=_date(2026, 1, 1),
            ),
            data_contracts=[
                DataContract(
                    id="txn",
                    source="t",
                    columns=[
                        Column(name="txn_id", type="string", nullable=False),
                        Column(name="customer_id", type="string", nullable=False),
                        Column(name="amount", type="decimal", nullable=False),
                        Column(name="booked_at", type="timestamp", nullable=False),
                    ],
                    quality_checks=[{"unique": ["txn_id"]}, {"not_null": ["customer_id"]}],
                ),
            ],
            rules=[
                Rule(
                    id="r",
                    name="R",
                    severity="low",
                    regulation_refs=[RegulationRef(citation="x", description="x")],
                    logic=AggregationWindowLogic(
                        type="aggregation_window",
                        source="txn",
                        group_by=["customer_id"],
                        window="365d",
                        having={"count": {"gte": 1}},
                    ),
                    escalate_to="q1",
                    evidence=[],
                )
            ],
            workflow=Workflow(queues=[Queue(id="q1", sla="24h")]),
        )

    def _data_with_one_dup(self) -> dict:
        # Two rows share txn_id "T1" — one unique-violation exception expected.
        return {
            "txn": [
                {"txn_id": "T1", "customer_id": "C1", "amount": 10.0, "booked_at": _AS_OF},
                {"txn_id": "T1", "customer_id": "C2", "amount": 20.0, "booked_at": _AS_OF},
                {"txn_id": "T2", "customer_id": "C3", "amount": 30.0, "booked_at": _AS_OF},
            ],
        }

    def test_dq_exceptions_jsonl_written_with_expected_content(self, tmp_path: Path):
        spec = self._spec_with_unique_violation()
        data = self._data_with_one_dup()

        # We need a real spec_path on disk because `run_spec` SHA-256s it.
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text("placeholder: 1\n", encoding="utf-8")

        run_spec(
            spec=spec,
            spec_path=spec_path,
            data=data,
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )

        run_dirs = sorted(tmp_path.glob("run-*"))
        assert run_dirs, "expected a run directory"
        run_dir = run_dirs[-1]
        dq_path = run_dir / "dq_exceptions.jsonl"
        assert dq_path.exists(), "dq_exceptions.jsonl must always be written"

        lines = [ln for ln in dq_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == 1, "expected one DQ exception (the duplicate)"
        rec = json.loads(lines[0])
        assert rec["check_type"] == "unique"
        assert rec["column"] == "txn_id"
        assert rec["row_index"] == 1
        assert rec["failing_value"] == "T1"

    def test_dq_exception_emitted_to_decisions_jsonl_with_intact_hash_chain(self, tmp_path: Path):
        spec = self._spec_with_unique_violation()
        data = self._data_with_one_dup()

        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text("placeholder: 1\n", encoding="utf-8")

        run_spec(
            spec=spec,
            spec_path=spec_path,
            data=data,
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )

        run_dir = sorted(tmp_path.glob("run-*"))[-1]

        # The ledger must include the new event type.
        decisions = (run_dir / "decisions.jsonl").read_text(encoding="utf-8")
        dq_events = [
            json.loads(ln)
            for ln in decisions.splitlines()
            if ln.strip() and json.loads(ln).get("event") == "dq_exception"
        ]
        assert len(dq_events) == 1
        ev = dq_events[0]
        assert ev["contract_id"] == "txn"
        assert ev["check_type"] == "unique"
        assert ev["column"] == "txn_id"

        # And the hash chain must still verify against the manifest.
        ok, msg = AuditLedger.verify_decisions(run_dir)
        assert ok, f"hash chain broken after dq_exception events: {msg}"

    def test_run_is_deterministic_across_two_runs(self, tmp_path: Path):
        spec = self._spec_with_unique_violation()
        data = self._data_with_one_dup()

        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text("placeholder: 1\n", encoding="utf-8")

        out_a = tmp_path / "a"
        out_b = tmp_path / "b"
        out_a.mkdir()
        out_b.mkdir()

        run_spec(spec=spec, spec_path=spec_path, data=data, as_of=_AS_OF, artifacts_root=out_a)
        run_spec(spec=spec, spec_path=spec_path, data=data, as_of=_AS_OF, artifacts_root=out_b)

        run_a = sorted(out_a.glob("run-*"))[-1]
        run_b = sorted(out_b.glob("run-*"))[-1]
        assert (run_a / "dq_exceptions.jsonl").read_bytes() == (
            run_b / "dq_exceptions.jsonl"
        ).read_bytes()

    def test_dq_scan_runs_before_warehouse_so_not_null_violations_are_caught(self, tmp_path: Path):
        """`_build_warehouse` declares columns with DuckDB NOT NULL when
        `nullable: false`. If the DQ scan ran AFTER the warehouse build,
        a not_null violation on such a column would crash the insert
        before the evaluator could log it. This test pins the ordering:
        a row with a null `customer_id` (declared `nullable=False`)
        must surface as a `dq_exception` ledger event, not as an
        uncaught DuckDB constraint error.

        Issue #369 — codex review pass 2.
        """
        spec = self._spec_with_unique_violation()
        # Row 1 has customer_id=None; the contract declares it as
        # not_null + nullable=False — both DuckDB and the DQ scan would
        # reject it. The DQ scan must win (run first).
        data = {
            "txn": [
                {"txn_id": "T1", "customer_id": "C1", "amount": 10.0, "booked_at": _AS_OF},
                {"txn_id": "T2", "customer_id": None, "amount": 20.0, "booked_at": _AS_OF},
            ],
        }

        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text("placeholder: 1\n", encoding="utf-8")

        # The run is allowed to fail at the warehouse layer AFTER the DQ
        # event lands; what matters is that `dq_exceptions.jsonl` carries
        # the not_null violation. We swallow the downstream raise so the
        # observability artifact can be checked.
        try:
            run_spec(
                spec=spec,
                spec_path=spec_path,
                data=data,
                as_of=_AS_OF,
                artifacts_root=tmp_path,
            )
        except Exception:
            pass

        run_dir = sorted(tmp_path.glob("run-*"))[-1]
        dq_path = run_dir / "dq_exceptions.jsonl"
        assert dq_path.exists()
        lines = [ln for ln in dq_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        not_null_events = [
            json.loads(ln) for ln in lines if json.loads(ln)["check_type"] == "not_null"
        ]
        assert any(
            ev["column"] == "customer_id" and ev["row_index"] == 1 for ev in not_null_events
        ), f"expected a not_null customer_id violation pre-warehouse; got {not_null_events}"

    def test_manifest_pins_dq_exceptions_hash_and_event_carries_queue_field(self, tmp_path: Path):
        """Two regulator-side hardening guarantees (issue #369 codex pass 4):

        1. `manifest.json` pins a SHA-256 of `dq_exceptions.jsonl` so the
           DQ artifact can't be edited post-finalization while
           `verify_decisions()` still passes.
        2. `dq_exception` decision rows carry a `queue` field (None) so
           the My Queue dashboard's `df_decisions["queue"]` indexer
           doesn't `KeyError` on DQ-only runs.
        """
        spec = self._spec_with_unique_violation()
        data = self._data_with_one_dup()

        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text("placeholder: 1\n", encoding="utf-8")

        run_spec(
            spec=spec,
            spec_path=spec_path,
            data=data,
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )

        run_dir = sorted(tmp_path.glob("run-*"))[-1]

        # Guarantee 1 — manifest pins the artifact digest.
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        import hashlib

        dq_bytes = (run_dir / "dq_exceptions.jsonl").read_bytes()
        expected = hashlib.sha256(dq_bytes).hexdigest()
        assert manifest["dq_exceptions_hash"] == expected, (
            "manifest must pin SHA-256 of dq_exceptions.jsonl for tamper detection"
        )

        # Guarantee 2 — every dq_exception event carries `queue` field.
        decisions = (run_dir / "decisions.jsonl").read_text(encoding="utf-8")
        dq_events = [
            json.loads(ln)
            for ln in decisions.splitlines()
            if ln.strip() and json.loads(ln).get("event") == "dq_exception"
        ]
        assert dq_events, "expected at least one dq_exception event"
        for ev in dq_events:
            assert "queue" in ev, f"dq_exception event missing `queue` field: {ev}"
            assert ev["queue"] is None, f"dq_exception `queue` should be None, got {ev['queue']!r}"

    def test_dq_failing_value_masked_when_pii_masking_enabled(self, tmp_path: Path, monkeypatch):
        """When `AML_PII_MASKING=1` and a `unique` violation fires on a
        column marked `pii: true`, the persisted `failing_value` must
        be the HMAC-SHA256 hash, not the raw plaintext — otherwise the
        observability artifact leaks PII that the rest of the audit
        ledger has already masked.

        Issue #369 — codex review pass 3.
        """
        spec = AMLSpec(
            version=1,
            program=Program(
                name="T",
                jurisdiction="US",
                regulator="FinCEN",
                owner="MLRO",
                effective_date=_date(2026, 1, 1),
            ),
            data_contracts=[
                DataContract(
                    id="txn",
                    source="t",
                    columns=[
                        Column(name="txn_id", type="string", nullable=False),
                        # customer_id is the PII column the violation fires on.
                        Column(name="customer_id", type="string", nullable=False, pii=True),
                        Column(name="amount", type="decimal", nullable=False),
                        Column(name="booked_at", type="timestamp", nullable=False),
                    ],
                    quality_checks=[{"unique": ["customer_id"]}],
                ),
            ],
            rules=[
                Rule(
                    id="r",
                    name="R",
                    severity="low",
                    regulation_refs=[RegulationRef(citation="x", description="x")],
                    logic=AggregationWindowLogic(
                        type="aggregation_window",
                        source="txn",
                        group_by=["customer_id"],
                        window="365d",
                        having={"count": {"gte": 1}},
                    ),
                    escalate_to="q1",
                    evidence=[],
                )
            ],
            workflow=Workflow(queues=[Queue(id="q1", sla="24h")]),
        )
        # Two rows with the same customer_id — duplicate must surface
        # as a `unique` exception. The raw plaintext value would
        # ordinarily land in `failing_value`.
        plaintext = "C-CONFIDENTIAL-001"
        data = {
            "txn": [
                {"txn_id": "T1", "customer_id": plaintext, "amount": 10.0, "booked_at": _AS_OF},
                {"txn_id": "T2", "customer_id": plaintext, "amount": 20.0, "booked_at": _AS_OF},
            ],
        }
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text("placeholder: 1\n", encoding="utf-8")

        monkeypatch.setenv("AML_PII_MASKING", "1")
        run_spec(
            spec=spec,
            spec_path=spec_path,
            data=data,
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )

        run_dir = sorted(tmp_path.glob("run-*"))[-1]
        dq_path = run_dir / "dq_exceptions.jsonl"
        lines = [ln for ln in dq_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == 1, f"expected one unique violation; got {lines}"
        rec = json.loads(lines[0])
        # Plaintext must NOT appear; failing_value must be a 16-char hex
        # hash (same length _pii_mask_value emits).
        assert rec["failing_value"] != plaintext
        assert rec["failing_value"] is not None
        assert len(rec["failing_value"]) == 16
        assert all(c in "0123456789abcdef" for c in rec["failing_value"])

        # And the dq_exception decisions.jsonl entries must carry the
        # masked value too — the ledger is the regulator-facing
        # artifact, so DQ events cannot leak. (case_id contains
        # plaintext in other entries — that's a pre-existing alert-id
        # construction concern outside #369's scope.)
        decisions = (run_dir / "decisions.jsonl").read_text(encoding="utf-8")
        dq_lines = [
            ln
            for ln in decisions.splitlines()
            if ln.strip() and json.loads(ln).get("event") == "dq_exception"
        ]
        for ln in dq_lines:
            assert plaintext not in ln, f"dq_exception ledger entry leaked plaintext PII: {ln}"

    def test_all_five_check_types_emit_and_pin(self, tmp_path: Path):
        """PR-B1 (#366) integration: a contract carrying all five quality_checks
        kinds (not_null, unique, enum, regex, range) fires the expected
        exceptions, writes them to `dq_exceptions.jsonl`, records a
        `dq_exception` event for each in `decisions.jsonl`, and the
        artifact digest is pinned in `manifest.json` so the new shapes
        inherit tamper detection from PR-B4.
        """
        spec = AMLSpec(
            version=1,
            program=Program(
                name="T",
                jurisdiction="US",
                regulator="FinCEN",
                owner="MLRO",
                effective_date=_date(2026, 1, 1),
            ),
            data_contracts=[
                DataContract(
                    id="txn",
                    source="t",
                    columns=[
                        Column(name="txn_id", type="string", nullable=False),
                        Column(name="customer_id", type="string", nullable=False),
                        Column(name="amount", type="decimal", nullable=False),
                        Column(name="currency", type="string", nullable=False),
                        Column(name="email", type="string", nullable=True),
                        Column(name="booked_at", type="timestamp", nullable=False),
                    ],
                    quality_checks=[
                        {"not_null": ["customer_id"]},
                        {"unique": ["txn_id"]},
                        {"enum": {"currency": ["USD", "CAD", "EUR"]}},
                        {"regex": {"email": r"^[^@]+@[^@]+\.[^@]+$"}},
                        {"range": {"amount": {"min": 0, "max": 1000000}}},
                    ],
                ),
            ],
            rules=[
                Rule(
                    id="r",
                    name="R",
                    severity="low",
                    regulation_refs=[RegulationRef(citation="x", description="x")],
                    logic=AggregationWindowLogic(
                        type="aggregation_window",
                        source="txn",
                        group_by=["customer_id"],
                        window="365d",
                        having={"count": {"gte": 1}},
                    ),
                    escalate_to="q1",
                    evidence=[],
                )
            ],
            workflow=Workflow(queues=[Queue(id="q1", sla="24h")]),
        )
        # Plant exactly one violation per check type:
        #   row 0: clean baseline
        #   row 1: txn_id duplicates row 0  → unique
        #   row 2: currency "XYZ"           → enum
        #   row 3: email "bad-email"        → regex
        #   row 4: amount -10               → range (below min)
        # Note: keep customer_id non-null on every row so we don't
        # crash the warehouse build before the integration check; the
        # not_null shape is still exercised by other tests in this file.
        data = {
            "txn": [
                {
                    "txn_id": "T1",
                    "customer_id": "C1",
                    "amount": 10.0,
                    "currency": "USD",
                    "email": "a@example.com",
                    "booked_at": _AS_OF,
                },
                {
                    "txn_id": "T1",  # duplicate → unique violation
                    "customer_id": "C2",
                    "amount": 20.0,
                    "currency": "USD",
                    "email": "b@example.com",
                    "booked_at": _AS_OF,
                },
                {
                    "txn_id": "T2",
                    "customer_id": "C3",
                    "amount": 30.0,
                    "currency": "XYZ",  # enum violation
                    "email": "c@example.com",
                    "booked_at": _AS_OF,
                },
                {
                    "txn_id": "T3",
                    "customer_id": "C4",
                    "amount": 40.0,
                    "currency": "CAD",
                    "email": "bad-email",  # regex violation
                    "booked_at": _AS_OF,
                },
                {
                    "txn_id": "T4",
                    "customer_id": "C5",
                    "amount": -10.0,  # range violation
                    "currency": "EUR",
                    "email": "e@example.com",
                    "booked_at": _AS_OF,
                },
            ],
        }

        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text("placeholder: 1\n", encoding="utf-8")

        run_spec(
            spec=spec,
            spec_path=spec_path,
            data=data,
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )

        run_dir = sorted(tmp_path.glob("run-*"))[-1]
        dq_path = run_dir / "dq_exceptions.jsonl"
        assert dq_path.exists()

        lines = [ln for ln in dq_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        recs = [json.loads(ln) for ln in lines]
        by_type = {r["check_type"] for r in recs}
        # All four planted shapes must have fired (we deliberately kept
        # customer_id populated so not_null wouldn't crash the warehouse;
        # the other 4 shapes must fire).
        assert {"unique", "enum", "regex", "range"} <= by_type, (
            f"missing one of the planted check_type violations: got {by_type!r}"
        )
        # And we planted exactly one violation each.
        assert sum(1 for r in recs if r["check_type"] == "unique") == 1
        assert sum(1 for r in recs if r["check_type"] == "enum") == 1
        assert sum(1 for r in recs if r["check_type"] == "regex") == 1
        assert sum(1 for r in recs if r["check_type"] == "range") == 1

        # Each emitted exception must surface as a `dq_exception` event
        # in decisions.jsonl with matching check_type.
        decisions = (run_dir / "decisions.jsonl").read_text(encoding="utf-8")
        dq_events = [
            json.loads(ln)
            for ln in decisions.splitlines()
            if ln.strip() and json.loads(ln).get("event") == "dq_exception"
        ]
        assert len(dq_events) == len(recs)
        assert {ev["check_type"] for ev in dq_events} == by_type

        # The manifest digest must pin the new artifact contents so
        # enum/regex/range exceptions inherit tamper detection from B4.
        import hashlib

        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        expected = hashlib.sha256(dq_path.read_bytes()).hexdigest()
        assert manifest["dq_exceptions_hash"] == expected

        # Hash chain still valid with the new event types in the mix.
        ok, msg = AuditLedger.verify_decisions(run_dir)
        assert ok, f"hash chain broken with B1 check-type events: {msg}"

    def test_dq_exception_artifact_is_empty_for_clean_canadian_spec(self, tmp_path: Path):
        """End-to-end smoke test on the canonical demo spec: the canned
        synthetic data is clean by design, so the artifact should exist
        but be empty (0 lines)."""
        from aml_framework.data.synthetic import generate_dataset

        src = (
            Path(__file__).resolve().parents[1]
            / "examples"
            / "canadian_schedule_i_bank"
            / "aml.yaml"
        )
        spec = load_spec(src)
        data = generate_dataset(as_of=_AS_OF, seed=42)
        run_spec(
            spec=spec,
            spec_path=src,
            data=data,
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )
        run_dir = sorted(tmp_path.glob("run-*"))[-1]
        dq_path = run_dir / "dq_exceptions.jsonl"
        assert dq_path.exists()
        assert dq_path.read_bytes() == b"", "demo spec is clean — expect zero DQ exceptions"


# ---------------------------------------------------------------------------
# DQException model invariants
# ---------------------------------------------------------------------------


def test_dq_exception_is_frozen_extra_forbid():
    exc = DQException(
        contract_id="c",
        check_id="not_null:x",
        check_type="not_null",
        column="x",
        reason="r",
        at=_AS_OF,
    )
    # Frozen — should refuse mutation.
    import pytest

    with pytest.raises(Exception):
        exc.contract_id = "other"  # type: ignore[misc]
    # extra="forbid" — unknown field at construction raises.
    with pytest.raises(Exception):
        DQException(
            contract_id="c",
            check_id="x",
            check_type="not_null",
            column="x",
            reason="r",
            at=_AS_OF,
            unknown_field="boom",  # type: ignore[call-arg]
        )


# ---------------------------------------------------------------------------
# PR-B5 (#370) — DQ severity model on quality_checks
# ---------------------------------------------------------------------------


class TestDQSeverityPropagation:
    """Severity declared on a `quality_checks` entry must thread into every
    `DQException` the entry produces. Default is `"high"` when omitted,
    preserving prior uniform-severity behaviour.
    """

    def test_default_severity_is_high_when_omitted(self):
        rows = [{"email": None}]
        checks = [{"not_null": ["email"]}]
        excs = evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF)
        assert len(excs) == 1
        assert excs[0].severity == "high"

    def test_severity_critical_propagates_through_not_null(self):
        rows = [{"customer_id": None}, {"customer_id": "C1"}]
        checks = [{"not_null": ["customer_id"], "severity": "critical"}]
        excs = evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF)
        assert len(excs) == 1
        assert excs[0].severity == "critical"
        assert excs[0].check_type == "not_null"

    def test_severity_info_propagates_through_regex(self):
        # Non-canonical phone format is the canonical "info" example
        # from issue #370 — the check fires but should not block triage.
        rows = [{"phone": "abc-not-a-phone"}]
        checks = [
            {"regex": {"phone": r"^\+?[0-9]{10,15}$"}, "severity": "info"},
        ]
        excs = evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF)
        assert len(excs) == 1
        assert excs[0].severity == "info"
        assert excs[0].check_type == "regex"

    def test_severity_low_propagates_through_enum(self):
        rows = [{"currency": "XYZ"}]
        checks = [{"enum": {"currency": ["USD", "CAD"]}, "severity": "low"}]
        excs = evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF)
        assert len(excs) == 1
        assert excs[0].severity == "low"
        assert excs[0].check_type == "enum"

    def test_severity_medium_propagates_through_range(self):
        rows = [{"amount": 999.0}]
        checks = [{"range": {"amount": {"min": 0, "max": 100}}, "severity": "medium"}]
        excs = evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF)
        assert len(excs) == 1
        assert excs[0].severity == "medium"
        assert excs[0].check_type == "range"

    def test_severity_critical_propagates_through_unique(self):
        rows = [{"txn_id": "T1"}, {"txn_id": "T1"}]
        checks = [{"unique": ["txn_id"], "severity": "critical"}]
        excs = evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF)
        assert len(excs) == 1
        assert excs[0].severity == "critical"
        assert excs[0].check_type == "unique"

    def test_severity_is_per_entry_not_global(self):
        # Two checks on the same contract with different severities —
        # each DQException carries its OWN entry's tier.
        rows = [{"a": None, "b": None}]
        checks = [
            {"not_null": ["a"], "severity": "critical"},
            {"not_null": ["b"], "severity": "info"},
        ]
        excs = evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF)
        by_col = {e.column: e.severity for e in excs}
        assert by_col == {"a": "critical", "b": "info"}

    def test_severity_threads_to_every_violation_in_entry(self):
        # Two violations from the same entry both pick up the entry's severity.
        rows = [{"x": None}, {"x": None}, {"x": "ok"}]
        checks = [{"not_null": ["x"], "severity": "low"}]
        excs = evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF)
        assert len(excs) == 2
        assert all(e.severity == "low" for e in excs)

    def test_severity_threads_to_malformed_check_emission(self):
        # `enum: [list]` (should be dict) emits a `malformed_check`
        # exception — the entry's severity must still ride along.
        checks = [{"enum": ["currency"], "severity": "critical"}]
        excs = evaluate_contract_checks([{"currency": "USD"}], checks, contract_id="c", at=_AS_OF)
        assert len(excs) == 1
        assert excs[0].check_type == "malformed_check"
        assert excs[0].severity == "critical"

    def test_unrecognised_severity_value_falls_back_to_default(self):
        # PR-B5 chose fallback-to-default rather than raise: an unknown
        # severity value would otherwise force every spec to declare one,
        # which is out of scope for this additive-only PR.
        rows = [{"x": None}]
        checks = [{"not_null": ["x"], "severity": "URGENT"}]  # not a valid tier
        excs = evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF)
        assert len(excs) == 1
        assert excs[0].severity == "high"  # default, not "URGENT"

    def test_severity_key_does_not_emit_as_check(self):
        # The outer loop iterates qc.items() — `severity` is metadata,
        # not a check_type. It must NOT generate a stray exception.
        rows = [{"email": "ok@example.com"}]
        checks = [{"severity": "critical"}]  # severity only, no checks
        excs = evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF)
        assert excs == []

    def test_dq_exception_severity_field_is_frozen(self):
        # Field is on the frozen Pydantic model — mutation must raise.
        import pytest

        exc = DQException(
            contract_id="c",
            check_id="not_null:email",
            check_type="not_null",
            column="email",
            reason="r",
            severity="critical",
            at=_AS_OF,
        )
        assert exc.severity == "critical"
        with pytest.raises(Exception):
            exc.severity = "low"  # type: ignore[misc]

    def test_dq_exception_rejects_invalid_severity_literal(self):
        # The Literal-typed `DQSeverity` field rejects out-of-set values.
        # This pins the contract: only the 5 declared tiers are accepted
        # at the model boundary (callers that construct directly).
        import pytest

        with pytest.raises(Exception):
            DQException(
                contract_id="c",
                check_id="x",
                check_type="not_null",
                column="x",
                reason="r",
                severity="URGENT",  # type: ignore[arg-type]
                at=_AS_OF,
            )

    def test_quality_check_typed_model_default_severity(self):
        # The typed `QualityCheck` model in spec.models pins the default.
        from aml_framework.spec.models import QualityCheck

        qc = QualityCheck()
        assert qc.severity == "high"

    def test_quality_check_typed_model_accepts_check_type_siblings(self):
        # `extra="allow"` is intentional: the wrapper carries any
        # check-type key (not_null/unique/enum/...) without each
        # becoming a hard-coded field.
        from aml_framework.spec.models import QualityCheck

        qc = QualityCheck.model_validate({"not_null": ["email"], "severity": "critical"})
        assert qc.severity == "critical"
        # Dump round-trips the extra payload so engine-side iteration sees it.
        dumped = qc.model_dump()
        assert dumped["not_null"] == ["email"]
        assert dumped["severity"] == "critical"

    def test_dq_exceptions_jsonl_carries_severity(self, tmp_path: Path):
        # End-to-end: severity declared on the spec entry must surface
        # in the on-disk `dq_exceptions.jsonl` artifact.
        spec = AMLSpec(
            version=1,
            program=Program(
                name="T",
                jurisdiction="US",
                regulator="FinCEN",
                owner="MLRO",
                effective_date=_date(2026, 1, 1),
            ),
            data_contracts=[
                DataContract(
                    id="txn",
                    source="t",
                    columns=[
                        Column(name="txn_id", type="string", nullable=False),
                        Column(name="customer_id", type="string", nullable=False),
                        Column(name="amount", type="decimal", nullable=False),
                        Column(name="booked_at", type="timestamp", nullable=False),
                    ],
                    quality_checks=[{"unique": ["txn_id"], "severity": "critical"}],
                ),
            ],
            rules=[
                Rule(
                    id="r",
                    name="R",
                    severity="low",
                    regulation_refs=[RegulationRef(citation="x", description="x")],
                    logic=AggregationWindowLogic(
                        type="aggregation_window",
                        source="txn",
                        group_by=["customer_id"],
                        window="365d",
                        having={"count": {"gte": 1}},
                    ),
                    escalate_to="q1",
                    evidence=[],
                ),
            ],
            workflow=Workflow(queues=[Queue(id="q1", sla="24h")]),
        )
        data = {
            "txn": [
                {"txn_id": "T1", "customer_id": "C1", "amount": 10.0, "booked_at": _AS_OF},
                {"txn_id": "T1", "customer_id": "C2", "amount": 20.0, "booked_at": _AS_OF},
            ],
        }
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text("placeholder: 1\n", encoding="utf-8")
        run_spec(
            spec=spec,
            spec_path=spec_path,
            data=data,
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )
        run_dir = sorted(tmp_path.glob("run-*"))[-1]
        dq_path = run_dir / "dq_exceptions.jsonl"
        lines = [ln for ln in dq_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert rec["severity"] == "critical"
        assert rec["check_type"] == "unique"
