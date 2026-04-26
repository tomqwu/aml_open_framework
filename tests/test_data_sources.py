"""Data source tests -- synthetic, CSV, Parquet, DuckDB, cloud, python_ref."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from aml_framework.data import generate_dataset
from aml_framework.data.sources import (
    _parse_value,
    load_csv_source,
    load_duckdb_source,
    load_parquet_source,
    resolve_source,
    validate_csv,
)
from aml_framework.engine import run_spec
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


# ---------------------------------------------------------------------------
# Original TestCSVSource
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Original TestResolveSource
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Original TestCSVEndToEnd
# ---------------------------------------------------------------------------


class TestCSVEndToEnd:
    def test_engine_runs_on_csv_data(self, tmp_path):
        """Full pipeline: CSV -> engine -> alerts."""
        data_dir = _create_test_csvs(tmp_path)
        spec = load_spec(SPEC)
        data = load_csv_source(data_dir, spec)
        result = run_spec(
            spec=spec,
            spec_path=SPEC,
            data=data,
            as_of=datetime(2026, 4, 23, 12, 0),
            artifacts_root=tmp_path / "out",
        )
        assert result.manifest is not None
        assert isinstance(result.alerts, dict)


# ---------------------------------------------------------------------------
# From test_coverage_99.py: TestSourcesParsing
# ---------------------------------------------------------------------------


class TestSourcesParsing:
    def test_parse_value_types(self):
        assert _parse_value("hello", "string", True) == "hello"
        assert _parse_value("42", "integer", True) == 42
        assert _parse_value("true", "boolean", True) is True
        assert _parse_value("", "string", True) is None
        assert _parse_value("", "integer", False) == 0

    def test_parquet_missing_file(self, tmp_path):
        spec = load_spec(SPEC)
        data = load_parquet_source(tmp_path, spec)
        assert data["txn"] == []
        assert data["customer"] == []

    def test_duckdb_source_missing_table(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        con = duckdb.connect(db_path)
        con.close()

        spec = load_spec(SPEC)
        data = load_duckdb_source(db_path, spec)
        assert data["txn"] == []

    def test_bigquery_raises_without_extension(self):
        spec = load_spec(SPEC)
        with pytest.raises(RuntimeError, match="bigquery"):
            resolve_source("bigquery", spec, datetime(2026, 4, 23), data_dir="dummy")


# ---------------------------------------------------------------------------
# From test_coverage_99.py: TestSourcesParsingExtended
# ---------------------------------------------------------------------------


class TestSourcesParsingExtended:
    def test_parse_date_value(self):
        result = _parse_value("2026-01-15", "date", True)
        assert result is not None

    def test_parse_timestamp_value(self):
        result = _parse_value("2026-01-15T10:30:00", "timestamp", True)
        assert result is not None

    def test_parse_boolean_false(self):
        assert _parse_value("false", "boolean", True) is False
        assert _parse_value("0", "boolean", True) is False

    def test_parse_invalid_decimal(self):
        result = _parse_value("not_a_number", "decimal", True)
        assert result == "not_a_number"

    def test_validate_unknown_contract(self, tmp_path):
        (tmp_path / "x.csv").write_text("a,b\n1,2\n")
        spec = load_spec(SPEC)
        errors = validate_csv(tmp_path / "x.csv", spec, "nonexistent_contract")
        assert any("No data contract" in e for e in errors)

    def test_load_csv_with_date_columns(self, tmp_path):
        (tmp_path / "txn.csv").write_text(
            "txn_id,customer_id,amount,currency,channel,direction,booked_at\n"
            "T1,C1,100.50,CAD,cash,in,2026-04-01T10:00:00\n"
        )
        (tmp_path / "customer.csv").write_text(
            "customer_id,full_name,country,risk_rating,onboarded_at,business_activity,edd_last_review\n"
            "C1,Test,CA,low,2025-01-01T00:00:00,,\n"
        )
        spec = load_spec(SPEC)
        data = load_csv_source(tmp_path, spec)
        assert len(data["txn"]) == 1
        assert len(data["customer"]) == 1


# ---------------------------------------------------------------------------
# From test_coverage_gaps.py: TestDataSourcesExtended
# ---------------------------------------------------------------------------


class TestDataSourcesExtended:
    def test_validate_csv_catches_extra_columns(self, tmp_path):
        (tmp_path / "txn.csv").write_text(
            "txn_id,customer_id,amount,currency,channel,direction,booked_at,EXTRA_COL\n"
            "T001,C001,100,CAD,cash,in,2026-01-01T00:00:00,foo\n"
        )
        spec = load_spec(SPEC)
        errors = validate_csv(tmp_path / "txn.csv", spec, "txn")
        assert any("Extra" in e for e in errors)

    def test_resolve_snowflake_raises_without_extension(self):
        spec = load_spec(SPEC)
        with pytest.raises(RuntimeError, match="snowflake"):
            resolve_source("snowflake", spec, datetime(2026, 4, 23), data_dir="dummy")


# ---------------------------------------------------------------------------
# From test_final_coverage.py: TestParquetAndDuckDB
# ---------------------------------------------------------------------------


class TestParquetAndDuckDB:
    def test_load_parquet_with_data(self, tmp_path):
        """Create a real parquet file via DuckDB and load it."""
        con = duckdb.connect(":memory:")
        con.execute(
            "CREATE TABLE test AS SELECT 'T001' AS txn_id, 'C001' AS customer_id, "
            "100.0 AS amount, 'CAD' AS currency, 'cash' AS channel, 'in' AS direction, "
            "TIMESTAMP '2026-04-01 10:00:00' AS booked_at"
        )
        con.execute(f"COPY test TO '{tmp_path}/txn.parquet' (FORMAT PARQUET)")
        con.close()

        spec = load_spec(SPEC)
        data = load_parquet_source(tmp_path, spec)
        assert len(data["txn"]) == 1
        assert data["txn"][0]["txn_id"] == "T001"

    def test_duckdb_with_custom_queries(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        con = duckdb.connect(db_path)
        con.execute("CREATE TABLE my_txns AS SELECT 'T001' AS txn_id, 'C001' AS customer_id")
        con.close()

        spec = load_spec(SPEC)
        data = load_duckdb_source(db_path, spec, queries={"txn": "SELECT * FROM my_txns"})
        assert len(data["txn"]) == 1

    def test_resolve_parquet(self, tmp_path):
        spec = load_spec(SPEC)
        data = resolve_source("parquet", spec, datetime(2026, 4, 23), data_dir=str(tmp_path))
        assert data["txn"] == []

    def test_resolve_duckdb(self, tmp_path):
        db_path = str(tmp_path / "test.duckdb")
        con = duckdb.connect(db_path)
        con.close()

        spec = load_spec(SPEC)
        data = resolve_source("duckdb", spec, datetime(2026, 4, 23), db_path=db_path)
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# From test_final_coverage.py: TestSourcesMore
# ---------------------------------------------------------------------------


class TestSourcesMore:
    def test_resolve_csv_no_dir_raises(self):
        spec = load_spec(SPEC)
        with pytest.raises(ValueError, match="data-dir"):
            resolve_source("csv", spec, datetime(2026, 4, 23))

    def test_resolve_parquet_no_dir_raises(self):
        spec = load_spec(SPEC)
        with pytest.raises(ValueError, match="data-dir"):
            resolve_source("parquet", spec, datetime(2026, 4, 23))

    def test_resolve_duckdb_no_path_raises(self):
        spec = load_spec(SPEC)
        with pytest.raises(ValueError, match="db-path"):
            resolve_source("duckdb", spec, datetime(2026, 4, 23))


# ---------------------------------------------------------------------------
# From test_new_sprint.py: TestPEPData, TestCloudSources
# ---------------------------------------------------------------------------


class TestPEPData:
    def test_synthetic_data_has_pep_customer(self):
        data = generate_dataset(as_of=datetime(2026, 4, 23), seed=42)
        pep_customers = [c for c in data["customer"] if c.get("pep_status")]
        assert len(pep_customers) >= 1
        assert pep_customers[0]["pep_status"] == "domestic_pep"

    def test_pep_customer_has_correct_profile(self):
        data = generate_dataset(as_of=datetime(2026, 4, 23), seed=42)
        c0009 = next((c for c in data["customer"] if c["customer_id"] == "C0009"), None)
        assert c0009 is not None
        assert c0009["country"] == "DE"
        assert c0009["risk_rating"] == "high"
        assert c0009["full_name"] == "Hans Mueller"


class TestCloudSources:
    def test_s3_without_dir_raises(self):
        spec = load_spec(SPEC)
        with pytest.raises(ValueError, match="data-dir"):
            resolve_source("s3", spec, datetime(2026, 4, 23))

    def test_gcs_without_dir_raises(self):
        spec = load_spec(SPEC)
        with pytest.raises(ValueError, match="data-dir"):
            resolve_source("gcs", spec, datetime(2026, 4, 23))


# ---------------------------------------------------------------------------
# From test_python_ref.py
# ---------------------------------------------------------------------------


EXAMPLE_CA = (
    Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"
)


def _run_ca(tmp_path):
    spec = load_spec(EXAMPLE_CA)
    as_of = datetime(2026, 4, 23, 12, 0, 0)
    data = generate_dataset(as_of=as_of, seed=42)
    return spec, run_spec(
        spec=spec, spec_path=EXAMPLE_CA, data=data, as_of=as_of, artifacts_root=tmp_path
    )


def test_python_ref_rule_executes(tmp_path):
    """The ml_risk_scorer python_ref rule must execute and produce alerts."""
    _, result = _run_ca(tmp_path)
    alerts = result.alerts.get("ml_risk_scorer", [])
    assert len(alerts) >= 1, "heuristic scorer should flag at least one customer"


def test_python_ref_alerts_have_risk_score(tmp_path):
    """Each alert from the scorer must include a risk_score field."""
    _, result = _run_ca(tmp_path)
    for alert in result.alerts.get("ml_risk_scorer", []):
        assert "risk_score" in alert, "scorer must return risk_score"
        assert alert["risk_score"] >= 0.65, "score must be above threshold"


def test_python_ref_creates_cases(tmp_path):
    """python_ref alerts must generate case files like any other rule."""
    _, result = _run_ca(tmp_path)
    run_dir = Path(result.manifest["run_dir"])
    ml_cases = list((run_dir / "cases").glob("ml_risk_scorer__*"))
    assert len(ml_cases) >= 1, "scorer alerts must create case files"


def test_python_ref_audit_trail(tmp_path):
    """python_ref execution must be recorded in the audit ledger."""
    _, result = _run_ca(tmp_path)
    run_dir = Path(result.manifest["run_dir"])
    sql_file = run_dir / "rules" / "ml_risk_scorer.sql"
    assert sql_file.exists(), "audit trail must record python_ref stub"
    content = sql_file.read_text()
    assert "python_ref" in content
    assert "heuristic_risk_v1" in content
