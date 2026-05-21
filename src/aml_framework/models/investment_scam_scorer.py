"""Investment-scam amplifier — pig-butchering payout-pattern python_ref.

Amplifies the existing `invs_velocity_investment_scam`
aggregation_window rule (in `eu_bank/aml.yaml` and
`community_bank/aml.yaml`) with cross-signal patterns the
count+sum SQL aggregation can't express: counterparty
concentration, foreign-destination dominance, velocity
acceleration.

The SQL rule fires on the simple shape: ≥ 3 INVS-purpose-code
outflows summing ≥ $5k within 14 days. It catches the planted
C0010 baseline perfectly (3 wires × €2.5-3k all to CH) and is the
right primary detector — keep it firing.

This scorer is the *amplifier*: it fires on the SAME signal as
the SQL plus a LOWER-count signal when the cross-signal pattern
makes the rule unambiguous:

  Path A (SQL-equivalent baseline): ≥ 3 INVS outflows summing ≥ $5k.
  Path B (cross-signal amplification): ≥ 2 INVS outflows AND
    counterparty concentration ≥ 50% (top counterparty receives
    ≥ half of the total) AND foreign-destination dominance
    (≥ 80% of total to non-domestic countries) AND velocity
    acceleration (gap between successive payouts strictly
    decreasing).

Path B catches the early pig-butchering shape — 2 payouts, both
to the same offshore vehicle, gap shrinking — that the SQL's
hard count threshold misses. The FinCEN FIN-2023-Alert005 +
FATF Cyber-Enabled Fraud (Feb 2026) reports both call out
"accelerating offshore single-beneficiary drain" as the early-
warning signature; the SQL count-3 threshold is the established
floor, the amplifier catches the lead.

Engine contract (`engine/runner.py:845-927`):

    scorer(con, as_of) -> list[dict]

`matched_row_ids` carries the `txn.rowid`s populated directly on
each alert (the SAME table as the existing aggregation_window
rule, so Lineage Explorer's `df_txns.iloc[rowid]` walk-back
works correctly — unlike the mule-return-burst scorer which had
to use `matched_return_ids` against a different table).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import duckdb

logger = logging.getLogger(__name__)

# Lookback aligned with the SQL rule's `window: 14d` so the
# python_ref alerts are anchored on the same window the operator
# tunes.
_LOOKBACK_DAYS = 14

# Threshold the SQL rule fires at — kept identical so Path A is a
# faithful snippet-equivalent.
_HIGH_COUNT_THRESHOLD = 3
_HIGH_SUM_THRESHOLD = Decimal("5000")

# Path B thresholds — looser count, but the cross-signal
# qualification has to hit BOTH the concentration AND foreign-
# destination dominance AND the velocity-acceleration shape.
_LOW_COUNT_THRESHOLD = 2
_COUNTERPARTY_CONCENTRATION_RATIO = Decimal("0.5")
_FOREIGN_DESTINATION_RATIO = Decimal("0.8")

# Same path-safety + column-presence pattern as
# `mule_return_burst_scorer` — defends against zero-row
# placeholder contracts and BYOD shapes.
_REQUIRED_COLUMNS = frozenset(
    {
        "customer_id",
        "amount",
        "direction",
        "purpose_code",
        "counterparty_country",
        "counterparty_id",
        "debtor_country",
        "booked_at",
    }
)


def _fetch_invs_outflows(
    con: duckdb.DuckDBPyConnection,
    as_of: datetime,
    *,
    lookback_days: int = _LOOKBACK_DAYS,
) -> dict[str, list[dict[str, Any]]]:
    """Pull every INVS-purpose-code outbound txn in the lookback
    window, grouped by customer_id.

    Probes `information_schema.columns` before SELECTing —
    `_build_warehouse` creates a zero-column placeholder for
    no-row contracts that would otherwise raise a DuckDB binder
    error and abort the strict-mode python_ref run.
    """
    present = {
        name
        for (name,) in con.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'txn'
            """
        ).fetchall()
    }
    if not _REQUIRED_COLUMNS.issubset(present):
        return {}
    window_start = as_of - timedelta(days=lookback_days)
    rows = con.execute(
        """
        SELECT rowid AS __row_id, customer_id, amount,
               counterparty_country, counterparty_id, debtor_country,
               booked_at
        FROM txn
        WHERE direction = 'out'
          AND purpose_code = 'INVS'
          AND booked_at >= ?
          AND booked_at <  ?
        ORDER BY customer_id, booked_at
        """,
        [window_start, as_of],
    ).fetchall()
    by_customer: dict[str, list[dict[str, Any]]] = {}
    for (
        row_id,
        customer_id,
        amount,
        counterparty_country,
        counterparty_id,
        debtor_country,
        booked_at,
    ) in rows:
        by_customer.setdefault(customer_id, []).append(
            {
                "row_id": int(row_id),
                "amount": Decimal(str(amount)),
                "counterparty_country": counterparty_country or "",
                "counterparty_id": counterparty_id or "",
                "debtor_country": debtor_country or "",
                "booked_at": booked_at,
            }
        )
    return by_customer


