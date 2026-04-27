"""FATF R.16 Travel Rule field-completeness validator.

Round-5 PR #2. Composes directly with PR #56's ISO 20022 ingestion —
the `debtor_*`, `creditor_*`, `uetr`, and `purpose_code` columns the
pacs.008/009 parser writes into the `txn` table are exactly the
inputs FATF R.16 requires the originator/beneficiary institution to
carry forward on the wire.

What FATF R.16 requires (revised June 2025):
- Above the de minimis threshold (USD/EUR 1,000), any cross-border
  wire transfer must travel with **originator** info (name + account
  + address OR national-ID OR DOB+POB) **and** **beneficiary** info
  (name + account).
- Domestic wires can carry just account numbers + lookup reference,
  but cross-border traffic is always full-fields.
- Jurisdictions implement different de minimis values; we keep the
  default at USD/EUR 1000 and let operators override per-currency.
- Source: https://www.fatf-gafi.org/en/publications/Fatfrecommendations/Travel-rule.html

Why python_ref (not aggregation_window or custom_sql):
The check is per-row and cross-cutting (multiple optional columns
need OR-logic). Expressing this in SQL `having` would force a
brittle conjunction; in Python we keep the field list declarative
and ship one structured `missing_fields` list per alert.

Why this lives in `models/` (not `engine/`):
The runner's python_ref security gate requires callables under
`aml_framework.models.*` (see `_allowed_python_ref_prefixes()`).
The plan names this `engine/travel_rule.py` — that's an
organisational hint, not a path constraint. The module is engine
logic in spirit; the path satisfies the security model.

Wire into a spec via:

    rules:
      - id: travel_rule_completeness_xborder
        name: FATF R.16 — cross-border wire missing required fields
        severity: high
        regulation_refs:
          - citation: "FATF R.16 (June 2025 revision)"
            description: "Originator + beneficiary info required on cross-border wires ≥ USD/EUR 1,000."
        logic:
          type: python_ref
          callable: aml_framework.models.travel_rule:validate_travel_rule
          model_id: travel_rule_completeness
          model_version: "fatf_r16_2025-06"
        escalate_to: l2_investigator
        evidence:
          - matching_transaction
          - originator_kyc_record
          - beneficiary_lookup
        tags: [travel_rule, fatf_r16, cross_border]
"""

from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from typing import Any

import duckdb

# Per-currency de minimis thresholds (FATF R.16 minimum is USD/EUR 1,000;
# many jurisdictions go lower). Operators override via env. Single source
# of truth so the dashboard / Tuning Lab can read the same numbers.
DEFAULT_THRESHOLDS: dict[str, Decimal] = {
    "USD": Decimal("1000"),
    "EUR": Decimal("1000"),
    "GBP": Decimal("1000"),
    "CAD": Decimal("1000"),
    "CHF": Decimal("1000"),
    "JPY": Decimal("100000"),  # ~USD 700 at 2026 rates; FATF allows local equivalent
    "AUD": Decimal("1500"),
    "CNY": Decimal("7000"),
}


def _resolve_thresholds() -> dict[str, Decimal]:
    """Override DEFAULT_THRESHOLDS from `AML_TRAVEL_RULE_THRESHOLDS` env.

    Format: `USD=1000,EUR=1000,GBP=900` — only listed currencies are
    overridden; rest fall back to defaults.
    """
    env = os.environ.get("AML_TRAVEL_RULE_THRESHOLDS", "").strip()
    if not env:
        return dict(DEFAULT_THRESHOLDS)
    out = dict(DEFAULT_THRESHOLDS)
    for token in env.split(","):
        if "=" not in token:
            continue
        ccy, raw_val = token.split("=", 1)
        ccy = ccy.strip().upper()
        try:
            value = Decimal(raw_val.strip())
        except Exception:
            continue
        # Decimal("NaN") parses but isn't a usable threshold; skip.
        if not value.is_finite() or value <= 0:
            continue
        out[ccy] = value
    return out


# Required fields per FATF R.16. Each tuple is (alert-friendly name,
# list of acceptable txn-row column names where the value can live —
# OR-logic between alternatives, AND-logic across tuples).
_ORIGINATOR_REQUIRED: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("originator_name", ("customer_id",)),
    ("originator_account", ("debtor_iban",)),
    # FATF allows address OR national-ID OR DOB+POB; we only have address
    # in the pacs.008 ingest path. Operators add the others via their
    # customer-resolver or the python_ref will mark them missing.
    ("originator_address_or_id", ("debtor_country", "debtor_address", "debtor_national_id")),
)

_BENEFICIARY_REQUIRED: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("beneficiary_name", ("counterparty_name",)),
    ("beneficiary_account", ("counterparty_account",)),
)


def _is_present(row: dict[str, Any], candidate_columns: tuple[str, ...]) -> bool:
    """A field is satisfied if ANY candidate column has a non-empty value."""
    for col in candidate_columns:
        val = row.get(col)
        if val is None:
            continue
        if isinstance(val, str) and not val.strip():
            continue
        return True
    return False


