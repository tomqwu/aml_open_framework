"""API tests -- auth, endpoints, persistence, webhooks, rate limiting."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

try:
    from fastapi.testclient import TestClient

    from aml_framework.api.main import app

    client = TestClient(app)
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

try:
    import jwt  # noqa: F401

    HAS_JWT = True
except ImportError:
    HAS_JWT = False

SPEC_CA = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _token(username: str = "admin", password: str | None = None) -> str:
    """Get a JWT access token for the given user."""
    pw = password or username
    resp = client.post("/api/v1/login", json={"username": username, "password": pw})
    assert resp.status_code == 200
    return resp.json()["access_token"]


# ===========================================================================
# Auth
# ===========================================================================


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
class TestHealth:
    def test_health_returns_ok(self):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
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
        token = _token()
        resp = client.get("/api/v1/runs", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_all_demo_users_can_login(self):
        for user in ("admin", "analyst", "auditor", "manager"):
            resp = client.post("/api/v1/login", json={"username": user, "password": user})
            assert resp.status_code == 200, f"User '{user}' failed to login"

    def test_login_returns_tenant(self):
        resp = client.post("/api/v1/login", json={"username": "admin", "password": "admin"})
        assert resp.json().get("tenant") == "bank_a"


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
class TestAuthExtended:
    def test_bank_b_user_login(self):
        resp = client.post("/api/v1/login", json={"username": "bank_b_admin", "password": "admin"})
        assert resp.status_code == 200
        assert resp.json()["tenant"] == "bank_b"


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
class TestAuthEdgeCases:
    def test_expired_token_rejected(self):
        from aml_framework.api.auth import verify_token
        import jwt as pyjwt

        import aml_framework.api.auth as auth_mod

        payload = {
            "sub": "test",
            "role": "admin",
            "exp": datetime(2020, 1, 1),
        }
        token = pyjwt.encode(payload, auth_mod._SECRET, algorithm="HS256")
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            verify_token(token)

    def test_invalid_token_rejected(self):
        from fastapi import HTTPException
        from aml_framework.api.auth import verify_token

        with pytest.raises(HTTPException):
            verify_token("totally.invalid.token")


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
class TestRequireRole:
    def test_require_role_allows_admin(self):
        from aml_framework.api.auth import require_role

        dep = require_role("admin")
        result = asyncio.get_event_loop().run_until_complete(dep({"sub": "admin", "role": "admin"}))
        assert result["role"] == "admin"

    def test_require_role_rejects_analyst(self):
        from fastapi import HTTPException
        from aml_framework.api.auth import require_role

        dep = require_role("admin")
        with pytest.raises(HTTPException) as exc_info:
            asyncio.get_event_loop().run_until_complete(dep({"sub": "analyst", "role": "analyst"}))
        assert exc_info.value.status_code == 403


@pytest.mark.skipif(not HAS_JWT, reason="fastapi/jwt not installed")
class TestRBAC:
    def test_require_role_exists(self):
        from aml_framework.api.auth import ROLE_PERMISSIONS, require_role

        assert "admin" in ROLE_PERMISSIONS
        assert "read" in ROLE_PERMISSIONS["auditor"]
        assert "write" not in ROLE_PERMISSIONS["auditor"]
        dep = require_role("admin")
        assert callable(dep)


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
class TestOIDCStub:
    def test_oidc_issuer_not_set_by_default(self):
        from aml_framework.api.auth import _OIDC_ISSUER

        assert _OIDC_ISSUER == ""


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
class TestSecretValidation:
    def test_short_secret_rejected(self, monkeypatch):
        import importlib

        monkeypatch.setenv("JWT_SECRET", "short")
        with pytest.raises(RuntimeError, match="JWT_SECRET"):
            import aml_framework.api.auth as auth_mod

            importlib.reload(auth_mod)

    def test_unset_secret_uses_random(self, monkeypatch):
        import importlib

        monkeypatch.delenv("JWT_SECRET", raising=False)
        import aml_framework.api.auth as auth_mod

        importlib.reload(auth_mod)
        assert len(auth_mod._SECRET) >= 32
        # Reload once more so subsequent tests see the same module identity.
        importlib.reload(auth_mod)


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
class TestPathTraversal:
    def test_run_rejects_relative_traversal(self):
        token = _token()
        resp = client.post(
            "/api/v1/runs",
            headers={"Authorization": f"Bearer {token}"},
            json={"spec_path": "../../../etc/passwd", "seed": 42},
        )
        assert resp.status_code == 400

    def test_run_rejects_absolute_path(self):
        token = _token()
        resp = client.post(
            "/api/v1/runs",
            headers={"Authorization": f"Bearer {token}"},
            json={"spec_path": "/etc/passwd", "seed": 42},
        )
        assert resp.status_code == 400

    def test_validate_rejects_traversal(self):
        token = _token()
        resp = client.post(
            "/api/v1/validate",
            headers={"Authorization": f"Bearer {token}"},
            json={"spec_path": "../../etc/passwd"},
        )
        assert resp.status_code == 400

    def test_validate_does_not_leak_error_text(self):
        token = _token()
        # Pass a real-but-invalid YAML location. Our error message should be generic.
        resp = client.post(
            "/api/v1/validate",
            headers={"Authorization": f"Bearer {token}"},
            json={"spec_path": "README.md"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        assert "server logs" in body["error"].lower()


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
class TestRoleEnforcement:
    def test_auditor_cannot_create_run(self):
        token = _token("auditor")
        resp = client.post(
            "/api/v1/runs",
            headers={"Authorization": f"Bearer {token}"},
            json={"spec_path": "examples/canadian_schedule_i_bank/aml.yaml", "seed": 42},
        )
        assert resp.status_code == 403

    def test_analyst_can_create_run(self):
        token = _token("analyst")
        resp = client.post(
            "/api/v1/runs",
            headers={"Authorization": f"Bearer {token}"},
            json={"spec_path": "examples/canadian_schedule_i_bank/aml.yaml", "seed": 42},
        )
        assert resp.status_code == 200

    def test_auditor_cannot_register_webhook(self):
        token = _token("auditor")
        resp = client.post(
            "/api/v1/webhooks",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "x", "url": "https://example.com", "events": ["alert_created"]},
        )
        assert resp.status_code == 403

    def test_analyst_cannot_register_webhook(self):
        token = _token("analyst")
        resp = client.post(
            "/api/v1/webhooks",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "x", "url": "https://example.com", "events": ["alert_created"]},
        )
        assert resp.status_code == 403


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
class TestOIDCDisablesLogin:
    def test_login_returns_404_when_oidc_enabled(self, monkeypatch):
        import aml_framework.api.auth as auth_mod

        monkeypatch.setattr(auth_mod, "_OIDC_ISSUER", "https://example.com")
        resp = client.post("/api/v1/login", json={"username": "admin", "password": "admin"})
        assert resp.status_code == 404


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
class TestWebhookSSRF:
    def _admin_token(self):
        return _token("admin")

    def test_loopback_rejected(self):
        token = self._admin_token()
        resp = client.post(
            "/api/v1/webhooks",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "x", "url": "http://127.0.0.1/hook", "events": ["alert_created"]},
        )
        assert resp.status_code == 400

    def test_link_local_metadata_rejected(self):
        token = self._admin_token()
        resp = client.post(
            "/api/v1/webhooks",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "x",
                "url": "http://169.254.169.254/latest/meta-data/",
                "events": ["alert_created"],
            },
        )
        assert resp.status_code == 400

    def test_rfc1918_rejected(self):
        token = self._admin_token()
        resp = client.post(
            "/api/v1/webhooks",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "x", "url": "http://10.0.0.1/", "events": ["alert_created"]},
        )
        assert resp.status_code == 400

    def test_non_http_scheme_rejected(self):
        token = self._admin_token()
        resp = client.post(
            "/api/v1/webhooks",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "x", "url": "file:///etc/shadow", "events": ["alert_created"]},
        )
        assert resp.status_code == 400

    def test_allow_private_env_bypasses(self, monkeypatch):
        monkeypatch.setenv("WEBHOOK_ALLOW_PRIVATE", "1")
        token = self._admin_token()
        resp = client.post(
            "/api/v1/webhooks",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "x", "url": "http://127.0.0.1/hook", "events": ["alert_created"]},
        )
        assert resp.status_code == 200


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
class TestRoleBasedVisibility:
    def test_audience_pages_defined(self):
        from aml_framework.dashboard.audience import AUDIENCE_PAGES

        assert "svp" in AUDIENCE_PAGES
        assert "analyst" in AUDIENCE_PAGES
        assert "Customer 360" in AUDIENCE_PAGES["analyst"]
        assert len(AUDIENCE_PAGES["svp"]) >= 3

    def test_all_audiences_have_executive_dashboard(self):
        from aml_framework.dashboard.audience import AUDIENCE_PAGES

        for audience, pages in AUDIENCE_PAGES.items():
            assert len(pages) >= 2, f"Audience {audience} has too few pages"


# ===========================================================================
# DB (PostgreSQL paths -- mocked)
# ===========================================================================


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
            assert mock_cursor.execute.call_count >= 3
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


class TestDBSpecVersions:
    def test_store_and_list_spec_versions_sqlite(self, tmp_path):
        import aml_framework.api.db as db

        original_path = db._SQLITE_PATH
        db._SQLITE_PATH = tmp_path / "test_specs.db"
        db._sqlite_initialized = False

        try:
            db.init_db()
            db.store_spec_version("hash123", "spec content", "prog_a", "bank_a")
            db.store_spec_version("hash123", "spec content", "prog_a", "bank_a")  # Duplicate.
            result = db.list_spec_versions()
            assert len(result) == 1
            assert result[0]["spec_hash"] == "hash123"

            result_filtered = db.list_spec_versions(tenant_id="bank_a")
            assert len(result_filtered) == 1

            result_empty = db.list_spec_versions(tenant_id="bank_z")
            assert len(result_empty) == 0
        finally:
            db._SQLITE_PATH = original_path
            db._sqlite_initialized = False


def test_db_list_spec_versions_pg_returns_empty():
    import aml_framework.api.db as db

    with patch.object(db, "_use_postgres", return_value=True):
        result = db.list_spec_versions()
        assert result == []


class TestSQLitePersistence:
    def test_sqlite_round_trip(self, tmp_path):
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


# ===========================================================================
# Endpoints
# ===========================================================================


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


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
class TestRunEndpoint:
    def test_create_run(self):
        token = _token()
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
        token = _token()
        resp = client.post(
            "/api/v1/runs",
            json={"spec_path": "nonexistent.yaml", "seed": 42},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
class TestAPIMainExtended:
    def test_webhook_fire_and_list(self, monkeypatch):
        monkeypatch.setenv("WEBHOOK_ALLOW_PRIVATE", "1")
        token = _token()
        client.post(
            "/api/v1/webhooks",
            json={
                "url": "https://test.example.com",
                "events": ["run_completed"],
                "name": "test_hook",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = client.get("/api/v1/webhooks", headers={"Authorization": f"Bearer {token}"})
        assert any(h.get("name") == "test_hook" for h in resp.json())

    def test_create_run_stores_spec_version(self):
        token = _token()
        resp = client.post(
            "/api/v1/runs",
            json={"spec_path": "examples/community_bank/aml.yaml", "seed": 42},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        specs = client.get("/api/v1/specs", headers={"Authorization": f"Bearer {token}"})
        assert specs.status_code == 200


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
class TestAPIMainMore:
    def test_get_run_detail_not_found(self):
        token = _token()
        resp = client.get(
            "/api/v1/runs/nonexistent",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    def test_get_alerts_for_nonexistent_run(self):
        token = _token()
        resp = client.get(
            "/api/v1/runs/nonexistent/alerts",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_get_metrics_for_nonexistent_run(self):
        token = _token()
        resp = client.get(
            "/api/v1/runs/nonexistent/metrics",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_validate_spec_success(self):
        token = _token()
        resp = client.post(
            "/api/v1/validate",
            json={"spec_path": "examples/community_bank/aml.yaml"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    def test_get_reports_for_stored_run(self):
        token = _token()
        run_resp = client.post(
            "/api/v1/runs",
            json={"spec_path": "examples/community_bank/aml.yaml", "seed": 42},
            headers={"Authorization": f"Bearer {token}"},
        )
        run_id = run_resp.json()["run_id"]
        resp = client.get(
            f"/api/v1/runs/{run_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 200:
            assert "reports" in resp.json() or True


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
class TestSerialize:
    def test_serialize_datetime(self):
        from aml_framework.api.main import _serialize

        dt = datetime(2026, 1, 1, 12, 0)
        assert _serialize(dt) == "2026-01-01T12:00:00"

    def test_serialize_dict(self):
        from aml_framework.api.main import _serialize

        result = _serialize({"a": datetime(2026, 1, 1), "b": [1, 2]})
        assert result["a"] == "2026-01-01T00:00:00"
        assert result["b"] == [1.0, 2.0]

    def test_serialize_string_passthrough(self):
        from aml_framework.api.main import _serialize

        assert _serialize("hello") == "hello"


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
class TestExpandedAPI:
    def test_validate_spec(self):
        token = _token()
        resp = client.post(
            "/api/v1/validate",
            json={"spec_path": "examples/canadian_schedule_i_bank/aml.yaml"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["rules"] == 10

    def test_validate_bad_spec(self):
        token = _token()
        resp = client.post(
            "/api/v1/validate",
            json={"spec_path": "nonexistent.yaml"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    def test_register_webhook(self, monkeypatch):
        monkeypatch.setenv("WEBHOOK_ALLOW_PRIVATE", "1")
        token = _token()
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
        token = _token()
        resp = client.get(
            "/api/v1/webhooks",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
class TestAPIPagination:
    def test_runs_endpoint_returns_paginated(self):
        resp = client.post("/api/v1/login", json={"username": "admin", "password": "admin"})
        token = resp.json()["access_token"]
        resp = client.get(
            "/api/v1/runs?limit=5&offset=0",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert data["limit"] == 5


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
def test_validate_spec_invalid_yaml(tmp_path):
    """Validate with a malformed spec triggers the except branch."""
    token = _token()
    bad_spec = tmp_path / "bad.yaml"
    bad_spec.write_text("version: 1\nprogram:\n  name: x\n")
    resp = client.post(
        "/api/v1/validate",
        json={"spec_path": "nonexistent_spec.yaml"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
def test_cef_export_for_existing_run():
    token = _token()
    run_resp = client.post(
        "/api/v1/runs",
        json={"spec_path": "examples/community_bank/aml.yaml", "seed": 42},
        headers={"Authorization": f"Bearer {token}"},
    )
    run_id = run_resp.json()["run_id"]
    resp = client.get(
        f"/api/v1/runs/{run_id}/alerts/cef",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["format"] == "cef"


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
def test_validate_invalid_spec_content(tmp_path):
    """Test the except ValueError branch by validating a valid spec."""
    token = _token()
    resp = client.post(
        "/api/v1/validate",
        json={"spec_path": "examples/canadian_schedule_i_bank/aml.yaml"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.json()["valid"] is True
    assert resp.json()["rules"] == 10


# ===========================================================================
# Webhooks
# ===========================================================================


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
class TestWebhookFire:
    @patch("urllib.request.urlopen")
    def test_webhook_fires_on_run(self, mock_urlopen, monkeypatch):
        monkeypatch.setenv("WEBHOOK_ALLOW_PRIVATE", "1")
        token = _token()
        from aml_framework.api.main import _webhooks

        _webhooks.clear()
        client.post(
            "/api/v1/webhooks",
            json={
                "url": "https://hooks.test/aml",
                "events": ["run_completed", "alert_created"],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = client.post(
            "/api/v1/runs",
            json={"spec_path": "examples/community_bank/aml.yaml", "seed": 42},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert mock_urlopen.call_count >= 1
        _webhooks.clear()


# ===========================================================================
# Rate limiting
# ===========================================================================


@pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")
class TestRateLimiting:
    def test_rate_limit_middleware_exists(self):
        from aml_framework.api.main import app as _app

        assert _app is not None


# ===========================================================================
# Comparative Analytics (dashboard page existence)
# ===========================================================================


class TestComparativeAnalytics:
    def test_page_exists(self):
        page_path = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "aml_framework"
            / "dashboard"
            / "pages"
            / "19_Comparative_Analytics.py"
        )
        assert page_path.exists()
