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

import pytest

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


def test_c0012_send_carries_counterparty_id() -> None:
    """Three us_rtp_fednow rules touch counterparty_id:
    - `unusual_send_hour_for_customer_rtp` SELECTs it (errors as a
      DuckDB BinderException if missing).
    - `first_use_payee_large_amount_rtp` and `ramp_up_then_drain_rtp`
      GROUP BY (customer_id, counterparty_id) — without a real value
      every txn collapses into a single (customer, NULL) group,
      hiding multi-counterparty fan-out structure.
    Pinning the planted send carries a non-null id keeps both
    semantics intact."""
    data = _data()
    rtp_send = next(
        t
        for t in data["txn"]
        if t["customer_id"] == "C0012" and t["channel"] == "rtp" and t["direction"] == "out"
    )
    assert rtp_send.get("counterparty_id"), (
        f"C0012's RTP send must carry a counterparty_id; got {rtp_send.get('counterparty_id')!r}"
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
# Window-pinning regression tests — `aggregation_window` rules use a sliding
# `[as_of - window, as_of)` window (see `parse_window` in
# src/aml_framework/generators/sql.py). Earlier plant timestamps were just
# outside their rules' windows, silently dropping coverage for two of the
# three intended within-spec rules. These tests pin the timing so a future
# refactor can't re-introduce the gap.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "as_of",
    [
        datetime(2026, 4, 28, 0, 0, 0),  # midnight (test fixture default)
        datetime(2026, 4, 28, 1, 0, 0),  # exact hour=1 (boundary case for the anchor)
        datetime(2026, 4, 28, 12, 30, 0),  # midday — would have failed pre-fix
        datetime(2026, 4, 28, 23, 59, 0),  # late-day — would have failed pre-fix
    ],
)
def test_c0012_send_anchored_outside_typical_window_for_any_as_of(as_of):
    """C0012's plant must satisfy both rules' constraints regardless of
    `as_of` hour: hour outside [9-17] AND inside `[as_of - 24h, as_of)`.
    The earlier `as_of - 23h` formulation only worked for midnight
    as_of values; for `as_of=15:00` it produced hour=16 (inside the
    typical window) and `unusual_send_hour_for_customer_rtp` silently
    didn't fire."""
    data = generate_dataset(as_of=as_of, seed=42)
    rtp_send = next(
        t
        for t in data["txn"]
        if t["customer_id"] == "C0012" and t["channel"] == "rtp" and t["direction"] == "out"
    )
    age = as_of - rtp_send["booked_at"]
    assert age > timedelta(0), f"plant must be before as_of; got {age}"
    assert age <= timedelta(days=1), f"plant must be inside the 1d window; got {age}"
    hour = rtp_send["booked_at"].hour
    cust = next(c for c in data["customer"] if c["customer_id"] == "C0012")
    start = cust["typical_send_window_start_hour"]
    end = cust["typical_send_window_end_hour"]
    assert hour < start or hour > end, (
        f"plant hour={hour} must be outside [{start},{end}] typical_send_window"
    )


def test_c0012_send_falls_within_first_use_rule_window() -> None:
    """`first_use_payee_large_amount_rtp` has window `1d` → 24h sliding.
    The plant's booked_at must be in the rule's `[as_of - 24h, as_of)`
    window. Mapped to `age = as_of - booked_at`:
      - The rule's open upper bound (`booked_at < as_of`) translates
        to `age > 0`.
      - The rule's closed lower bound (`booked_at >= as_of - 24h`)
        translates to `age <= 24h`. The strict `age < 24h` here is
        intentional plant-safety margin so a tiny clock skew in
        the test fixture can't push the plant onto/past the
        boundary."""
    data = _data()
    rtp_send = next(
        t
        for t in data["txn"]
        if t["customer_id"] == "C0012" and t["channel"] == "rtp" and t["direction"] == "out"
    )
    age = AS_OF - rtp_send["booked_at"]
    assert age > timedelta(0), f"C0012 RTP send must be before as_of; got {age}"
    assert age < timedelta(days=1), (
        f"C0012 RTP send must be inside the 1d rule window; got {age} before as_of"
    )


