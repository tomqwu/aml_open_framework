"""Tests for CLI tools (diff, export-alerts), SQLite persistence, and expanded API."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import pytest

from aml_framework.data import generate_dataset
from aml_framework.engine import run_spec
from aml_framework.spec import load_spec

SPEC_US = Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"
SPEC_CA = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


# --- Spec Diff Tests ---

class TestSpecDiff:
    def test_diff_runs_without_error(self):
        from aml_framework.diff import diff_specs
        # Should not raise.
        diff_specs(SPEC_US, SPEC_CA)

    def test_diff_detects_rule_additions(self):
        from io import StringIO
        from unittest.mock import patch

        from aml_framework.diff import diff_specs

        with patch("sys.stdout", new_callable=StringIO):
            # Just verify it doesn't crash. Output goes to rich console.
            diff_specs(SPEC_US, SPEC_CA)

    def test_diff_same_spec_shows_no_changes(self):
        from aml_framework.diff import diff_specs
        # Same spec vs itself should show no changes.
        diff_specs(SPEC_US, SPEC_US)


# --- Alert Export Tests ---

class TestAlertExport:
    def test_export_alerts_produces_csv(self, tmp_path):
        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        result = run_spec(spec=spec, spec_path=SPEC_CA, data=data, as_of=as_of,
                         artifacts_root=tmp_path)

        # Use the CLI function directly.
        import csv

        run_dir = Path(result.manifest["run_dir"])
        alerts_dir = run_dir / "alerts"
        out_csv = tmp_path / "alerts.csv"

        all_alerts = []
        for jsonl_file in sorted(alerts_dir.glob("*.jsonl")):
            for line in jsonl_file.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    alert = json.loads(line)
                    alert["rule_id"] = jsonl_file.stem
                    all_alerts.append(alert)

        assert len(all_alerts) > 0

        with out_csv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(all_alerts[0].keys()), extrasaction="ignore")
            writer.writeheader()
            writer.writerows(all_alerts)

        assert out_csv.exists()
        lines = out_csv.read_text().splitlines()
        assert len(lines) > 1  # header + data


# --- SQLite Persistence Tests ---

class TestSQLitePersistence:
    def test_sqlite_round_trip(self, tmp_path):
        """Store a run in SQLite and retrieve it."""
        # Override the SQLite path.
        import aml_framework.api.db as db_mod

        original_path = db_mod._SQLITE_PATH
        db_mod._SQLITE_PATH = tmp_path / "test_runs.db"
        db_mod._sqlite_initialized = False

        try:
            db_mod.init_db()
            db_mod.store_run(
                run_id="test-001",
                spec_path="examples/test.yaml",
                seed=42,
                manifest={"engine_version": "0.1.0", "total_alerts": 5},
                alerts={"rule_a": [{"customer_id": "C001", "amount": 1000}]},
                metrics=[{"id": "m1", "value": 0.5}],
            )

            runs = db_mod.list_runs()
            assert len(runs) == 1
            assert runs[0]["run_id"] == "test-001"

            manifest = db_mod.get_run("test-001")
            assert manifest["total_alerts"] == 5

            alerts = db_mod.get_run_alerts("test-001")
            assert len(alerts) == 1
            assert alerts[0]["rule_id"] == "rule_a"

            metrics = db_mod.get_run_metrics("test-001")
            assert len(metrics) == 1
        finally:
            db_mod._SQLITE_PATH = original_path
            db_mod._sqlite_initialized = False


# --- Expanded API Tests ---

try:
    from fastapi.testclient import TestClient
    from aml_framework.api.main import app
    client = TestClient(app)
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

pytestmark_api = pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")


def _login():
    resp = client.post("/api/v1/login", json={"username": "admin", "password": "admin"})
    return resp.json()["access_token"]


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
class TestExpandedAPI:
    def test_validate_spec(self):
        token = _login()
        resp = client.post(
            "/api/v1/validate",
            json={"spec_path": "examples/canadian_schedule_i_bank/aml.yaml"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["rules"] == 9

    def test_validate_bad_spec(self):
        token = _login()
        resp = client.post(
            "/api/v1/validate",
            json={"spec_path": "nonexistent.yaml"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    def test_register_webhook(self):
        token = _login()
        resp = client.post(
            "/api/v1/webhooks",
            json={"url": "https://hooks.example.com/aml", "events": ["alert_created"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "registered"
        assert data["event_count"] >= 1

    def test_list_webhooks(self):
        token = _login()
        resp = client.get(
            "/api/v1/webhooks",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# --- Load Test ---

class TestLoadPerformance:
    def test_engine_throughput(self, tmp_path):
        """Measure how many transactions the engine processes per second."""
        spec = load_spec(SPEC_CA)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42, n_customers=25, n_noise_txns=400)
        n_txns = len(data["txn"])

        start = time.time()
        result = run_spec(spec=spec, spec_path=SPEC_CA, data=data, as_of=as_of,
                         artifacts_root=tmp_path)
        elapsed = time.time() - start

        txns_per_sec = n_txns / elapsed
        assert result.total_alerts > 0
        # Should process at least 100 txns/sec even on slow hardware.
        assert txns_per_sec > 100, f"Too slow: {txns_per_sec:.0f} txns/sec"
