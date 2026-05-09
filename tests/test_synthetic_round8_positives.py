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
from decimal import Decimal

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
# UK APP-fraud planted positives
# ---------------------------------------------------------------------------


def test_c0016_carries_first_use_payee_large_amount() -> None:
    data = _data()
    outs = [
        t
        for t in data["txn"]
        if t["customer_id"] == "C0016" and t["direction"] == "out" and t["payee_first_use"]
    ]
    assert len(outs) >= 1, "expected ≥1 first-use-payee outbound for C0016"
    assert any(t["amount"] >= 1000 for t in outs), (
        "C0016's payment must clear the first_use_payee_large_amount £1,000 threshold"
    )


def test_c0017_carries_atypical_payment_for_vulnerable_customer() -> None:
    data = _data()
    cust = next(c for c in data["customer"] if c["customer_id"] == "C0017")
    assert cust["vulnerable_customer_flag"] is True
    assert cust["typical_payment_size_p95"] is not None
    p95 = cust["typical_payment_size_p95"]
    # At least one outbound must clear the rule's `5 * p95 AND >= 500` floor.
    # Other outbounds may exist as noise — we only need one match.
    qualifying = [
        t
        for t in data["txn"]
        if t["customer_id"] == "C0017"
        and t["direction"] == "out"
        and t["amount"] >= 5 * p95
        and t["amount"] >= 500
    ]
    assert len(qualifying) >= 1, f"expected ≥1 outbound clearing 5×p95 (£{5 * p95}) for C0017"


def test_c0018_carries_cop_mismatch_pair() -> None:
    data = _data()
    mismatches = [
        t
        for t in data["txn"]
        if t["customer_id"] == "C0018"
        and t["direction"] == "out"
        and t["confirmation_of_payee_status"] in ("no_match", "close_match")
    ]
    assert len(mismatches) >= 1, "expected ≥1 outbound CoP-mismatch payment for C0018"
    assert all(t["amount"] >= 100 for t in mismatches), (
        "all C0018 mismatch payments must clear the rule's £100 floor"
    )


def test_c0019_carries_rapid_pass_through() -> None:
    data = _data()
    ins = [
        t
        for t in data["txn"]
        if t["customer_id"] == "C0019" and t["direction"] == "in" and t["amount"] >= 500
    ]
    outs = [
        t
        for t in data["txn"]
        if t["customer_id"] == "C0019" and t["direction"] == "out" and t["amount"] >= 500
    ]
    # Look for at least one (inbound, outbound) pair matching the rule:
    # outbound within 1h after inbound, ≥80% pass-through.
    matches = [
        (i, o)
        for i in ins
        for o in outs
        if o["booked_at"] > i["booked_at"]
        and (o["booked_at"] - i["booked_at"]) <= timedelta(hours=1)
        and o["amount"] >= Decimal("0.8") * i["amount"]
    ]
    assert len(matches) >= 1, (
        "expected ≥1 inbound→outbound pair on C0019 matching rapid_pass_through_mule"
    )


# ---------------------------------------------------------------------------
# Cross-spec contamination guard (UK APP fraud)
# ---------------------------------------------------------------------------
# The C0016-C0019 plants live alongside random noise-loop activity. Without
# a guard, that noise pushes the customers' 4-week baselines high enough
# for non-UK specs' `unusual_volume_spike` (no channel/currency filter) to
# fire false positives at certain seeds — observed at seed=7 where C0019
# tripped uk_bank's rule. This pins the guard so a future change can't
# silently re-introduce the leak.


_UK_APP_FRAUD_IDS = ("C0016", "C0017", "C0018", "C0019")


def test_uk_app_fraud_customers_have_only_planted_txns() -> None:
    """No random-noise rows should remain for C0016-C0019 — only the
    planted shape (GBP, faster_payments) survives the guard."""
    data = _data()
    for cid in _UK_APP_FRAUD_IDS:
        rows = [t for t in data["txn"] if t["customer_id"] == cid]
        assert rows, f"{cid} should still have its planted rows"
        for r in rows:
            assert r["currency"] == "GBP", f"{cid} carries non-GBP txn — noise-loop leak: {r}"
            assert r["channel"] == "faster_payments", (
                f"{cid} carries non-faster_payments txn — noise-loop leak: {r}"
            )


