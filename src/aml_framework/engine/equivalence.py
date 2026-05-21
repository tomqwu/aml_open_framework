"""Legacy↔new alert equivalence classifier (PR-EQ-2 / TM Gap 1 step 2).

Bank-side parallel-run divergence engine. Given the alert output of the
new framework and a CSV/Parquet export from the legacy TM system,
classify every (customer, period) cell into one of four classes:

* ``MATCH``       — both systems alerted on the same cell, same rule mapping.
* ``NEW_ONLY``    — the new framework alerted; legacy did not.
* ``LEGACY_ONLY`` — legacy alerted; the new framework did not.
* ``DIFF``        — both alerted but the severity differs.

This is the hard requirement under SR 11-7 and OSFI E-23 for replacing
an established TM system: the operator must show, for every cell where
the systems disagree, *why* — data, rule logic, mapping, or intentional
scope change. PR-EQ-2 produces the cell-level classification; PR-EQ-3
will surface it on the dashboard with the explanatory drill-downs.

Design rules:

* **Pure / deterministic.** ``classify_alerts`` has no I/O, no clock
  reads, no random state. Same inputs → identical ``EquivalenceReport``
  (modulo ``generated_at`` which the caller supplies for determinism).
* **No engine/runner.py changes.** This module is a post-hoc analyzer
  over the runner's alert output — not part of the per-run pipeline.
  The runner stays oblivious to ``program.legacy_reference``; the
  ``test_legacy_reference_does_not_break_determinism_contract`` test
  pinned in PR-EQ-1 still holds.
* **Stdlib + pydantic only.** No pandas, no duckdb, no new deps.
* **Cell key** = ``(customer_id, period_start, period_end, rule_id_new)``
  on the new side and ``(customer_id, period_start, period_end,
  rule_id_legacy)`` on the legacy side, joined via the operator-supplied
  ``rule_map`` (new_rule_id → legacy_rule_id).

PR-EQ-3 will add a CLI wrapper and dashboard page on top of this module.
"""

from __future__ import annotations

import csv
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EquivalenceClass(str, Enum):
    """Four-way classification for a single (customer, period, rule) cell."""

    MATCH = "MATCH"
    NEW_ONLY = "NEW_ONLY"
    LEGACY_ONLY = "LEGACY_ONLY"
    DIFF = "DIFF"


class LegacyAlert(_Base):
    """One alert as exported from the legacy TM system.

    The shape matches the columns the operator declares in
    ``program.legacy_reference.key_columns`` plus optional metadata.
    ``payload`` carries any additional columns from the export verbatim
    so dashboard drill-downs can show the legacy evidence without the
    engine modelling every legacy schema.
    """

    customer_id: str = Field(min_length=1)
    period_start: datetime
    period_end: datetime
    rule_id_legacy: str = Field(min_length=1)
    severity: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class EquivalenceCell(_Base):
    """One classified (customer, period, rule) cell."""

    customer_id: str
    period_start: datetime
    period_end: datetime
    # New-side rule_id may be None when this cell is LEGACY_ONLY and the
    # legacy rule isn't in the operator's rule_map.
    rule_id_new: str | None
    # Legacy-side rule_id may be None when this cell is NEW_ONLY and the
    # operator's rule_map doesn't carry that new rule.
    rule_id_legacy: str | None
    classification: EquivalenceClass
    new_severity: str | None = None
    legacy_severity: str | None = None
    # Human-readable explanation for DIFF cells (e.g. "severity mismatch:
    # new=high legacy=medium"). None for MATCH / NEW_ONLY / LEGACY_ONLY.
    diff_reason: str | None = None


class EquivalenceReport(_Base):
    """Cell-level classification plus per-class and per-rule rollups."""

    cells: list[EquivalenceCell]
    counts: dict[EquivalenceClass, int]
    # by_rule keyed by the *new* rule_id when available, else the legacy
    # rule_id prefixed with ``legacy:`` so unmapped-legacy rules stay
    # visible in the rollup without colliding with new rule ids.
    by_rule: dict[str, dict[EquivalenceClass, int]]
    generated_at: datetime


def _coerce_datetime(value: Any) -> datetime:
    """Parse a datetime from a string or pass through if already a datetime.

    Accepts ISO 8601 strings (with or without ``Z`` suffix); raises
    ``ValueError`` on anything else so the caller's CSV cannot silently
    inject malformed periods.
    """
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            raise ValueError("empty datetime string")
        # Tolerate the trailing-Z form some tools emit.
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    raise ValueError(f"cannot coerce {type(value).__name__} to datetime")


def _cell_key(
    customer_id: str,
    period_start: datetime,
    period_end: datetime,
    rule_id: str,
) -> tuple[str, str, str, str]:
    """Canonical hashable key for cell lookup.

    ISO-8601 isoformat for periods so the tuple stays sortable and
    deterministic regardless of timezone object identity.
    """
    return (customer_id, period_start.isoformat(), period_end.isoformat(), rule_id)


