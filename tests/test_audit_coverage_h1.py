"""Coverage backfill for the tamper-evident ledger (PR-H1a).

`engine/audit.py` was excluded from the coverage gate (omit list) — the
single most compliance-critical module was unmeasured. PR-H1a un-omits it;
these are real assertion-bearing tests for the previously-uncovered paths
(malformed-line surfacing, freeze chmod, verify_decisions failure modes,
unmask round-trip, defensive early-returns), not coverage padding.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from aml_framework.engine.audit import (
    AuditLedger,
    _freeze_snapshot_files,
    _pii_columns_from_spec,
    _sha256,
    unmask_alerts,
    walk_lineage,
)


def _ledger(tmp_path: Path, **kw) -> AuditLedger:
    return AuditLedger(
        run_dir=tmp_path,
        spec_path=tmp_path / "spec.yaml",
        spec_content_hash="deadbeef",
        as_of=datetime(2026, 1, 1),
        **kw,
    )


# --- walk_lineage: malformed-line surfacing + case_id filter --------------


def test_walk_lineage_surfaces_malformed_and_filters_other_cases(tmp_path):
    (tmp_path / "decisions.jsonl").write_text(
        "\n"  # blank line skipped
        + json.dumps({"case_id": "OTHER", "event": "case_opened"})
        + "\n"
        + "{not valid json}\n"  # malformed -> surfaced, not silently dropped
        + json.dumps({"case_id": "C1", "event": "case_opened"})
        + "\n",
        encoding="utf-8",
    )
    chain = walk_lineage(tmp_path, "C1")
    decisions = chain["decisions"]
    assert any(d.get("malformed_line") for d in decisions), "malformed line must be surfaced"
    # Only the matching case's well-formed event is included.
    assert any(d.get("case_id") == "C1" for d in decisions)
    assert not any(d.get("case_id") == "OTHER" for d in decisions)


# --- defensive early-returns ----------------------------------------------


def test_pii_columns_from_spec_none_is_empty():
    assert _pii_columns_from_spec(None) == frozenset()


def test_mask_alert_noop_without_pii_columns(tmp_path):
    ledger = _ledger(tmp_path)  # pii_columns defaults to empty frozenset
    alert = {"customer_id": "C1"}
    assert ledger._mask_alert(alert) is alert


def test_compute_decisions_hash_empty_when_no_log(tmp_path):
    ledger = _ledger(tmp_path)
    assert ledger._compute_decisions_hash() == hashlib.sha256(b"").hexdigest()


# --- verify_decisions failure modes ---------------------------------------


def test_verify_decisions_manifest_missing(tmp_path):
    ok, msg = AuditLedger.verify_decisions(tmp_path)
    assert ok is False
    assert "manifest.json not found" in msg


def test_verify_decisions_no_hash_in_manifest(tmp_path):
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    ok, msg = AuditLedger.verify_decisions(tmp_path)
    assert ok is False
    assert "No decisions_hash" in msg


def test_verify_decisions_expected_hash_roundtrip(tmp_path):
    (tmp_path / "decisions.jsonl").write_text('{"a":1}\n{"b":2}\n', encoding="utf-8")
    chain = b""
    for line in (tmp_path / "decisions.jsonl").read_bytes().splitlines():
        if line.strip():
            chain = hashlib.sha256(chain + line).digest()
    ok, msg = AuditLedger.verify_decisions(tmp_path, expected_hash=chain.hex())
    assert ok is True
    bad, _ = AuditLedger.verify_decisions(tmp_path, expected_hash="00" * 32)
    assert bad is False


def test_verify_decisions_empty_log_against_expected(tmp_path):
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    ok, _ = AuditLedger.verify_decisions(tmp_path, expected_hash=_sha256(b""))
    assert ok is True  # no decisions.jsonl -> empty-hash matches


# --- unmask_alerts --------------------------------------------------------


def test_unmask_alerts_roundtrip_and_blank_lines(tmp_path):
    h = "0123456789abcdef"  # 16 hex chars == a mask token by construction
    (tmp_path / "pii_map.jsonl").write_text(
        "\n" + json.dumps({"field": "customer_id", "hash": h, "plaintext": "C0001"}) + "\n",
        encoding="utf-8",
    )
    alerts_dir = tmp_path / "alerts"
    alerts_dir.mkdir()
    (alerts_dir / "rule_a.jsonl").write_text(
        "\n" + json.dumps({"customer_id": h, "amount": 5000}) + "\n", encoding="utf-8"
    )
    out = unmask_alerts(tmp_path)
    assert out["rule_a"][0]["customer_id"] == "C0001"
    assert out["rule_a"][0]["amount"] == 5000


def test_unmask_alerts_no_alerts_dir_returns_empty(tmp_path):
    assert unmask_alerts(tmp_path) == {}


# --- _freeze_snapshot_files -----------------------------------------------


@pytest.mark.skipif(
    os.name == "nt",
    reason="POSIX chmod read-only bits; on Windows _freeze_snapshot_files no-ops (ACLs)",
)
def test_freeze_snapshot_files_chmods_file_and_dir_children(tmp_path):
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    alerts = tmp_path / "alerts"
    alerts.mkdir()
    (alerts / "rule_a.jsonl").write_text("{}", encoding="utf-8")

    _freeze_snapshot_files(tmp_path)  # must not raise

    # The single-file target and the dir-child are now read-only (0o444).
    assert (os.stat(tmp_path / "manifest.json").st_mode & 0o222) == 0
    assert (os.stat(alerts / "rule_a.jsonl").st_mode & 0o222) == 0


def test_freeze_snapshot_files_noop_on_windows(tmp_path, monkeypatch):
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(os, "name", "nt")
    _freeze_snapshot_files(tmp_path)
    # Windows branch returns early; file stays writable.
    assert os.stat(tmp_path / "manifest.json").st_mode & 0o222


def test_freeze_snapshot_files_tolerates_chmod_oserror(tmp_path, monkeypatch):
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    alerts = tmp_path / "alerts"
    alerts.mkdir()
    (alerts / "rule_a.jsonl").write_text("{}", encoding="utf-8")

    def _boom(*_a, **_k):
        raise OSError("read-only fs")

    monkeypatch.setattr(os, "chmod", _boom)
    _freeze_snapshot_files(tmp_path)  # both except OSError branches, no raise
