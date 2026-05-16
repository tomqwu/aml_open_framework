"""Cosmos-DB-backed code paths in `aml_framework.api.db`.

`test_db_precedence.py` pins postgres-first precedence and the SQL
path; this file exercises the previously-uncovered *Cosmos* branches
of `api.db` — the cross-partition query path, the point-read /
not-found path, the `_from_json` bytes+scalar branches, the
`_get_cosmos_db` cache, and the `_CosmosNotFound` ImportError shim —
by mocking the Cosmos container client. No live Azure required.
(Not every CRUD function — `store_run` / `list_runs` /
`store_spec_version` retain their existing coverage elsewhere.)

Each test forces `_active_backend() == "cosmos"` (postgres + sqlite
unset) and patches `_cosmos_container` to return a MagicMock whose
`query_items` / `read_item` return the documents we want, then
asserts the function returns the exact normalised shape the API
contract promises.
"""

from __future__ import annotations

import importlib
import sys
from contextlib import ExitStack
from unittest.mock import MagicMock, patch


def _make_not_found(db):
    """Build a `_CosmosNotFound` instance. When azure-cosmos is
    installed the alias is the real `CosmosResourceNotFoundError`
    (constructor wants a numeric status_code); the `.[dev]`-only
    fallback shim is a plain Exception. Handle both."""
    try:
        return db._CosmosNotFound(status_code=404, message="not found")
    except TypeError:
        return db._CosmosNotFound("not found")


def _cosmos_ctx(db, container):
    """An ExitStack that forces the cosmos backend and stubs the
    container client to `container`."""
    stack = ExitStack()
    stack.enter_context(patch.object(db, "_use_postgres", return_value=False))
    stack.enter_context(patch.object(db, "_use_cosmos", return_value=True))
    stack.enter_context(patch.object(db, "_cosmos_container", return_value=container))
    return stack


class TestGetCosmosDbCachesHandle:
    """`_get_cosmos_db()` must return the already-built handle without
    re-importing azure.cosmos when `_cosmos_db` is already set — the
    early-return cache path (db.py:157-158)."""

    def test_cached_handle_returned_without_reinit(self):
        import aml_framework.api.db as db

        sentinel = object()
        original = db._cosmos_db
        try:
            db._cosmos_db = sentinel  # type: ignore[assignment]
            # If the cache path is taken, no azure import happens and
            # the exact same object comes back.
            assert db._get_cosmos_db() is sentinel
        finally:
            db._cosmos_db = original


class TestCosmosNotFoundFallbackShim:
    """When `azure.cosmos.exceptions` can't be imported (unit-test CI
    installs only `.[dev]`, not `.[azure]`), the module must fall back
    to a local `_CosmosNotFound(Exception)` stub so the rest of the
    module still imports. Reload the module with the import blocked
    and assert the shim is a plain Exception subclass."""

    def test_importerror_falls_back_to_stub_exception(self):
        import aml_framework.api.db as db

        real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __import__

        def blocked_import(name, *args, **kwargs):
            if name == "azure.cosmos.exceptions":
                raise ImportError("simulated: azure-cosmos not installed")
            return real_import(name, *args, **kwargs)

        saved = sys.modules.pop("azure.cosmos.exceptions", None)
        try:
            with patch("builtins.__import__", side_effect=blocked_import):
                reloaded = importlib.reload(db)
                shim = reloaded._CosmosNotFound
                assert issubclass(shim, Exception)
                # The shim is a *distinct* class defined in db.py, not
                # the azure one — instantiable and raisable.
                assert shim.__module__ == reloaded.__name__
                with __import__("pytest").raises(shim):
                    raise shim("not found")
        finally:
            if saved is not None:
                sys.modules["azure.cosmos.exceptions"] = saved
            # Restore the real module state for the rest of the suite.
            importlib.reload(db)


class TestFromJsonDecodesBackendValues:
    """`_from_json` normalises the three shapes the backends hand back:
    already-decoded dict/list (psycopg2 JSONB), bytes/bytearray
    (some drivers), and JSON strings (SQLite)."""

    def test_bytes_value_is_utf8_decoded_then_parsed(self):
        from aml_framework.api.db import _from_json

        # db.py:335 — bytes get decoded before json.loads.
        assert _from_json(b'{"k": 1}') == {"k": 1}
        assert _from_json(bytearray(b"[1, 2, 3]")) == [1, 2, 3]

    def test_non_json_scalar_passes_through_unchanged(self):
        from aml_framework.api.db import _from_json

        # db.py:338 — an int/None isn't dict/list/bytes/str, returned as-is.
        assert _from_json(42) == 42
        assert _from_json(None) is None

    def test_already_decoded_container_returned_as_is(self):
        from aml_framework.api.db import _from_json

        d = {"already": "decoded"}
        assert _from_json(d) is d


