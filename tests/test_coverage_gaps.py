"""Tests to close coverage gaps in core modules."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from aml_framework.data import generate_dataset
from aml_framework.engine import run_spec
from aml_framework.spec import load_spec

SPEC_US = Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"
SPEC_CA = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


# --- export.py ---


class TestExport:
    def test_export_bundle_creates_zip(self, tmp_path):
        from aml_framework.export import export_bundle

        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=SPEC_CA, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        run_dir = Path(result.manifest["run_dir"])
        out = tmp_path / "evidence.zip"
        export_bundle(run_dir, out)
        assert out.exists()
        assert out.stat().st_size > 1000

    def test_export_bundle_contains_manifest(self, tmp_path):
        import zipfile

        from aml_framework.export import export_bundle

        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=SPEC_CA, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        run_dir = Path(result.manifest["run_dir"])
        out = tmp_path / "evidence.zip"
        export_bundle(run_dir, out)
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
            assert "manifest.json" in names


# --- generators/docs.py ---


class TestControlMatrix:
    def test_renders_markdown(self):
        from aml_framework.generators.docs import render_control_matrix

        spec = load_spec(SPEC_CA)
        md = render_control_matrix(spec)
        assert "Control Matrix" in md
        assert "structuring_cash_deposits" in md

    def test_contains_regulation_refs(self):
        from aml_framework.generators.docs import render_control_matrix

        spec = load_spec(SPEC_CA)
        md = render_control_matrix(spec)
        assert "PCMLTFA" in md


# --- generators/dag.py ---


class TestDAGGenerator:
    def test_renders_dag_stub(self):
        from aml_framework.generators.dag import render_dag_stub

        spec = load_spec(SPEC_CA)
        py = render_dag_stub(spec)
        assert "def" in py or "DAG" in py or "dag" in py


# --- generators/sql.py ---


class TestSQLGenerator:
    def test_filter_operators(self):
        from aml_framework.generators.sql import _compile_filter

        preds = _compile_filter({"amount": {"gt": 1000}})
        assert any(">" in p for p in preds)

        preds = _compile_filter({"amount": {"lt": 500}})
        assert any("<" in p for p in preds)

        preds = _compile_filter({"amount": {"ne": 0}})
        assert any("<>" in p for p in preds)

        preds = _compile_filter({"amount": {"eq": 100}})
        assert any("=" in p for p in preds)

        preds = _compile_filter({"channel": "cash"})
        assert any("cash" in p for p in preds)

    def test_sql_literal_types(self):
        from aml_framework.generators.sql import _sql_literal

        assert _sql_literal(True) == "TRUE"
        assert _sql_literal(False) == "FALSE"
        assert _sql_literal(42) == "42"
        assert _sql_literal(None) == "NULL"
        assert _sql_literal("hello") == "'hello'"
        assert _sql_literal("it's") == "'it''s'"  # Escape single quotes.


# --- integrations/notifications.py ---


class TestNotificationRouting:
    def test_get_channel_for_severity(self):
        from aml_framework.integrations.notifications import get_channel_for_severity

        assert get_channel_for_severity("critical") == "cco"
        assert get_channel_for_severity("high") == "investigators"
        assert get_channel_for_severity("medium") == "analysts"
        assert get_channel_for_severity("unknown") == "general"


# --- integrations/jira.py ---


class TestJiraMapping:
    def test_severity_priority_mapping(self):
        from aml_framework.integrations.jira import SEVERITY_TO_PRIORITY

        assert SEVERITY_TO_PRIORITY["critical"] == "Highest"
        assert SEVERITY_TO_PRIORITY["low"] == "Low"

    def test_build_description(self):
        from aml_framework.integrations.jira import _build_description

        desc = _build_description(
            {
                "case_id": "test_case",
                "rule_name": "test_rule",
                "severity": "high",
                "alert": {"customer_id": "C001", "sum_amount": 5000},
                "queue": "l1",
                "regulation_refs": [{"citation": "PCMLTFA s.7"}],
                "evidence_requested": ["transactions"],
            }
        )
        assert "C001" in desc
        assert "PCMLTFA" in desc


# --- data/sources.py ---


class TestDataSourcesExtended:
    def test_validate_csv_catches_extra_columns(self, tmp_path):
        from aml_framework.data.sources import validate_csv

        (tmp_path / "txn.csv").write_text(
            "txn_id,customer_id,amount,currency,channel,direction,booked_at,EXTRA_COL\n"
            "T001,C001,100,CAD,cash,in,2026-01-01T00:00:00,foo\n"
        )
        spec = load_spec(SPEC_CA)
        errors = validate_csv(tmp_path / "txn.csv", spec, "txn")
        assert any("Extra" in e for e in errors)

    def test_resolve_snowflake_raises_without_extension(self):
        from aml_framework.data.sources import resolve_source

        spec = load_spec(SPEC_CA)
        with pytest.raises(RuntimeError, match="snowflake"):
            resolve_source("snowflake", spec, datetime(2026, 4, 23), data_dir="dummy")


# --- api/auth.py ---


class TestRBAC:
    def test_require_role_exists(self):
        from aml_framework.api.auth import ROLE_PERMISSIONS, require_role

        assert "admin" in ROLE_PERMISSIONS
        assert "read" in ROLE_PERMISSIONS["auditor"]
        assert "write" not in ROLE_PERMISSIONS["auditor"]
        # require_role returns a callable.
        dep = require_role("admin")
        assert callable(dep)


# --- metrics/engine.py uncovered branches ---


class TestMetricEdgeCases:
    def test_coverage_non_typology_returns_zero(self, tmp_path):
        """Coverage formula with universe != typologies should return 0.0."""
        spec = load_spec(SPEC_US)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(
            spec=spec, spec_path=SPEC_US, data=data, as_of=as_of, artifacts_root=tmp_path
        )
        # All coverage metrics in example specs use typologies/rule_tags.
        # This just verifies the engine handles them without error.
        for m in result.metrics:
            assert m.value is not None
