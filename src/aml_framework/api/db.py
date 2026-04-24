"""PostgreSQL storage for run results — thin wrapper, no ORM."""

from __future__ import annotations

import json
import os
from typing import Any

_DATABASE_URL = os.environ.get("DATABASE_URL", "")


def _get_conn():
    import psycopg2

    return psycopg2.connect(_DATABASE_URL)


def init_db() -> None:
    """Create tables if they don't exist. Called on API startup."""
    if not _DATABASE_URL:
        return
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
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
            """)
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
) -> None:
    if not _DATABASE_URL:
        return
    conn = _get_conn()
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


def list_runs() -> list[dict[str, Any]]:
    if not _DATABASE_URL:
        return []
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT run_id, spec_path, seed, created_at FROM runs ORDER BY created_at DESC LIMIT 50"
            )
            return [
                {"run_id": r[0], "spec_path": r[1], "seed": r[2], "created_at": r[3].isoformat()}
                for r in cur.fetchall()
            ]
    finally:
        conn.close()


def get_run(run_id: str) -> dict[str, Any] | None:
    if not _DATABASE_URL:
        return None
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT manifest FROM runs WHERE run_id = %s", (run_id,))
            row = cur.fetchone()
            return json.loads(row[0]) if row else None
    finally:
        conn.close()


def get_run_alerts(run_id: str) -> list[dict[str, Any]]:
    if not _DATABASE_URL:
        return []
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT rule_id, alerts FROM run_alerts WHERE run_id = %s", (run_id,))
            return [{"rule_id": r[0], "alerts": json.loads(r[1])} for r in cur.fetchall()]
    finally:
        conn.close()


def get_run_metrics(run_id: str) -> list[dict[str, Any]]:
    if not _DATABASE_URL:
        return []
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT metrics FROM run_metrics WHERE run_id = %s", (run_id,))
            row = cur.fetchone()
            return json.loads(row[0]) if row else []
    finally:
        conn.close()