class TestGetRunCosmosCrossPartition:
    """`get_run(run_id)` with no tenant must take the Cosmos
    cross-partition query path (db.py:487-492) and return the
    manifest of the first matching doc, or None when empty."""

    def test_returns_manifest_from_cross_partition_query(self):
        import aml_framework.api.db as db

        container = MagicMock()
        container.query_items.return_value = iter([{"manifest": {"rules": 3, "spec": "ca"}}])
        with _cosmos_ctx(db, container):
            result = db.get_run("run-1")

        assert result == {"rules": 3, "spec": "ca"}
        # Cross-partition query (no tenant scoping).
        _, kwargs = container.query_items.call_args
        assert kwargs["enable_cross_partition_query"] is True
        assert kwargs["parameters"] == [{"name": "@r", "value": "run-1"}]

    def test_returns_none_when_no_doc(self):
        import aml_framework.api.db as db

        container = MagicMock()
        container.query_items.return_value = iter([])
        with _cosmos_ctx(db, container):
            assert db.get_run("missing") is None

    def test_tenant_scoped_point_read_hits_not_found(self):
        import aml_framework.api.db as db

        container = MagicMock()
        container.read_item.side_effect = _make_not_found(db)
        with _cosmos_ctx(db, container):
            assert db.get_run("r1", tenant_id="acme") is None


class TestGetRunAlertsCosmosNoTenant:
    """`get_run_alerts(run_id)` without a tenant takes the
    cross-partition query branch (db.py:516-518)."""

    def test_no_tenant_cross_partition_query_returns_rows(self):
        import aml_framework.api.db as db

        container = MagicMock()
        container.query_items.return_value = iter(
            [
                {"rule_id": "structuring", "alerts": [{"customer_id": "C1"}]},
                {"rule_id": "rapid_pass", "alerts": []},
            ]
        )
        with _cosmos_ctx(db, container):
            rows = db.get_run_alerts("run-9")

        assert rows == [
            {"rule_id": "structuring", "alerts": [{"customer_id": "C1"}]},
            {"rule_id": "rapid_pass", "alerts": []},
        ]
        _, kwargs = container.query_items.call_args
        assert kwargs["enable_cross_partition_query"] is True


class TestGetRunMetricsCosmosNoTenant:
    """`get_run_metrics(run_id)` without a tenant takes the TOP-1
    cross-partition query branch (db.py:544-551)."""

    def test_no_tenant_query_returns_metrics_list(self):
        import aml_framework.api.db as db

        container = MagicMock()
        container.query_items.return_value = iter(
            [{"metrics": [{"id": "alert_rate", "value": 0.12}]}]
        )
        with _cosmos_ctx(db, container):
            assert db.get_run_metrics("run-x") == [{"id": "alert_rate", "value": 0.12}]

    def test_no_tenant_query_empty_returns_empty_list(self):
        import aml_framework.api.db as db

        container = MagicMock()
        container.query_items.return_value = iter([])
        with _cosmos_ctx(db, container):
            assert db.get_run_metrics("none") == []

    def test_tenant_scoped_metrics_not_found_returns_empty(self):
        import aml_framework.api.db as db

        container = MagicMock()
        container.read_item.side_effect = _make_not_found(db)
        with _cosmos_ctx(db, container):
            assert db.get_run_metrics("r1", tenant_id="acme") == []


class TestListSpecVersionsCosmosNoTenant:
    """`list_spec_versions()` without a tenant takes the cross-
    partition ORDER-BY-created_at query branch (db.py:615-617)."""

    def test_no_tenant_query_returns_normalised_rows(self):
        import aml_framework.api.db as db

        container = MagicMock()
        container.query_items.return_value = iter(
            [
                {
                    "spec_hash": "abc",
                    "program_name": "CA Sched I",
                    "tenant_id": "default",
                    "created_at": "2026-05-01T00:00:00+00:00",
                }
            ]
        )
        with _cosmos_ctx(db, container):
            rows = db.list_spec_versions()

        assert rows == [
            {
                "spec_hash": "abc",
                "program_name": "CA Sched I",
                "tenant_id": "default",
                "created_at": "2026-05-01T00:00:00+00:00",
            }
        ]
        _, kwargs = container.query_items.call_args
        assert kwargs["enable_cross_partition_query"] is True
