"""Tests for round-8 planted positives — RTP/FedNow + BOI workflow.

Process invariant guarded: tuning + backtest scores against the new
specs are credible because the synthetic dataset carries ground-truth
positives that match the typology shapes those specs detect. If a
contributor edits the synthetic generator and breaks one of these
markers, the new specs' scores will silently regress to 0/0 — these
tests fail loudly first.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from aml_framework.data import generate_dataset


AS_OF = datetime(2026, 4, 28)


def _data():
    return generate_dataset(as_of=AS_OF, seed=42)


# ---------------------------------------------------------------------------
# RTP / FedNow planted positives
# ---------------------------------------------------------------------------


def test_c0012_carries_planted_rtp_send() -> None:
    data = _data()
    rtp_outs = [
        t
        for t in data["txn"]
        if t["customer_id"] == "C0012" and t["channel"] == "rtp" and t["direction"] == "out"
    ]
    assert len(rtp_outs) >= 1, "expected ≥ 1 RTP outbound for C0012"
    assert any(t["amount"] >= 1000 for t in rtp_outs), (
        "C0012's RTP send must clear the first_use_payee_large_amount threshold"
    )


def test_c0012_send_falls_outside_typical_window() -> None:
    data = _data()
    cust = next(c for c in data["customer"] if c["customer_id"] == "C0012")
    rtp_send = next(
        t
        for t in data["txn"]
        if t["customer_id"] == "C0012" and t["channel"] == "rtp" and t["direction"] == "out"
    )
    hour = rtp_send["booked_at"].hour
    assert (
        hour < cust["typical_send_window_start_hour"] or hour > cust["typical_send_window_end_hour"]
    ), "send must be outside typical window so unusual_send_hour rule fires"


def test_c0013_has_velocity_burst_on_receive() -> None:
    data = _data()
    rtp_ins = [
        t
        for t in data["txn"]
        if t["customer_id"] == "C0013" and t["channel"] == "rtp" and t["direction"] == "in"
    ]
    assert len(rtp_ins) >= 5, "expected ≥ 5 inbound RTP credits for C0013"
    # All inside one hour window?
    timestamps = sorted(t["booked_at"] for t in rtp_ins)
    span = timestamps[-1] - timestamps[0]
    assert span <= timedelta(hours=1), "burst must fit inside the rule's 1h window — got " + str(
        span
    )


# ---------------------------------------------------------------------------
# BOI planted positives
# ---------------------------------------------------------------------------


def test_c0014_marked_as_reporting_company_with_no_review() -> None:
    """When the BOI module ships separately, this record is what makes
    that page's `missing` count non-zero. Verifying the data shape here
    keeps the two PRs decoupled but mutually consistent."""
    data = _data()
    cust = next(c for c in data["customer"] if c["customer_id"] == "C0014")
    assert cust["business_activity"], "C0014 must be an entity (reporting company)"
    assert cust["edd_last_review"] is None, "C0014 must have no review on file"


def test_c0015_marked_as_entity_with_stale_review() -> None:
    data = _data()
    cust = next(c for c in data["customer"] if c["customer_id"] == "C0015")
    assert cust["business_activity"], "C0015 must be an entity"
    assert cust["edd_last_review"] is not None
    age_days = (AS_OF - cust["edd_last_review"]).days
    assert age_days > 365, f"C0015's review must be stale (>365 days); got {age_days} days"


def test_synthetic_data_has_at_least_two_entity_customers() -> None:
    """Once these planted positives exist, the BOI page never opens
    on an empty state — the demo always has reporting companies to show."""
    data = _data()
    entities = [c for c in data["customer"] if c["business_activity"]]
    assert len(entities) >= 2


# ---------------------------------------------------------------------------
# Determinism — same seed must reproduce exactly
# ---------------------------------------------------------------------------


def test_planted_positives_are_deterministic() -> None:
    a = generate_dataset(as_of=AS_OF, seed=42)
    b = generate_dataset(as_of=AS_OF, seed=42)
    a_c0012 = sorted((t["amount"], t["booked_at"]) for t in a["txn"] if t["customer_id"] == "C0012")
    b_c0012 = sorted((t["amount"], t["booked_at"]) for t in b["txn"] if t["customer_id"] == "C0012")
    assert a_c0012 == b_c0012