def classify_alerts(
    new_alerts: list[dict[str, Any]],
    legacy_alerts: list[LegacyAlert],
    *,
    rule_map: dict[str, str],
    generated_at: datetime | None = None,
) -> EquivalenceReport:
    """Classify every cell across the two alert sets.

    Parameters
    ----------
    new_alerts:
        Alert dicts as emitted by ``engine/runner.py`` — must carry
        ``customer_id``, ``window_start``, ``window_end``, ``rule_id``,
        and optionally ``severity``.
    legacy_alerts:
        ``LegacyAlert`` records loaded via ``load_legacy_alerts_csv`` (or
        any other format-specific loader).
    rule_map:
        New-framework ``rule_id`` → legacy ``rule_id`` mapping. Usually
        taken from ``spec.program.legacy_reference.rule_map`` but the
        caller may override (e.g. when iterating mappings).
    generated_at:
        Caller-supplied timestamp so the report stays deterministic for
        equivalence-of-equivalence tests. Defaults to a fixed sentinel
        (``datetime.min``) when omitted to keep this function I/O-free
        and clock-independent.

    Returns
    -------
    EquivalenceReport
        Cells sorted by ``(customer_id, period_start, period_end,
        rule_id_new or rule_id_legacy)`` so the output stream is stable
        for diffing across runs.
    """
    if generated_at is None:
        generated_at = datetime.min

    # Forward map (new → legacy) — local copy so the caller's dict can't
    # mutate mid-classification. The join key on the new side is the
    # *legacy* rule_id, because that's what makes the cross-system cell
    # alignable.
    legacy_for_new: dict[str, str] = dict(rule_map)

    # Reverse map: legacy rule_id → new rule_id (when the operator
    # declared a 1:1 mapping). When the same legacy id maps from
    # multiple new ids, last-write-wins on the reverse — that's an
    # operator-declared ambiguity we surface in the report by leaving
    # the unmatched cells as LEGACY_ONLY rather than guessing.
    new_for_legacy: dict[str, str] = {}
    for new_id, legacy_id in rule_map.items():
        new_for_legacy[legacy_id] = new_id

    # Build the new-side index keyed by (customer, period, legacy_rule).
    # Cells whose new rule_id isn't in the map are kept under a synthetic
    # key so they still classify (as NEW_ONLY when no legacy match).
    new_index: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    unmapped_new: list[dict[str, Any]] = []
    for alert in new_alerts:
        rule_id_new = str(alert.get("rule_id", ""))
        if not rule_id_new:
            continue
        customer_id = str(alert.get("customer_id", ""))
        period_start = _coerce_datetime(alert["window_start"])
        period_end = _coerce_datetime(alert["window_end"])
        mapped_legacy = legacy_for_new.get(rule_id_new)
        if mapped_legacy is None:
            unmapped_new.append(alert)
            continue
        key = _cell_key(customer_id, period_start, period_end, mapped_legacy)
        new_index[key] = alert

    # Walk the legacy side and classify each cell.
    cells: list[EquivalenceCell] = []
    consumed_new_keys: set[tuple[str, str, str, str]] = set()

    for legacy in legacy_alerts:
        key = _cell_key(
            legacy.customer_id,
            legacy.period_start,
            legacy.period_end,
            legacy.rule_id_legacy,
        )
        mapped_new = new_for_legacy.get(legacy.rule_id_legacy)
        new_alert = new_index.get(key)
        if new_alert is None:
            cells.append(
                EquivalenceCell(
                    customer_id=legacy.customer_id,
                    period_start=legacy.period_start,
                    period_end=legacy.period_end,
                    rule_id_new=mapped_new,
                    rule_id_legacy=legacy.rule_id_legacy,
                    classification=EquivalenceClass.LEGACY_ONLY,
                    new_severity=None,
                    legacy_severity=legacy.severity,
                    diff_reason=None,
                )
            )
            continue

        consumed_new_keys.add(key)
        new_sev = _coerce_optional_str(new_alert.get("severity"))
        if new_sev is not None and legacy.severity is not None and new_sev != legacy.severity:
            cells.append(
                EquivalenceCell(
                    customer_id=legacy.customer_id,
                    period_start=legacy.period_start,
                    period_end=legacy.period_end,
                    rule_id_new=str(new_alert["rule_id"]),
                    rule_id_legacy=legacy.rule_id_legacy,
                    classification=EquivalenceClass.DIFF,
                    new_severity=new_sev,
                    legacy_severity=legacy.severity,
                    diff_reason=f"severity mismatch: new={new_sev} legacy={legacy.severity}",
                )
            )
        else:
            cells.append(
                EquivalenceCell(
                    customer_id=legacy.customer_id,
                    period_start=legacy.period_start,
                    period_end=legacy.period_end,
                    rule_id_new=str(new_alert["rule_id"]),
                    rule_id_legacy=legacy.rule_id_legacy,
                    classification=EquivalenceClass.MATCH,
                    new_severity=new_sev,
                    legacy_severity=legacy.severity,
                    diff_reason=None,
                )
            )

    # Anything in the new index not consumed above is NEW_ONLY.
    for key, alert in new_index.items():
        if key in consumed_new_keys:
            continue
        cells.append(
            EquivalenceCell(
                customer_id=str(alert.get("customer_id", "")),
                period_start=_coerce_datetime(alert["window_start"]),
                period_end=_coerce_datetime(alert["window_end"]),
                rule_id_new=str(alert["rule_id"]),
                rule_id_legacy=legacy_for_new.get(str(alert["rule_id"])),
                classification=EquivalenceClass.NEW_ONLY,
                new_severity=_coerce_optional_str(alert.get("severity")),
                legacy_severity=None,
                diff_reason=None,
            )
        )

    # Unmapped-new alerts (no entry in rule_map) classify as NEW_ONLY
    # with rule_id_legacy=None so the rollup tells the operator which
    # new rules they still need to map. Distinct path from the mapped
    # NEW_ONLY branch above because we never had a join key to consume.
    for alert in unmapped_new:
        cells.append(
            EquivalenceCell(
                customer_id=str(alert.get("customer_id", "")),
                period_start=_coerce_datetime(alert["window_start"]),
                period_end=_coerce_datetime(alert["window_end"]),
                rule_id_new=str(alert["rule_id"]),
                rule_id_legacy=None,
                classification=EquivalenceClass.NEW_ONLY,
                new_severity=_coerce_optional_str(alert.get("severity")),
                legacy_severity=None,
                diff_reason=None,
            )
        )

    # Deterministic ordering: by customer, then period, then rule_id.
    cells.sort(
        key=lambda c: (
            c.customer_id,
            c.period_start.isoformat(),
            c.period_end.isoformat(),
            c.rule_id_new or "",
            c.rule_id_legacy or "",
        )
    )

    # Counts: every class always present in the dict (zero when absent)
    # so dashboard code doesn't need to defensively `.get(cls, 0)`.
    counts: dict[EquivalenceClass, int] = {cls: 0 for cls in EquivalenceClass}
    by_rule: dict[str, dict[EquivalenceClass, int]] = {}
    for cell in cells:
        counts[cell.classification] += 1
        # Roll up under the new rule_id when available, else under a
        # ``legacy:<id>`` synthetic key so unmapped legacy rules stay
        # visible without colliding with new rule_ids.
        rollup_key = cell.rule_id_new or f"legacy:{cell.rule_id_legacy}"
        bucket = by_rule.setdefault(rollup_key, {cls: 0 for cls in EquivalenceClass})
        bucket[cell.classification] += 1

    return EquivalenceReport(
        cells=cells,
        counts=counts,
        by_rule=by_rule,
        generated_at=generated_at,
    )