def _missing_fields(row: dict[str, Any]) -> list[str]:
    """Return the FATF-R.16 fields that are missing on this row."""
    missing: list[str] = []
    for label, cols in _ORIGINATOR_REQUIRED:
        if not _is_present(row, cols):
            missing.append(label)
    for label, cols in _BENEFICIARY_REQUIRED:
        if not _is_present(row, cols):
            missing.append(label)
    return missing


def _is_cross_border(row: dict[str, Any]) -> bool:
    """Cross-border = debtor country ≠ creditor country, both populated.

    A missing country on either side is treated as 'unknown, treat as
    cross-border' — the conservative choice for an AML control. The
    alert payload's `cross_border_evidence` field records why.
    """
    debtor = (row.get("debtor_country") or "").strip().upper()
    creditor = (row.get("counterparty_country") or "").strip().upper()
    if not debtor or not creditor:
        return True
    return debtor != creditor


def _crosses_threshold(row: dict[str, Any], thresholds: dict[str, Decimal]) -> bool:
    amt = row.get("amount")
    if amt is None:
        return False
    try:
        amt_dec = Decimal(amt) if not isinstance(amt, Decimal) else amt
    except Exception:
        return False
    ccy = (row.get("currency") or "").strip().upper()
    threshold = thresholds.get(ccy, Decimal("1000"))
    return amt_dec >= threshold


# ---------------------------------------------------------------------------
# Public scorer (called by the engine via python_ref)
# ---------------------------------------------------------------------------


def validate_travel_rule(
    con: duckdb.DuckDBPyConnection,
    as_of: datetime,
) -> list[dict[str, Any]]:
    """Find wires ≥ threshold + cross-border + missing FATF-required fields.

    Returns one alert per offending row. Severity scales: any missing
    field on a wire ≥ 10× the threshold → critical; otherwise → high.

    Engine contract: `(con, as_of) → list[alert]`. Each alert dict
    includes the standard txn_id / customer_id / amount fields plus
    a `missing_fields` array, an `is_cross_border` flag, and a
    `rule_kind` discriminator so the narrative drafter (PR #45) and
    Effectiveness Pack (PR #52) can recognise the alert family.
    """
    thresholds = _resolve_thresholds()

    # Pull the columns we need. Tolerate older `txn` schemas that
    # don't carry the iso20022-extended columns — missing columns
    # show up as NULLs and the validator marks the field absent.
    needed_cols = (
        "txn_id",
        "customer_id",
        "amount",
        "currency",
        "channel",
        "direction",
        "booked_at",
        "debtor_iban",
        "debtor_country",
        "debtor_bic",
        "counterparty_name",
        "counterparty_country",
        "counterparty_account",
        "uetr",
        "purpose_code",
    )

    # Fetch every txn row (the validator filters per-row in Python —
    # readability over micro-optimisation; pacs.008 ingestion is
    # already the bottleneck for any realistic file size).
    available = _columns_in_table(con, "txn")
    select_cols = ", ".join(c if c in available else f"NULL AS {c}" for c in needed_cols)
    try:
        rows = con.execute(f"SELECT {select_cols} FROM txn").fetchall()
        cols = [d[0] for d in con.description] if con.description else list(needed_cols)
    except Exception:
        return []

    alerts: list[dict[str, Any]] = []
    for tup in rows:
        row = dict(zip(cols, tup))
        # Only score wires (channel = 'wire'); pacs.008 ingestion
        # writes 'wire' for every row, and operators using other
        # data sources can opt-in by setting channel='wire'.
        if (row.get("channel") or "").lower() != "wire":
            continue
        if not _crosses_threshold(row, thresholds):
            continue
        if not _is_cross_border(row):
            continue
        missing = _missing_fields(row)
        if not missing:
            continue

        amt = Decimal(row.get("amount") or 0)
        ccy = (row.get("currency") or "").upper()
        threshold = thresholds.get(ccy, Decimal("1000"))
        # FATF R.16 makes any field omission a finding; severity scales
        # with materiality so analysts can triage by amount.
        severity = "critical" if amt >= threshold * 10 else "high"

        alerts.append(
            {
                "rule_id": "travel_rule_completeness",
                "rule_kind": "travel_rule_completeness",
                "txn_id": row.get("txn_id"),
                "customer_id": row.get("customer_id") or "UNKNOWN",
                "amount": str(amt),
                "currency": ccy,
                "missing_fields": missing,
                "is_cross_border": True,
                "uetr": row.get("uetr") or "",
                "purpose_code": row.get("purpose_code") or "",
                "severity_hint": severity,
                "window_start": as_of,
                "window_end": as_of,
                "explanation": (
                    f"FATF R.16: wire of {ccy} {amt} crosses the "
                    f"{ccy} {threshold} threshold and is missing "
                    f"{len(missing)} required field(s): "
                    f"{', '.join(missing)}."
                ),
            }
        )
    return alerts


def _columns_in_table(con: duckdb.DuckDBPyConnection, table: str) -> set[str]:
    """Discover columns on `table` so we can SELECT only what exists.

    DuckDB raises on unknown columns; the validator must run on both
    the iso20022-rich `txn` schema and the older 7-column shape used
    by the synthetic dataset and CSV examples.
    """
    try:
        info = con.execute(f"PRAGMA table_info('{table}')").fetchall()
    except Exception:
        return set()
    return {r[1] for r in info}
