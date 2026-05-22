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
        # evaluator should not crash on `enum`/`range`/etc.
        rows = [{"x": 1}]
        checks = [{"enum": {"x": [1, 2]}}, {"range": {"x": {"min": 0}}}]
        assert evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF) == []

    def test_unique_ignores_nulls(self):
        # Multiple null values must not collide on the unique check —
        # nulls are not equal under SQL UNIQUE semantics.
        rows = [{"x": None}, {"x": None}, {"x": "a"}]
        checks = [{"unique": ["x"]}]
        assert evaluate_contract_checks(rows, checks, contract_id="c", at=_AS_OF) == []


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
