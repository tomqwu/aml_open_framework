"""Run persistence — SQLite locally, PostgreSQL in production.

When DATABASE_URL is set, uses psycopg2. Otherwise falls back to SQLite
at ~/.aml_framework/runs.db so the API works without Docker.

Internal layout: every public CRUD function calls `_with_conn()` and writes
its query once with `?` placeholders. The wrapper translates `?` to `%s`
on the Postgres path so we don't carry two near-identical SQL bodies per
function.
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


def _use_postgres() -> bool:
    return bool(_DATABASE_URL)


def _get_pg_conn():
    import psycopg2  # pragma: no cover

    return psycopg2.connect(_DATABASE_URL)  # pragma: no cover


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
    on psycopg2)."""
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
