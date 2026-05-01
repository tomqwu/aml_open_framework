"""Fail-closed contract validation (PR-DATA-1).

Backs the "Data is the AML problem" whitepaper's DATA-1 claim that the
engine refuses to fire rules against input data that doesn't satisfy a
declared `data_contract`'s required-column constraints. Until this PR,
the engine silently `.get()`d missing columns and let DuckDB's NOT NULL
constraint surface a raw driver error instead of a domain exception.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from aml_framework.engine.runner import ContractViolation, _build_warehouse, run_spec
from aml_framework.spec.loader import load_spec


_AS_OF = datetime(2026, 5, 1, tzinfo=timezone.utc)


def _community_bank_spec(tmp_path: Path):
    """Reload the canonical community_bank spec into tmp_path so the
    AuditLedger writes its run dir under tmp."""
    src = Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"
    return load_spec(src)


def _community_bank_path() -> Path:
    return Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"


# ---------------------------------------------------------------------------
# _build_warehouse pre-flight checks
# ---------------------------------------------------------------------------


class TestPreflightContractValidation:
    def test_raises_when_required_column_missing(self):
        import duckdb

        spec = _community_bank_spec(Path("/tmp"))
        # Drop `customer_id` — declared non-nullable in the txn contract.
        bad_data = {
            "txn": [
                {
                    "txn_id": "T0001",
                    "amount": 100.0,
                    "currency": "USD",
                    "channel": "wire",
                    "direction": "out",
                    "booked_at": _AS_OF,
                }
            ],
            "customer": [],
        }
        con = duckdb.connect(":memory:")
        with pytest.raises(ContractViolation) as exc_info:
            _build_warehouse(con, spec, bad_data)
        assert exc_info.value.contract_id == "txn"
        assert "customer_id" in exc_info.value.missing_columns

    def test_passes_when_all_required_columns_present(self):
        import duckdb

        spec = _community_bank_spec(Path("/tmp"))
        good_data = {
            "txn": [
                {
                    "txn_id": "T0001",
                    "customer_id": "C0001",
                    "amount": 100.0,
                    "currency": "USD",
                    "channel": "wire",
                    "direction": "out",
                    "booked_at": _AS_OF,
                }
            ],
            "customer": [
                {
                    "customer_id": "C0001",
                    "full_name": "Alice",
                    "country": "US",
                    "risk_rating": "low",
                    "onboarded_at": _AS_OF,
                }
            ],
        }
        con = duckdb.connect(":memory:")
        # Should not raise.
        _build_warehouse(con, spec, good_data)
        # And the table should have the row.
        result = con.execute("SELECT count(*) FROM txn").fetchone()
        assert result[0] == 1

    def test_empty_rows_for_a_contract_does_not_violate(self):
        """Zero rows is not a contract violation — it just means the engine
        runs against an empty table. Useful for partial-day runs or staging
        environments where one stream is silent."""
        import duckdb

        spec = _community_bank_spec(Path("/tmp"))
        empty = {"txn": [], "customer": []}
        con = duckdb.connect(":memory:")
        _build_warehouse(con, spec, empty)
        result = con.execute("SELECT count(*) FROM txn").fetchone()
        assert result[0] == 0

    def test_multiple_required_columns_missing_lists_all(self):
        import duckdb

        spec = _community_bank_spec(Path("/tmp"))
        bad = {
            "txn": [{"txn_id": "T0001"}],  # missing many required fields
            "customer": [],
        }
        con = duckdb.connect(":memory:")
        with pytest.raises(ContractViolation) as exc_info:
            _build_warehouse(con, spec, bad)
        # All missing required columns should be enumerated, not just the first.
        for required in ("customer_id", "amount", "currency", "booked_at"):
            assert required in exc_info.value.missing_columns


# ---------------------------------------------------------------------------
# Audit-ledger event on violation (run_spec wraps the failure)
# ---------------------------------------------------------------------------


class TestContractViolationEmitsAuditEvent:
    def test_run_spec_writes_contract_violation_to_decisions_jsonl(self, tmp_path: Path):
        spec = _community_bank_spec(tmp_path)
        # Drop the entire customer contract's required fields — guarantees
        # _build_warehouse will raise ContractViolation.
        bad_data = {
            "txn": [
                {
                    "txn_id": "T0001",
                    "customer_id": "C0001",
                    "amount": 100.0,
                    "currency": "USD",
                    "channel": "wire",
                    "direction": "out",
                    "booked_at": _AS_OF,
                }
            ],
            "customer": [{"customer_id": "C0001"}],  # missing full_name, country, etc.
        }
        with pytest.raises(ContractViolation):
            run_spec(
                spec=spec,
                spec_path=_community_bank_path(),
                data=bad_data,
                as_of=_AS_OF,
                artifacts_root=tmp_path,
            )
        # Find the run dir created by the failed run; assert decisions.jsonl
        # has a contract_violation entry.
        run_dirs = sorted(tmp_path.glob("run-*"))
        assert run_dirs, "run dir should be created even on contract violation"
        decisions = (run_dirs[-1] / "decisions.jsonl").read_text(encoding="utf-8")
        assert "contract_violation" in decisions
        assert "customer" in decisions  # the violating contract id

    def test_run_spec_clean_data_does_not_emit_violation(self, tmp_path: Path):
        from aml_framework.data.synthetic import generate_dataset

        spec = _community_bank_spec(tmp_path)
        data = generate_dataset(as_of=_AS_OF, seed=42)
        result = run_spec(
            spec=spec,
            spec_path=_community_bank_path(),
            data=data,
            as_of=_AS_OF,
            artifacts_root=tmp_path,
        )
        # Successful run: result is a RunResult, not an exception.
        assert result.manifest is not None
        # decisions.jsonl should not contain contract_violation.
        run_dirs = sorted(tmp_path.glob("run-*"))
        decisions_text = (run_dirs[-1] / "decisions.jsonl").read_text(encoding="utf-8")
        assert "contract_violation" not in decisions_text


# ---------------------------------------------------------------------------
# ContractViolation message shape
# ---------------------------------------------------------------------------


class TestExceptionMessage:
    def test_message_names_contract_and_columns(self):
        exc = ContractViolation(
            contract_id="customer",
            missing_columns=["country", "full_name"],
            detail="input rows expose columns ['customer_id']",
        )
        msg = str(exc)
        assert "customer" in msg
        assert "country" in msg
        assert "full_name" in msg
        assert "input rows expose" in msg

    def test_missing_columns_attribute_is_sorted(self):
        exc = ContractViolation("c", ["zzz", "aaa", "mmm"])
        assert exc.missing_columns == ["aaa", "mmm", "zzz"]