def test_uk_app_fraud_customers_have_no_baseline_window_activity() -> None:
    """Plants sit within the recent window (≤5 days before as_of). Any
    row ≥7 days old (the standard `unusual_volume_spike` baseline-start
    cutoff) for these customer ids would mean noise leaked into the
    baseline window — exactly what flips the spike-ratio comparison."""
    data = _data()
    cutoff = AS_OF - timedelta(days=7)
    for cid in _UK_APP_FRAUD_IDS:
        old = [t for t in data["txn"] if t["customer_id"] == cid and t["booked_at"] < cutoff]
        assert old == [], f"{cid} has rows in the baseline window (noise leak): {old[:3]}"


# ---------------------------------------------------------------------------
# Trade-based ML planted positives (trade_based_ml spec)
# ---------------------------------------------------------------------------


def test_c0020_carries_over_invoicing_pair() -> None:
    data = _data()
    over = [
        t
        for t in data["txn"]
        if t["customer_id"] == "C0020"
        and t.get("purpose_code") == "TRAD"
        and t.get("hs_code") == "8471.30"
        and t.get("declared_unit_price") is not None
    ]
    assert len(over) >= 2, "expected ≥2 planted TRAD txns for C0020"
    # Total amount must clear the rule's `HAVING SUM >= 25000` threshold.
    assert sum(t["amount"] for t in over) >= 25000


def test_c0020_unit_price_at_least_3x_baseline_median() -> None:
    """The planted unit price must trip `declared_unit_price >= 3 * median`
    against the hs_code_baseline row this PR ships."""
    data = _data()
    baseline = next(b for b in data["hs_code_baseline"] if b["hs_code"] == "8471.30")
    over = [t for t in data["txn"] if t["customer_id"] == "C0020" and t.get("hs_code") == "8471.30"]
    for t in over:
        assert t["declared_unit_price"] >= 3 * baseline["median_unit_price"]


def test_c0021_carries_phantom_shipping_burst() -> None:
    data = _data()
    phantom = [
        t
        for t in data["txn"]
        if t["customer_id"] == "C0021"
        and t.get("purpose_code") == "TRAD"
        and t.get("invoice_id") is None
        and t["direction"] == "out"
    ]
    assert len(phantom) >= 3, "expected ≥3 phantom-shipping TRAD txns for C0021"
    assert sum(t["amount"] for t in phantom) >= 50000


def test_c0022_has_duplicate_invoice_id() -> None:
    data = _data()
    dup = [
        t
        for t in data["txn"]
        if t["customer_id"] == "C0022"
        and t.get("purpose_code") == "TRAD"
        and t.get("invoice_id") == "INV-DUP-2026-04-001"
        and t["direction"] == "out"
    ]
    assert len(dup) == 2, f"C0022 must pay the same invoice twice; got {len(dup)}"


def test_hs_code_baseline_present_and_complete() -> None:
    data = _data()
    baseline = data["hs_code_baseline"]
    assert len(baseline) >= 5, "expected ≥5 hs_code_baseline reference rows"
    for row in baseline:
        # Monotonic distribution: p5 < median < p95.
        assert row["p5_unit_price"] < row["median_unit_price"]
        assert row["median_unit_price"] < row["p95_unit_price"]
    # Rule 1 (over_invoicing) joins on the planted hs_code, so it must be present.
    assert any(b["hs_code"] == "8471.30" for b in baseline)


# ---------------------------------------------------------------------------
# Determinism — same seed must reproduce exactly
# ---------------------------------------------------------------------------


def test_planted_positives_are_deterministic() -> None:
    a = generate_dataset(as_of=AS_OF, seed=42)
    b = generate_dataset(as_of=AS_OF, seed=42)
    for cid in (
        "C0012",
        "C0016",
        "C0017",
        "C0018",
        "C0019",
        "C0020",
        "C0021",
        "C0022",
    ):
        a_txns = sorted((t["amount"], t["booked_at"]) for t in a["txn"] if t["customer_id"] == cid)
        b_txns = sorted((t["amount"], t["booked_at"]) for t in b["txn"] if t["customer_id"] == cid)
        assert a_txns == b_txns, f"determinism break on {cid}"
