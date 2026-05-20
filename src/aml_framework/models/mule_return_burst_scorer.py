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

The alert dict carries `matched_return_ids` (the pacs.004 natural
identifier strings, NOT the framework's lineage-keyed
`matched_row_ids`). Existing Lineage Explorer / Audit Evidence
pages treat `matched_row_ids` as indexes into `df_txns`; emitting
`txn_return` rowids under that name would walk back to unrelated
transaction rows. The `return_id` strings give reviewers a
queryable identifier without mis-rendering.

`customer_id` on the alert is resolved by joining
`originator_name` against `customer.full_name` so downstream
Customer 360 / case KYC lookups land on the right entity (e.g.
"ROAMR LTD" → C0011 for the planted positive). Falls back to the
originator name when no customer match exists (BYOD-friendly).
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


_REQUIRED_COLUMNS = frozenset(
    {
        "return_id",
        "originator_name",
        "reason_code",
        "beneficiary_name",
        "beneficiary_country",
        "amount",
        "returned_at",
    }
)


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
    sending PSP's internal customer id; the snippet does the same
    (alert customer_id is resolved downstream via
    `_resolve_customer_id`).

    Empty-contract guard: when `txn_return` exists in the spec but
    has zero rows, `_build_warehouse` creates a placeholder
    `SELECT NULL WHERE 1=0` table with no columns. A SELECT against
    the named columns then raises a DuckDB binder error and the
    strict python_ref runner aborts the whole run (Codex P1 round
    1). Probe `information_schema.columns` first; if the required
    columns aren't present, return empty — the scorer is correctly
    silent on a no-returns dataset rather than crashing.
    """
    present = {
        name
        for (name,) in con.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'txn_return'
            """
        ).fetchall()
    }
    if not _REQUIRED_COLUMNS.issubset(present):
        return {}
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


def _path_safe(value: str) -> str:
    """Replace filesystem-unsafe characters in a fallback id.

    `cases/aggregator.py:_build_case()` embeds `alert.customer_id`
    in the case filename; it only strips spaces/colons. A raw
    originator name containing `/` (e.g. "ACME/UK LTD" — common in
    BYOD/CSV pacs.004 feeds) would make `record_case()` try to
    write `cases/mule_return_burst_scorer__ACME/UK LTD.json` —
    `ACME/` is treated as a sub-directory that doesn't exist and
    the run aborts (Codex P2 round 2). Replace `/`, `\\`, NUL,
    `..` with `_`. Keep the original name visible via the alert's
    separate `originator_name` field.
    """
    if not value:
        return "unknown"
    out = value
    for ch in ("/", "\\", "\x00"):
        out = out.replace(ch, "_")
    out = out.replace("..", "__")
    return out


def _resolve_customer_id(con: duckdb.DuckDBPyConnection, originator_name: str) -> str:
    """Look up the customer's internal `customer_id` by joining
    `originator_name` against `customer.full_name`. Falls back to
    a PATH-SAFE form of the originator name when no match —
    graceful for BYOD scenarios where the customer table doesn't
    carry every counterparty AND safe for the case-file writer
    downstream (Codex P2 round 2).

    Why customer_id resolution matters in the first place:
    downstream pages (Customer 360, case profile, Audit Evidence)
    join on `alert.customer_id == customer.customer_id`. If we
    stamp `customer_id = "ROAMR LTD"` but the customer table has
    `customer_id = "C0011"`, the KYC lookup says "not found" even
    though the case requests `originator_kyc_profile` as
    evidence (Codex P2 round 1).
    """
    try:
        row = con.execute(
            """
            SELECT customer_id FROM customer
            WHERE full_name = ?
            LIMIT 1
            """,
            [originator_name],
        ).fetchone()
    except duckdb.Error:
        # customer table may not exist in tests or in non-canonical
        # BYOD shapes — fall back to a path-safe form of the name.
        return _path_safe(originator_name)
    if row and row[0]:
        return str(row[0])
    return _path_safe(originator_name)


def _alert_from_qualification(
    customer_id: str, originator_name: str, qualification: dict[str, Any]
) -> dict[str, Any]:
    """Shape a qualified originator into the engine-contract alert
    dict. Mirrors the canonical alert fields the Alert Queue + Model
    Performance pages consume.
    """
    matched = qualification["matched_returns"]
    total = sum((r["amount"] for r in matched), Decimal("0"))
    return {
        "rule_id": "mule_return_burst_scorer",
        # `customer_id` is the resolved internal id (joined from
        # `customer.full_name = originator_name`) so the Alert Queue
        # / Customer 360 / Audit Evidence joins work. Falls back to
        # originator_name if no customer match (Codex P2 round 1).
        "customer_id": customer_id,
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
        # `matched_return_ids` (NOT `matched_row_ids`) — the
        # framework's existing `matched_row_ids` lineage contract
        # indexes into `df_txns` per Lineage Explorer; emitting
        # rowids from a different table (`txn_return`) under that
        # name would walk back to UNRELATED txn rows and mislead
        # reviewers (Codex P1 round 1). Use the `return_id` strings
        # instead — they're the natural pacs.004 identifier and the
        # evidence drill-down can show them as-is.
        "matched_return_ids": [r["return_id"] for r in matched],
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
        customer_id = _resolve_customer_id(con, originator_name)
        alerts.append(_alert_from_qualification(customer_id, originator_name, qualification))
    return alerts
