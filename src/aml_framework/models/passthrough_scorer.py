"""Pass-through funnel scorer — procedural python_ref.

Detects the in-channel → out-channel pass-through typology that the TD
Bank $470M-undetected case made canonical: funds arrive, sit briefly,
then exit through a different channel. Channel-agnostic — works for
cash → e_transfer (Canadian Schedule I), cash → wire (community bank),
and the equivalent shapes in other example specs.

This module exists because R1's `custom_sql` pass-through rule went
through five rounds of Codex review with each round catching another
SQL windowing edge case — benign top-up after the drain suppresses the
alert, multi-anchor windowing double-counts, phase-boundary attribution
mis-assigns drain to funding when interleaved. The team descoped it in
PR e3e598e with the note that *"correct cash-in → payout funnel
detection needs event-pairing / funding-prefix logic that is its own
focused effort"*. This is that focused effort, expressed in Python
where the edge cases are four lines instead of four CTEs.

Algorithm — "first out-event marks the phase boundary":

  1. An anchor is any `direction='in'` transaction inside the lookback
     window (default 7 days).
  2. For each anchor, the funnel window is `[anchor, anchor + 48h)`.
  3. Funding = `direction='in'` events in `[anchor, first_out)` where
     `first_out` is the earliest `direction='out'` event inside the
     funnel window.
  4. Drain = `direction='out'` events in `[first_out, anchor + 48h)`.
  5. A benign top-up after the drain is NOT folded into funding — it
     becomes its own subsequent anchor candidate (its own later
     window). This is the R1-round-5 edge case the SQL kept getting
     wrong.
  6. Qualify the window if BOTH legs are non-empty AND
     `funding_total + drain_total >= threshold` (matches the existing
     `rapid_pass_through` custom_sql rule's combined-total semantic).
  7. Emit one alert per customer — the EARLIEST qualifying window.

Engine contract (`engine/runner.py:845-927`):

    scorer(con, as_of) -> list[dict]

`matched_row_ids` is populated directly on each alert dict (the
funding-leg + drain-leg txn_ids) — no `_inspect_context` hook needed
because the scorer already has the rows in hand.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import duckdb

logger = logging.getLogger(__name__)

# 48h funnel window — matches the existing `rapid_pass_through`
# custom_sql rule's window length so the procedural scorer's
# threshold-fired alerts line up against the SQL rule's evidence.
_FUNNEL_WINDOW_HOURS = 48

# 7d lookback for candidate anchors. Same length as the SQL rule's
# {window_start}..{as_of} default. Long enough that a customer's
# planted typology lands inside the window even when `as_of` is a few
# days past the planted event.
_LOOKBACK_DAYS = 7

# $30k combined funding+drain threshold — matches the existing
# canonical `rapid_pass_through` rule's `WHERE cash_in_total +
# etransfer_out_total >= 30000` clause so an operator switching from
# the SQL rule to this scorer sees the same headline alert volume.
_DEFAULT_THRESHOLD = 30_000


def _fetch_customer_events(
    con: duckdb.DuckDBPyConnection,
    as_of: datetime,
    *,
    lookback_days: int = _LOOKBACK_DAYS,
) -> dict[str, list[dict[str, Any]]]:
    """Pull every txn in the lookback window, grouped by customer.

    Returns a `{customer_id: [event_dict, ...]}` map with each list
    sorted chronologically. Pulling once and partitioning in Python is
    simpler than running per-customer SQL — the lookback window is
    bounded (7 days × ~thousand customers ⇒ tens of thousands of
    rows, well within memory).
    """
    window_start = as_of - timedelta(days=lookback_days)
    rows = con.execute(
        """
        SELECT customer_id, txn_id, amount, direction, channel, booked_at
        FROM txn
        WHERE booked_at >= ?
          AND booked_at <  ?
        ORDER BY customer_id, booked_at, txn_id
        """,
        [window_start, as_of],
    ).fetchall()
    events: dict[str, list[dict[str, Any]]] = {}
    for cust, txn_id, amount, direction, channel, booked_at in rows:
        events.setdefault(cust, []).append(
            {
                "txn_id": txn_id,
                "amount": float(amount),
                "direction": direction,
                "channel": channel,
                "booked_at": booked_at,
            }
        )
    return events


def _find_first_qualifying_window(
    sorted_events: list[dict[str, Any]],
    *,
    threshold: float = _DEFAULT_THRESHOLD,
    window_hours: int = _FUNNEL_WINDOW_HOURS,
) -> dict[str, Any] | None:
    """Pure function — return the earliest qualifying funnel window
    for one customer's chronologically-sorted events, or None.

    Lifted out as a pure function so the 5 R1-Codex edge cases can be
    unit-tested directly without DuckDB or the rest of the runner.
    """
    window_delta = timedelta(hours=window_hours)
    # Every IN-event is a candidate anchor. Iterate in chronological
    # order so the FIRST qualifying window wins — that's the
    # "earliest qualifying" contract.
    for anchor_idx, anchor in enumerate(sorted_events):
        if anchor["direction"] != "in":
            continue
        window_end = anchor["booked_at"] + window_delta
        # Find the first OUT-event inside [anchor, window_end). That
        # boundary defines funding (events before it) vs drain (events
        # at or after it). If there's no OUT-event in the window,
        # nothing to drain — skip.
        first_out_idx: int | None = None
        for i in range(anchor_idx, len(sorted_events)):
            evt = sorted_events[i]
            if evt["booked_at"] >= window_end:
                break
            if evt["direction"] == "out":
                first_out_idx = i
                break
        if first_out_idx is None:
            continue
        # Funding = IN-events in [anchor, first_out_idx). A benign
        # top-up AFTER first_out is NOT funding — it's an out-of-
        # phase deposit that becomes its own subsequent anchor
        # candidate.
        funding = [
            evt
            for evt in sorted_events[anchor_idx:first_out_idx]
            if evt["direction"] == "in" and evt["booked_at"] < window_end
        ]
        # Drain = OUT-events in [first_out, window_end).
        drain = [
            sorted_events[i]
            for i in range(first_out_idx, len(sorted_events))
            if sorted_events[i]["direction"] == "out" and sorted_events[i]["booked_at"] < window_end
        ]
        funding_total = sum(e["amount"] for e in funding)
        drain_total = sum(e["amount"] for e in drain)
        # Qualifying condition: BOTH legs present (a real funnel has
        # both phases — pure deposits or pure outflows never qualify)
        # AND combined volume ≥ threshold. Matches the existing
        # `rapid_pass_through` custom_sql rule's `WHERE cash_in_total
        # + etransfer_out_total >= 30000` semantic so the procedural
        # scorer's headline alert volume aligns with operators'
        # existing baseline.
        if funding_total > 0 and drain_total > 0 and funding_total + drain_total >= threshold:
            return {
                "anchor": anchor,
                "window_end": window_end,
                "funding": funding,
                "drain": drain,
                "funding_total": funding_total,
                "drain_total": drain_total,
            }
    return None


def _alert_from_window(customer_id: str, window: dict[str, Any]) -> dict[str, Any]:
    """Shape a qualifying window into an engine-contract alert dict.

    `sum_amount` and `count` mirror the existing canonical alert
    fields (used by KPIs + the Alert Queue grid). `risk_score`
    summarises the funnel intensity as `min(1.0, total / 100k)` so
    Model Performance's score-distribution histogram has a
    monotonically-rising signal to bin. `matched_row_ids` is the
    funding-leg + drain-leg `txn_id`s so the Lineage Explorer / audit
    walk-back can show the analyst the exact evidence the scorer
    fired on — populated directly here instead of via an
    `_inspect_context` hook because the scorer already has the rows
    in hand (re-deriving them in a second pass would be wasted work
    AND would risk drift if the algorithm changed).
    """
    funding = window["funding"]
    drain = window["drain"]
    total = window["funding_total"] + window["drain_total"]
    return {
        "rule_id": "passthrough_funnel_scorer",
        "customer_id": customer_id,
        "sum_amount": total,
        "count": len(funding) + len(drain),
        "funding_total": window["funding_total"],
        "drain_total": window["drain_total"],
        "window_start": window["anchor"]["booked_at"],
        "window_end": max(e["booked_at"] for e in drain),
        "risk_score": round(min(1.0, total / 100_000), 4),
        "matched_row_ids": [e["txn_id"] for e in funding] + [e["txn_id"] for e in drain],
    }


def passthrough_funnel_scorer(
    con: duckdb.DuckDBPyConnection,
    as_of: datetime,
) -> list[dict[str, Any]]:
    """Procedural python_ref scorer — pass-through funnel detection.

    Engine contract entry point. The heavy lifting is in
    `_find_first_qualifying_window` (pure) so this function is just
    glue: pull → partition by customer → run the pure detector → shape
    alerts.
    """
    events = _fetch_customer_events(con, as_of)
    alerts: list[dict[str, Any]] = []
    # Iterate customers in sorted id order so the alert list is
    # deterministic — same `as_of`, same data, identical bytes (the
    # `test_run_is_reproducible` contract).
    for cust_id in sorted(events):
        window = _find_first_qualifying_window(events[cust_id])
        if window is None:
            continue
        alerts.append(_alert_from_window(cust_id, window))
    return alerts


# NOTE: no `_inspect_context` hook is exported — `matched_row_ids` is
# populated directly on each alert by `_alert_from_window`. The runner
# only calls the hook if the module exposes it, so omitting it leaves
# the alert's own `matched_row_ids` intact (verified against
# `engine/runner.py:876-892`).
