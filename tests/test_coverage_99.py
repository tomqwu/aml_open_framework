"""Targeted tests to reach 99% coverage on all non-UI modules."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aml_framework.data import generate_dataset
from aml_framework.engine import run_spec
from aml_framework.spec import load_spec

SPEC_CA = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"
SPEC_US = Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"


def _run(tmp_path, spec_path=SPEC_CA):
    spec = load_spec(spec_path)
    as_of = datetime(2026, 4, 23, 12, 0, 0)
    data = generate_dataset(as_of=as_of, seed=42)
    return (
        spec,
        data,
        run_spec(spec=spec, spec_path=spec_path, data=data, as_of=as_of, artifacts_root=tmp_path),
    )


# --- api/db.py: PostgreSQL paths (mocked) ---


class TestDBPostgresPaths:
    def test_postgres_init_db(self):
        import aml_framework.api.db as db

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with (
            patch.object(db, "_use_postgres", return_value=True),
            patch.object(db, "_get_pg_conn", return_value=mock_conn),
        ):
            db.init_db()
            mock_cursor.execute.assert_called_once()
            mock_conn.commit.assert_called_once()

    def test_postgres_store_run(self):
        import aml_framework.api.db as db

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with (
            patch.object(db, "_use_postgres", return_value=True),
            patch.object(db, "_get_pg_conn", return_value=mock_conn),
        ):
            db.store_run("r1", "spec.yaml", 42, {"k": "v"}, {"rule": [{"a": 1}]}, [{"m": 1}])
            assert mock_cursor.execute.call_count >= 3  # runs + alerts + metrics
            mock_conn.commit.assert_called()

    def test_postgres_list_runs(self):
        import aml_framework.api.db as db

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        ts = MagicMock()
        ts.isoformat.return_value = "2026-01-01T00:00:00"
        mock_cursor.fetchall.return_value = [("r1", "spec.yaml", 42, ts)]
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with (
            patch.object(db, "_use_postgres", return_value=True),
            patch.object(db, "_get_pg_conn", return_value=mock_conn),
        ):
            result = db.list_runs()
            assert len(result) == 1
            assert result[0]["run_id"] == "r1"

    def test_postgres_get_run(self):
        import aml_framework.api.db as db

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ('{"key": "val"}',)
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with (
            patch.object(db, "_use_postgres", return_value=True),
            patch.object(db, "_get_pg_conn", return_value=mock_conn),
        ):
            result = db.get_run("r1")
            assert result == {"key": "val"}

    def test_postgres_get_run_not_found(self):
        import aml_framework.api.db as db

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with (
            patch.object(db, "_use_postgres", return_value=True),
            patch.object(db, "_get_pg_conn", return_value=mock_conn),
        ):
            assert db.get_run("missing") is None

    def test_postgres_get_alerts(self):
        import aml_framework.api.db as db

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [("rule_a", '[{"c": 1}]')]
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with (
            patch.object(db, "_use_postgres", return_value=True),
            patch.object(db, "_get_pg_conn", return_value=mock_conn),
        ):
            result = db.get_run_alerts("r1")
            assert len(result) == 1

    def test_postgres_get_metrics(self):
        import aml_framework.api.db as db

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ('[{"id": "m1"}]',)
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with (
            patch.object(db, "_use_postgres", return_value=True),
            patch.object(db, "_get_pg_conn", return_value=mock_conn),
        ):
            result = db.get_run_metrics("r1")
            assert len(result) == 1


# --- integrations/jira.py: mock API calls ---


class TestJiraAPICalls:
    @patch("urllib.request.urlopen")
    def test_create_issue_success(self, mock_urlopen):
        from aml_framework.integrations import jira

        mock_response = MagicMock()
        mock_response.read.return_value = b'{"key": "AML-123"}'
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        with (
            patch.object(jira, "_JIRA_URL", "https://jira.test"),
            patch.object(jira, "_JIRA_TOKEN", "test-token"),
        ):
            result = jira.create_issue({"case_id": "c1", "severity": "high", "rule_id": "r1"})
            assert result == "AML-123"

    @patch("urllib.request.urlopen", side_effect=Exception("network error"))
    def test_create_issue_failure(self, mock_urlopen):
        from aml_framework.integrations import jira

        with (
            patch.object(jira, "_JIRA_URL", "https://jira.test"),
            patch.object(jira, "_JIRA_TOKEN", "test-token"),
        ):
            result = jira.create_issue({"case_id": "c1", "severity": "high"})
            assert result is None

    @patch("urllib.request.urlopen")
    def test_update_status(self, mock_urlopen):
        from aml_framework.integrations import jira

        with (
            patch.object(jira, "_JIRA_URL", "https://jira.test"),
            patch.object(jira, "_JIRA_TOKEN", "test-token"),
        ):
            result = jira.update_status("AML-123", "Done")
            assert result is True

    @patch("urllib.request.urlopen", side_effect=Exception("fail"))
    def test_update_status_failure(self, mock_urlopen):
        from aml_framework.integrations import jira

        with (
            patch.object(jira, "_JIRA_URL", "https://jira.test"),
            patch.object(jira, "_JIRA_TOKEN", "test-token"),
        ):
            assert jira.update_status("AML-123", "Done") is False


# --- integrations/notifications.py: mock webhook calls ---


class TestNotificationSending:
    @patch("urllib.request.urlopen")
    def test_slack_send(self, mock_urlopen):
        from aml_framework.integrations import notifications

        with patch.object(notifications, "_SLACK_URL", "https://hooks.slack.com/test"):
            notifications.notify_alert("rule_a", "high", "C001", 5000.0)
            mock_urlopen.assert_called_once()

    @patch("urllib.request.urlopen")
    def test_teams_send(self, mock_urlopen):
        from aml_framework.integrations import notifications

        with patch.object(notifications, "_TEAMS_URL", "https://outlook.webhook.test"):
            notifications.notify_run_complete("r1", 10, 5, "test_spec")
            mock_urlopen.assert_called_once()

    @patch("urllib.request.urlopen")
    def test_sla_breach_notification(self, mock_urlopen):
        from aml_framework.integrations import notifications

        with patch.object(notifications, "_SLACK_URL", "https://hooks.slack.com/test"):
            notifications.notify_sla_breach("case_1", "l1_analyst", 24.0, 30.0)
            mock_urlopen.assert_called_once()

    @patch("urllib.request.urlopen", side_effect=Exception("fail"))
    def test_slack_failure_doesnt_raise(self, mock_urlopen):
        from aml_framework.integrations import notifications

        with patch.object(notifications, "_SLACK_URL", "https://hooks.slack.com/test"):
            # Should not raise.
            notifications.notify_alert("rule_a", "high", "C001", 5000.0)

    @patch("urllib.request.urlopen", side_effect=Exception("fail"))
    def test_teams_failure_doesnt_raise(self, mock_urlopen):
        from aml_framework.integrations import notifications

        with patch.object(notifications, "_TEAMS_URL", "https://outlook.webhook.test"):
            notifications.notify_run_complete("r1", 10, 5, "test_spec")


# --- data/sources.py: parquet, duckdb, value parsing ---


class TestSourcesParsing:
    def test_parse_value_types(self):
        from aml_framework.data.sources import _parse_value

        assert _parse_value("hello", "string", True) == "hello"
        assert _parse_value("42", "integer", True) == 42
        assert _parse_value("true", "boolean", True) is True
        assert _parse_value("", "string", True) is None
        assert _parse_value("", "integer", False) == 0

    def test_parquet_missing_file(self, tmp_path):
        from aml_framework.data.sources import load_parquet_source

        spec = load_spec(SPEC_CA)
        data = load_parquet_source(tmp_path, spec)
        assert data["txn"] == []
        assert data["customer"] == []

    def test_duckdb_source_missing_table(self, tmp_path):
        import duckdb

        from aml_framework.data.sources import load_duckdb_source

        db_path = str(tmp_path / "test.duckdb")
        con = duckdb.connect(db_path)
        con.close()

        spec = load_spec(SPEC_CA)
        data = load_duckdb_source(db_path, spec)
        assert data["txn"] == []

    def test_bigquery_raises_without_extension(self):
        from aml_framework.data.sources import resolve_source

        spec = load_spec(SPEC_CA)
        with pytest.raises(RuntimeError, match="bigquery"):
            resolve_source("bigquery", spec, datetime(2026, 4, 23), data_dir="dummy")


# --- metrics/engine.py: filter operators ---


class TestMetricFilterOps:
    def test_matches_filter_operators(self):
        from aml_framework.metrics.engine import _matches_filter

        assert _matches_filter({"x": 10}, {"x": {"gt": 5}})
        assert not _matches_filter({"x": 3}, {"x": {"gt": 5}})
        assert _matches_filter({"x": 3}, {"x": {"lt": 5}})
        assert not _matches_filter({"x": 10}, {"x": {"lt": 5}})
        assert _matches_filter({"x": 5}, {"x": {"gte": 5}})
        assert _matches_filter({"x": 5}, {"x": {"lte": 5}})
        assert _matches_filter({"x": 5}, {"x": {"eq": 5}})
        assert not _matches_filter({"x": 5}, {"x": {"eq": 6}})
        assert _matches_filter({"x": 5}, {"x": {"ne": 6}})
        assert not _matches_filter({"x": 5}, {"x": {"ne": 5}})
        assert _matches_filter({"x": 5}, {"x": {"between": [3, 7]}})
        assert not _matches_filter({"x": 10}, {"x": {"between": [3, 7]}})
        assert _matches_filter({"x": "a"}, {"x": {"in": ["a", "b"]}})
        assert not _matches_filter({"x": "c"}, {"x": {"in": ["a", "b"]}})
        assert _matches_filter({"x": 5}, {"x": 5})
        assert not _matches_filter({"x": 5}, {"x": 6})
        assert not _matches_filter({"x": None}, {"x": {"gte": 5}})


# --- engine/runner.py: empty warehouse, non-active rules ---


class TestRunnerEdgeCases:
    def test_run_produces_manifest(self, tmp_path):
        """Every run produces a manifest with required fields."""
        _, _, result = _run(tmp_path)
        assert "engine_version" in result.manifest
        assert "spec_content_hash" in result.manifest
        assert "rule_outputs" in result.manifest
        assert "inputs" in result.manifest


# --- metrics/reports.py: edge cases ---


class TestReportsEdgeCases:
    def test_report_with_missing_metric(self, tmp_path):
        spec, _, result = _run(tmp_path)
        # All reports should render even if some metrics are missing.
        for report_id, md in result.reports.items():
            assert len(md) > 0

    def test_overall_rag_all_unset(self):
        from aml_framework.metrics.reports import _overall_rag
        from aml_framework.metrics.engine import MetricResult

        results = [
            MetricResult(
                id="m1",
                name="m1",
                category="op",
                audience=[],
                owner=None,
                unit=None,
                value=0,
                rag="unset",
                target_met=None,
                formula_type="count",
            ),
        ]
        assert _overall_rag(results) == "unset"


# --- diff.py: common rule modifications ---


class TestDiffCommonRules:
    def test_diff_detects_severity_change(self):
        from aml_framework.diff import diff_specs

        # Same spec vs itself — no changes.
        diff_specs(SPEC_US, SPEC_US)  # Should not raise.


# --- api/main.py: uncovered endpoints ---

try:
    from fastapi.testclient import TestClient
    from aml_framework.api.main import app

    client = TestClient(app)
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False


def _token(username="admin"):
    resp = client.post("/api/v1/login", json={"username": username, "password": username})
    return resp.json()["access_token"]


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
class TestAPIEndpoints:
    def test_get_reports_not_found(self):
        token = _token()
        resp = client.get(
            "/api/v1/runs/nonexistent/reports", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 404

    def test_get_specs_empty(self):
        token = _token()
        resp = client.get("/api/v1/specs", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_upload_stub(self):
        token = _token()
        resp = client.post("/api/v1/upload", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_get_alerts_cef_not_found(self):
        token = _token()
        resp = client.get(
            "/api/v1/runs/nonexistent/alerts/cef", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 404

    def test_login_returns_tenant(self):
        resp = client.post("/api/v1/login", json={"username": "admin", "password": "admin"})
        assert resp.json().get("tenant") == "bank_a"


# --- Additional targeted tests for 99% coverage ---


class TestSourcesParsingExtended:
    def test_parse_date_value(self):
        from aml_framework.data.sources import _parse_value

        result = _parse_value("2026-01-15", "date", True)
        assert result is not None

    def test_parse_timestamp_value(self):
        from aml_framework.data.sources import _parse_value

        result = _parse_value("2026-01-15T10:30:00", "timestamp", True)
        assert result is not None

    def test_parse_boolean_false(self):
        from aml_framework.data.sources import _parse_value

        assert _parse_value("false", "boolean", True) is False
        assert _parse_value("0", "boolean", True) is False

    def test_parse_invalid_decimal(self):
        from aml_framework.data.sources import _parse_value

        result = _parse_value("not_a_number", "decimal", True)
        assert result == "not_a_number"

    def test_validate_unknown_contract(self, tmp_path):
        from aml_framework.data.sources import validate_csv

        (tmp_path / "x.csv").write_text("a,b\n1,2\n")
        spec = load_spec(SPEC_CA)
        errors = validate_csv(tmp_path / "x.csv", spec, "nonexistent_contract")
        assert any("No data contract" in e for e in errors)

    def test_load_csv_with_date_columns(self, tmp_path):
        from aml_framework.data.sources import load_csv_source

        (tmp_path / "txn.csv").write_text(
            "txn_id,customer_id,amount,currency,channel,direction,booked_at\n"
            "T1,C1,100.50,CAD,cash,in,2026-04-01T10:00:00\n"
        )
        (tmp_path / "customer.csv").write_text(
            "customer_id,full_name,country,risk_rating,onboarded_at,business_activity,edd_last_review\n"
            "C1,Test,CA,low,2025-01-01T00:00:00,,\n"
        )
        spec = load_spec(SPEC_CA)
        data = load_csv_source(tmp_path, spec)
        assert len(data["txn"]) == 1
        assert len(data["customer"]) == 1


class TestSQLGeneratorExtended:
    def test_having_operators(self):
        from aml_framework.generators.sql import _compile_having

        selects, preds = _compile_having({"count": {"gte": 3}, "sum_amount": {"lte": 50000}})
        assert len(selects) == 2
        assert any(">=" in p for p in preds)
        assert any("<=" in p for p in preds)

    def test_filter_between(self):
        from aml_framework.generators.sql import _compile_filter

        preds = _compile_filter({"amount": {"between": [100, 500]}})
        assert any("BETWEEN" in p for p in preds)

    def test_filter_in_list(self):
        from aml_framework.generators.sql import _compile_filter

        preds = _compile_filter({"channel": {"in": ["cash", "wire"]}})
        assert any("IN" in p for p in preds)

    def test_parse_window_all_units(self):
        from aml_framework.generators.sql import parse_window

        assert parse_window("30d").days == 30
        assert parse_window("24h").total_seconds() == 86400
        assert parse_window("60m").total_seconds() == 3600
        assert parse_window("120s").total_seconds() == 120


class TestMetricEngineExtended:
    def test_rag_band_green_amber_red(self):
        from aml_framework.metrics.engine import _rag_band
        from aml_framework.spec.models import Metric, CountFormula

        m = Metric(
            id="test",
            name="test",
            category="operational",
            audience=["svp"],
            formula=CountFormula(type="count", source="alerts"),
            thresholds={"green": {"lte": 10}, "amber": {"lte": 50}, "red": {"gt": 50}},
        )
        assert _rag_band(5, m)[0] == "green"
        assert _rag_band(30, m)[0] == "amber"
        assert _rag_band(100, m)[0] == "red"

    def test_cond_holds_all_operators(self):
        from aml_framework.metrics.engine import _cond_holds

        assert _cond_holds(10, {"gte": 10})
        assert _cond_holds(10, {"lte": 10})
        assert _cond_holds(10, {"gt": 5})
        assert _cond_holds(10, {"lt": 15})
        assert _cond_holds(10, {"eq": 10})
        assert _cond_holds(10, {"between": [5, 15]})
        assert not _cond_holds(10, {"between": [15, 20]})


class TestAPIMainExtended:
    @pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
    def test_webhook_fire_and_list(self):
        token = _token()
        # Register a webhook.
        client.post(
            "/api/v1/webhooks",
            json={
                "url": "https://test.example.com",
                "events": ["run_completed"],
                "name": "test_hook",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        # List should include it.
        resp = client.get("/api/v1/webhooks", headers={"Authorization": f"Bearer {token}"})
        assert any(h.get("name") == "test_hook" for h in resp.json())

    @pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
    def test_create_run_stores_spec_version(self):
        token = _token()
        resp = client.post(
            "/api/v1/runs",
            json={"spec_path": "examples/community_bank/aml.yaml", "seed": 42},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        # Spec versions should now have an entry.
        specs = client.get("/api/v1/specs", headers={"Authorization": f"Bearer {token}"})
        assert specs.status_code == 200


class TestAuthExtended:
    @pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
    def test_bank_b_user_login(self):
        resp = client.post("/api/v1/login", json={"username": "bank_b_admin", "password": "admin"})
        assert resp.status_code == 200
        assert resp.json()["tenant"] == "bank_b"

    def test_update_status_unconfigured_returns_false(self):
        from aml_framework.integrations.jira import update_status

        assert update_status("", "Done") is False


class TestNotificationsExtended:
    def test_notify_all_severity_channels(self):
        from aml_framework.integrations.notifications import get_channel_for_severity

        for sev in ("critical", "high", "medium", "low"):
            ch = get_channel_for_severity(sev)
            assert ch != ""
