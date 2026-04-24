"""Tests for data source abstraction and CSV ingestion."""

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from aml_framework.data.sources import load_csv_source, resolve_source, validate_csv
from aml_framework.spec import load_spec

SPEC = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


def _create_test_csvs(tmp_path: Path) -> Path:
    """Create minimal CSV files matching the spec's data contracts."""
    (tmp_path / "customer.csv").write_text(
        "customer_id,full_name,country,risk_rating,onboarded_at,business_activity,edd_last_review\n"
        "C0001,Test User,CA,low,2025-01-01T00:00:00,retail,\n"
        "C0002,High Risk Corp,RU,high,2024-06-15T00:00:00,,\n"
    )
    (tmp_path / "txn.csv").write_text(
        "txn_id,customer_id,amount,currency,channel,direction,booked_at\n"
        "T001,C0001,5000.00,CAD,cash,in,2026-04-01T10:00:00\n"
        "T002,C0001,8500.00,CAD,cash,in,2026-04-05T14:00:00\n"
        "T003,C0002,25000.00,CAD,wire,in,2026-04-10T09:00:00\n"
    )
    return tmp_path


class TestCSVSource:
    def test_load_csv_parses_types(self, tmp_path):
        data_dir = _create_test_csvs(tmp_path)
        spec = load_spec(SPEC)
        data = load_csv_source(data_dir, spec)
        assert len(data["customer"]) == 2
        assert len(data["txn"]) == 3
        assert isinstance(data["txn"][0]["amount"], Decimal)

    def test_load_csv_missing_file_returns_empty(self, tmp_path):
        spec = load_spec(SPEC)
        data = load_csv_source(tmp_path, spec)
        assert data["customer"] == []
        assert data["txn"] == []

    def test_validate_csv_passes_valid_file(self, tmp_path):
        data_dir = _create_test_csvs(tmp_path)
        spec = load_spec(SPEC)
        errors = validate_csv(data_dir / "txn.csv", spec, "txn")
        # Should pass — all required columns present.
        assert not any("Missing required" in e for e in errors)

    def test_validate_csv_catches_missing_columns(self, tmp_path):
        (tmp_path / "txn.csv").write_text("txn_id,amount\nT001,100\n")
        spec = load_spec(SPEC)
        errors = validate_csv(tmp_path / "txn.csv", spec, "txn")
        assert any("Missing required" in e for e in errors)

    def test_validate_csv_catches_missing_file(self, tmp_path):
        spec = load_spec(SPEC)
        errors = validate_csv(tmp_path / "missing.csv", spec, "txn")
        assert any("not found" in e for e in errors)


class TestResolveSource:
    def test_resolve_synthetic(self):
        spec = load_spec(SPEC)
        data = resolve_source("synthetic", spec, datetime(2026, 4, 23, 12, 0), seed=42)
        assert len(data["txn"]) > 0
        assert len(data["customer"]) > 0

    def test_resolve_csv(self, tmp_path):
        data_dir = _create_test_csvs(tmp_path)
        spec = load_spec(SPEC)
        data = resolve_source("csv", spec, datetime(2026, 4, 23, 12, 0), data_dir=str(data_dir))
        assert len(data["txn"]) == 3

    def test_resolve_unknown_raises(self):
        spec = load_spec(SPEC)
        try:
            resolve_source("unknown", spec, datetime(2026, 4, 23, 12, 0))
            assert False, "Should raise ValueError"
        except ValueError:
            pass

    def test_csv_without_dir_raises(self):
        spec = load_spec(SPEC)
        try:
            resolve_source("csv", spec, datetime(2026, 4, 23, 12, 0))
            assert False, "Should raise ValueError"
        except ValueError:
            pass


class TestCSVEndToEnd:
    def test_engine_runs_on_csv_data(self, tmp_path):
        """Full pipeline: CSV -> engine -> alerts."""
        from aml_framework.engine import run_spec

        data_dir = _create_test_csvs(tmp_path)
        spec = load_spec(SPEC)
        data = load_csv_source(data_dir, spec)
        result = run_spec(
            spec=spec, spec_path=SPEC, data=data,
            as_of=datetime(2026, 4, 23, 12, 0), artifacts_root=tmp_path / "out",
        )
        # Engine should run without errors even with minimal data.
        assert result.manifest is not None
        assert isinstance(result.alerts, dict)
