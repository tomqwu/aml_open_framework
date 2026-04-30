"""Behaviour tests for PR-K's ai_interactions.jsonl audit log.

Pins:
  - Every reply via the panel logs ONE row to ai_interactions.jsonl
  - The row carries the documented schema (ts, page, persona, backend,
    citations, confidence, question, and either reply_text or
    reply_text_hash depending on the spec's ai_audit_log mode)
  - `AuditLedger.append_to_run_dir` accepts a `jsonl_name` kwarg so
    the helper is reusable for any append-only log
"""

from __future__ import annotations

import json
from pathlib import Path

from aml_framework.assistant import AssistantContext, TemplateBackend
from aml_framework.assistant.models import reply_to_audit_dict
from aml_framework.engine.audit import AuditLedger


def _append_one(run_dir: Path, *, full_text: bool, question: str) -> dict:
    """Replicate the panel's audit-log path without involving Streamlit."""
    backend = TemplateBackend()
    ctx = AssistantContext(page="Executive Dashboard", persona="cco")
    reply = backend.reply(question, ctx)
    row = reply_to_audit_dict(reply, full_text=full_text)
    row["question"] = question
    AuditLedger.append_to_run_dir(
        run_dir,
        {"event": "ai_interaction", **row},
        jsonl_name="ai_interactions.jsonl",
    )
    return row


def test_append_writes_to_ai_interactions_jsonl(tmp_path: Path):
    log_path = tmp_path / "ai_interactions.jsonl"
    assert not log_path.exists()

    _append_one(tmp_path, full_text=False, question="why is volume high?")

    assert log_path.exists(), "ai_interactions.jsonl must be created on first interaction"
    rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1


def test_jsonl_name_kwarg_does_not_affect_decisions_log(tmp_path: Path):
    """Sanity: the existing decisions.jsonl path is unchanged by PR-K."""
    AuditLedger.append_to_run_dir(tmp_path, {"event": "ack", "case_id": "C-1"})
    AuditLedger.append_to_run_dir(
        tmp_path, {"event": "ai_interaction", "page": "Test"}, jsonl_name="ai_interactions.jsonl"
    )
    assert (tmp_path / "decisions.jsonl").exists()
    assert (tmp_path / "ai_interactions.jsonl").exists()
    # Each file gets exactly one line.
    for name in ("decisions.jsonl", "ai_interactions.jsonl"):
        lines = (tmp_path / name).read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1


def test_hash_only_mode_writes_hash_not_full_text(tmp_path: Path):
    _append_one(tmp_path, full_text=False, question="redact me")
    rows = [
        json.loads(line)
        for line in (tmp_path / "ai_interactions.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    row = rows[0]
    assert "reply_text" not in row, "hash_only must NEVER write full reply text to disk"
    assert "reply_text_hash" in row
    assert len(row["reply_text_hash"]) == 64  # sha-256 hex


def test_full_text_mode_writes_complete_reply(tmp_path: Path):
    _append_one(tmp_path, full_text=True, question="forensic recall please")
    rows = [
        json.loads(line)
        for line in (tmp_path / "ai_interactions.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    row = rows[0]
    assert "reply_text" in row
    assert "reply_text_hash" not in row, (
        "full_text mode is exclusive; logging both would let an audit pipeline "
        "double-count or pick the wrong field"
    )
    assert isinstance(row["reply_text"], str) and row["reply_text"]


def test_logged_row_carries_documented_schema(tmp_path: Path):
    _append_one(tmp_path, full_text=False, question="schema test")
    rows = [
        json.loads(line)
        for line in (tmp_path / "ai_interactions.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    row = rows[0]
    expected_keys = {
        "ts",
        "event",
        "page",
        "persona",
        "backend",
        "confidence",
        "citations",
        "referenced_metric_ids",
        "referenced_case_ids",
        "referenced_customer_ids",
        "question",
        "reply_text_hash",
    }
    assert expected_keys.issubset(row.keys()), f"row missing keys: {expected_keys - row.keys()}"
    assert row["event"] == "ai_interaction"
    assert row["page"] == "Executive Dashboard"
    assert row["persona"] == "cco"
    assert row["backend"] == "template:v1"
