"""PR-ML-3 — investment-scam amplifier scorer unit tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import duckdb
import pytest

from aml_framework.models.investment_scam_scorer import (
    _alert_from_qualification,
    _fetch_invs_outflows,
    _gaps_strictly_decreasing,
    _qualifies,
    investment_scam_scorer,
)


def _outflow(
    row_id: int,
    amount: float,
    days_ago: float,
    *,
    counterparty_id: str = "CP-OFFSHORE-1",
    counterparty_country: str = "CH",
    debtor_country: str = "DE",
    as_of: datetime | None = None,
) -> dict:
    """Build one synthetic INVS outflow event. Defaults to the
    canonical C0010 shape (CH-offshore from DE)."""
    as_of = as_of or datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
    return {
        "row_id": row_id,
        "amount": Decimal(str(amount)),
        "counterparty_id": counterparty_id,
        "counterparty_country": counterparty_country,
        "debtor_country": debtor_country,
        "booked_at": as_of - timedelta(days=days_ago, hours=14),
    }


# ---------------------------------------------------------------------------
# Gap-acceleration check
# ---------------------------------------------------------------------------


class TestGapsStrictlyDecreasing:
    def test_decreasing_gaps_qualify(self):
        # Days 10, 5, 2 → gaps 5d, 3d (decreasing). True.
        events = [_outflow(1, 1000, 10), _outflow(2, 1000, 5), _outflow(3, 1000, 2)]
        assert _gaps_strictly_decreasing(events) is True

    def test_increasing_gaps_do_not_qualify(self):
        # Days 10, 7, 2 → gaps 3d, 5d (increasing). False.
        events = [_outflow(1, 1000, 10), _outflow(2, 1000, 7), _outflow(3, 1000, 2)]
        assert _gaps_strictly_decreasing(events) is False

    def test_constant_gaps_do_not_qualify(self):
        # Strictly decreasing means NOT equal. Constant fails.
        events = [_outflow(1, 1000, 10), _outflow(2, 1000, 7), _outflow(3, 1000, 4)]
        assert _gaps_strictly_decreasing(events) is False

    def test_two_events_returns_false(self):
        # Only one gap — can't say "decreasing"; Path B handles
        # 2-event case via the single-counterparty gate instead.
        events = [_outflow(1, 1000, 5), _outflow(2, 1000, 2)]
        assert _gaps_strictly_decreasing(events) is False

    def test_one_event_returns_false(self):
        assert _gaps_strictly_decreasing([_outflow(1, 1000, 5)]) is False


# ---------------------------------------------------------------------------
# Qualification — pure function
# ---------------------------------------------------------------------------


class TestQualifies:
    def test_c0010_baseline_path_a_fires(self):
        # The canonical planted shape: 3 outflows (€2.5k, €3k,
        # €2.8k = €8.3k) all to a single CH-offshore beneficiary.
        # Path A (count ≥ 3 AND sum ≥ $5k) fires.
        outflows = [
            _outflow(1, 2500, 10),
            _outflow(2, 3000, 5),
            _outflow(3, 2800, 2),
        ]
        q = _qualifies(outflows)
        assert q is not None
        assert q["count"] == 3
        assert q["sum_amount"] == Decimal("8300")
        assert q["qualifying_path"] == "snippet"

    def test_path_a_two_outflows_does_not_fire(self):
        # 2 outflows totaling $5500 — under the count floor.
        # Path B might still qualify if cross-signals hit; this
        # test pins the single-signal failure.
        outflows = [
            _outflow(1, 2500, 5, counterparty_country="DE"),  # domestic — kills foreign-ratio
            _outflow(2, 3000, 2, counterparty_country="DE"),
        ]
        assert _qualifies(outflows) is None

    def test_path_b_two_outflows_single_offshore_cp_fires(self):
        # 2 outflows, same offshore counterparty (single_cp ⇒
        # acceleration evidence), 100% foreign destination → path B.
        outflows = [
            _outflow(1, 2500, 5, counterparty_id="CP-OFFSHORE-1"),
            _outflow(2, 3000, 2, counterparty_id="CP-OFFSHORE-1"),
        ]
        q = _qualifies(outflows)
        assert q is not None
        assert q["count"] == 2
        assert q["qualifying_path"] == "cross_signal"
        assert q["top_counterparty_concentration"] == Decimal("1.0")
        assert q["foreign_destination_ratio"] == Decimal("1.0")

    def test_path_b_three_outflows_accelerating_fires(self):
        # 3 outflows but with diverse counterparties (1 each):
        # concentration = 1/3 < 50% → path B fails on
        # concentration. Tighten — single counterparty.
        outflows = [
            _outflow(1, 2500, 10, counterparty_id="CP-1"),
            _outflow(2, 3000, 5, counterparty_id="CP-1"),
            _outflow(3, 2800, 2, counterparty_id="CP-1"),
        ]
        q = _qualifies(outflows)
        # Path A also qualifies (count=3 sum>5k) — picks A first.
        assert q is not None
        assert q["qualifying_path"] == "snippet"
        # And the accelerating attribute IS True (10→5→2 gaps
        # are 5d, 3d — decreasing).
        assert q["accelerating"] is True

    def test_path_b_two_diversified_counterparties_does_not_fire(self):
        # 2 outflows, 2 different counterparties — concentration
        # is 50% per counterparty (just at the threshold), so the
        # check is `>=`. But also need foreign-dest and single-
        # counterparty acceleration on count=2 — only one
        # counterparty would pass that gate. With TWO different
        # counterparties: concentration is 0.5 (just at edge);
        # single_cp = False; gap-accel N/A on 2-event → no fire.
        outflows = [
            _outflow(1, 2500, 5, counterparty_id="CP-1"),
            _outflow(2, 2500, 2, counterparty_id="CP-2"),  # different cp
        ]
        assert _qualifies(outflows) is None

    def test_path_b_low_foreign_ratio_does_not_fire(self):
        # 2 outflows, single counterparty (good concentration),
        # but mostly DOMESTIC destination — foreign ratio < 80%
        # so path B fails.
        outflows = [
            _outflow(1, 8000, 5, counterparty_country="DE", debtor_country="DE"),
            _outflow(2, 1000, 2, counterparty_country="CH", debtor_country="DE"),
        ]
        # foreign_total = 1000 / 9000 = 11%, well under 80%
        assert _qualifies(outflows) is None

    def test_empty_outflows_does_not_fire(self):
        assert _qualifies([]) is None

    def test_path_b_null_counterparty_id_does_not_qualify(self):
        # Codex P2 round 1: 2 payouts both with NULL counterparty_id
        # would have bucketed under "<unknown>" making concentration
        # = 100% and single_cp = True, firing a high-severity alert
        # without evidence the payouts went to the same beneficiary.
        # The fix: NULL ids skip the concentration calculation
        # entirely, so concentration = 0 and Path B can't fire.
        outflows = [
            _outflow(1, 5000, 5, counterparty_id=""),
            _outflow(2, 5000, 2, counterparty_id=""),
        ]
        # Path A fails (count=2 < 3); Path B fails (concentration=0).
        assert _qualifies(outflows) is None

    def test_path_b_one_known_one_unknown_counterparty_does_not_fire(self):
        # Codex P2 round 2: 2 outflows where one has a known
        # offshore counterparty and the other has NULL would have
        # given concentration=100% on the known-cp denominator and
        # single_cp=True (only one known bucket). Result: Path B
        # would fire without evidence the unknown payout went to
        # the same beneficiary.
        # Fix: synthetic `<unknown-N>` bucket in concentration AND
        # `single_known_cp` gate that requires ALL outflows to have
        # known counterparty_ids. With this fix, concentration
        # drops to 50% (two buckets) and single_known_cp = False.
        outflows = [
            _outflow(1, 5000, 5, counterparty_id="CP-OFFSHORE-1"),
            _outflow(2, 5000, 2, counterparty_id=""),  # missing id
        ]
        assert _qualifies(outflows) is None

    def test_path_b_all_unknown_counterparties_does_not_fire(self):
        # Codex P2 round 3: 3 accelerating outflows with skewed
        # amounts (300/100/100), all NULL counterparty_ids, all
        # foreign destination — the prior version made each
        # unknown a distinct bucket so top_cp_total = 300 →
        # concentration = 60% → fires Path B without ANY real
        # counterparty evidence.
        # Fix: unknown counterparties contribute to denominator
        # but NEVER to numerator → concentration = 0 → no fire.
        outflows = [
            _outflow(1, 300, 10, counterparty_id=""),
            _outflow(2, 100, 5, counterparty_id=""),
            _outflow(3, 100, 2, counterparty_id=""),
        ]
        # Path A fails too (total $500 < $5k). Path B must also
        # fail — no real concentration evidence.
        assert _qualifies(outflows) is None

    def test_path_b_country_case_mismatch_does_not_count_as_foreign(self):
        # Codex P2 round 3: ISO country codes are case-
        # insensitive. The prior version would treat
        # `counterparty_country='DE'` vs `debtor_country='de'` as
        # foreign, inflating foreign_ratio to 100% on actually-
        # domestic payouts.
        # Fix: normalize (strip + upper) before comparing.
        outflows = [
            _outflow(
                1,
                5000,
                5,
                counterparty_id="CP-1",
                counterparty_country="DE",
                debtor_country="de",
            ),
            _outflow(
                2,
                5000,
                2,
                counterparty_id="CP-1",
                counterparty_country=" DE ",
                debtor_country="DE",
            ),
        ]
        # All domestic. Path A fails (count < 3). Path B must
        # fail on foreign_ratio = 0%.
        assert _qualifies(outflows) is None

    def test_path_a_still_fires_when_optional_columns_missing(self):
        # Codex P1 round 1: when the spec's contract doesn't
        # declare counterparty_id/country/debtor_country (eu_bank's
        # actual shape), the loaded rows have empty strings for
        # those fields. Path A must STILL fire (it doesn't depend
        # on those columns) — the prior all-or-nothing column guard
        # made the scorer a no-op on eu_bank.
        outflows = [
            _outflow(1, 2500, 10, counterparty_id="", counterparty_country="", debtor_country=""),
            _outflow(2, 3000, 5, counterparty_id="", counterparty_country="", debtor_country=""),
            _outflow(3, 2800, 2, counterparty_id="", counterparty_country="", debtor_country=""),
        ]
        q = _qualifies(outflows)
        assert q is not None
        assert q["qualifying_path"] == "snippet"
        assert q["count"] == 3


# ---------------------------------------------------------------------------
# Alert shape
# ---------------------------------------------------------------------------


class TestAlertShape:
    def test_alert_contract_fields(self):
        outflows = [
            _outflow(1, 2500, 10),
            _outflow(2, 3000, 5),
            _outflow(3, 2800, 2),
        ]
        q = _qualifies(outflows)
        alert = _alert_from_qualification("C0010", q)
        for key in (
            "rule_id",
            "customer_id",
            "sum_amount",
            "count",
            "top_counterparty_concentration",
            "foreign_destination_ratio",
            "accelerating",
            "qualifying_path",
            "window_start",
            "window_end",
            "risk_score",
            "matched_row_ids",
        ):
            assert key in alert, f"missing key {key!r}"
        assert alert["rule_id"] == "investment_scam_scorer"
        assert alert["customer_id"] == "C0010"
        assert alert["sum_amount"] == 8300.0
        assert alert["matched_row_ids"] == [1, 2, 3]
        assert all(isinstance(r, int) for r in alert["matched_row_ids"])
        assert 0.0 <= alert["risk_score"] <= 1.0


# ---------------------------------------------------------------------------
# DuckDB integration
# ---------------------------------------------------------------------------


@pytest.fixture
def duck_con():
    con = duckdb.connect(":memory:")
    con.execute(
        """
        CREATE TABLE txn (
            customer_id          VARCHAR,
            amount               DOUBLE,
            direction            VARCHAR,
            purpose_code         VARCHAR,
            counterparty_country VARCHAR,
            counterparty_id      VARCHAR,
            debtor_country       VARCHAR,
            booked_at            TIMESTAMP
        )
        """
    )
    yield con
    con.close()


class TestEngineContract:
    def test_fires_on_c0010_planted_shape(self, duck_con):
        as_of = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
        rows = [
            (
                "C0010",
                2500.0,
                "out",
                "INVS",
                "CH",
                "CP-OFFSHORE-1",
                "DE",
                as_of - timedelta(days=10, hours=14),
            ),
            (
                "C0010",
                3000.0,
                "out",
                "INVS",
                "CH",
                "CP-OFFSHORE-1",
                "DE",
                as_of - timedelta(days=5, hours=14),
            ),
            (
                "C0010",
                2800.0,
                "out",
                "INVS",
                "CH",
                "CP-OFFSHORE-1",
                "DE",
                as_of - timedelta(days=2, hours=14),
            ),
            # negative — non-INVS outflows
            ("C0099", 5000.0, "out", "SUPP", "DE", "CP-DOMESTIC", "DE", as_of - timedelta(days=3)),
        ]
        duck_con.executemany("INSERT INTO txn VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
        alerts = investment_scam_scorer(duck_con, as_of)
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert["customer_id"] == "C0010"
        assert alert["count"] == 3

    def test_inbound_not_counted(self, duck_con):
        # Direction=in should be excluded — the scorer only
        # cares about OUT-flows for scam-payout detection.
        as_of = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
        rows = [
            (
                "C0010",
                2500.0,
                "in",
                "INVS",
                "CH",
                "CP-OFFSHORE-1",
                "DE",
                as_of - timedelta(days=10),
            ),
            ("C0010", 3000.0, "in", "INVS", "CH", "CP-OFFSHORE-1", "DE", as_of - timedelta(days=5)),
            ("C0010", 2800.0, "in", "INVS", "CH", "CP-OFFSHORE-1", "DE", as_of - timedelta(days=2)),
        ]
        duck_con.executemany("INSERT INTO txn VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
        assert investment_scam_scorer(duck_con, as_of) == []

    def test_non_invs_purpose_not_counted(self, duck_con):
        as_of = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
        rows = [
            ("C0010", 2500.0, "out", "SUPP", "CH", "CP", "DE", as_of - timedelta(days=10)),
            ("C0010", 3000.0, "out", "GDDS", "CH", "CP", "DE", as_of - timedelta(days=5)),
        ]
        duck_con.executemany("INSERT INTO txn VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
        assert investment_scam_scorer(duck_con, as_of) == []

    def test_empty_contract_returns_empty(self):
        # Same empty-contract guard as PR-ML-2.
        con = duckdb.connect(":memory:")
        try:
            con.execute("CREATE TABLE txn AS SELECT NULL WHERE 1=0")
            as_of = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
            assert _fetch_invs_outflows(con, as_of) == {}
            assert investment_scam_scorer(con, as_of) == []
        finally:
            con.close()

    def test_missing_table_returns_empty(self):
        con = duckdb.connect(":memory:")
        try:
            as_of = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
            assert _fetch_invs_outflows(con, as_of) == {}
        finally:
            con.close()

    def test_fires_against_eu_bank_shape_with_only_required_columns(self):
        # Codex P1 round 1: eu_bank's `txn` contract doesn't
        # declare counterparty_id/debtor_country. With the
        # all-or-nothing column guard, the scorer was a no-op.
        # Now it must STILL run Path A by SELECTing NULL for the
        # missing optional columns.
        con = duckdb.connect(":memory:")
        try:
            con.execute(
                """
                CREATE TABLE txn (
                    customer_id          VARCHAR,
                    amount               DOUBLE,
                    direction            VARCHAR,
                    purpose_code         VARCHAR,
                    counterparty_country VARCHAR,
                    booked_at            TIMESTAMP
                )
                """
            )
            as_of = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
            rows = [
                ("C0010", 2500.0, "out", "INVS", "CH", as_of - timedelta(days=10)),
                ("C0010", 3000.0, "out", "INVS", "CH", as_of - timedelta(days=5)),
                ("C0010", 2800.0, "out", "INVS", "CH", as_of - timedelta(days=2)),
            ]
            con.executemany("INSERT INTO txn VALUES (?, ?, ?, ?, ?, ?)", rows)
            alerts = investment_scam_scorer(con, as_of)
            assert len(alerts) == 1
            assert alerts[0]["customer_id"] == "C0010"
            assert alerts[0]["qualifying_path"] == "snippet"
        finally:
            con.close()

    def test_blank_counterparty_id_falls_through_to_account(self):
        # Codex P2 round 7: warehouse/BYOD feeds preserve blanks
        # (e.g. `counterparty_id = ''`); without NULLIF(TRIM())
        # the COALESCE returns the empty string, masking the
        # counterparty_account fallback.
        con = duckdb.connect(":memory:")
        try:
            con.execute(
                """
                CREATE TABLE txn (
                    customer_id          VARCHAR,
                    amount               DOUBLE,
                    direction            VARCHAR,
                    purpose_code         VARCHAR,
                    counterparty_country VARCHAR,
                    counterparty_id      VARCHAR,
                    counterparty_account VARCHAR,
                    debtor_country       VARCHAR,
                    booked_at            TIMESTAMP
                )
                """
            )
            as_of = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
            # Two outflows: counterparty_id = '' (blank), but
            # counterparty_account populated. Path B must fire
            # via the fallback.
            rows = [
                (
                    "C0010",
                    5000.0,
                    "out",
                    "INVS",
                    "CH",
                    "",
                    "CH-ACCT-12345",
                    "DE",
                    as_of - timedelta(days=5),
                ),
                (
                    "C0010",
                    5000.0,
                    "out",
                    "INVS",
                    "CH",
                    "  ",
                    "CH-ACCT-12345",
                    "DE",
                    as_of - timedelta(days=2),
                ),
            ]
            con.executemany("INSERT INTO txn VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
            alerts = investment_scam_scorer(con, as_of)
            assert len(alerts) == 1
            assert alerts[0]["qualifying_path"] == "cross_signal"
        finally:
            con.close()

    def test_counterparty_account_falls_back_for_path_b(self):
        # Codex P2 round 5: framework's pacs.008 parser emits the
        # beneficiary identifier as `counterparty_account`, not
        # `counterparty_id`. The scorer's COALESCE picks
        # counterparty_id first, falls back to counterparty_account
        # so Path B activates on the common ISO 20022 ingestion
        # path. Pin: 2 INVS outflows to same counterparty_account
        # → Path B fires.
        con = duckdb.connect(":memory:")
        try:
            con.execute(
                """
                CREATE TABLE txn (
                    customer_id          VARCHAR,
                    amount               DOUBLE,
                    direction            VARCHAR,
                    purpose_code         VARCHAR,
                    counterparty_country VARCHAR,
                    counterparty_account VARCHAR,
                    debtor_country       VARCHAR,
                    booked_at            TIMESTAMP
                )
                """
            )
            as_of = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
            rows = [
                (
                    "C0010",
                    5000.0,
                    "out",
                    "INVS",
                    "CH",
                    "CH-ACCT-12345",
                    "DE",
                    as_of - timedelta(days=5),
                ),
                (
                    "C0010",
                    5000.0,
                    "out",
                    "INVS",
                    "CH",
                    "CH-ACCT-12345",
                    "DE",
                    as_of - timedelta(days=2),
                ),
            ]
            con.executemany("INSERT INTO txn VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
            alerts = investment_scam_scorer(con, as_of)
            assert len(alerts) == 1
            # 2 outflows + same counterparty_account + foreign +
            # single_known_cp → Path B (cross_signal) fires.
            assert alerts[0]["qualifying_path"] == "cross_signal"
            assert alerts[0]["count"] == 2
        finally:
            con.close()

    def test_loop_skips_non_qualifying_customer(self, duck_con):
        # Two customers in the table: one qualifies, the other
        # has just 1 INVS outflow (below all thresholds). Exercises
        # the `continue` branch in the main loop so coverage is
        # complete.
        as_of = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
        rows = [
            # C0010 qualifies — 3 INVS outflows to single offshore cp
            (
                "C0010",
                2500.0,
                "out",
                "INVS",
                "CH",
                "CP-OFFSHORE-1",
                "DE",
                as_of - timedelta(days=10),
            ),
            (
                "C0010",
                3000.0,
                "out",
                "INVS",
                "CH",
                "CP-OFFSHORE-1",
                "DE",
                as_of - timedelta(days=5),
            ),
            (
                "C0010",
                2800.0,
                "out",
                "INVS",
                "CH",
                "CP-OFFSHORE-1",
                "DE",
                as_of - timedelta(days=2),
            ),
            # C0099 has 1 INVS outflow — qualifies neither path A
            # nor path B. The scorer must skip and emit no alert
            # for this customer (the `continue` branch).
            ("C0099", 1000.0, "out", "INVS", "CH", "CP-1", "DE", as_of - timedelta(days=3)),
        ]
        duck_con.executemany("INSERT INTO txn VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
        alerts = investment_scam_scorer(duck_con, as_of)
        assert [a["customer_id"] for a in alerts] == ["C0010"]

    def test_alerts_deterministic_in_customer_order(self, duck_con):
        as_of = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
        rows = []
        for cust in ("C0050", "C0010", "C0030"):
            for d, amt in [(10, 2500.0), (5, 3000.0), (2, 2800.0)]:
                rows.append(
                    (
                        cust,
                        amt,
                        "out",
                        "INVS",
                        "CH",
                        "CP-OFFSHORE-1",
                        "DE",
                        as_of - timedelta(days=d, hours=14),
                    )
                )
        duck_con.executemany("INSERT INTO txn VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
        alerts = investment_scam_scorer(duck_con, as_of)
        ids = [a["customer_id"] for a in alerts]
        assert ids == sorted(ids)
