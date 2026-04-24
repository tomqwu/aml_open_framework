"""End-to-end tests for the FastAPI REST API.

Uses FastAPI's TestClient (no real server needed, no PostgreSQL needed).
Run with: pytest tests/test_e2e_api.py -v
"""

from __future__ import annotations

import pytest

try:
    from fastapi.testclient import TestClient

    from aml_framework.api.main import app

    client = TestClient(app)
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

pytestmark = pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")


def _login(username: str = "admin", password: str = "admin") -> str:
    resp = client.post("/api/v1/login", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


class TestHealth:
    def test_health_returns_ok(self):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestAuth:
    def test_login_valid_user(self):
        resp = client.post("/api/v1/login", json={"username": "admin", "password": "admin"})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["role"] == "admin"

    def test_login_invalid_password(self):
        resp = client.post("/api/v1/login", json={"username": "admin", "password": "wrong"})
        assert resp.status_code == 401

    def test_login_unknown_user(self):
        resp = client.post("/api/v1/login", json={"username": "nobody", "password": "x"})
        assert resp.status_code == 401

    def test_protected_endpoint_without_token(self):
        resp = client.get("/api/v1/runs")
        assert resp.status_code in (401, 403)

    def test_protected_endpoint_with_token(self):
        token = _login()
        resp = client.get("/api/v1/runs", headers={"Authorization": f"Bearer {token}"})
        # Returns empty list (no PostgreSQL) but doesn't error.
        assert resp.status_code == 200

    def test_all_demo_users_can_login(self):
        for user in ("admin", "analyst", "auditor", "manager"):
            resp = client.post("/api/v1/login", json={"username": user, "password": user})
            assert resp.status_code == 200, f"User '{user}' failed to login"


class TestRunEndpoint:
    def test_create_run(self):
        token = _login()
        resp = client.post(
            "/api/v1/runs",
            json={"spec_path": "examples/canadian_schedule_i_bank/aml.yaml", "seed": 42},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        assert data["total_alerts"] > 0
        assert data["total_cases"] > 0
        assert data["total_metrics"] > 0
        assert "cao_quarterly" in data["reports"]

    def test_create_run_invalid_spec(self):
        token = _login()
        resp = client.post(
            "/api/v1/runs",
            json={"spec_path": "nonexistent.yaml", "seed": 42},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404
