"""Run persistence — SQLite, PostgreSQL, or Cosmos DB.

Backend selection (highest priority first):
  1. COSMOS_ENDPOINT set → Azure Cosmos DB (serverless). Used on Azure
     Sponsorship subscriptions where Postgres Flexible Server is locked
     (LocationIsOfferRestricted on every region we tried).
  2. DATABASE_URL set → PostgreSQL via psycopg2. Used on PAYG/EA/MCA Azure
     subscriptions and self-hosted deployments.
  3. Otherwise → SQLite at ~/.aml_framework/runs.db, so the API works
     without Docker.

Internal layout for SQL backends: every public CRUD function calls
`_with_conn()` and writes its query once with `?` placeholders. The
wrapper translates `?` to `%s` on the Postgres path so we don't carry
two near-identical SQL bodies per function.

Cosmos doesn't speak placeholder SQL — it has a SQL-like query language
with `@parameters` and a separate point-read API. Each public function
branches early on `_use_cosmos()` and uses the Cosmos client directly.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DATABASE_URL = os.environ.get("DATABASE_URL", "")
_SQLITE_PATH = Path.home() / ".aml_framework" / "runs.db"
_COSMOS_ENDPOINT = os.environ.get("COSMOS_ENDPOINT", "")
_COSMOS_DATABASE = os.environ.get("COSMOS_DATABASE", "aml")


def _use_cosmos() -> bool:
    return bool(_COSMOS_ENDPOINT)


def _use_postgres() -> bool:
    return bool(_DATABASE_URL)


def _get_pg_conn():
    import psycopg2  # pragma: no cover

    return psycopg2.connect(_DATABASE_URL)  # pragma: no cover


# Cosmos DB containers — partition key is /tenant_id on every container, so
# tenant-scoped queries stay single-partition. Document `id` is the natural
# unique identifier per container (run_id, run_alert_id, etc.); see the
# per-container builders below for the id shape.
_COSMOS_CONTAINERS = ("runs", "run_alerts", "run_metrics", "spec_versions")
_cosmos_client = None
_cosmos_db = None


def _get_cosmos_db():
    """Lazy-init the Cosmos client + database handle. DefaultAzureCredential
    pulls the UAMI on Container Apps and falls back to az CLI / env locally.
    """
    global _cosmos_client, _cosmos_db
    if _cosmos_db is not None:
        return _cosmos_db
    from azure.cosmos import CosmosClient  # pragma: no cover
    from azure.identity import DefaultAzureCredential  # pragma: no cover

    _cosmos_client = CosmosClient(  # pragma: no cover
        _COSMOS_ENDPOINT, credential=DefaultAzureCredential()
    )
    _cosmos_db = _cosmos_client.get_database_client(_COSMOS_DATABASE)  # pragma: no cover
    return _cosmos_db  # pragma: no cover


def _cosmos_container(name: str):
    return _get_cosmos_db().get_container_client(name)  # pragma: no cover


_sqlite_initialized = False


def _get_sqlite_conn() -> sqlite3.Connection:
    global _sqlite_initialized
    _SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_SQLITE_PATH))
    conn.row_factory = sqlite3.Row
    if not _sqlite_initialized:
        conn.executescript(_SQLITE_SCHEMA)
        _sqlite_initialized = True
    return conn


_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    spec_path TEXT NOT NULL,
    seed INTEGER NOT NULL,
    manifest TEXT NOT NULL,
    tenant_id TEXT DEFAULT 'default',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT REFERENCES runs(run_id),
    rule_id TEXT NOT NULL,
    alerts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT REFERENCES runs(run_id),
    metrics TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS spec_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    spec_hash TEXT NOT NULL,
    spec_content TEXT NOT NULL,
    program_name TEXT,
    tenant_id TEXT DEFAULT 'default',
    created_at TEXT NOT NULL
);
"""

