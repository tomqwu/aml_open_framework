"""Run persistence — SQLite locally, PostgreSQL in production.

When DATABASE_URL is set, uses psycopg2. Otherwise falls back to SQLite
at ~/.aml_framework/runs.db so the API works without Docker.
"""

from __future__ import annotations

import json
import os
import sqlite3
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
"""


def init_db() -> None:
    """Create tables if they don't exist."""
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
        conn.executescript(_SQLITE_SCHEMA)
        conn.close()


def store_run(
    run_id: str,
    spec_path: str,
    seed: int,
    manifest: dict[str, Any],
    alerts: dict[str, list[dict]],
    metrics: list[dict],
) -> None:
    now = datetime.now(tz=timezone.utc).isoformat()

    if _use_postgres():
        conn = _get_pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO runs (run_id, spec_path, seed, manifest) VALUES (%s, %s, %s, %s)",
                    (run_id, spec_path, seed, json.dumps(manifest)),
                )
                for rule_id, rule_alerts in alerts.items():
                    cur.execute(
                        "INSERT INTO run_alerts (run_id, rule_id, alerts) VALUES (%s, %s, %s)",
                        (run_id, rule_id, json.dumps(rule_alerts)),
                    )
                cur.execute(
                    "INSERT INTO run_metrics (run_id, metrics) VALUES (%s, %s)",
                    (run_id, json.dumps(metrics)),
                )
            conn.commit()
        finally:
            conn.close()
    else:
        conn = _get_sqlite_conn()
        conn.execute(
            "INSERT INTO runs (run_id, spec_path, seed, manifest, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (run_id, spec_path, seed, json.dumps(manifest), now),
        )
        for rule_id, rule_alerts in alerts.items():
            conn.execute(
                "INSERT INTO run_alerts (run_id, rule_id, alerts) VALUES (?, ?, ?)",
                (run_id, rule_id, json.dumps(rule_alerts)),
            )
        conn.execute(
            "INSERT INTO run_metrics (run_id, metrics) VALUES (?, ?)",
            (run_id, json.dumps(metrics)),
        )
        conn.commit()
        conn.close()


def list_runs() -> list[dict[str, Any]]:
    if _use_postgres():
        conn = _get_pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT run_id, spec_path, seed, created_at FROM runs ORDER BY created_at DESC LIMIT 50"
                )
                return [
                    {
                        "run_id": r[0],
                        "spec_path": r[1],
                        "seed": r[2],
                        "created_at": r[3].isoformat(),
                    }
                    for r in cur.fetchall()
                ]
        finally:
            conn.close()
    else:
        conn = _get_sqlite_conn()
        rows = conn.execute(
            "SELECT run_id, spec_path, seed, created_at FROM runs ORDER BY created_at DESC LIMIT 50"
        ).fetchall()
        conn.close()
        return [{"run_id": r[0], "spec_path": r[1], "seed": r[2], "created_at": r[3]} for r in rows]


def get_run(run_id: str) -> dict[str, Any] | None:
    if _use_postgres():
        conn = _get_pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT manifest FROM runs WHERE run_id = %s", (run_id,))
                row = cur.fetchone()
                return json.loads(row[0]) if row else None
        finally:
            conn.close()
    else:
        conn = _get_sqlite_conn()
        row = conn.execute("SELECT manifest FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        conn.close()
        return json.loads(row[0]) if row else None


def get_run_alerts(run_id: str) -> list[dict[str, Any]]:
    if _use_postgres():
        conn = _get_pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT rule_id, alerts FROM run_alerts WHERE run_id = %s", (run_id,))
                return [{"rule_id": r[0], "alerts": json.loads(r[1])} for r in cur.fetchall()]
        finally:
            conn.close()
    else:
        conn = _get_sqlite_conn()
        rows = conn.execute(
            "SELECT rule_id, alerts FROM run_alerts WHERE run_id = ?", (run_id,)
        ).fetchall()
        conn.close()
        return [{"rule_id": r[0], "alerts": json.loads(r[1])} for r in rows]


def get_run_metrics(run_id: str) -> list[dict[str, Any]]:
    if _use_postgres():
        conn = _get_pg_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT metrics FROM run_metrics WHERE run_id = %s", (run_id,))
                row = cur.fetchone()
                return json.loads(row[0]) if row else []
        finally:
            conn.close()
    else:
        conn = _get_sqlite_conn()
        row = conn.execute("SELECT metrics FROM run_metrics WHERE run_id = ?", (run_id,)).fetchone()
        conn.close()
        return json.loads(row[0]) if row else []


def store_spec_version(
    spec_hash: str,
    spec_content: str,
    program_name: str,
    tenant_id: str = "default",
) -> None:
    """Store a spec version for tracking."""
    now = datetime.now(tz=timezone.utc).isoformat()
    if not _use_postgres():
        conn = _get_sqlite_conn()
        existing = conn.execute(
            "SELECT id FROM spec_versions WHERE spec_hash = ?", (spec_hash,)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO spec_versions (spec_hash, spec_content, program_name, tenant_id, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (spec_hash, spec_content, program_name, tenant_id, now),
            )
            conn.commit()
        conn.close()


def list_spec_versions(tenant_id: str | None = None) -> list[dict[str, Any]]:
    """List stored spec versions."""
    if not _use_postgres():
        conn = _get_sqlite_conn()
        query = "SELECT spec_hash, program_name, tenant_id, created_at FROM spec_versions"
        params: tuple = ()
        if tenant_id:
            query += " WHERE tenant_id = ?"
            params = (tenant_id,)
        query += " ORDER BY created_at DESC LIMIT 50"
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [
            {"spec_hash": r[0], "program_name": r[1], "tenant_id": r[2], "created_at": r[3]}
            for r in rows
        ]
    return []
