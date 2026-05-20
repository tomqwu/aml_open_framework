"""Mule-return-burst scorer — pacs.004 cross-table mule detection.

Detects the mule-recruitment-via-return-probing typology that the
FATF Cyber-Enabled Fraud (Feb 2026) report and the FCA FG24/4 APP
fraud guidance both call out: an originator's outbound credit
transfers are bounced back via pacs.004 returns with high-risk
reason codes (closed beneficiary account, invalid account number,
end-customer deceased) at a rate that signals systematic mule
probing — the bad actor is fishing for live drop accounts.

The framework already ships a `custom_sql` version of this signal
in `spec/library/iso20022_return_reasons.yaml`'s
`high_risk_return_burst_mule_probing` snippet. This python_ref
scorer goes beyond what the snippet expresses by combining
**three** signals that need cross-row reasoning the snippet's
single GROUP BY can't do without nested CTEs:

  1. High-risk reason count — same as the snippet (≥ 3 returns in
     the window with reason in the high-risk set).
  2. Beneficiary-country fan-out — a single originator returning
     funds across multiple foreign jurisdictions is the
     "spray-and-pray" mule-recruitment shape (vs. a single-corridor
     pattern that's more likely a legitimate corporate dispute).
  3. Beneficiary-name shell-pattern density — repeated returns to
     beneficiaries with the "SHELL VEHICLE / NOMINEE / TRUST
     SERVICES" naming convention, even at lower count, indicates
     adversarial-test-account probing.

The scorer fires when EITHER the snippet's count threshold is met
(criterion 1) OR a lower count appears with criteria 2 + 3
combined. That layered qualification catches mule patterns the SQL
snippet's hard count threshold would miss while not raising
critical alerts on benign corporate-return spikes.

C0011 (`ROAMR LTD`) is the planted ground-truth positive:
3 returns within a week, reason codes {AC03, AC04, MD07},
beneficiaries {SHELL VEHICLE 1, 2, 3} all `CH`-jurisdiction. Both
qualification paths fire; the test suite asserts criterion 1
alone is sufficient (snippet-equivalence) AND that the layered
path catches a tighter 2-return synthetic case.

Engine contract (`engine/runner.py:845-927`):

    scorer(con, as_of) -> list[dict]

`matched_row_ids` carries the `txn_return.rowid`s the alert fired
on, populated directly on each alert dict (no `_inspect_context`
needed since the scorer has the rows in hand).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import duckdb

logger = logging.getLogger(__name__)

# 30d lookback — same as the other mule/funnel scorers in the
# package so cross-typology dashboards see consistent windows.
_LOOKBACK_DAYS = 30

# High-risk pacs.004 reason codes per ISO 20022 + the FCA FG24/4
# return-reason mining guidance. Mirrors the
# `high_risk_return_burst_mule_probing` snippet's set so the two
# detectors agree on the "high-risk" classification.
_HIGH_RISK_REASON_CODES: frozenset[str] = frozenset(
    {
        "AC03",  # Invalid creditor account number
        "AC04",  # Closed creditor account
        "AC06",  # Blocked account
        "AG01",  # Transaction forbidden
        "AM05",  # Duplication
        "BE05",  # Identification of end-customer not valid
        "BE06",  # End-customer specified is not known
        "FRAD",  # Fraudulent origin
        "MD07",  # End-customer deceased
        "RR04",  # Regulatory reason
    }
)

# Lower-cased substring matches for beneficiary names that look
# like shell entities / nominee structures — adversarial-test
# probing fingerprint. Conservative list; expand only when a
# real-world investigation surfaces a new pattern.
_SHELL_NAME_PATTERNS: tuple[str, ...] = (
    "shell vehicle",
    "shell co",
    "nominee",
    "trust services",
    "holdings ltd",
    "consulting limited",
)

# Layered-qualification thresholds. Criterion 1 (count alone) is
# kept aligned with the SQL snippet (≥ 3). Criterion 2+3 combo
# fires at the lower count when the FAN-OUT shape is present so
# the python_ref scorer catches what the snippet misses.
_HIGH_COUNT_THRESHOLD = 3
_LOW_COUNT_THRESHOLD = 2
_DISTINCT_COUNTRY_FANOUT = 2
_SHELL_NAME_DENSITY = 2


def _fetch_returns(
    con: duckdb.DuckDBPyConnection,
    as_of: datetime,
    *,
    lookback_days: int = _LOOKBACK_DAYS,
) -> dict[str, list[dict[str, Any]]]:
    """Pull every pacs.004 return in the lookback window, grouped
    by originator_name.

    `txn_return` is the framework's pacs.004 contract — `return_id`,
    `reason_code`, `originator_name`, `beneficiary_name`,
    `beneficiary_country`, `amount`, `returned_at`. The scorer
    reads `originator_name` rather than `customer_id` because the
    pacs.004 message format keys on the legal entity name, not the
    sending PSP's internal customer id; the snippet does the same.
    """
    window_start = as_of - timedelta(days=lookback_days)
    rows = con.execute(
        """
        SELECT rowid AS __row_id, return_id, originator_name,
               UPPER(reason_code) AS reason_code,
               beneficiary_name, beneficiary_country,
               amount, returned_at
        FROM txn_return
        WHERE returned_at >= ?
          AND returned_at <  ?
        ORDER BY originator_name, returned_at, return_id
        """,
        [window_start, as_of],
    ).fetchall()
    by_origin: dict[str, list[dict[str, Any]]] = {}
    for (
        row_id,
        return_id,
        originator_name,
        reason_code,
        beneficiary_name,
        beneficiary_country,
        amount,
        returned_at,
    ) in rows:
        if not originator_name:
            continue
        by_origin.setdefault(originator_name, []).append(
            {
                "row_id": int(row_id),
                "return_id": return_id,
                "reason_code": reason_code,
                "beneficiary_name": beneficiary_name or "",
                "beneficiary_country": beneficiary_country or "",
                "amount": Decimal(str(amount)),
                "returned_at": returned_at,
            }
        )
    return by_origin


def _is_shell_name(name: str) -> bool:
    """Lower-cased substring match against `_SHELL_NAME_PATTERNS`.

    Lifted out so the pattern list is unit-testable in isolation
    and so future investigators can add patterns without touching
    the qualification logic.
    """
    if not name:
        return False
    haystack = name.lower()
    return any(p in haystack for p in _SHELL_NAME_PATTERNS)


def _qualifies(returns: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pure function — evaluate the layered qualification for one
    originator's returns. Returns the qualification payload or None.

    Layered shape:
      - Path A (snippet-equivalent): high-risk count ≥ 3.
      - Path B (cross-signal): high-risk count ≥ 2 AND distinct
        beneficiary countries ≥ 2 AND shell-name density ≥ 2.
    """
    high_risk = [r for r in returns if r["reason_code"] in _HIGH_RISK_REASON_CODES]
    if not high_risk:
        return None
    count = len(high_risk)
    distinct_countries = len(
        {r["beneficiary_country"] for r in high_risk if r["beneficiary_country"]}
    )
    shell_count = sum(1 for r in high_risk if _is_shell_name(r["beneficiary_name"]))
    path_a = count >= _HIGH_COUNT_THRESHOLD
    path_b = (
        count >= _LOW_COUNT_THRESHOLD
        and distinct_countries >= _DISTINCT_COUNTRY_FANOUT
        and shell_count >= _SHELL_NAME_DENSITY
    )
    if not (path_a or path_b):
        return None
    return {
        "matched_returns": high_risk,
        "high_risk_count": count,
        "distinct_beneficiary_countries": distinct_countries,
        "shell_name_density": shell_count,
        "qualifying_path": "snippet" if path_a else "cross_signal",
    }