def _gaps_strictly_decreasing(sorted_outflows: list[dict[str, Any]]) -> bool:
    """Velocity-acceleration check — successive payout intervals
    must be strictly decreasing. Returns True for `[5d, 3d]` (gap
    shrinks) and False for `[3d, 5d]` (gap widens or stable).

    Requires at least 3 events (= 2 gaps). The 2-event Path B
    case is already gated by the count floor; this function
    just answers whether the gap shape qualifies for triggering.
    """
    if len(sorted_outflows) < 3:
        # 2 events = only 1 gap — no "decreasing" relationship
        # to assert. For Path B's 2-count case we treat
        # acceleration as N/A (the count gate alone won't fire
        # without the concentration + foreign-dom signals).
        return False
    deltas = [
        (sorted_outflows[i]["booked_at"] - sorted_outflows[i - 1]["booked_at"]).total_seconds()
        for i in range(1, len(sorted_outflows))
    ]
    return all(deltas[i] < deltas[i - 1] for i in range(1, len(deltas)))


def _qualifies(outflows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pure function — evaluate the layered qualification for one
    customer's INVS outflows. Returns the qualification payload or
    None.

    Path A: count ≥ 3 AND sum ≥ $5k (SQL-equivalent baseline).
    Path B: count ≥ 2 AND counterparty concentration ≥ 50% AND
      foreign-destination ratio ≥ 80% AND (gap-acceleration on
      3+ events OR all-to-single-counterparty on 2 events).
    """
    if not outflows:
        return None
    count = len(outflows)
    total = sum((o["amount"] for o in outflows), Decimal("0"))
    # Concentration: top counterparty's share of total.
    cp_totals: dict[str, Decimal] = {}
    for o in outflows:
        cp = o["counterparty_id"] or "<unknown>"
        cp_totals[cp] = cp_totals.get(cp, Decimal("0")) + o["amount"]
    top_cp_total = max(cp_totals.values()) if cp_totals else Decimal("0")
    concentration = top_cp_total / total if total > 0 else Decimal("0")
    # Foreign dominance: how much went to a country different
    # from the originator's debtor_country.
    foreign_total = sum(
        (
            o["amount"]
            for o in outflows
            if o["counterparty_country"]
            and o["debtor_country"]
            and o["counterparty_country"] != o["debtor_country"]
        ),
        Decimal("0"),
    )
    foreign_ratio = foreign_total / total if total > 0 else Decimal("0")
    accelerating = _gaps_strictly_decreasing(outflows)
    path_a = count >= _HIGH_COUNT_THRESHOLD and total >= _HIGH_SUM_THRESHOLD
    # Path B's "or" clause: on 2-event count, all-to-single-
    # counterparty is sufficient acceleration evidence (it's the
    # same beneficiary getting drained again — pig-butchering
    # signature). On 3+ events, gaps must actually decrease.
    single_cp = len(cp_totals) == 1
    accel_or_single = accelerating if count >= 3 else single_cp
    path_b = (
        count >= _LOW_COUNT_THRESHOLD
        and concentration >= _COUNTERPARTY_CONCENTRATION_RATIO
        and foreign_ratio >= _FOREIGN_DESTINATION_RATIO
        and accel_or_single
    )
    if not (path_a or path_b):
        return None
    return {
        "matched_outflows": outflows,
        "count": count,
        "sum_amount": total,
        "top_counterparty_concentration": concentration,
        "foreign_destination_ratio": foreign_ratio,
        "accelerating": accelerating,
        "qualifying_path": "snippet" if path_a else "cross_signal",
    }


def _alert_from_qualification(customer_id: str, qualification: dict[str, Any]) -> dict[str, Any]:
    """Shape a qualified customer into the engine-contract alert
    dict. matched_row_ids points back at `txn` rowids (same table
    the SQL rule fires against, so Lineage Explorer walks back
    correctly — see module docstring).
    """
    matched = qualification["matched_outflows"]
    total = qualification["sum_amount"]
    return {
        "rule_id": "investment_scam_scorer",
        "customer_id": customer_id,
        "sum_amount": float(total),
        "count": qualification["count"],
        "top_counterparty_concentration": float(qualification["top_counterparty_concentration"]),
        "foreign_destination_ratio": float(qualification["foreign_destination_ratio"]),
        "accelerating": qualification["accelerating"],
        "qualifying_path": qualification["qualifying_path"],
        "window_start": min(o["booked_at"] for o in matched),
        "window_end": max(o["booked_at"] for o in matched),
        # Risk score: concentration + foreign-dominance + accel
        # all contribute. Bonus for path B (cross-signal evidence
        # is intrinsically harder to fake than count alone — same
        # discipline as the mule-return-burst scorer).
        "risk_score": round(
            min(
                1.0,
                float(qualification["top_counterparty_concentration"]) * 0.4
                + float(qualification["foreign_destination_ratio"]) * 0.4
                + (0.2 if qualification["accelerating"] else 0)
                + (0.1 if qualification["qualifying_path"] == "cross_signal" else 0),
            ),
            4,
        ),
        "matched_row_ids": [o["row_id"] for o in matched],
    }


def investment_scam_scorer(
    con: duckdb.DuckDBPyConnection,
    as_of: datetime,
) -> list[dict[str, Any]]:
    """Procedural python_ref scorer — investment-scam amplifier.

    Engine contract entry point. Heavy lifting in `_qualifies`
    (pure) so the layered qualification is testable in isolation.
    Iterates customers in sorted order for determinism (the
    `test_run_is_reproducible` contract).
    """
    by_customer = _fetch_invs_outflows(con, as_of)
    alerts: list[dict[str, Any]] = []
    for customer_id in sorted(by_customer):
        qualification = _qualifies(by_customer[customer_id])
        if qualification is None:
            continue
        alerts.append(_alert_from_qualification(customer_id, qualification))
    return alerts
