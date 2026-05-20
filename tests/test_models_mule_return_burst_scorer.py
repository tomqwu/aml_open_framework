"""PR-ML-2 — mule-return-burst scorer unit tests.

The pure detector (`_qualifies`) carries the layered-qualification
logic — each path A (snippet-equivalent count threshold) and path B
(cross-signal fan-out + shell-name density) gets its own named
test. The DuckDB integration test rounds out the engine-contract
end (`mule_return_burst_scorer(con, as_of) -> list[dict]`).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import duckdb
import pytest

from aml_framework.models.mule_return_burst_scorer import (
    _alert_from_qualification,
    _fetch_returns,
    _is_shell_name,
    _qualifies,
    mule_return_burst_scorer,
)


def _return(
    return_id: int,
    reason_code: str,
    amount: float,
    days_ago: float,
    *,
    beneficiary_name: str = "SHELL VEHICLE 1",
    beneficiary_country: str = "CH",
    as_of: datetime | None = None,
) -> dict:
    """Build one synthetic txn_return row. Defaults mirror C0011's
    planted shape so most tests can override only the field they're
    exercising."""
    as_of = as_of or datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
    return {
        "row_id": return_id,
        "return_id": f"RTR-{return_id:03d}",
        "reason_code": reason_code.upper(),
        "beneficiary_name": beneficiary_name,
        "beneficiary_country": beneficiary_country,
        "amount": Decimal(str(amount)),
        "returned_at": as_of - timedelta(days=days_ago, hours=10),
    }


# ---------------------------------------------------------------------------
# Shell-name pattern matcher
# ---------------------------------------------------------------------------


class TestIsShellName:
    def test_matches_known_patterns(self):
        for name in (
            "SHELL VEHICLE 1",
            "Some Nominee Co",
            "Atlas Trust Services",
            "Random Holdings Ltd",
            "Generic Consulting Limited",
            "SHELL CO ALPHA",
        ):
            assert _is_shell_name(name), f"expected match: {name!r}"

    def test_rejects_legitimate_names(self):
        for name in (
            "Acme Corp",
            "Tesla Inc",
            "Sainsbury's Plc",
            "",  # empty
            None,  # null safe
        ):
            assert not _is_shell_name(name or ""), f"unexpected match: {name!r}"

    def test_match_is_case_insensitive(self):
        # The patterns are stored lowercased; the matcher must
        # lowercase the haystack. Both casings must hit.
        assert _is_shell_name("shell vehicle 99")
        assert _is_shell_name("SHELL VEHICLE 99")
        assert _is_shell_name("Shell Vehicle 99")


# ---------------------------------------------------------------------------
# Qualification — pure function
# ---------------------------------------------------------------------------


class TestQualifies:
    def test_c0011_baseline_path_a_fires(self):
        # The canonical planted shape: 3 returns, all high-risk
        # reason codes. Path A (count ≥ 3) qualifies regardless
        # of fan-out, matching the SQL snippet's behavior.
        returns = [
            _return(1, "AC03", 12_000, 2),
            _return(2, "AC04", 9_500, 4),
            _return(3, "MD07", 7_800, 5),
        ]
        q = _qualifies(returns)
        assert q is not None
        assert q["high_risk_count"] == 3
        assert q["qualifying_path"] == "snippet"

    def test_path_a_one_return_below_threshold_does_not_fire(self):
        # A single high-risk return is too noisy to fire on
        # (could be a real account-closure dispute). Pins the
        # count-threshold contract.
        returns = [_return(1, "AC03", 12_000, 2)]
        assert _qualifies(returns) is None

    def test_path_b_two_returns_with_fanout_and_shells_fires(self):
        # The cross-signal path: only 2 returns, but 2 distinct
        # beneficiary countries + 2 shell-pattern beneficiaries.
        # SQL snippet would miss this (count < 3); python_ref
        # catches it.
        returns = [
            _return(1, "AC03", 8_000, 2, beneficiary_country="CH"),
            _return(2, "MD07", 7_500, 4, beneficiary_country="LI"),
        ]
        q = _qualifies(returns)
        assert q is not None
        assert q["high_risk_count"] == 2
        assert q["distinct_beneficiary_countries"] == 2
        assert q["shell_name_density"] == 2
        assert q["qualifying_path"] == "cross_signal"

    def test_path_b_two_returns_single_country_does_not_fire(self):
        # 2 returns, but BOTH to the same country — fan-out
        # signal absent. Stays silent (no path qualifies).
        returns = [
            _return(1, "AC03", 8_000, 2, beneficiary_country="CH"),
            _return(2, "MD07", 7_500, 4, beneficiary_country="CH"),
        ]
        assert _qualifies(returns) is None

    def test_path_b_two_returns_no_shell_names_does_not_fire(self):
        # 2 returns, 2 countries, but legitimate-looking
        # beneficiary names. Path B's shell-density gate stays
        # closed → no alert (the false-positive guard).
        returns = [
            _return(1, "AC03", 8_000, 2, beneficiary_name="Acme Corp"),
            _return(
                2, "MD07", 7_500, 4, beneficiary_name="Sainsbury Plc", beneficiary_country="LI"
            ),
        ]
        assert _qualifies(returns) is None

    def test_low_risk_reason_codes_excluded(self):
        # The pacs.004 set includes many benign reason codes
        # (e.g. RC09 "Beneficiary IBAN format error" — operational,
        # not mule-probing). Only the high-risk set counts toward
        # qualification.
        returns = [
            _return(1, "RC09", 1_000, 1),  # benign
            _return(2, "RC09", 1_000, 2),
            _return(3, "RC09", 1_000, 3),
            _return(4, "RC09", 1_000, 4),
        ]
        assert _qualifies(returns) is None

    def test_mixed_high_and_low_only_counts_high(self):
        # Mix high-risk + low-risk reason codes. Low-risk codes
        # must be excluded from `high_risk_count` so the qualifying
        # paths don't get inflated. Here: 2 high + 1 low; the high
        # legs span 2 jurisdictions (CH + LI) + 2 shell names →
        # path B qualifies on count=2.
        returns = [
            _return(1, "AC03", 8_000, 1, beneficiary_country="CH"),
            _return(2, "AC04", 7_000, 2, beneficiary_country="LI"),
            _return(3, "RC09", 1_000, 3, beneficiary_country="DE"),  # ignored (low-risk)
        ]
        q = _qualifies(returns)
        assert q is not None
        # Count reflects HIGH-RISK rows only — the RC09 row never
        # contributes to the count even though it's in the window.
        assert q["high_risk_count"] == 2
        # 2 distinct countries on the HIGH-RISK legs → path B fires.
        assert q["distinct_beneficiary_countries"] == 2
        assert q["qualifying_path"] == "cross_signal"

    def test_empty_returns_does_not_fire(self):
        assert _qualifies([]) is None


# ---------------------------------------------------------------------------
# Alert shaping
# ---------------------------------------------------------------------------


class TestAlertShape:
    def test_alert_carries_engine_contract_fields(self):
        returns = [
            _return(1, "AC03", 12_000, 2),
            _return(2, "AC04", 9_500, 4),
            _return(3, "MD07", 7_800, 5),
        ]
        q = _qualifies(returns)
        alert = _alert_from_qualification("ROAMR LTD", q)
        for key in (
            "rule_id",
            "customer_id",
            "originator_name",
            "sum_amount",
            "count",
            "distinct_beneficiary_countries",
            "shell_name_density",
            "qualifying_path",
            "window_start",
            "window_end",
            "risk_score",
            "matched_row_ids",
        ):
            assert key in alert, f"missing required key {key!r}"
        assert alert["rule_id"] == "mule_return_burst_scorer"
        assert alert["customer_id"] == "ROAMR LTD"  # originator-as-customer
        assert alert["sum_amount"] == 29_300.0
        assert alert["count"] == 3
        assert alert["matched_row_ids"] == [1, 2, 3]
        assert all(isinstance(r, int) for r in alert["matched_row_ids"])
        assert 0.0 <= alert["risk_score"] <= 1.0

    def test_cross_signal_path_has_higher_risk_score(self):
        # Two qualifying returns: same count (2) but one as path A
        # (impossible — count 2 < 3 so always path B). Compare a
        # 3-return path-A alert vs a 2-return path-B alert with the
        # SAME count: path B should outscore on the same count.
        path_a_returns = [
            _return(1, "AC03", 8_000, 2),
            _return(2, "AC04", 7_000, 3),
            _return(3, "MD07", 6_000, 4),
        ]
        # Make path-B specifically score the same count by
        # generating 3 returns that ALSO satisfy path B.
        path_b_returns = [
            _return(1, "AC03", 8_000, 2, beneficiary_country="CH"),
            _return(2, "AC04", 7_000, 3, beneficiary_country="LI"),
            _return(3, "MD07", 6_000, 4, beneficiary_country="LU"),
        ]
        # Path A picks "snippet" because count ≥ 3 hits first.
        a_alert = _alert_from_qualification("X", _qualifies(path_a_returns))
        # Path B forces the score-bonus path by rebuilding the
        # qualification with the path label override (the qualification
        # function picks A when both qualify; we override here purely
        # to test the score branch).
        b_qual = _qualifies(path_b_returns)
        b_qual["qualifying_path"] = "cross_signal"
        b_alert = _alert_from_qualification("X", b_qual)
        assert b_alert["risk_score"] > a_alert["risk_score"]


# ---------------------------------------------------------------------------
# DuckDB engine-contract integration
# ---------------------------------------------------------------------------


@pytest.fixture
def duck_con():
    con = duckdb.connect(":memory:")
    con.execute(
        """
        CREATE TABLE txn_return (
            return_id            VARCHAR,
            amount               DOUBLE,
            currency             VARCHAR,
            returned_at          TIMESTAMP,
            reason_code          VARCHAR,
            originator_name      VARCHAR,
            beneficiary_name     VARCHAR,
            beneficiary_country  VARCHAR
        )
        """
    )
    yield con
    con.close()


class TestEngineContract:
    def test_scorer_fires_on_c0011_planted_shape(self, duck_con):
        # Plant exactly C0011's shape: ROAMR LTD, 3 high-risk
        # returns over 5 days, all to CH-jurisdiction SHELL
        # VEHICLE beneficiaries.
        as_of = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
        rows = []
        for i, (days, code, amt, ben) in enumerate(
            [
                (2, "AC03", 12_000.0, "SHELL VEHICLE 1"),
                (4, "AC04", 9_500.0, "SHELL VEHICLE 2"),
                (5, "MD07", 7_800.0, "SHELL VEHICLE 3"),
            ],
            start=1,
        ):
            rows.append(
                (
                    f"RTR-{i:03d}",
                    amt,
                    "EUR",
                    as_of - timedelta(days=days, hours=10),
                    code,
                    "ROAMR LTD",
                    ben,
                    "CH",
                )
            )
        # A second benign originator with one return — must NOT fire.
        rows.append(
            (
                "RTR-099",
                500.0,
                "EUR",
                as_of - timedelta(days=1, hours=2),
                "AC03",
                "BENIGN CORP",
                "Acme Holdings AG",
                "CH",
            )
        )
        duck_con.executemany(
            "INSERT INTO txn_return VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        alerts = mule_return_burst_scorer(duck_con, as_of)
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert["customer_id"] == "ROAMR LTD"
        assert alert["count"] == 3
        # rowids assigned by DuckDB insertion order: ROAMR LTD's
        # rows are 0 (days=2), 1 (days=4), 2 (days=5). The fetch's
        # `ORDER BY returned_at` returns them oldest-first, so
        # matched_row_ids is [2, 1, 0] (Lineage Explorer's
        # `df_returns.iloc[rowid]` walk-back works on any order).
        assert sorted(alert["matched_row_ids"]) == [0, 1, 2]
        assert all(isinstance(r, int) for r in alert["matched_row_ids"])

    def test_scorer_returns_empty_when_no_returns(self, duck_con):
        as_of = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
        assert mule_return_burst_scorer(duck_con, as_of) == []

    def test_scorer_excludes_returns_outside_lookback(self, duck_con):
        # 3 high-risk returns but all > 30d old → outside the
        # default lookback → no alert.
        as_of = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
        rows = [
            (
                f"RTR-OLD-{i}",
                10_000.0,
                "EUR",
                as_of - timedelta(days=45 + i),
                "AC03",
                "OLD CORP",
                "SHELL VEHICLE",
                "CH",
            )
            for i in range(3)
        ]
        duck_con.executemany("INSERT INTO txn_return VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
        assert mule_return_burst_scorer(duck_con, as_of) == []

    def test_alerts_deterministic_in_originator_order(self, duck_con):
        # Plant two qualifying originators in non-sorted insert
        # order. The scorer must emit them in alphabetic originator
        # order so the alert list bytes are deterministic
        # (`test_run_is_reproducible` contract).
        as_of = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
        rows = []
        for originator in ("ZULU LTD", "ALPHA LTD"):
            for i, (days, code) in enumerate([(2, "AC03"), (3, "AC04"), (4, "MD07")], start=1):
                rows.append(
                    (
                        f"RTR-{originator[:1]}-{i}",
                        10_000.0,
                        "EUR",
                        as_of - timedelta(days=days),
                        code,
                        originator,
                        "SHELL VEHICLE",
                        "CH",
                    )
                )
        duck_con.executemany("INSERT INTO txn_return VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
        alerts = mule_return_burst_scorer(duck_con, as_of)
        names = [a["originator_name"] for a in alerts]
        assert names == sorted(names), "must be sorted by originator_name for determinism"


# ---------------------------------------------------------------------------
# Fetch helper
# ---------------------------------------------------------------------------


class TestFetchReturns:
    def test_null_originator_skipped(self, duck_con):
        # If a row's originator_name is NULL, the row can't be
        # grouped by originator — drop it so the scorer doesn't
        # produce a `customer_id: None` alert.
        as_of = datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)
        rows = [
            (
                "RTR-NULL",
                10_000.0,
                "EUR",
                as_of - timedelta(days=2),
                "AC03",
                None,  # null originator
                "SHELL VEHICLE",
                "CH",
            ),
        ]
        duck_con.executemany("INSERT INTO txn_return VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
        events = _fetch_returns(duck_con, as_of)
        assert events == {}