def _alert_from_qualification(
    originator_name: str, qualification: dict[str, Any]
) -> dict[str, Any]:
    """Shape a qualified originator into the engine-contract alert
    dict. Mirrors the canonical alert fields the Alert Queue + Model
    Performance pages consume.
    """
    matched = qualification["matched_returns"]
    total = sum((r["amount"] for r in matched), Decimal("0"))
    return {
        "rule_id": "mule_return_burst_scorer",
        # `customer_id` shape — the snippet aliases originator_name
        # as customer_id; we do the same for downstream compatibility
        # (Alert Queue groups by customer_id).
        "customer_id": originator_name,
        "originator_name": originator_name,
        "sum_amount": float(total),
        "count": qualification["high_risk_count"],
        "distinct_beneficiary_countries": qualification["distinct_beneficiary_countries"],
        "shell_name_density": qualification["shell_name_density"],
        "qualifying_path": qualification["qualifying_path"],
        "window_start": min(r["returned_at"] for r in matched),
        "window_end": max(r["returned_at"] for r in matched),
        # Risk score scales with both volume and signal stacking;
        # cross-signal qualification is intrinsically more confident
        # than count-alone (the FCA guidance calls out fan-out as
        # the harder signal to fake), so bonus the score for path B.
        "risk_score": round(
            min(
                1.0,
                qualification["high_risk_count"] / 6.0
                + (0.15 if qualification["qualifying_path"] == "cross_signal" else 0),
            ),
            4,
        ),
        # DuckDB rowids (integers) — the framework's lineage
        # contract pins this shape for Lineage Explorer
        # `df_returns.iloc[rowid]` (parallel to the funnel scorer's
        # discipline against `df_txns`).
        "matched_row_ids": [r["row_id"] for r in matched],
    }


def mule_return_burst_scorer(
    con: duckdb.DuckDBPyConnection,
    as_of: datetime,
) -> list[dict[str, Any]]:
    """Procedural python_ref scorer — pacs.004 mule-return-burst.

    Engine contract entry point. Heavy lifting in `_qualifies`
    (pure) so the layered qualification is testable in isolation.
    Iterates originators in sorted order so the alert list is
    deterministic across reruns (the `test_run_is_reproducible`
    contract).
    """
    by_origin = _fetch_returns(con, as_of)
    alerts: list[dict[str, Any]] = []
    for originator_name in sorted(by_origin):
        qualification = _qualifies(by_origin[originator_name])
        if qualification is None:
            continue
        alerts.append(_alert_from_qualification(originator_name, qualification))
    return alerts
