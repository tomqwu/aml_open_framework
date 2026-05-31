"""Engine correctness hardening (PR-H6 + nested PII masking).

Covers three real defects found in review:
1. freshness scan naivized aware datetimes by *wall clock* instead of by
   instant — a non-UTC timestamp produced a wrong staleness age.
2. (observability) matched_row_ids lookup failures were swallowed silently
   — exercised indirectly; the fix only adds a log line.
3. PII masking only masked top-level alert keys, so a network_pattern
   alert leaked its subject's customer_id inside the nested `subgraph`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from aml_framework.engine.audit import AuditLedger, _mask_nested, _pii_mask_value
from aml_framework.engine.freshness import _to_utc_naive, scan_contract_freshness
from aml_framework.spec.models import Column, DataContract


# --- freshness timezone correctness ---------------------------------------


def test_to_utc_naive_converts_aware_by_instant():
    # 02:00 at +08:00 is 18:00 the previous day in UTC.
    aware = datetime(2026, 1, 10, 2, 0, tzinfo=timezone(timedelta(hours=8)))
    assert _to_utc_naive(aware) == datetime(2026, 1, 9, 18, 0)


def test_to_utc_naive_leaves_naive_unchanged():
    naive = datetime(2026, 1, 10, 2, 0)
    assert _to_utc_naive(naive) == naive


def test_to_utc_naive_utc_aware_strips_to_same_walltime():
    aware = datetime(2026, 1, 10, 2, 0, tzinfo=timezone.utc)
    assert _to_utc_naive(aware) == datetime(2026, 1, 10, 2, 0)


def _freshness_contract(max_days: int) -> DataContract:
    return DataContract(
        id="customer",
        source="raw.customer",
        columns=[
            Column(
                name="risk_rating",
                type="string",
                nullable=False,
                max_staleness_days=max_days,
                last_refreshed_at_column="refreshed_at",
            ),
            Column(name="refreshed_at", type="timestamp"),
        ],
    )


def test_freshness_uses_instant_not_wallclock():
    """A row refreshed at 02:00 +08:00 (== 18:00 UTC the day before) is 10d
    6h stale at the naive-UTC as_of — a violation. The old wall-clock strip
    treated it as 02:00 naive (9d 22h) and would have MISSED the breach."""
    contract = _freshness_contract(max_days=10)
    as_of = datetime(2026, 1, 20, 0, 0)  # naive UTC
    rows = [
        {
            "customer_id": "C1",
            "risk_rating": "high",
            "refreshed_at": datetime(2026, 1, 10, 2, 0, tzinfo=timezone(timedelta(hours=8))),
        }
    ]
    violations = scan_contract_freshness(contract, rows, as_of)
    assert len(violations) == 1
    assert violations[0].age_days == 10


def test_freshness_fresh_row_no_violation():
    contract = _freshness_contract(max_days=10)
    as_of = datetime(2026, 1, 20, 0, 0)
    rows = [
        {"customer_id": "C1", "risk_rating": "high", "refreshed_at": datetime(2026, 1, 19, 0, 0)}
    ]
    assert scan_contract_freshness(contract, rows, as_of) == []


# --- nested PII masking ---------------------------------------------------


def test_mask_nested_replaces_known_plaintext_everywhere():
    m = {"C0001": "HASH1"}
    assert _mask_nested("C0001", m) == "HASH1"
    assert _mask_nested("other", m) == "other"
    assert _mask_nested({"a": "C0001", "b": "x"}, m) == {"a": "HASH1", "b": "x"}
    assert _mask_nested(["C0001", "y"], m) == ["HASH1", "y"]
    assert _mask_nested(("C0001", 2), m) == ("HASH1", 2)
    assert _mask_nested(5000, m) == 5000  # non-string untouched


def _masking_ledger(tmp_path: Path) -> AuditLedger:
    return AuditLedger(
        run_dir=tmp_path,
        spec_path=tmp_path / "spec.yaml",
        spec_content_hash="deadbeef",
        as_of=datetime(2026, 1, 1),
        pii_columns=frozenset({"customer_id", "full_name"}),
        pii_salt="salt123",
    )


def test_mask_alert_masks_subject_inside_nested_subgraph(tmp_path):
    """A network_pattern alert embeds its subject's customer_id inside
    `subgraph.nodes[].id`. The subject must be masked there too, identically
    to the top-level field — value-based masking guarantees this."""
    ledger = _masking_ledger(tmp_path)
    alert = {
        "customer_id": "C0001",
        "full_name": "Jane Roe",
        "amount": 5000,
        "pattern": "component_size",
        "subgraph": {"nodes": [{"id": "C0001", "label": "seed"}], "edges": []},
    }
    masked = ledger._mask_alert(alert)

    h_cid = _pii_mask_value("C0001", "salt123")
    assert masked["customer_id"] == h_cid
    assert masked["full_name"] == _pii_mask_value("Jane Roe", "salt123")
    # The same id, nested under a different key (`id`), is masked identically.
    assert masked["subgraph"]["nodes"][0]["id"] == h_cid
    # Non-PII fields are untouched.
    assert masked["amount"] == 5000
    assert masked["pattern"] == "component_size"
    assert masked["subgraph"]["nodes"][0]["label"] == "seed"


def test_mask_alert_noop_without_pii_columns(tmp_path):
    ledger = AuditLedger(
        run_dir=tmp_path,
        spec_path=tmp_path / "spec.yaml",
        spec_content_hash="x",
        as_of=datetime(2026, 1, 1),
    )
    alert = {"customer_id": "C0001", "subgraph": {"nodes": [{"id": "C0001"}]}}
    assert ledger._mask_alert(alert) is alert  # unchanged identity, no masking
