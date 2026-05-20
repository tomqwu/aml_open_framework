"""Pass-through funnel scorer — procedural python_ref.

Detects the cross-channel pass-through typology that the TD Bank
$470M-undetected case made canonical: funds arrive through one
channel, sit briefly, then exit through a different channel.
Channel-set-agnostic — works for cash → e_transfer (Canadian
Schedule I), cash → wire (community bank), and equivalent
cross-channel shapes in other example specs. Same-channel patterns
(cash IN → cash OUT, faster_payments IN → faster_payments OUT) are
either ordinary churn or mule signals — PR-ML-2's mule-network
scorer is the right detector for those.

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
from decimal import Decimal
from typing import Any

import duckdb

logger = logging.getLogger(__name__)

# 48h funnel window — matches the existing `rapid_pass_through`
# custom_sql rule's window length so the procedural scorer's
# threshold-fired alerts line up against the SQL rule's evidence.
_FUNNEL_WINDOW_HOURS = 48

# 30d lookback for candidate anchors — covers the typical monthly
# detection cadence the rest of the python_ref scorers in this
# package use (heuristic + xgboost both window 30d in
# `models/scoring.py` and `models/xgboost_scorer.py`). Long enough
# that the canonical `rapid_pass_through` SQL rule's any-channel
# variant doesn't silently miss funnels 8-30 days old (Codex P2
# round 2 catch — original 7d window left most of the monthly
# detection horizon uncovered).
_LOOKBACK_DAYS = 30

# $30k combined funding+drain threshold — matches the existing
# canonical `rapid_pass_through` rule's `WHERE cash_in_total +
# etransfer_out_total >= 30000` clause so an operator switching from
# the SQL rule to this scorer sees the same headline alert volume.
# Decimal not float so that a row total like 25223.53 + 2879.19 +
# 1897.28 doesn't compare as 29999.999999999996 < 30000 (Codex P2
# round 4 — float drift at the exact threshold silently dropped
# boundary alerts).
_DEFAULT_THRESHOLD = Decimal("30000")

# Known channel allowlist — matches the `canadian_schedule_i_bank`
# `txn.channel` enum exactly (the one example spec that wires this
# scorer in today). Codex P2 round 9: a broader union-of-all-specs
# allowlist would still allow out-of-contract channels through
# when a different spec is loaded — e.g. `faster_payments`
# (uk_app_fraud only) on a Canadian run would falsely count as
# cross-channel evidence. Until the python_ref contract grows
# spec-awareness (deferred follow-up — would require passing the
# loaded `AMLSpec` into `(con, as_of)` callables), this allowlist
# stays scoped to the wired spec. When a new spec wires the scorer
# in, either (a) plant in-contract synthetic data + extend this
# set in lockstep, or (b) make the scorer spec-aware first.
_KNOWN_CHANNELS: frozenset[str] = frozenset(
    {
        "cash",
        "wire",
        "ach",
        "card",
        "cheque",
        "e_transfer",
        "rtp",
        "crypto",
        "prepaid",
    }
)


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
    # `rowid` is the DuckDB pseudo-column the framework's lineage
    # contract pins for `matched_row_ids` (Lineage Explorer
    # `df_txns.iloc[rowid]`); same idiom as `list_match` in
    # `engine/runner.py`'s execution path. Pull it alongside the
    # business columns so each event carries the rowid the engine
    # later stamps onto the alert.
    # Tie-policy: on equal `booked_at`, IN events sort BEFORE OUT
    # events. That makes the funding/drain attribution
    # ID-independent — without this, a tied IN/OUT pair fires when
    # the IN's txn_id sorts first and misses when the OUT does
    # (Codex P2 round 5). The `direction = 'in'` evaluates to TRUE
    # for IN rows; DESC puts TRUE (=1) before FALSE (=0).
    rows = con.execute(
        """
        SELECT rowid AS __row_id, customer_id, txn_id, amount,
               direction, channel, booked_at
        FROM txn
        WHERE booked_at >= ?
          AND booked_at <  ?
        ORDER BY customer_id,
                 booked_at,
                 (direction = 'in') DESC,
                 txn_id
        """,
        [window_start, as_of],
    ).fetchall()
    events: dict[str, list[dict[str, Any]]] = {}
    for row_id, cust, txn_id, amount, direction, channel, booked_at in rows:
        events.setdefault(cust, []).append(
            {
                "row_id": int(row_id),
                "txn_id": txn_id,
                # Decimal not float — preserves exact cents through
                # the threshold comparison (Codex P2 round 4).
                "amount": Decimal(str(amount)),
                "direction": direction,
                "channel": channel,
                "booked_at": booked_at,
            }
        )
    return events


def _find_first_qualifying_window(
    sorted_events: list[dict[str, Any]],
    *,
    threshold: Decimal | int = _DEFAULT_THRESHOLD,
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
        # Find the first OUT-event inside [anchor, window_end]. The
        # 48h boundary is INCLUSIVE — matches the existing
        # `rapid_pass_through` SQL rule's `BETWEEN ci.booked_at AND
        # ci.booked_at + INTERVAL '48' HOUR`. A cross-channel funnel
        # whose drain leg lands exactly at anchor+48h must fire
        # (Codex P2 round 5 — the prior `>=` break missed it).
        first_out_idx: int | None = None
        for i in range(anchor_idx, len(sorted_events)):
            evt = sorted_events[i]
            if evt["booked_at"] > window_end:
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
            if evt["direction"] == "in" and evt["booked_at"] <= window_end
        ]
        # Drain = OUT-events in [first_out, window_end] (boundary
        # inclusive, per the SQL rule's BETWEEN semantics). Early
        # break when `booked_at > window_end` — events are sorted by
        # booked_at so the rest of the tail can't qualify. Avoids
        # the quadratic-on-busy-account scan Codex P3 round 8
        # flagged.
        drain: list[dict[str, Any]] = []
        for i in range(first_out_idx, len(sorted_events)):
            evt = sorted_events[i]
            if evt["booked_at"] > window_end:
                break
            if evt["direction"] == "out":
                drain.append(evt)
        # Filter funding + drain legs to recognized-channel events
        # BEFORE computing totals. Unknown/NULL/typo-channel rows are
        # excluded from the threshold too — Codex P2 round 10
        # caught: cash IN $1 + wiree OUT $29,999 + wire OUT $1 used
        # to clear the $30k floor on $2 of legitimate cross-channel
        # movement. Recognized totals only is the tighter contract.
        funding_known = [e for e in funding if e["channel"] and e["channel"] in _KNOWN_CHANNELS]
        drain_known = [e for e in drain if e["channel"] and e["channel"] in _KNOWN_CHANNELS]
        funding_total = sum((e["amount"] for e in funding_known), Decimal("0"))
        drain_total = sum((e["amount"] for e in drain_known), Decimal("0"))
        # Cross-channel discipline: a true *pass-through* moves funds
        # between distinct channels (cash IN → e_transfer/wire OUT —
        # the TD pattern). Use set-INEQUALITY (`!=`) not strict
        # subset difference so a mixed-rail funding leg with a
        # benign top-up in the same rail as the drain still
        # qualifies: $40k cash IN + $1 wire IN → $40k wire OUT has
        # `{cash, wire} != {wire}` → cross-channel ✓ (Codex P2
        # round 10). Pure same-channel patterns ({cash} == {cash})
        # still don't qualify (mule territory — PR-ML-2's typology).
        funding_channels = {e["channel"] for e in funding_known}
        drain_channels = {e["channel"] for e in drain_known}
        cross_channel = (
            bool(funding_channels) and bool(drain_channels) and funding_channels != drain_channels
        )
        # Qualifying condition: BOTH legs present (a real funnel has
        # both phases — pure deposits or pure outflows never qualify)
        # AND combined volume ≥ threshold AND funding/drain channel
        # sets differ. Matches the existing `rapid_pass_through`
        # custom_sql rule's `WHERE cash_in_total + etransfer_out_total
        # >= 30000` semantic (cross-channel implicit in cash →
        # e_transfer).
        if (
            funding_total > 0
            and drain_total > 0
            and funding_total + drain_total >= threshold
            and cross_channel
        ):
            # Stash only the RECOGNIZED-channel events as the
            # alert's evidence — matched_row_ids walking back to
            # unknown-channel rows would mislead reviewers since
            # those rows didn't contribute to the qualifying
            # decision.
            return {
                "anchor": anchor,
                "window_end": window_end,
                "funding": funding_known,
                "drain": drain_known,
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
    # Coerce monetary fields to float for the dashboard/JSON layer
    # AFTER the threshold comparison has happened in Decimal — the
    # canonical_json serializer + Streamlit grid prefer floats, but
    # the *qualifying decision* was made on Decimal-exact arithmetic.
    return {
        "rule_id": "passthrough_funnel_scorer",
        "customer_id": customer_id,
        "sum_amount": float(total),
        "count": len(funding) + len(drain),
        "funding_total": float(window["funding_total"]),
        "drain_total": float(window["drain_total"]),
        "window_start": window["anchor"]["booked_at"],
        "window_end": max(e["booked_at"] for e in drain),
        "risk_score": round(min(1.0, float(total) / 100_000), 4),
        # DuckDB rowids (integers) — the Lineage Explorer's
        # `df_txns.iloc[rowid]` walk-back expects this shape. txn_id
        # strings would TypeError there (Codex P2 round 1, PR-ML-1).
        "matched_row_ids": [e["row_id"] for e in funding] + [e["row_id"] for e in drain],
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
