"""Pillar-2 defect log artifact + lifecycle (PR-C1 — issues #371, #372, #373).

Covers:
- Pydantic model invariants (`Defect` frozen + extra="forbid").
- Enum coverage: 11 ``DefectCategory``, 3 ``DefectClassification``, 5
  ``DefectSeverity``, 5 ``DefectStatus``.
- ``classify_defect`` decision-tree routing for every known DQ
  check_type + the unknown-fallback.
- ``build_defect_log`` derivation from DQ exceptions, python_ref
  failures, and both combined.
- Empty-inputs edge case → empty defect list.
- Byte-stable JSONL output (sort_keys=True).
- ``write_defect_log`` always writes (even when empty).
- Engine integration: ``defect_log.jsonl`` artifact written, manifest
  pins ``defect_log_hash``, artifact frozen post-finalize.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import date as _date, datetime, timezone
from pathlib import Path

import pytest

from aml_framework.engine.audit import _FROZEN_SNAPSHOT_TARGETS
from aml_framework.engine.defect_log import (
    Defect,
    DefectCategory,
    DefectClassification,
    DefectSeverity,
    DefectStatus,
    build_defect_log,
    classify_defect,
    derive_run_id,
    write_defect_log,
)
from aml_framework.engine.dq import DQException
from aml_framework.engine.runner import run_spec
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


def _exc(
    *,
    check_type: str,
    column: str = "amount",
    row_index: int | None = 0,
    failing_value: str | None = None,
    reason: str | None = None,
    contract_id: str = "txn",
) -> DQException:
    return DQException(
        contract_id=contract_id,
        check_id=f"{check_type}:{column}",
        check_type=check_type,  # type: ignore[arg-type]
        column=column,
        failing_value=failing_value,
        row_index=row_index,
        reason=reason or f"{check_type} failure on {column}",
        at=_AS_OF,
    )


# ---------------------------------------------------------------------------
# Enum coverage
# ---------------------------------------------------------------------------


class TestEnumCoverage:
    def test_defect_category_has_eleven_values(self):
        # Issue #372 — exactly 11 categories.
        assert len(list(DefectCategory)) == 11

    def test_defect_category_includes_expected_values(self):
        expected = {
            "data_quality",
            "rule_logic",
            "mapping",
            "threshold",
            "lineage",
            "metric",
            "spec_config",
            "external",
            "runtime",
            "sanctions_ref",
            "typology_coverage",
        }
        assert {c.value for c in DefectCategory} == expected

    def test_defect_classification_has_three_values(self):
        # Issue #373 — data / rule / mapping triage decision tree.
        assert {c.value for c in DefectClassification} == {"data", "rule", "mapping"}

    def test_defect_severity_has_five_values(self):
        assert {s.value for s in DefectSeverity} == {
            "critical",
            "high",
            "medium",
            "low",
            "info",
        }

    def test_defect_status_has_five_values(self):
        assert {s.value for s in DefectStatus} == {
            "open",
            "acknowledged",
            "resolved",
            "closed",
            "wont_fix",
        }


# ---------------------------------------------------------------------------
# Pydantic model invariants
# ---------------------------------------------------------------------------


class TestDefectModel:
    def _defect_kwargs(self) -> dict:
        return dict(
            id="defect:run-x:0001:not_null:amount",
            category=DefectCategory.DATA_QUALITY,
            classification=DefectClassification.DATA,
            severity=DefectSeverity.MEDIUM,
            summary="column 'amount' is null on row 0",
            detected_by="dq.evaluator",
            source_run_id="run-x",
            created_at=_AS_OF,
            status=DefectStatus.OPEN,
        )

    def test_defect_is_frozen(self):
        d = Defect(**self._defect_kwargs())
        with pytest.raises(Exception):
            d.status = DefectStatus.RESOLVED  # type: ignore[misc]

    def test_defect_forbids_extra_fields(self):
        kwargs = self._defect_kwargs()
        kwargs["surprise"] = "extra"
        with pytest.raises(Exception):
            Defect(**kwargs)  # type: ignore[arg-type]

    def test_defect_status_defaults_to_open(self):
        kwargs = self._defect_kwargs()
        kwargs.pop("status")
        d = Defect(**kwargs)
        assert d.status == DefectStatus.OPEN

    def test_defect_serializes_enums_as_strings(self):
        d = Defect(**self._defect_kwargs())
        payload = d.model_dump(mode="json")
        assert payload["category"] == "data_quality"
        assert payload["classification"] == "data"
        assert payload["severity"] == "medium"
        assert payload["status"] == "open"


# ---------------------------------------------------------------------------
# classify_defect — issue #373 decision tree
# ---------------------------------------------------------------------------


class TestClassifyDefect:
    def test_not_null_routes_to_data_quality_data(self):
        cat, cls = classify_defect(_exc(check_type="not_null"))
        assert cat == DefectCategory.DATA_QUALITY
        assert cls == DefectClassification.DATA

    def test_unique_routes_to_data_quality_data(self):
        cat, cls = classify_defect(_exc(check_type="unique", failing_value="T1"))
        assert (cat, cls) == (DefectCategory.DATA_QUALITY, DefectClassification.DATA)

    def test_enum_routes_to_data_quality_data(self):
        cat, cls = classify_defect(_exc(check_type="enum"))
        assert (cat, cls) == (DefectCategory.DATA_QUALITY, DefectClassification.DATA)

    def test_regex_routes_to_data_quality_data(self):
        cat, cls = classify_defect(_exc(check_type="regex"))
        assert (cat, cls) == (DefectCategory.DATA_QUALITY, DefectClassification.DATA)

    def test_range_routes_to_data_quality_data(self):
        cat, cls = classify_defect(_exc(check_type="range"))
        assert (cat, cls) == (DefectCategory.DATA_QUALITY, DefectClassification.DATA)

    def test_malformed_check_routes_to_spec_config_mapping(self):
        # The spec itself is wrong — not the feed. Classification flips.
        cat, cls = classify_defect(_exc(check_type="malformed_check"))
        assert cat == DefectCategory.SPEC_CONFIG
        assert cls == DefectClassification.MAPPING


# ---------------------------------------------------------------------------
# build_defect_log
# ---------------------------------------------------------------------------


class TestBuildDefectLog:
    def test_empty_inputs_return_empty_list(self):
        out = build_defect_log(
            run_id="run-x",
            dq_exceptions=[],
            python_ref_failures={},
            created_at=_AS_OF,
        )
        assert out == []

    def test_none_python_ref_failures_handled(self):
        # Defensive — runners may pass None when there were no scorers.
        out = build_defect_log(
            run_id="run-x",
            dq_exceptions=[],
            python_ref_failures=None,
            created_at=_AS_OF,
        )
        assert out == []

    def test_one_dq_exception_becomes_one_defect(self):
        exc = _exc(check_type="not_null", column="amount", row_index=3)
        out = build_defect_log(
            run_id="run-x",
            dq_exceptions=[exc],
            created_at=_AS_OF,
        )
        assert len(out) == 1
        d = out[0]
        assert d.category == DefectCategory.DATA_QUALITY
        assert d.classification == DefectClassification.DATA
        assert d.severity == DefectSeverity.MEDIUM
        assert d.summary == exc.reason
        assert d.detected_by == "dq.evaluator"
        assert d.source_run_id == "run-x"
        assert d.created_at == _AS_OF
        assert d.status == DefectStatus.OPEN
        assert d.id.startswith("defect:run-x:0000:not_null:amount")

    def test_dq_severity_unique_is_high(self):
        exc = _exc(check_type="unique", column="txn_id", failing_value="T1")
        out = build_defect_log(run_id="run-x", dq_exceptions=[exc], created_at=_AS_OF)
        assert out[0].severity == DefectSeverity.HIGH

    def test_dq_severity_malformed_check_is_high(self):
        exc = _exc(check_type="malformed_check", column="enum", failing_value="list(len=1)")
        out = build_defect_log(run_id="run-x", dq_exceptions=[exc], created_at=_AS_OF)
        assert out[0].severity == DefectSeverity.HIGH
        assert out[0].category == DefectCategory.SPEC_CONFIG
        assert out[0].classification == DefectClassification.MAPPING

    def test_python_ref_failures_yield_rule_logic_defects(self):
        out = build_defect_log(
            run_id="run-x",
            dq_exceptions=[],
            python_ref_failures={"r_ml_score": "RuntimeError: model missing"},
            created_at=_AS_OF,
        )
        assert len(out) == 1
        d = out[0]
        assert d.category == DefectCategory.RULE_LOGIC
        assert d.classification == DefectClassification.RULE
        assert d.severity == DefectSeverity.HIGH
        assert "r_ml_score" in d.summary
        assert "RuntimeError" in d.summary
        assert d.detected_by == "engine.runner.python_ref"

    def test_mixed_sources_combined_deterministically(self):
        excs = [
            _exc(check_type="not_null", column="amount", row_index=0),
            _exc(check_type="unique", column="txn_id", failing_value="T1", row_index=2),
        ]
        ref_failures = {"r_b": "boom", "r_a": "boom2"}
        out = build_defect_log(
            run_id="run-x",
            dq_exceptions=excs,
            python_ref_failures=ref_failures,
            created_at=_AS_OF,
        )
        # Two DQ defects + two python_ref defects.
        assert len(out) == 4
        # DQ defects come first (input order); python_ref defects sorted
        # by rule_id so the artifact is dict-order-invariant.
        assert out[0].category == DefectCategory.DATA_QUALITY
        assert out[1].category == DefectCategory.DATA_QUALITY
        assert out[2].category == DefectCategory.RULE_LOGIC
        assert "r_a" in out[2].summary
        assert "r_b" in out[3].summary

    def test_defect_ids_are_unique_for_repeated_check_id(self):
        # Two row-level violations sharing check_id — position index
        # disambiguates the defect id.
        excs = [
            _exc(check_type="not_null", column="amount", row_index=0),
            _exc(check_type="not_null", column="amount", row_index=1),
        ]
        out = build_defect_log(run_id="run-x", dq_exceptions=excs, created_at=_AS_OF)
        assert len({d.id for d in out}) == 2

    def test_created_at_pinned_when_provided(self):
        pinned = datetime(2025, 1, 1, tzinfo=timezone.utc)
        excs = [_exc(check_type="not_null")]
        out = build_defect_log(run_id="run-x", dq_exceptions=excs, created_at=pinned)
        assert out[0].created_at == pinned


# ---------------------------------------------------------------------------
# write_defect_log
# ---------------------------------------------------------------------------


class TestWriteDefectLog:
    def test_writes_empty_file_when_no_defects(self, tmp_path: Path):
        path = write_defect_log(tmp_path, [])
        assert path == tmp_path / "defect_log.jsonl"
        assert path.exists()
        assert path.read_bytes() == b""

    def test_writes_one_line_per_defect(self, tmp_path: Path):
        excs = [
            _exc(check_type="not_null", column="amount", row_index=0),
            _exc(check_type="unique", column="txn_id", failing_value="T1", row_index=2),
        ]
        defects = build_defect_log(run_id="run-x", dq_exceptions=excs, created_at=_AS_OF)
        path = write_defect_log(tmp_path, defects)
        text = path.read_text(encoding="utf-8")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        assert len(lines) == 2
        # Each line is valid JSON.
        for line in lines:
            json.loads(line)

    def test_output_is_byte_stable_across_writes(self, tmp_path: Path):
        # Same defects → same bytes (manifest-hash determinism contract).
        excs = [_exc(check_type="enum", column="currency")]
        defects = build_defect_log(run_id="run-x", dq_exceptions=excs, created_at=_AS_OF)
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        write_defect_log(a, defects)
        write_defect_log(b, defects)
        bytes_a = (a / "defect_log.jsonl").read_bytes()
        bytes_b = (b / "defect_log.jsonl").read_bytes()
        assert bytes_a == bytes_b

    def test_jsonl_records_use_sorted_keys(self, tmp_path: Path):
        excs = [_exc(check_type="not_null", column="amount", row_index=0)]
        defects = build_defect_log(run_id="run-x", dq_exceptions=excs, created_at=_AS_OF)
        write_defect_log(tmp_path, defects)
        line = (tmp_path / "defect_log.jsonl").read_text(encoding="utf-8").splitlines()[0]
        # Re-encoding with sort_keys should match the on-disk bytes.
        rec = json.loads(line)
        assert line == json.dumps(rec, sort_keys=True, default=str)


# ---------------------------------------------------------------------------
# Frozen snapshot membership
# ---------------------------------------------------------------------------


class TestFrozenSnapshotMembership:
    def test_defect_log_in_frozen_targets(self):
        # PR-C1 — the defect artifact must be in the frozen-targets list
        # so a post-finalize edit on POSIX is caught.
        assert "defect_log.jsonl" in _FROZEN_SNAPSHOT_TARGETS


# ---------------------------------------------------------------------------
# Engine integration
# ---------------------------------------------------------------------------


def _txn_contract_with_unique_check() -> DataContract:
    return DataContract(
        id="txn",
        source="t",
        columns=[
            Column(name="txn_id", type="string", nullable=False),
            Column(name="customer_id", type="string", nullable=False),
            Column(name="amount", type="decimal", nullable=False),
            Column(name="booked_at", type="timestamp", nullable=False),
        ],
        quality_checks=[{"unique": ["txn_id"]}],
    )


def _spec_with_unique_check() -> AMLSpec:
    return AMLSpec(
        version=1,
        program=Program(
            name="TestProgram",
            jurisdiction="US",
            regulator="FinCEN",
            owner="MLRO",
            effective_date=_date(2026, 1, 1),
        ),
        data_contracts=[_txn_contract_with_unique_check()],
        rules=[
            Rule(
                id="r1",
                name="R1",
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


def _data_with_dup() -> dict:
    return {
        "txn": [
            {"txn_id": "T1", "customer_id": "C1", "amount": 10.0, "booked_at": _AS_OF},
            {"txn_id": "T1", "customer_id": "C2", "amount": 20.0, "booked_at": _AS_OF},
        ],
    }


class TestEngineIntegration:
    def test_runner_emits_defect_log_jsonl(self, tmp_path: Path):
        spec = _spec_with_unique_check()
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text("placeholder: 1\n", encoding="utf-8")
        run_spec(
            spec=spec,
            spec_path=spec_path,
            data=_data_with_dup(),
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )
        run_dir = sorted(tmp_path.glob("run-*"))[-1]
        path = run_dir / "defect_log.jsonl"
        assert path.exists()
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        # One unique-violation DQ exception → one defect.
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert rec["category"] == "data_quality"
        assert rec["classification"] == "data"
        assert rec["severity"] == "high"

    def test_runner_emits_empty_file_when_no_defects(self, tmp_path: Path):
        # Spec with no quality_checks → no DQ exceptions → empty defect log.
        spec = AMLSpec(
            version=1,
            program=Program(
                name="TestProgram",
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
                )
            ],
            rules=[
                Rule(
                    id="r1",
                    name="R1",
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
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text("placeholder: 1\n", encoding="utf-8")
        run_spec(
            spec=spec,
            spec_path=spec_path,
            data={
                "txn": [
                    {"txn_id": "T1", "customer_id": "C1", "amount": 10.0, "booked_at": _AS_OF},
                ]
            },
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )
        run_dir = sorted(tmp_path.glob("run-*"))[-1]
        path = run_dir / "defect_log.jsonl"
        assert path.exists()
        assert path.read_bytes() == b""

    def test_manifest_pins_defect_log_hash(self, tmp_path: Path):
        spec = _spec_with_unique_check()
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text("placeholder: 1\n", encoding="utf-8")
        run_spec(
            spec=spec,
            spec_path=spec_path,
            data=_data_with_dup(),
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )
        run_dir = sorted(tmp_path.glob("run-*"))[-1]
        manifest = json.loads((run_dir / "manifest.json").read_bytes())
        assert "defect_log_hash" in manifest
        expected = hashlib.sha256((run_dir / "defect_log.jsonl").read_bytes()).hexdigest()
        assert manifest["defect_log_hash"] == expected

    def test_manifest_pins_none_when_artifact_absent(self, tmp_path: Path):
        # Direct AuditLedger.finalize() without the runner — older
        # callers that don't write the artifact still produce a valid
        # manifest with defect_log_hash=None.
        from aml_framework.engine.audit import AuditLedger

        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text("placeholder: 1\n", encoding="utf-8")
        ledger = AuditLedger.create(
            artifacts_root=tmp_path,
            spec_path=spec_path,
            spec_hash="abc",
            as_of=_AS_OF,
            spec=None,
        )
        manifest = ledger.finalize()
        assert manifest["defect_log_hash"] is None

    def test_defect_log_frozen_post_finalize(self, tmp_path: Path):
        if os.name == "nt":
            pytest.skip("chmod-based freeze is a no-op on Windows")
        spec = _spec_with_unique_check()
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text("placeholder: 1\n", encoding="utf-8")
        run_spec(
            spec=spec,
            spec_path=spec_path,
            data=_data_with_dup(),
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )
        run_dir = sorted(tmp_path.glob("run-*"))[-1]
        path = run_dir / "defect_log.jsonl"
        # 0o444 → read-only for all. Owner write bit must be clear.
        assert (path.stat().st_mode & 0o200) == 0, (
            f"defect_log.jsonl must be read-only after finalize "
            f"(got mode {oct(path.stat().st_mode)})"
        )

    def test_runner_writes_deterministic_defect_log_across_runs(self, tmp_path: Path):
        # Codex P2 on PR-C1: defect IDs + source_run_id must NOT carry
        # the wall-clock run-directory basename, else two re-runs at
        # different seconds produce different bytes and break the
        # `defect_log_hash` reproducibility contract. Force the second
        # run to land in a different run directory (sleep crossing the
        # 1-second boundary the directory name uses) so this test
        # would catch the pre-fix regression.
        import time

        spec = _spec_with_unique_check()
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text("placeholder: 1\n", encoding="utf-8")
        out_a = tmp_path / "a"
        out_b = tmp_path / "b"
        out_a.mkdir()
        out_b.mkdir()
        run_spec(
            spec=spec,
            spec_path=spec_path,
            data=_data_with_dup(),
            as_of=_AS_OF,
            artifacts_root=out_a,
        )
        time.sleep(1.05)  # cross the second boundary used by run-{ts}
        run_spec(
            spec=spec,
            spec_path=spec_path,
            data=_data_with_dup(),
            as_of=_AS_OF,
            artifacts_root=out_b,
        )
        run_a_dir = sorted(out_a.glob("run-*"))[-1]
        run_b_dir = sorted(out_b.glob("run-*"))[-1]
        # Sanity: directory basenames must differ — else the test is
        # vacuous and would have passed even with the run-dir-name bug.
        assert run_a_dir.name != run_b_dir.name
        run_a = run_a_dir / "defect_log.jsonl"
        run_b = run_b_dir / "defect_log.jsonl"
        assert run_a.read_bytes() == run_b.read_bytes()
        # The manifest-pinned hash should match too.
        manifest_a = json.loads((run_a_dir / "manifest.json").read_bytes())
        manifest_b = json.loads((run_b_dir / "manifest.json").read_bytes())
        assert manifest_a["defect_log_hash"] == manifest_b["defect_log_hash"]


# ---------------------------------------------------------------------------
# derive_run_id — codex P2 on PR-C1
# ---------------------------------------------------------------------------


class TestDeriveRunId:
    def test_same_inputs_same_id(self):
        a = derive_run_id("hash-abc", _AS_OF)
        b = derive_run_id("hash-abc", _AS_OF)
        assert a == b

    def test_different_spec_hash_different_id(self):
        a = derive_run_id("hash-abc", _AS_OF)
        b = derive_run_id("hash-xyz", _AS_OF)
        assert a != b

    def test_different_as_of_different_id(self):
        a = derive_run_id("hash-abc", _AS_OF)
        b = derive_run_id("hash-abc", datetime(2026, 6, 1, tzinfo=timezone.utc))
        assert a != b

    def test_id_is_sixteen_hex_chars(self):
        out = derive_run_id("hash-abc", _AS_OF)
        assert len(out) == 16
        assert all(c in "0123456789abcdef" for c in out)


# ---------------------------------------------------------------------------
# Strict python_ref aborts still emit defect_log — codex P2 on PR-C1
# ---------------------------------------------------------------------------


class TestStrictPythonRefDefectLog:
    """Codex P2 on PR-C1: when strict python_ref aborts the run before
    `_finalize_run()`, the defect log must still land on disk so the
    RULE_LOGIC ticket is observable in the run directory.
    """

    def _spec_with_python_ref_rule(self, callable_str: str) -> AMLSpec:
        from aml_framework.spec.models import PythonRefLogic

        return AMLSpec(
            version=1,
            program=Program(
                name="TestProgram",
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
                )
            ],
            rules=[
                Rule(
                    id="r_pyref",
                    name="R",
                    severity="high",
                    regulation_refs=[RegulationRef(citation="x", description="x")],
                    logic=PythonRefLogic(
                        type="python_ref",
                        callable=callable_str,
                        model_id="test",
                        model_version="v0",
                    ),
                    escalate_to="q1",
                    evidence=[],
                )
            ],
            workflow=Workflow(queues=[Queue(id="q1", sla="24h")]),
        )

    def test_strict_python_ref_failure_writes_defect_log_before_raising(
        self, tmp_path: Path, monkeypatch
    ):
        # Point allowed prefixes at a test scorer that raises so the
        # strict path triggers without smuggling in real ml/model code.
        monkeypatch.setenv("AML_PYTHON_REF_PREFIX", "tests.")
        monkeypatch.setenv("AML_STRICT_PYTHON_REF", "1")
        # Reference a non-existent module under the allowed prefix —
        # the import inside the rule loop raises, which the strict
        # branch promotes to PythonRefFailure after writing the
        # defect log.
        spec = self._spec_with_python_ref_rule("tests.does_not_exist:scorer")
        spec_path = tmp_path / "spec.yaml"
        spec_path.write_text("placeholder: 1\n", encoding="utf-8")
        from aml_framework.engine.runner import PythonRefFailure

        with pytest.raises(PythonRefFailure):
            run_spec(
                spec=spec,
                spec_path=spec_path,
                data={
                    "txn": [
                        {
                            "txn_id": "T1",
                            "customer_id": "C1",
                            "amount": 10.0,
                            "booked_at": _AS_OF,
                        }
                    ]
                },
                as_of=_AS_OF,
                artifacts_root=tmp_path,
            )
        run_dirs = sorted(tmp_path.glob("run-*"))
        assert run_dirs, "run directory should exist even after strict abort"
        run_dir = run_dirs[-1]
        defect_path = run_dir / "defect_log.jsonl"
        assert defect_path.exists(), (
            "defect_log.jsonl must be written before strict PythonRefFailure raises"
        )
        lines = [ln for ln in defect_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        # One python_ref defect for the failed rule.
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert rec["category"] == "rule_logic"
        assert rec["classification"] == "rule"
        assert rec["severity"] == "high"
        assert "r_pyref" in rec["summary"]