def test_c0013_burst_credits_all_within_velocity_rule_window() -> None:
    """`velocity_spike_on_receive_rtp` has window `1h` → 60min sliding,
    threshold `count >= 5`. ALL planted credits must sit in the rule's
    `[as_of - 1h, as_of)` window — if even one falls outside, count
    drops to 5 (still passes) but a one-credit drift further would
    push it to 4 and the rule would silently stop firing. Pinning the
    whole burst (not just `most_recent`) is the regression-safe shape."""
    data = _data()
    rtp_ins = [
        t
        for t in data["txn"]
        if t["customer_id"] == "C0013" and t["channel"] == "rtp" and t["direction"] == "in"
    ]
    assert len(rtp_ins) >= 5, "expected ≥ 5 inbound RTP credits for C0013"
    for t in rtp_ins:
        age = AS_OF - t["booked_at"]
        assert age > timedelta(0), f"C0013 burst credit must be before as_of; got {age}"
        assert age < timedelta(hours=1), (
            f"C0013 burst credit must be inside the 1h rule window; got {age} before as_of"
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
# Cross-spec contamination guard (RTP/BOI plants — symmetric guard)
# ---------------------------------------------------------------------------
# C0012 fires uk_bank's `unusual_volume_spike` at seed=42 because the
# planted $7,500 RTP send sits in the recent window while the noise loop
# fills the 4-week baseline. The C0012-C0015 plants get the same
# noise-stripping guard as the UK APP fraud and trade-based-ML plants.


# C0023 (ramp_up_then_drain plant) is intentionally excluded from
# `_RTP_BOI_IDS` even though its noise is stripped: its plant txns
# legitimately span 14 days (the rule's window), so a "no baseline
# window activity" assertion would false-fail. C0023's recent-sum
# stays below `unusual_volume_spike`'s $5k floor anyway, so the
# cross-spec leak guard isn't compromised — verified e2e.
_RTP_BOI_IDS = ("C0012", "C0013", "C0014", "C0015")


def test_c0023_carries_ramp_up_pattern() -> None:
    """`ramp_up_then_drain_rtp` filters direction=out, channel in [rtp,fednow],
    amount < 500; groups by (customer_id, counterparty_id); window 14d;
    having count >= 3 AND sum_amount >= 1000. C0023 plants 4 small RTP
    sends to one counterparty totaling >= $1000 inside the 14d window."""
    data = _data()
    sends = [
        t
        for t in data["txn"]
        if t["customer_id"] == "C0023"
        and t["channel"] == "rtp"
        and t["direction"] == "out"
        and t["amount"] < 500
    ]
    # Exact pin: 4 plants, $1,550 total, single counterparty
    # `CP-RAMP-2026-001` — anything else is a regression in the plant
    # block, not a tuning change to the rule's thresholds.
    assert len(sends) == 4, f"expected exactly 4 small RTP sends for C0023; got {len(sends)}"
    assert sum(t["amount"] for t in sends) == Decimal("1550.00"), (
        f"C0023 small-send total must equal $1,550; got {sum(t['amount'] for t in sends)}"
    )
    counterparties = {t["counterparty_id"] for t in sends}
    assert counterparties == {"CP-RAMP-2026-001"}, (
        f"C0023 ramp-up sends must share `CP-RAMP-2026-001`; got {counterparties}"
    )
    # All inside the 14d window.
    cutoff = AS_OF - timedelta(days=14)
    for t in sends:
        assert t["booked_at"] > cutoff, (
            f"C0023 send must be inside 14d window; got {t['booked_at']}"
        )


def test_rtp_boi_customers_have_no_baseline_window_activity() -> None:
    """No row ≥7 days old (the unusual_volume_spike baseline-start cutoff)
    for these customer ids — guard ensures non-RTP specs see only the
    planted shape, which is rule-inert for them."""
    data = _data()
    cutoff = AS_OF - timedelta(days=7)
    for cid in _RTP_BOI_IDS:
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


def test_c0024_to_c0027_share_one_device_id_for_network_clustering() -> None:
    """`mule_receiver_fan_out_rtp` is a `network_pattern` rule that
    fires on customers clustered by entity-resolution's shared linking
    attributes. Plant 4 mules all sharing one `device_id` so
    `entity_resolution.resolve_entities` builds a 4-node connected
    component → `component_size >= 4` threshold trips.
    """
    data = _data()
    mules = [
        c for c in data["customer"] if c["customer_id"] in ("C0024", "C0025", "C0026", "C0027")
    ]
    assert len(mules) == 4, f"expected 4 planted mules; got {len(mules)}"
    device_ids = {c["device_id"] for c in mules}
    assert device_ids == {"DEV-MULE-2026-001"}, (
        f"all 4 mules must share `DEV-MULE-2026-001`; got {device_ids}"
    )


def test_c0024_to_c0027_have_inbound_rtp_evidence_rows() -> None:
    """Each mule needs at least one inbound RTP credit so the case
    investigation panel has evidence to display. Pinned at exactly 1
    per mule (not enough to trip velocity_spike's `count >= 5` —
    only the network_pattern rule fires, which is the intended
    detection signal)."""
    data = _data()
    for cid in ("C0024", "C0025", "C0026", "C0027"):
        rtp_ins = [
            t
            for t in data["txn"]
            if t["customer_id"] == cid and t["channel"] == "rtp" and t["direction"] == "in"
        ]
        assert len(rtp_ins) == 1, (
            f"{cid} must have exactly 1 inbound RTP credit; got {len(rtp_ins)}"
        )


def test_mule_cluster_gated_on_n_customers_28_or_more() -> None:
    """Partial cluster = no detection. Below 4 ids, `component_size >=
    4` can't fire; pin that the plant short-circuits cleanly rather
    than emitting a half-formed cluster (e.g., 1 customer with
    device_id but no peers to cluster with)."""
    data = generate_dataset(as_of=AS_OF, seed=42, n_customers=27)
    # The auto-generated customer loop populates customer_ids
    # `C0001..C{n-1}` regardless of plants, so the customer rows for
    # those ids may still exist as random Faker rows. The marker is
    # the `device_id` field — only the plant block sets it. Pin that
    # no customer carries the mule device id when the gate is closed.
    with_device = [c for c in data["customer"] if c.get("device_id") == "DEV-MULE-2026-001"]
    assert with_device == [], (
        f"expected zero mule device-id plants under n_customers<28; got {[c['customer_id'] for c in with_device]}"
    )


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


# ---------------------------------------------------------------------------
# New-rail planted positives (rtp / crypto / prepaid) — C0028, C0029
# ---------------------------------------------------------------------------
# These plants are appended AFTER the C0022 block and use only hardcoded
# amounts + day/hour/minute offsets (zero random.*), so the seeded RNG
# sequence — and therefore every pre-existing planted/noise row — is
# untouched. The anchor test below pins an EXISTING shape to prove the
# dataset did not re-base.


def test_new_rails_appear_in_channels() -> None:
    """rtp / crypto / prepaid must be present in the txn channel set —
    the plants plus the RNG-free background-volume block emit them."""
    data = _data()
    channels = {t["channel"] for t in data["txn"]}
    for rail in ("rtp", "crypto", "prepaid"):
        assert rail in channels, f"{rail} missing from generated txn channels"


def test_c0028_carries_crypto_passthrough_pair() -> None:
    """Cash-in $42,000 then crypto-out $40,000 within 48h (both legs
    ≥ $30k) → crypto_vasp_rapid_passthrough shape."""
    data = _data()
    cash_in = [
        t
        for t in data["txn"]
        if t["customer_id"] == "C0028" and t["channel"] == "cash" and t["direction"] == "in"
    ]
    crypto_out = [
        t
        for t in data["txn"]
        if t["customer_id"] == "C0028" and t["channel"] == "crypto" and t["direction"] == "out"
    ]
    assert any(t["amount"] == Decimal("42000.00") for t in cash_in), (
        "C0028 must carry the planted $42,000 cash-in"
    )
    assert len(crypto_out) == 1 and crypto_out[0]["amount"] == Decimal("40000.00"), (
        f"C0028 must carry exactly one $40,000 crypto-out; got {crypto_out}"
    )
    ci = next(t for t in cash_in if t["amount"] == Decimal("42000.00"))
    gap = crypto_out[0]["booked_at"] - ci["booked_at"]
    assert timedelta(0) < gap <= timedelta(hours=48), (
        f"crypto-out must follow cash-in within 48h; got {gap}"
    )


def test_c0028_carries_prepaid_structuring_loads() -> None:
    """6 prepaid loads of $2,900 each, all < $3,000, count ≥ 5 and
    sum ≥ $14,000 inside 30 days → prepaid_load_structuring shape."""
    data = _data()
    loads = [
        t
        for t in data["txn"]
        if t["customer_id"] == "C0028" and t["channel"] == "prepaid" and t["direction"] == "in"
    ]
    assert len(loads) == 6, f"expected exactly 6 prepaid loads for C0028; got {len(loads)}"
    assert all(t["amount"] == Decimal("2900.00") for t in loads), (
        "every prepaid load must be $2,900 (below the $3,000 floor)"
    )
    assert all(t["amount"] < Decimal("3000.00") for t in loads)
    assert sum(t["amount"] for t in loads) == Decimal("17400.00")
    cutoff = AS_OF - timedelta(days=30)
    for t in loads:
        assert t["booked_at"] > cutoff, f"prepaid load must be inside 30d window; got {t}"


def test_c0029_carries_rtp_instant_payment_burst() -> None:
    """8 RTP sends of $950 each inside a tight span, all within the
    rule's 1d sliding window → rtp_instant_payment_burst shape."""
    data = _data()
    sends = [
        t
        for t in data["txn"]
        if t["customer_id"] == "C0029" and t["channel"] == "rtp" and t["direction"] == "out"
    ]
    assert len(sends) == 8, f"expected exactly 8 RTP sends for C0029; got {len(sends)}"
    assert all(t["amount"] == Decimal("950.00") for t in sends)
    assert sum(t["amount"] for t in sends) == Decimal("7600.00")
    timestamps = sorted(t["booked_at"] for t in sends)
    assert timestamps[-1] - timestamps[0] <= timedelta(hours=2), "burst must be tight"
    for t in sends:
        age = AS_OF - t["booked_at"]
        assert timedelta(0) < age < timedelta(days=1), (
            f"every burst send must sit inside the rule's 1d window; got age {age}"
        )


def test_new_rail_background_volume_is_rule_inert() -> None:
    """The RNG-free background-volume block emits small lone txns
    (from a fixed ≤ $1,500 amount list) on CAD `CP-NOISE-*`
    counterparties, spread across non-guarded customers/time so it
    never aggregates into the new rules' count/sum thresholds.

    Identified precisely by the background block's distinguishing
    markers (new rail + CAD + CP-NOISE counterparty) so the planted
    RTP positives (e.g. C0012's $7,500 send) are not misclassified
    as background volume."""
    data = _data()
    bg = [
        t
        for t in data["txn"]
        if t["channel"] in ("rtp", "crypto", "prepaid")
        and t["currency"] == "CAD"
        and str(t.get("counterparty_id") or "").startswith("CP-NOISE-")
    ]
    assert bg, "expected background-volume new-rail rows"
    # Fixed amount list is [75, 140, 260, 520, 910, 1500] — all small.
    assert all(t["amount"] <= Decimal("1500.00") for t in bg), (
        "background-volume amounts must stay small / rule-inert"
    )
    # None of the background rows may land on a guarded plant customer.
    guarded = {f"C{n:04d}" for n in range(12, 30)}
    assert not ({t["customer_id"] for t in bg} & guarded), (
        "background volume leaked onto a guarded plant customer"
    )


def test_c0028_c0029_plants_are_deterministic() -> None:
    a = generate_dataset(as_of=AS_OF, seed=42)
    b = generate_dataset(as_of=AS_OF, seed=42)
    for cid in ("C0028", "C0029"):
        a_txns = sorted((t["amount"], t["booked_at"]) for t in a["txn"] if t["customer_id"] == cid)
        b_txns = sorted((t["amount"], t["booked_at"]) for t in b["txn"] if t["customer_id"] == cid)
        assert a_txns == b_txns, f"determinism break on {cid}"


def test_existing_anchor_unchanged_proves_no_rebase() -> None:
    """The new blocks are appended AFTER C0022 and consume zero
    `random.*`, so they must NOT shift the seeded RNG. Pin an EXISTING
    shape — the C0001 structuring plant rows and the global cash-txn
    count — to fail loudly if a future edit re-bases the dataset."""
    data = _data()
    # C0001's planted cash structuring deposits (hardcoded in the
    # C0001 block) — exact amounts must be unchanged.
    c0001_cash = sorted(
        t["amount"]
        for t in data["txn"]
        if t["customer_id"] == "C0001" and t["channel"] == "cash" and t["amount"] >= 5000
    )
    assert c0001_cash == [
        Decimal("7500.00"),
        Decimal("9200.00"),
        Decimal("9500.00"),
        Decimal("9800.00"),
        Decimal("9900.00"),
    ], f"C0001 structuring plant changed — dataset re-based: {c0001_cash}"
    # The seeded noise loop + C0001..C0022 plants produce a stable 259
    # rows on the legacy code path; the new blocks append exactly 76
    # RNG-free rows (16 C0028/C0029 plant rows + 60 background-volume),
    # so the total must be exactly 259 + 76. Any other value means an
    # appended block consumed `random.*` and shifted the noise loop.
    assert len(data["txn"]) == 259 + 76, (
        f"txn count drifted to {len(data['txn'])} — expected 335 "
        "(legacy 259 + 16 plant + 60 background); dataset re-based"
    )
    # The seeded noise loop produces a stable 49 cash txns; the new
    # RNG-free blocks emit exactly ONE additional cash row (C0028's
    # planted $42k cash-in), so the total is exactly the legacy count + 1.
    cash_count = sum(1 for t in data["txn"] if t["channel"] == "cash")
    assert cash_count == 49 + 1, (
        f"cash-txn count drifted to {cash_count} — noise loop re-based "
        "(legacy 49 + C0028's single planted cash-in)"
    )
    # The C0028 noise-loop rows (e.g. the $4,800 cash-out the noise loop
    # assigned before our plant block ran) must still be present —
    # direct proof the seeded RNG sequence was not disturbed.
    c0028_noise_cash_out = [
        t
        for t in data["txn"]
        if t["customer_id"] == "C0028"
        and t["channel"] == "cash"
        and t["direction"] == "out"
        and t["amount"] == Decimal("4800.00")
    ]
    assert len(c0028_noise_cash_out) == 1, (
        "C0028's pre-existing noise-loop $4,800 cash-out vanished — "
        "appended block re-based the seeded RNG"
    )