_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    spec_path TEXT NOT NULL,
    seed INTEGER NOT NULL,
    manifest JSONB NOT NULL,
    tenant_id TEXT DEFAULT 'default',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS run_alerts (
    id SERIAL PRIMARY KEY,
    run_id TEXT REFERENCES runs(run_id),
    rule_id TEXT NOT NULL,
    alerts JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS run_metrics (
    id SERIAL PRIMARY KEY,
    run_id TEXT REFERENCES runs(run_id),
    metrics JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS spec_versions (
    id SERIAL PRIMARY KEY,
    spec_hash TEXT NOT NULL,
    spec_content TEXT NOT NULL,
    program_name TEXT,
    tenant_id TEXT DEFAULT 'default',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
"""


class _PgCursor:
    """Translates `?` placeholders to `%s` for psycopg2."""

    def __init__(self, cur):
        self._cur = cur

    def execute(self, query: str, params: tuple = ()):
        self._cur.execute(query.replace("?", "%s"), params)
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()


class _SqliteWrapper:
    """Thin wrapper around sqlite3.Connection so callers can use the same API."""

    def __init__(self, conn):
        self._conn = conn
        self._last = None

    def execute(self, query: str, params: tuple = ()):
        self._last = self._conn.execute(query, params)
        return self

    def fetchone(self):
        return self._last.fetchone() if self._last else None

    def fetchall(self):
        return self._last.fetchall() if self._last else []


@contextmanager
def _with_conn():
    """Open a connection, yield a cursor-like wrapper, commit on exit."""
    if _use_postgres():
        conn = _get_pg_conn()
        try:
            with conn.cursor() as cur:
                yield _PgCursor(cur)
            conn.commit()
        finally:
            conn.close()
    else:
        conn = _get_sqlite_conn()
        try:
            yield _SqliteWrapper(conn)
            conn.commit()
        finally:
            conn.close()


def _coerce_ts(value: Any) -> str:
    """Both backends return timestamps; PG gives datetime, SQLite gives str."""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value) if value is not None else ""


def _from_json(value: Any) -> Any:
    """Decode backend JSON values.

    SQLite returns stored JSON as strings. Psycopg2 commonly returns JSONB as
    already-decoded dict/list values.
    """
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        return json.loads(value)
    return value


def init_db() -> None:
    """Create tables if they don't exist. Multi-statement scripts need
    backend-specific entry points (executescript on SQLite, single execute
    on psycopg2). Cosmos containers are created by Terraform — confirm
    the database handle resolves so misconfiguration surfaces at startup."""
    if _use_cosmos():
        _get_cosmos_db()  # pragma: no cover -- live Cosmos handshake
        return
    if _use_postgres():
        conn = _get_pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(_PG_SCHEMA)
            conn.commit()
        finally:
            conn.close()
    else:
        conn = _get_sqlite_conn()
        try:
            conn.executescript(_SQLITE_SCHEMA)
            conn.commit()
        finally:
            conn.close()


def store_run(
    run_id: str,
    spec_path: str,
    seed: int,
    manifest: dict[str, Any],
    alerts: dict[str, list[dict]],
    metrics: list[dict],
    tenant_id: str = "default",
) -> None:
    now = datetime.now(tz=timezone.utc).isoformat()
    if _use_cosmos():
        runs = _cosmos_container("runs")
        runs.upsert_item(
            {
                "id": run_id,
                "run_id": run_id,
                "tenant_id": tenant_id,
                "spec_path": spec_path,
                "seed": seed,
                "manifest": manifest,
                "created_at": now,
            }
        )
        run_alerts = _cosmos_container("run_alerts")
        for rule_id, rule_alerts in alerts.items():
            run_alerts.upsert_item(
                {
                    "id": f"{run_id}:{rule_id}",
                    "run_id": run_id,
                    "tenant_id": tenant_id,
                    "rule_id": rule_id,
                    "alerts": rule_alerts,
                }
            )
        _cosmos_container("run_metrics").upsert_item(
            {
                "id": run_id,
                "run_id": run_id,
                "tenant_id": tenant_id,
                "metrics": metrics,
            }
        )
        return
    with _with_conn() as cur:
        cur.execute(
            "INSERT INTO runs (run_id, spec_path, seed, manifest, tenant_id, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, spec_path, seed, json.dumps(manifest), tenant_id, now),
        )
        for rule_id, rule_alerts in alerts.items():
            cur.execute(
                "INSERT INTO run_alerts (run_id, rule_id, alerts) VALUES (?, ?, ?)",
                (run_id, rule_id, json.dumps(rule_alerts)),
            )
        cur.execute(
            "INSERT INTO run_metrics (run_id, metrics) VALUES (?, ?)",
            (run_id, json.dumps(metrics)),
        )


def list_runs(tenant_id: str | None = None) -> list[dict[str, Any]]:
    """List recent runs. When `tenant_id` is given, only that tenant's runs."""
    if _use_cosmos():
        runs = _cosmos_container("runs")
        if tenant_id is None:
            query = "SELECT TOP 50 c.run_id, c.spec_path, c.seed, c.created_at FROM c ORDER BY c.created_at DESC"
            params: list[dict[str, Any]] = []
            items = runs.query_items(
                query=query, parameters=params, enable_cross_partition_query=True
            )
        else:
            query = "SELECT TOP 50 c.run_id, c.spec_path, c.seed, c.created_at FROM c WHERE c.tenant_id = @t ORDER BY c.created_at DESC"
            params = [{"name": "@t", "value": tenant_id}]
            items = runs.query_items(query=query, parameters=params, partition_key=tenant_id)
        return [
            {
                "run_id": r["run_id"],
                "spec_path": r["spec_path"],
                "seed": r["seed"],
                "created_at": _coerce_ts(r["created_at"]),
            }
            for r in items
        ]
    with _with_conn() as cur:
        if tenant_id is None:
            cur.execute(
                "SELECT run_id, spec_path, seed, created_at FROM runs"
                " ORDER BY created_at DESC LIMIT 50"
            )
        else:
            cur.execute(
                "SELECT run_id, spec_path, seed, created_at FROM runs"
                " WHERE tenant_id = ? ORDER BY created_at DESC LIMIT 50",
                (tenant_id,),
            )
        return [
            {
                "run_id": r[0],
                "spec_path": r[1],
                "seed": r[2],
                "created_at": _coerce_ts(r[3]),
            }
            for r in cur.fetchall()
        ]


def get_run(run_id: str, tenant_id: str | None = None) -> dict[str, Any] | None:
    """Fetch a run's manifest. When `tenant_id` is given, returns None if the
    run belongs to a different tenant — prevents cross-tenant reads."""
    if _use_cosmos():
        runs = _cosmos_container("runs")
        if tenant_id is not None:
            try:
                doc = runs.read_item(item=run_id, partition_key=tenant_id)
            except Exception:
                return None
            return doc.get("manifest")
        query = "SELECT TOP 1 c.manifest FROM c WHERE c.run_id = @r"
        params = [{"name": "@r", "value": run_id}]
        rows = list(
            runs.query_items(query=query, parameters=params, enable_cross_partition_query=True)
        )
        return rows[0]["manifest"] if rows else None
    with _with_conn() as cur:
        if tenant_id is None:
            cur.execute("SELECT manifest FROM runs WHERE run_id = ?", (run_id,))
        else:
            cur.execute(
                "SELECT manifest FROM runs WHERE run_id = ? AND tenant_id = ?",
                (run_id, tenant_id),
            )
        row = cur.fetchone()
        return _from_json(row[0]) if row else None


def get_run_alerts(run_id: str, tenant_id: str | None = None) -> list[dict[str, Any]]:
    if _use_cosmos():
        run_alerts = _cosmos_container("run_alerts")
        if tenant_id is not None:
            query = "SELECT c.rule_id, c.alerts FROM c WHERE c.run_id = @r AND c.tenant_id = @t"
            params = [
                {"name": "@r", "value": run_id},
                {"name": "@t", "value": tenant_id},
            ]
            rows = run_alerts.query_items(query=query, parameters=params, partition_key=tenant_id)
        else:
            query = "SELECT c.rule_id, c.alerts FROM c WHERE c.run_id = @r"
            params = [{"name": "@r", "value": run_id}]
            rows = run_alerts.query_items(
                query=query, parameters=params, enable_cross_partition_query=True
            )
        return [{"rule_id": r["rule_id"], "alerts": r["alerts"]} for r in rows]
    with _with_conn() as cur:
        if tenant_id is None:
            cur.execute("SELECT rule_id, alerts FROM run_alerts WHERE run_id = ?", (run_id,))
        else:
            cur.execute(
                "SELECT ra.rule_id, ra.alerts FROM run_alerts ra"
                " JOIN runs r ON r.run_id = ra.run_id"
                " WHERE ra.run_id = ? AND r.tenant_id = ?",
                (run_id, tenant_id),
            )
        return [{"rule_id": r[0], "alerts": _from_json(r[1])} for r in cur.fetchall()]


def get_run_metrics(run_id: str, tenant_id: str | None = None) -> list[dict[str, Any]]:
    if _use_cosmos():
        run_metrics = _cosmos_container("run_metrics")
        if tenant_id is not None:
            try:
                doc = run_metrics.read_item(item=run_id, partition_key=tenant_id)
            except Exception:
                return []
            return doc.get("metrics", [])
        query = "SELECT TOP 1 c.metrics FROM c WHERE c.run_id = @r"
        params = [{"name": "@r", "value": run_id}]
        rows = list(
            run_metrics.query_items(
                query=query, parameters=params, enable_cross_partition_query=True
            )
        )
        return rows[0]["metrics"] if rows else []
    with _with_conn() as cur:
        if tenant_id is None:
            cur.execute("SELECT metrics FROM run_metrics WHERE run_id = ?", (run_id,))
        else:
            cur.execute(
                "SELECT rm.metrics FROM run_metrics rm"
                " JOIN runs r ON r.run_id = rm.run_id"
                " WHERE rm.run_id = ? AND r.tenant_id = ?",
                (run_id, tenant_id),
            )
        row = cur.fetchone()
        return _from_json(row[0]) if row else []


def store_spec_version(
    spec_hash: str,
    spec_content: str,
    program_name: str,
    tenant_id: str = "default",
) -> None:
    """Store a spec version for tracking."""
    now = datetime.now(tz=timezone.utc).isoformat()
    if _use_cosmos():
        specs = _cosmos_container("spec_versions")
        # Cosmos `id` must be unique within partition; combine spec_hash +
        # tenant_id so the same hash can exist for two tenants without
        # the upsert creating accidental writes.
        item_id = f"{tenant_id}:{spec_hash}"
        try:
            specs.read_item(item=item_id, partition_key=tenant_id)
            return  # already stored — preserve original created_at
        except Exception:
            pass
        specs.create_item(
            {
                "id": item_id,
                "spec_hash": spec_hash,
                "spec_content": spec_content,
                "program_name": program_name,
                "tenant_id": tenant_id,
                "created_at": now,
            }
        )
        return
    with _with_conn() as cur:
        cur.execute(
            "SELECT id FROM spec_versions WHERE spec_hash = ? AND tenant_id = ?",
            (spec_hash, tenant_id),
        )
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO spec_versions"
                " (spec_hash, spec_content, program_name, tenant_id, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (spec_hash, spec_content, program_name, tenant_id, now),
            )


def list_spec_versions(tenant_id: str | None = None) -> list[dict[str, Any]]:
    """List stored spec versions."""
    if _use_cosmos():
        specs = _cosmos_container("spec_versions")
        if tenant_id is None:
            query = "SELECT TOP 50 c.spec_hash, c.program_name, c.tenant_id, c.created_at FROM c ORDER BY c.created_at DESC"
            params: list[dict[str, Any]] = []
            rows = specs.query_items(
                query=query, parameters=params, enable_cross_partition_query=True
            )
        else:
            query = "SELECT TOP 50 c.spec_hash, c.program_name, c.tenant_id, c.created_at FROM c WHERE c.tenant_id = @t ORDER BY c.created_at DESC"
            params = [{"name": "@t", "value": tenant_id}]
            rows = specs.query_items(query=query, parameters=params, partition_key=tenant_id)
        return [
            {
                "spec_hash": r["spec_hash"],
                "program_name": r["program_name"],
                "tenant_id": r["tenant_id"],
                "created_at": _coerce_ts(r["created_at"]),
            }
            for r in rows
        ]
    with _with_conn() as cur:
        query = "SELECT spec_hash, program_name, tenant_id, created_at FROM spec_versions"
        params: tuple = ()
        if tenant_id:
            query += " WHERE tenant_id = ?"
            params = (tenant_id,)
        query += " ORDER BY created_at DESC LIMIT 50"
        cur.execute(query, params)
        rows = cur.fetchall()
        return [
            {
                "spec_hash": r[0],
                "program_name": r[1],
                "tenant_id": r[2],
                "created_at": _coerce_ts(r[3]),
            }
            for r in rows
        ]
