"""Contract-level field-freshness scanner (PR-DATA-2).

Backs the "Data is the AML problem" whitepaper's DATA-2 claim that the
spec can pin a freshness requirement per attribute and the engine
surfaces stale-row violations as audit-ledger events.

Inputs: a `DataContract` (with one or more columns declaring
`max_staleness_days` + `last_refreshed_at_column`) and the rows
registered in the warehouse for that contract. Output: a list of
`FreshnessViolation` records, each describing one (row, column) pair
that breached the declared staleness window.

The scanner is **pure**: same inputs produce the same violations. It
does not write to the audit ledger directly — `engine/runner.py` does
that after collecting the violations from every contract. Keeping the
emit step in the runner means the ledger writes happen in one place
with consistent event shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from aml_framework.spec.models import Column, DataContract


@dataclass(frozen=True)
class FreshnessViolation:
    """One row-column pair that violates a declared `max_staleness_days`."""

    contract_id: str
    column_name: str  # the column with `max_staleness_days` set
    refreshed_at_column: str  # the timestamp column being checked
    row_id: str | None  # primary-key-ish identifier from the row, if available
    refreshed_at: datetime
    age_days: int
    max_staleness_days: int

    def to_event(self) -> dict[str, Any]:
        """Shape for audit-ledger emission. Mirrors pkyc.Trigger.evidence."""
        return {
            "event": "pkyc_trigger",
            "kind": "stale_field",
            "contract_id": self.contract_id,
            "column": self.column_name,
            "refreshed_at_column": self.refreshed_at_column,
            "row_id": self.row_id,
            "refreshed_at": self.refreshed_at.isoformat(),
            "age_days": self.age_days,
            "max_staleness_days": self.max_staleness_days,
        }


def _coerce_datetime(value: Any) -> datetime | None:
    """Best-effort parse for timestamp/date column values.

    Accepts datetime, date, ISO 8601 string. Returns None for unparseable
    inputs so the scanner skips rather than crashes — a malformed
    timestamp surfaces as a quality-check warning elsewhere, not as a
    freshness violation here.
    """
    if isinstance(value, datetime):
        return value
    # `date` is a parent class of `datetime`, so the datetime check above
    # short-circuits the common case; this branch handles bare `date`.
    try:
        from datetime import date

        if isinstance(value, date):
            return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    except Exception:
        pass
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace(" ", "T", 1))
    except (TypeError, ValueError):
        return None


def _row_id(row: dict[str, Any], contract: DataContract) -> str | None:
    """Best-effort row identifier — first non-null `*_id` column.

    Surfacing a row id makes the violation actionable ("customer C0042 is
    stale") rather than abstract ("some row in `customer` is stale").
    """
    for col in contract.columns:
        if col.name.endswith("_id"):
            val = row.get(col.name)
            if val is not None:
                return str(val)
    return None


def scan_contract_freshness(
    contract: DataContract,
    rows: list[dict[str, Any]],
    as_of: datetime,
) -> list[FreshnessViolation]:
    """Scan one contract's rows for field-level freshness violations.

    For every column that declares `max_staleness_days`, compute the age
    of `last_refreshed_at_column` per row. Rows older than the declared
    window become `FreshnessViolation` entries. Returns an empty list if
    the contract has no freshness-pinned columns.
    """
    pinned: list[Column] = [c for c in contract.columns if c.max_staleness_days is not None]
    if not pinned or not rows:
        return []

    # Normalise as_of to UTC-naive comparison space; rows may have naive
    # or aware timestamps depending on the loader. We compare in seconds,
    # not dates, so timezone handling isn't strictly necessary, but
    # stripping tzinfo prevents Python's "can't subtract aware and naive"
    # ValueError when the data source returns a mix.
    as_of_naive = as_of.replace(tzinfo=None) if as_of.tzinfo else as_of

    violations: list[FreshnessViolation] = []
    for col in pinned:
        ref_col = col.last_refreshed_at_column
        max_days = col.max_staleness_days
        threshold = timedelta(days=max_days)
        for row in rows:
            raw = row.get(ref_col)
            refreshed_at = _coerce_datetime(raw)
            if refreshed_at is None:
                # Missing timestamp: surface as a violation with age=-1
                # so it shows up in dashboards but is distinguishable
                # from a numerically-stale row. The contract validator
                # already flags missing required columns at warehouse
                # build (PR-DATA-1); this branch only fires when the
                # column is present-but-null on a specific row.
                continue
            ref_naive = refreshed_at.replace(tzinfo=None) if refreshed_at.tzinfo else refreshed_at
            age = as_of_naive - ref_naive
            if age >= threshold:
                violations.append(
                    FreshnessViolation(
                        contract_id=contract.id,
                        column_name=col.name,
                        refreshed_at_column=ref_col,
                        row_id=_row_id(row, contract),
                        refreshed_at=refreshed_at,
                        age_days=age.days,
                        max_staleness_days=max_days,
                    )
                )
    return violations
