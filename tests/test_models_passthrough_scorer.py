"""PR-ML-1 — pass-through funnel scorer unit tests.

Every R1 Codex P2 edge case that the `custom_sql` rule kept tripping
on becomes a named test here. The pure detector
(`_find_first_qualifying_window`) is what the tests exercise directly
— that keeps each edge case a one-liner of construction + one
assertion, instead of round-tripping through DuckDB.

Plus a single integration test against the planted C0007 typology
(via DuckDB) to pin the engine-contract path
(`passthrough_funnel_scorer(con, as_of) -> list[dict]`) end-to-end.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import duckdb
import pytest

from aml_framework.models.passthrough_scorer import (
    _alert_from_window,
    _fetch_customer_events,
    _find_first_qualifying_window,
    passthrough_funnel_scorer,
)


# Sentinel for "channel arg not passed at all" — distinguishes from
# `channel=None` which the unknown-channel tests pass explicitly to
# exercise the NULL-channel BYOD-CSV scenario (Codex P2 round 4).
_UNSET: Any = object()


def _event(
    txn_id: int,
    direction: str,
    amount: float,
    hours_from_base: float,
    *,
    channel: Any = _UNSET,
    base: datetime | None = None,
) -> dict:
    """Test fixture helper — build one event dict at `base + Nh`.

    `row_id` mirrors the DuckDB rowid the engine pulls from the
    `txn` table; the scorer uses it for `matched_row_ids` lineage so
    the Lineage Explorer's `df_txns.iloc[rowid]` walk-back resolves.
    `txn_id` stays as a human-readable label (it's not the lineage
    key — the Codex P2 round 1 catch on PR-ML-1).

    `channel` defaults to **cash for IN, wire for OUT** so the
    fixture matches the cross-channel pass-through shape the scorer
    qualifies on by default. Callers wanting to exercise the same-
    channel-rejection contract pass `channel="cash"` etc. explicitly,
    or `channel=None` to construct the unknown-channel scenario.
    """
    base = base or datetime(2026, 5, 15, 0, 0, 0, tzinfo=timezone.utc)
    if channel is _UNSET:
        channel = "cash" if direction == "in" else "wire"
    return {
        "row_id": txn_id,
        "txn_id": f"T{txn_id:05d}",
        # Decimal — pinned by the threshold-correctness contract;
        # `_find_first_qualifying_window` sums Decimals and compares
        # to a Decimal threshold (Codex P2 round 4 fix).
        "amount": Decimal(str(amount)),
        "direction": direction,
        "channel": channel,
        "booked_at": base + timedelta(hours=hours_from_base),
    }


# ---------------------------------------------------------------------------
# Pure detector — `_find_first_qualifying_window`
# ---------------------------------------------------------------------------


class TestFindFirstQualifyingWindow:
    """Pin every R1-era windowing edge case as a one-test-per-case
    contract. Each test constructs an event sequence and asserts the
    detector picks the right window (or no window)."""

    def test_c0007_baseline_pattern_fires(self):
        # The canonical TD-pattern planted shape: 2 cash IN + 3
        # e_transfer OUT inside 48h, totals $22k + $21k = $43k.
        # Above the $30k floor so MUST fire.
        events = [
            _event(1, "in", 12_000, 9),
            _event(2, "in", 10_000, 14),
            _event(3, "out", 8_000, 28),
            _event(4, "out", 7_000, 36),
            _event(5, "out", 6_000, 42),
        ]
        window = _find_first_qualifying_window(events)
        assert window is not None
        assert window["funding_total"] == 22_000
        assert window["drain_total"] == 21_000
        # First drain at h=28 marks the phase boundary — both IN
        # events at h=9 and h=14 are funding.
        assert {e["txn_id"] for e in window["funding"]} == {"T00001", "T00002"}
        assert {e["txn_id"] for e in window["drain"]} == {"T00003", "T00004", "T00005"}

    def test_benign_top_up_after_drain_does_not_suppress_alert(self):
        # The R1 round-5 descope case. A benign deposit at h=46
        # (inside the 48h window from h=9, but AFTER the drain
        # started at h=28) must NOT be folded into funding — if it
        # were, the SQL "last_fund" pointer jumps to h=46 and the
        # drain window shrinks to nothing, killing the alert.
        events = [
            _event(1, "in", 12_000, 9),
            _event(2, "in", 10_000, 14),
            _event(3, "out", 8_000, 28),
            _event(4, "out", 7_000, 36),
            _event(5, "out", 6_000, 42),
            _event(6, "in", 5_000, 46),  # benign top-up after drain
        ]
        window = _find_first_qualifying_window(events)
        assert window is not None
        # Funding is still the pre-drain pair; the top-up is NOT
        # folded in (this is the bug class the SQL kept tripping on).
        assert {e["txn_id"] for e in window["funding"]} == {"T00001", "T00002"}
        assert window["funding_total"] == 22_000
        assert window["drain_total"] == 21_000

    def test_multi_anchor_windowing_emits_earliest_qualifying_window(self):
        # Two complete funnels for the same customer — one starting at
        # h=9, another starting at h=72 (well outside the first
        # window). The detector must pick the EARLIEST qualifying
        # window, not both, and not a later one. (The "one alert per
        # customer" contract — keeps the alert queue's headline count
        # honest.)
        base2 = 72  # 24h after first window ends
        events = [
            _event(1, "in", 12_000, 9),
            _event(2, "in", 10_000, 14),
            _event(3, "out", 8_000, 28),
            _event(4, "out", 7_000, 36),
            _event(5, "out", 6_000, 42),
            _event(6, "in", 15_000, base2 + 1),
            _event(7, "in", 16_000, base2 + 5),
            _event(8, "out", 14_000, base2 + 12),
            _event(9, "out", 17_000, base2 + 18),
        ]
        window = _find_first_qualifying_window(events)
        assert window is not None
        # Earliest window's anchor is h=9, not h=73.
        assert window["anchor"]["txn_id"] == "T00001"
        assert window["funding_total"] == 22_000

    def test_phase_boundary_attribution_excludes_in_events_after_first_out(self):
        # Interleaved IN/OUT pattern: a later IN BEFORE the next OUT
        # is technically "after" the first OUT — it must NOT be
        # counted as funding. (Funding is strictly events before
        # `first_out_in_window`.)
        events = [
            _event(1, "in", 15_000, 9),
            _event(2, "in", 16_000, 14),  # funding
            _event(3, "out", 14_000, 20),  # first OUT — phase boundary
            _event(4, "in", 99_999, 25),  # AFTER first_out — NOT funding
            _event(5, "out", 18_000, 30),
        ]
        window = _find_first_qualifying_window(events)
        assert window is not None
        # The h=25 deposit is NOT in funding. Funding total stays at
        # $31k (h=9 + h=14), not $130,999 (which would include h=25).
        assert window["funding_total"] == 31_000
        assert "T00004" not in {e["txn_id"] for e in window["funding"]}
        # And NOT in drain either — drain is OUT-events only.
        assert "T00004" not in {e["txn_id"] for e in window["drain"]}

    def test_pure_inbound_no_drain_does_not_fire(self):
        # A customer making large cash deposits and no outbound
        # activity inside the window — savings, not pass-through.
        # AND-threshold means no alert.
        events = [
            _event(1, "in", 25_000, 5),
            _event(2, "in", 30_000, 10),
            _event(3, "in", 40_000, 20),
        ]
        assert _find_first_qualifying_window(events) is None

    def test_pure_outbound_no_funding_does_not_fire(self):
        # Mirror case — drain-only inside the window. No funding
        # source ⇒ no funnel.
        events = [
            _event(1, "out", 25_000, 5),
            _event(2, "out", 30_000, 10),
            _event(3, "out", 40_000, 20),
        ]
        assert _find_first_qualifying_window(events) is None

    def test_below_threshold_funnel_does_not_fire(self):
        # Real funnel shape (IN then OUT inside 48h) but totals
        # under $30k — must NOT fire. Pins the threshold contract.
        events = [
            _event(1, "in", 5_000, 9),
            _event(2, "in", 6_000, 14),
            _event(3, "out", 4_000, 28),
            _event(4, "out", 5_000, 36),
        ]
        assert _find_first_qualifying_window(events) is None

    def test_first_out_outside_48h_window_does_not_fire(self):
        # IN at h=9 + h=14, OUTs pushed past the 48h window of BOTH
        # anchor candidates: h=70 is 56h after the h=14 anchor —
        # outside its 48h funnel window (62h). No anchor can pair
        # with these OUT events ⇒ no funnel.
        events = [
            _event(1, "in", 20_000, 9),
            _event(2, "in", 15_000, 14),
            _event(3, "out", 20_000, 70),
            _event(4, "out", 15_000, 75),
        ]
        assert _find_first_qualifying_window(events) is None

    def test_cross_channel_cash_to_wire_fires(self):
        # The community_bank spec has `[cash, wire, ach, card]` and
        # no `e_transfer`. The scorer must catch cash→wire — any
        # cross-channel pass-through pattern (cash→ach, cash→card,
        # ...) qualifies. Only the channel-CROSS matters; the
        # algorithm is channel-set-agnostic, not channel-agnostic.
        events = [
            _event(1, "in", 12_000, 9, channel="cash"),
            _event(2, "in", 10_000, 14, channel="cash"),
            _event(3, "out", 8_000, 28, channel="wire"),
            _event(4, "out", 7_000, 36, channel="wire"),
            _event(5, "out", 6_000, 42, channel="wire"),
        ]
        window = _find_first_qualifying_window(events)
        assert window is not None
        assert window["funding_total"] == 22_000

    def test_same_channel_pattern_does_not_fire(self):
        # Cash IN followed by cash OUT (or wire IN → wire OUT, or
        # faster_payments IN → faster_payments OUT — the C0019 mule
        # signal) is NOT a pass-through funnel — it's either
        # ordinary same-rail churn or a mule pattern that belongs to
        # PR-ML-2's mule-network scorer. Codex P2 round 2 catch on
        # PR-ML-1: original channel-agnostic version raised critical
        # alerts for benign cash-in-cash-out activity above $30k.
        events = [
            _event(1, "in", 20_000, 9, channel="cash"),
            _event(2, "in", 15_000, 14, channel="cash"),
            _event(3, "out", 18_000, 28, channel="cash"),
            _event(4, "out", 12_000, 36, channel="cash"),
        ]
        assert _find_first_qualifying_window(events) is None

    def test_partial_cross_channel_drain_fires(self):
        # If even ONE drain leg uses a channel outside the funding
        # channel set, the cross-channel predicate qualifies. Mixed
        # drain rails (cash + wire OUT) are still a real funnel as
        # long as the wire leg pushes funds out a different rail
        # than the funding came in on.
        events = [
            _event(1, "in", 20_000, 9, channel="cash"),
            _event(2, "in", 15_000, 14, channel="cash"),
            _event(3, "out", 18_000, 28, channel="cash"),  # same-rail
            _event(4, "out", 12_000, 36, channel="wire"),  # cross-rail
        ]
        window = _find_first_qualifying_window(events)
        assert window is not None
        # Both drain legs count toward drain_total — cross-channel is
        # a qualifier, not a per-event filter.
        assert window["drain_total"] == 30_000

    def test_threshold_override_via_kwarg(self):
        # Pin the kwarg surface — callers (tests, future spec
        # parameterisation) need to be able to push the threshold
        # down without monkey-patching the module constant.
        events = [
            _event(1, "in", 5_000, 9),
            _event(2, "in", 6_000, 14),
            _event(3, "out", 4_000, 28),
            _event(4, "out", 5_000, 36),
        ]
        window = _find_first_qualifying_window(events, threshold=1_000)
        assert window is not None
        assert window["funding_total"] == 11_000

    def test_exact_threshold_with_fractional_cents_fires(self):
        # Codex P2 round 4 — the cent-precision case the float path
        # silently dropped. 25223.53 + 2879.19 + 1897.28 = exactly
        # 30000.00 in Decimal, but as floats sums to
        # 29999.999999999996 < 30000. The scorer MUST fire.
        events = [
            _event(1, "in", "25223.53", 9),
            _event(2, "in", "2879.19", 14),
            _event(3, "out", "1897.28", 28),
            # Pad the drain side to clear the >0 floor with another
            # cross-channel event — Decimal-correct funding sum
            # 25223.53 + 2879.19 = 28102.72, drain 1897.28 → combined
            # exactly 30000.00.
        ]
        window = _find_first_qualifying_window(events)
        assert window is not None
        assert window["funding_total"] + window["drain_total"] == Decimal("30000")

    def test_unknown_channel_on_drain_does_not_fire(self):
        # BYOD/CSV inputs may omit `channel` if the source system
        # doesn't classify it. The contract column allows NULL;
        # `_build_warehouse` inserts None. The scorer MUST refuse to
        # treat None as "different channel" evidence and stay silent —
        # raising a critical alert without proof of cross-channel
        # movement would be a regulatory false positive.
        events = [
            _event(1, "in", 20_000, 9, channel="cash"),
            _event(2, "in", 15_000, 14, channel="cash"),
            _event(3, "out", 18_000, 28, channel=None),
            _event(4, "out", 12_000, 36, channel=None),
        ]
        assert _find_first_qualifying_window(events) is None

    def test_unknown_channel_on_funding_does_not_fire(self):
        # Mirror — funding side has unknown channels. Same rule:
        # cannot prove cross-channel without evidence on BOTH legs.
        events = [
            _event(1, "in", 20_000, 9, channel=None),
            _event(2, "in", 15_000, 14, channel=None),
            _event(3, "out", 18_000, 28, channel="wire"),
            _event(4, "out", 12_000, 36, channel="wire"),
        ]
        assert _find_first_qualifying_window(events) is None

    def test_unknown_enum_value_does_not_fire(self):
        # Codex P2 round 8 — a typo like `wiree` on an outbound leg
        # must NOT count as cross-channel proof. The scorer drops
        # channels outside `_KNOWN_CHANNELS` from the cross-channel
        # set; without this, `{wiree} - {cash}` is non-empty and the
        # rule would raise a critical alert on a typo.
        events = [
            _event(1, "in", 20_000, 9, channel="cash"),
            _event(2, "in", 15_000, 14, channel="cash"),
            _event(3, "out", 18_000, 28, channel="wiree"),  # typo
            _event(4, "out", 12_000, 36, channel="wiree"),
        ]
        assert _find_first_qualifying_window(events) is None

    def test_unknown_channel_amounts_excluded_from_threshold(self):
        # Codex P2 round 10 — the prior implementation summed every
        # leg toward the threshold even if the channel was unknown,
        # so cash IN $1 + wiree OUT $29999 + wire OUT $1 cleared
        # $30k on $2 of legitimate movement. The recognized-only
        # totals stay at $1 + $1 = $2 ⇒ no alert.
        events = [
            _event(1, "in", 1, 9, channel="cash"),
            _event(2, "out", 29_999, 28, channel="wiree"),  # unrecognized
            _event(3, "out", 1, 36, channel="wire"),
        ]
        assert _find_first_qualifying_window(events) is None

    def test_mixed_funding_rails_with_benign_topup_still_fires(self):
        # Codex P2 round 10 — `$40k cash IN + $1 wire IN → $40k wire
        # OUT` is a clear cross-rail funnel; the $1 wire IN is a
        # benign top-up that shouldn't disqualify the alert just
        # because `wire` happens to appear on both sides. The new
        # set-inequality check qualifies on `{cash, wire} != {wire}`.
        events = [
            _event(1, "in", 40_000, 9, channel="cash"),
            _event(2, "in", 1, 14, channel="wire"),  # benign mixed-rail funding
            _event(3, "out", 40_000, 28, channel="wire"),
        ]
        window = _find_first_qualifying_window(events)
        assert window is not None
        assert window["funding_total"] == 40_001
        assert window["drain_total"] == 40_000

    def test_drain_leg_exactly_at_48h_boundary_fires(self):
        # Codex P2 round 5 — the SQL rule uses BETWEEN which is
        # inclusive on both ends. A cross-channel drain leg landing
        # exactly at anchor+48h must qualify here too — otherwise the
        # python_ref scorer's alert volume drifts under the SQL
        # rule's on hour-boundary cases.
        events = [
            _event(1, "in", 20_000, 0),  # anchor at h=0
            _event(2, "in", 15_000, 1),
            _event(3, "out", 35_000, 48),  # exactly at anchor+48h
        ]
        window = _find_first_qualifying_window(events)
        assert window is not None
        assert window["drain_total"] == 35_000


# ---------------------------------------------------------------------------
# Alert shaping — `_alert_from_window`
# ---------------------------------------------------------------------------


class TestAlertShape:
    def test_alert_carries_required_engine_contract_fields(self):
        # Pin the alert dict shape against the Alert Queue / Model
        # Performance / audit-ledger consumers. Any field rename
        # downstream is a 1-bug-class regression.
        events = [
            _event(1, "in", 12_000, 9),
            _event(2, "in", 10_000, 14),
            _event(3, "out", 8_000, 28),
            _event(4, "out", 7_000, 36),
            _event(5, "out", 6_000, 42),
        ]
        window = _find_first_qualifying_window(events)
        alert = _alert_from_window("C0007", window)
        for key in (
            "rule_id",
            "customer_id",
            "sum_amount",
            "count",
            "funding_total",
            "drain_total",
            "window_start",
            "window_end",
            "risk_score",
            "matched_row_ids",
        ):
            assert key in alert, f"alert missing required key {key!r}"
        assert alert["rule_id"] == "passthrough_funnel_scorer"
        assert alert["customer_id"] == "C0007"
        assert alert["sum_amount"] == 43_000
        assert alert["count"] == 5
        # risk_score is bounded [0, 1] for the Model Performance
        # score-distribution bucketing.
        assert 0.0 <= alert["risk_score"] <= 1.0
        # All 5 source rowids walk back in matched_row_ids — the
        # Lineage Explorer reads this for audit evidence. INTEGER
        # rowids (not txn_id strings) is the engine's lineage
        # contract — `df_txns.iloc[rowid]` would TypeError on strings
        # (Codex P2 round 1 catch on PR-ML-1).
        assert alert["matched_row_ids"] == [1, 2, 3, 4, 5]
        assert all(isinstance(r, int) for r in alert["matched_row_ids"])


# ---------------------------------------------------------------------------
# Engine-contract integration — DuckDB round-trip
# ---------------------------------------------------------------------------


@pytest.fixture
def duck_con():
    con = duckdb.connect(":memory:")
    con.execute(
        """
        CREATE TABLE txn (
            customer_id VARCHAR,
            txn_id      VARCHAR,
            amount      DOUBLE,
            direction   VARCHAR,
            channel     VARCHAR,
            booked_at   TIMESTAMP
        )
        """
    )
    yield con
    con.close()


class TestEngineContract:
    def test_passthrough_funnel_scorer_runs_against_duckdb_and_returns_c0007(self, duck_con):
        # Plant the exact C0007 shape from synthetic.py (cash IN at
        # h=9 + h=14, e_transfer OUT at h=28/36/42, 5 days back from
        # as_of) and confirm the engine-contract entry point fires.
        as_of = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
        base = as_of - timedelta(days=5)
        rows = [
            ("C0007", "T1", 12_000.0, "in", "cash", base + timedelta(hours=9)),
            ("C0007", "T2", 10_000.0, "in", "cash", base + timedelta(hours=14)),
            ("C0007", "T3", 8_000.0, "out", "e_transfer", base + timedelta(hours=28)),
            ("C0007", "T4", 7_000.0, "out", "e_transfer", base + timedelta(hours=36)),
            ("C0007", "T5", 6_000.0, "out", "e_transfer", base + timedelta(hours=42)),
            # Negative customer — only deposits, no drain.
            ("C0099", "T6", 50_000.0, "in", "cash", base + timedelta(hours=10)),
        ]
        duck_con.executemany(
            "INSERT INTO txn VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        alerts = passthrough_funnel_scorer(duck_con, as_of)
        # Exactly one alert: C0007. C0099 has no drain so no funnel.
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert["customer_id"] == "C0007"
        assert alert["sum_amount"] == 43_000
        # DuckDB rowids — integers in [0, len(table)). C0007's 5
        # source rows were inserted first (rowids 0..4); C0099's
        # negative-control row got rowid 5. Lineage Explorer's
        # `df_txns.iloc[rowid]` indexes on these integers.
        assert alert["matched_row_ids"] == [0, 1, 2, 3, 4]
        assert all(isinstance(r, int) for r in alert["matched_row_ids"])

    def test_passthrough_funnel_scorer_returns_empty_when_no_txns(self, duck_con):
        as_of = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
        assert passthrough_funnel_scorer(duck_con, as_of) == []

    def test_alerts_are_deterministic_in_customer_id_order(self, duck_con):
        # Plant 3 customers with qualifying funnels in non-sorted
        # insert order. The scorer must emit them in customer_id
        # order so the alert list bytes are deterministic across
        # reruns (the `test_run_is_reproducible` contract).
        as_of = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
        base = as_of - timedelta(days=5)
        rows = []
        for cust in ("C0050", "C0007", "C0030"):
            rows.extend(
                [
                    (cust, f"{cust}-1", 16_000.0, "in", "cash", base + timedelta(hours=9)),
                    (cust, f"{cust}-2", 15_000.0, "in", "cash", base + timedelta(hours=14)),
                    (cust, f"{cust}-3", 14_000.0, "out", "wire", base + timedelta(hours=28)),
                    (cust, f"{cust}-4", 17_000.0, "out", "wire", base + timedelta(hours=36)),
                ]
            )
        duck_con.executemany("INSERT INTO txn VALUES (?, ?, ?, ?, ?, ?)", rows)
        alerts = passthrough_funnel_scorer(duck_con, as_of)
        ids = [a["customer_id"] for a in alerts]
        assert ids == sorted(ids), "alerts must be sorted by customer_id for determinism"


# ---------------------------------------------------------------------------
# Fetch helper coverage
# ---------------------------------------------------------------------------


class TestFetchCustomerEvents:
    def test_respects_lookback_window(self, duck_con):
        # Events older than the lookback must be excluded so a
        # year-old funnel doesn't bleed into today's run.
        as_of = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
        rows = [
            # Inside default 7d window
            ("C0001", "T1", 10_000.0, "in", "cash", as_of - timedelta(days=2)),
            # Outside default 7d window — must be filtered
            ("C0001", "T2", 10_000.0, "in", "cash", as_of - timedelta(days=30)),
        ]
        duck_con.executemany("INSERT INTO txn VALUES (?, ?, ?, ?, ?, ?)", rows)
        events = _fetch_customer_events(duck_con, as_of, lookback_days=7)
        ids = [e["txn_id"] for e in events.get("C0001", [])]
        assert ids == ["T1"]

    def test_events_sorted_chronologically_per_customer(self, duck_con):
        # The pure detector assumes per-customer events are already
        # in time order; pin the fetch helper's contract.
        as_of = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
        rows = [
            ("C0001", "T2", 10_000.0, "out", "wire", as_of - timedelta(hours=10)),
            ("C0001", "T1", 12_000.0, "in", "cash", as_of - timedelta(hours=40)),
        ]
        duck_con.executemany("INSERT INTO txn VALUES (?, ?, ?, ?, ?, ?)", rows)
        events = _fetch_customer_events(duck_con, as_of)
        ts = [e["booked_at"] for e in events["C0001"]]
        assert ts == sorted(ts)

    def test_tied_timestamps_sort_in_before_out(self, duck_con):
        # Codex P2 round 5 — when source systems provide only
        # coarse timestamps, a tied IN/OUT pair must always classify
        # IN as funding and OUT as drain regardless of which txn_id
        # sorts first. Without an explicit tie policy, the same pair
        # could fire one run and miss the next (Z-OUT vs A-IN
        # alphabetical ordering). The fetch helper's ORDER BY pins
        # IN-before-OUT on tied booked_at.
        as_of = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
        tied_at = as_of - timedelta(hours=24)
        rows = [
            # OUT inserted with id sorting LEXICALLY BEFORE the IN's
            # id — without a tie policy this would sort OUT first.
            ("C0001", "AAA-OUT", 35_000.0, "out", "wire", tied_at),
            ("C0001", "ZZZ-IN", 35_000.0, "in", "cash", tied_at),
        ]
        duck_con.executemany("INSERT INTO txn VALUES (?, ?, ?, ?, ?, ?)", rows)
        events = _fetch_customer_events(duck_con, as_of)
        directions = [e["direction"] for e in events["C0001"]]
        assert directions == ["in", "out"], (
            "tie policy: on equal booked_at, IN must sort before OUT regardless of txn_id"
        )
