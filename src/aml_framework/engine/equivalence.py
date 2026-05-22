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
from datetime import datetime, timezone
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


def _to_naive_utc(dt: datetime) -> datetime:
    """Normalize a datetime to naive UTC for cell-key equality.

    The runner emits naive UTC datetimes; CSV exports often carry the
    trailing ``Z`` form which `_coerce_datetime` parses to a
    UTC-aware datetime. Without normalization, identical (customer,
    period, rule) cells would key as different strings (``+00:00`` vs
    no offset) and split into NEW_ONLY + LEGACY_ONLY instead of
    MATCH. Codex pass 3 — closes timezone-format misclassification.
    """
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _cell_key(
    customer_id: str,
    period_start: datetime,
    period_end: datetime,
    rule_id: str,
) -> tuple[str, str, str, str]:
    """Canonical hashable key for cell lookup.

    Periods are normalized to naive UTC before isoformat so two
    spellings of the same instant key identically.
    """
    return (
        customer_id,
        _to_naive_utc(period_start).isoformat(),
        _to_naive_utc(period_end).isoformat(),
        rule_id,
    )


def _flatten_new_alerts(
    new_alerts: list[dict[str, Any]] | dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Accept either a flat alert list or `RunResult.alerts`-style
    ``dict[rule_id, list[alert]]`` mapping.

    The runner emits alerts as a per-rule mapping. Callers that want
    to compare a run against a legacy export would otherwise have to
    flatten manually — easy to forget, and an oversight would iterate
    rule-id strings and crash inside the classifier. Codex pass 4 —
    accept both shapes at the boundary.

    When the value is already a flat list, returns it unchanged.
    When it's a mapping, injects ``rule_id=<key>`` into each alert
    only if the alert dict doesn't already carry that field so the
    classifier's key extraction works.
    """
    if isinstance(new_alerts, dict):
        flat: list[dict[str, Any]] = []
        for rule_id, alerts in sorted(new_alerts.items()):
            for alert in alerts:
                # The outer dict KEY is authoritative — overwrite any
                # `rule_id` the payload happens to carry (custom_sql /
                # python_ref alerts may emit a source/sub-rule id that
                # differs from the spec rule that owns the bucket).
                # Codex pass 6 — don't trust the payload.
                flat.append({**alert, "rule_id": rule_id})
        return flat
    return list(new_alerts)


def classify_alerts(
    new_alerts: list[dict[str, Any]] | dict[str, list[dict[str, Any]]],
    legacy_alerts: list[LegacyAlert],
    *,
    rule_map: dict[str, str],
    rule_severities: dict[str, str] | None = None,
    generated_at: datetime | None = None,
) -> EquivalenceReport:
    """Classify every cell across the two alert sets.

    Parameters
    ----------
    new_alerts:
        Alert dicts as emitted by ``engine/runner.py``. Must carry
        ``customer_id``, ``window_start``, ``window_end``, ``rule_id``.
        ``severity`` may be absent — the runner stores it on the
        ``Rule`` spec / case, not the alert dict — so callers should
        usually pass ``rule_severities=`` so the classifier can derive
        per-cell severity for DIFF detection.
    legacy_alerts:
        ``LegacyAlert`` records loaded via ``load_legacy_alerts_csv`` (or
        any other format-specific loader).
    rule_map:
        New-framework ``rule_id`` → legacy ``rule_id`` mapping. Usually
        taken from ``spec.program.legacy_reference.rule_map`` but the
        caller may override (e.g. when iterating mappings).
    rule_severities:
        Optional new ``rule_id`` → severity string mapping
        (``{r.id: r.severity for r in spec.rules}``). When ``severity``
        is missing from an alert payload, the classifier falls back to
        this map so legacy-vs-new severity comparisons still produce
        DIFF rather than silently degrading to MATCH. Without this
        argument, severity-diff detection is best-effort against
        whatever the alert dict happens to carry.
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
    rule_severities = dict(rule_severities or {})
    if generated_at is None:
        generated_at = datetime.min

    # Forward map (new → legacy) — local copy so the caller's dict can't
    # mutate mid-classification. The join key on the new side is the
    # *legacy* rule_id, because that's what makes the cross-system cell
    # alignable.
    legacy_for_new: dict[str, str] = dict(rule_map)

    # Reverse map: legacy rule_id → set of new rule_ids. Many new
    # rules can declare the same legacy mapping (operator-declared
    # many-to-one consolidation). When that legacy rule fires LEGACY_ONLY
    # we must not arbitrarily pick one of the candidates — leave
    # `rule_id_new=None` so the report doesn't blame the wrong rule
    # and the by_rule rollup buckets under `legacy:<id>`.
    new_for_legacy_set: dict[str, set[str]] = {}
    for new_id, legacy_id in rule_map.items():
        new_for_legacy_set.setdefault(legacy_id, set()).add(new_id)

    def _legacy_only_attribution(legacy_id: str) -> str | None:
        candidates = new_for_legacy_set.get(legacy_id, set())
        if len(candidates) == 1:
            return next(iter(candidates))
        # 0 candidates → unmapped legacy rule. >1 candidates →
        # ambiguous many-to-one; report unattributed.
        return None

    # Build the new-side index keyed by (customer, period, legacy_rule).
    # Use a list value so multiple new rules mapping to the same legacy
    # rule (operator-declared many-to-one) don't clobber each other —
    # otherwise the second alert would silently disappear and the cell
    # count under-reports.
    new_index: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    unmapped_new: list[dict[str, Any]] = []
    flat_new_alerts = _flatten_new_alerts(new_alerts)
    # Dedupe new alerts by their *new-side* cell key (customer, period,
    # rule_id_new) before indexing, mirroring the legacy-side dedupe.
    # The report is cell-level by contract; duplicate emissions from a
    # custom_sql join would otherwise inflate NEW_ONLY counts after the
    # legacy side has been deduped to one row per cell.
    # Codex pass 6 — closes new-side duplicate over-counting.
    seen_new_keys: set[tuple[str, str, str, str]] = set()
    for alert in flat_new_alerts:
        rule_id_new = str(alert.get("rule_id", ""))
        if not rule_id_new:
            # Fail loudly rather than silently dropping a malformed
            # alert — a missing rule_id would otherwise turn a real
            # MATCH/NEW_ONLY into a false LEGACY_ONLY count and
            # silently break the parallel-run report. Codex pass 8.
            raise ValueError(f"new alert missing required `rule_id` field: {alert!r}")
        customer_id_raw = alert.get("customer_id")
        if customer_id_raw is None or str(customer_id_raw).strip() == "":
            # Same rationale as rule_id above: a missing customer_id
            # would coerce to a blank cell key and silently produce
            # a spurious NEW_ONLY against any real legacy alert.
            # Codex pass 9.
            raise ValueError(f"new alert missing required `customer_id` field: {alert!r}")
        customer_id = str(customer_id_raw)
        period_start = _coerce_datetime(alert["window_start"])
        period_end = _coerce_datetime(alert["window_end"])
        new_cell_key = _cell_key(customer_id, period_start, period_end, rule_id_new)
        if new_cell_key in seen_new_keys:
            continue
        seen_new_keys.add(new_cell_key)
        mapped_legacy = legacy_for_new.get(rule_id_new)
        if mapped_legacy is None:
            unmapped_new.append(alert)
            continue
        key = _cell_key(customer_id, period_start, period_end, mapped_legacy)
        new_index.setdefault(key, []).append(alert)

    def _resolve_new_severity(alert: dict[str, Any]) -> str | None:
        """Severity for a new alert: prefer the payload, fall back to
        the spec via `rule_severities`. Without the fallback, runner
        alerts (which don't inject severity onto the dict) would
        compare as None vs a legacy `high` and silently degrade to
        MATCH instead of DIFF. See codex review pass 1 on PR-EQ-2."""
        from_payload = _coerce_optional_str(alert.get("severity"))
        if from_payload is not None:
            return from_payload
        return rule_severities.get(str(alert.get("rule_id", ""))) or None

    # Deduplicate legacy alerts to one row per (customer, period,
    # rule_id_legacy) cell — this report is cell-level by contract,
    # so duplicate legacy rows for the same cell must not consume
    # multiple new alerts and produce spurious LEGACY_ONLY tallies.
    # Codex pass 5 — preserves the first occurrence's severity +
    # payload so deterministic ordering survives dedupe.
    deduped_legacy: list[LegacyAlert] = []
    seen_legacy_keys: set[tuple[str, str, str, str]] = set()
    for legacy in legacy_alerts:
        key = _cell_key(
            legacy.customer_id,
            legacy.period_start,
            legacy.period_end,
            legacy.rule_id_legacy,
        )
        if key in seen_legacy_keys:
            continue
        seen_legacy_keys.add(key)
        deduped_legacy.append(legacy)

    # Walk the legacy side and classify each cell.
    cells: list[EquivalenceCell] = []
    consumed_alert_ids: set[int] = set()

    for legacy in deduped_legacy:
        key = _cell_key(
            legacy.customer_id,
            legacy.period_start,
            legacy.period_end,
            legacy.rule_id_legacy,
        )
        mapped_new = _legacy_only_attribution(legacy.rule_id_legacy)
        # Take the unconsumed new alert at this key that best matches
        # this legacy alert. Pairing rule (deterministic):
        #   1. severity match wins (avoids order-dependent MATCH/DIFF
        #      when multiple new rules map to the same legacy rule).
        #   2. tie-break on rule_id_new alphabetical so two identical-
        #      severity candidates produce the same MATCH attribution
        #      regardless of input order.
        # Codex pass 3+4 — closes order-dependent many-to-one pairing.
        candidates = new_index.get(key, [])
        unconsumed = sorted(
            (c for c in candidates if id(c) not in consumed_alert_ids),
            key=lambda c: str(c.get("rule_id", "")),
        )
        new_alert: dict[str, Any] | None = None
        if unconsumed and legacy.severity is not None:
            for cand in unconsumed:
                if _resolve_new_severity(cand) == legacy.severity:
                    new_alert = cand
                    break
        if new_alert is None and unconsumed:
            new_alert = unconsumed[0]
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

        consumed_alert_ids.add(id(new_alert))
        new_sev = _resolve_new_severity(new_alert)
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

    # Anything in the new index not consumed above is NEW_ONLY. Walk
    # each bucket so many-to-one mappings (multiple new rules under the
    # same legacy key) each surface as their own NEW_ONLY cell instead
    # of collapsing.
    for alerts in new_index.values():
        for alert in alerts:
            if id(alert) in consumed_alert_ids:
                continue
            cells.append(
                EquivalenceCell(
                    customer_id=str(alert.get("customer_id", "")),
                    period_start=_coerce_datetime(alert["window_start"]),
                    period_end=_coerce_datetime(alert["window_end"]),
                    rule_id_new=str(alert["rule_id"]),
                    rule_id_legacy=legacy_for_new.get(str(alert["rule_id"])),
                    classification=EquivalenceClass.NEW_ONLY,
                    new_severity=_resolve_new_severity(alert),
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
                # Use the same severity resolution path as mapped cells
                # so the unmapped-rule drilldown shows spec severity
                # when the runner payload doesn't carry one. Codex pass 2.
                new_severity=_resolve_new_severity(alert),
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


def load_legacy_alerts_csv(
    path: Path,
    *,
    column_mapping: dict[str, str] | None = None,
) -> list[LegacyAlert]:
    """Read a legacy-alert export from CSV.

    Canonical required columns: ``customer_id``, ``period_start``,
    ``period_end``, ``rule_id_legacy``. Optional column: ``severity``.
    Any additional columns are preserved verbatim in ``LegacyAlert.payload``.

    ``column_mapping``: optional ``{canonical: csv_column}`` rename map
    so a spec whose ``program.legacy_reference.key_columns`` declares
    legacy-system-native names (e.g. ``window_start`` instead of
    ``period_start``, ``rule_id`` instead of ``rule_id_legacy``) can
    drive the loader without re-formatting the export. Unmapped keys
    fall through to the canonical name, so the existing single-column
    CSV fixtures still load with no mapping argument. Codex review
    pass 2 — closes spec/loader misalignment.

    Stdlib ``csv`` only — no pandas/duckdb, matching PR-EQ-2's
    no-new-dependencies constraint.
    """
    mapping = dict(column_mapping or {})

    def _csv_col(canonical: str) -> str:
        return mapping.get(canonical, canonical)

    rows: list[LegacyAlert] = []
    with Path(path).open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            # Silently returning [] here was a footgun: a zero-byte or
            # headerless export would classify as "no legacy alerts"
            # and silently inflate NEW_ONLY counts. Raise the same
            # shape of error as the missing-required-column path.
            # Codex pass 7.
            raise ValueError(f"legacy alert CSV {path} has no header row — cannot read columns")
        required_csv_cols = [_csv_col(c) for c in _REQUIRED_CSV_COLUMNS]
        optional_csv_cols = [_csv_col(c) for c in _OPTIONAL_CSV_COLUMNS]
        missing = [c for c in required_csv_cols if c not in reader.fieldnames]
        if missing:
            raise ValueError(
                f"legacy alert CSV {path} missing required column(s): {sorted(missing)}"
            )
        reserved = set(required_csv_cols) | set(optional_csv_cols)
        for raw in reader:
            payload = {k: v for k, v in raw.items() if k not in reserved and k is not None}
            rows.append(
                LegacyAlert(
                    customer_id=raw[_csv_col("customer_id")],
                    period_start=_coerce_datetime(raw[_csv_col("period_start")]),
                    period_end=_coerce_datetime(raw[_csv_col("period_end")]),
                    rule_id_legacy=raw[_csv_col("rule_id_legacy")],
                    severity=_coerce_optional_str(raw.get(_csv_col("severity"))),
                    payload=payload,
                )
            )
    return rows
