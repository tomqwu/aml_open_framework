"""Coverage backfill for the regulator evidence bundle (PR-H1b).

`generators/audit_pack.py` builds the regulator-ready ZIP (the run's
exported evidence) and was excluded from the coverage gate. PR-H1b un-omits
it; these are real assertion-bearing tests for the previously-uncovered
helper paths (hash-chain break detection, PII-map loading/masking,
serialisation fallback, malformed-case skips).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from aml_framework.generators.audit_pack import (
    _alerts_for_case,
    _audit_trail_verification,
    _case_lineage_summary,
    _json_default,
    _load_pii_map,
    _PiiMap,
)


# --- _json_default --------------------------------------------------------


def test_json_default_serialises_datetime_and_path():
    assert _json_default(datetime(2026, 1, 2, 3, 4, 5)) == "2026-01-02T03:04:05"
    assert _json_default(Path("/tmp/x")) == "/tmp/x"


def test_json_default_raises_on_unserialisable():
    with pytest.raises(TypeError, match="unserialisable type"):
        _json_default(object())


# --- _audit_trail_verification (hash-chain integrity) ---------------------


def test_audit_trail_intact_chain():
    decisions = [
        {"hash": "a", "prev_hash": ""},
        {"hash": "b", "prev_hash": "a"},
    ]
    result = _audit_trail_verification(decisions)
    assert result["chain_intact"] is True
    assert result["breaks_at_indices"] == []


def test_audit_trail_detects_broken_chain():
    decisions = [
        {"hash": "a", "prev_hash": "GENESIS_TAMPERED"},  # first prev must be ""/zeros
        {"hash": "b", "prev_hash": "WRONG"},  # should be "a"
    ]
    result = _audit_trail_verification(decisions)
    assert result["chain_intact"] is False
    assert result["breaks_at_indices"] == [0, 1]


# --- _case_lineage_summary ------------------------------------------------


def test_case_lineage_summary_skips_caseless_entries():
    cases = [{"case_id": ""}, {"case_id": "C1", "rule_id": "r1", "alert": {}}]
    summary = _case_lineage_summary(cases)
    assert summary["case_count"] == 1
    assert "C1" in summary["by_case_id"]
    assert "" not in summary["by_case_id"]


# --- _PiiMap.mask_field ---------------------------------------------------


def test_pii_map_lookup_guards():
    pm = _PiiMap({"customer_id": {"C0001": "deadbeefdeadbeef"}})
    assert pm.lookup("customer_id", "C0001") == "deadbeefdeadbeef"
    assert pm.lookup(None, "C0001") is None  # no field context
    assert pm.lookup("not_a_pii_field", "C0001") is None  # unknown field


# --- _load_pii_map --------------------------------------------------------


def test_load_pii_map_skips_blank_lines(tmp_path):
    (tmp_path / "pii_map.jsonl").write_text(
        "\n"  # blank line tolerated
        + json.dumps({"field": "customer_id", "plaintext": "C1", "hash": "h1"})
        + "\n",
        encoding="utf-8",
    )
    pm = _load_pii_map(tmp_path)
    assert pm.lookup("customer_id", "C1") == "h1"


def test_load_pii_map_absent_sidecar_is_empty(tmp_path):
    pm = _load_pii_map(tmp_path)
    assert not pm  # __bool__ is False when empty


# --- _alerts_for_case -----------------------------------------------------


def test_alerts_for_case_empty_when_no_alert():
    assert _alerts_for_case({"case_id": "C1"}, {}) == []


def test_audit_trail_verification_empty_is_intact():
    # An empty decision log is a (trivially) intact chain. Asserts the result
    # shape without depending on a wall-clock field — the bundle is
    # byte-deterministic and carries no `verified_at` (see the determinism fix).
    result = _audit_trail_verification([])
    assert result["chain_intact"] is True
    assert result["chain_length"] == 0
