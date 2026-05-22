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