def _coerce_optional_str(value: Any) -> str | None:
    """Return a stripped str or None — empty strings normalize to None."""
    if value is None:
        return None
    s = str(value).strip()
    return s or None


# CSV column names the loader recognizes. Operators wire up their export
# to match these names (or pre-rename in the legacy system); keeping the
# loader strict avoids silent miscounts when an unexpected column
# replaces an expected one. ``key_columns`` from ``LegacyReference``
# tells the dashboard which subset to surface as the join key; the
# loader itself always reads the full set.
_REQUIRED_CSV_COLUMNS: tuple[str, ...] = (
    "customer_id",
    "period_start",
    "period_end",
    "rule_id_legacy",
)
_OPTIONAL_CSV_COLUMNS: tuple[str, ...] = ("severity",)


def load_legacy_alerts_csv(path: Path) -> list[LegacyAlert]:
    """Read a legacy-alert export from CSV.

    Required columns: ``customer_id``, ``period_start``, ``period_end``,
    ``rule_id_legacy``. Optional column: ``severity``. Any additional
    columns are preserved verbatim in ``LegacyAlert.payload`` so
    dashboard drill-downs can show the legacy evidence without the
    engine modelling every legacy schema.

    Stdlib ``csv`` only — no pandas/duckdb, matching PR-EQ-2's
    no-new-dependencies constraint.
    """
    rows: list[LegacyAlert] = []
    with Path(path).open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return rows
        missing = [c for c in _REQUIRED_CSV_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(
                f"legacy alert CSV {path} missing required column(s): {sorted(missing)}"
            )
        for raw in reader:
            payload = {
                k: v
                for k, v in raw.items()
                if k not in _REQUIRED_CSV_COLUMNS
                and k not in _OPTIONAL_CSV_COLUMNS
                and k is not None
            }
            rows.append(
                LegacyAlert(
                    customer_id=raw["customer_id"],
                    period_start=_coerce_datetime(raw["period_start"]),
                    period_end=_coerce_datetime(raw["period_end"]),
                    rule_id_legacy=raw["rule_id_legacy"],
                    severity=_coerce_optional_str(raw.get("severity")),
                    payload=payload,
                )
            )
    return rows
