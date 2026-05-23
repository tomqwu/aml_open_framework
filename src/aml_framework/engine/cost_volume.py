"""Run cost + data volume artifact (LF2 — closes #384).

Pillar 6 (Alert lifecycle / explainability / monitoring) artefact. Every
run already emits `audit/decisions.jsonl`, `field_lineage.jsonl`, the
regulator ZIP, etc. This module adds `run_cost_volume.json` — a
hash-pinned snapshot of:

- Data volume per input table: row count, distinct customer_id count
  (when the column exists), transaction date range (when a `timestamp`
  / `date` column exists).
- Run cost surrogate: total wall-clock seconds, peak resident memory
  (best-effort via `resource.getrusage` — may be None on platforms
  where it's unavailable), total SQL queries executed, and per-rule
  SQL elapsed seconds.

The artifact is regulator-shippable evidence ("this run scanned N rows
across M tables in T seconds") rather than a real-time performance
counter. It's NOT a substitute for application metrics — Prometheus /
Datadog should still scrape the API/dashboard. The point here is the
SAME numbers land in the audit bundle alongside `manifest.json` so a
reviewer reading a frozen run dir can answer "how much data did this
run see?" without re-querying the warehouse.

Determinism note: `wall_clock_seconds`, `peak_memory_mb`, and
`per_rule_seconds` are intentionally NOT deterministic across runs —
they're physical measurements. They are EXCLUDED from any byte-stability
comparison (the reproducibility contract pins alerts/cases/decisions,
not wall-clock). The `tables` payload IS deterministic for a fixed
input.

`resource` import is best-effort: it's POSIX-only and ships with CPython
on Linux/macOS but is absent on Windows. When the import fails or
`getrusage` raises, `peak_memory_mb` is None and the run continues.
On Linux `ru_maxrss` is reported in KiB; on macOS it's in bytes. The
helper normalises both to MiB.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict


class TableVolume(BaseModel):
    """Row + cardinality summary for one input table.

    `distinct_customers` is None when the table has no `customer_id`
    column (e.g. a reference list). `date_range_start`/`_end` are None
    when no `timestamp`/`date` column is present (e.g. a customer master
    snapshot). Frozen + `extra="forbid"` so the artifact shape is
    locked — same posture as `FieldLineageEntry` / `DQException`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    row_count: int
    distinct_customers: int | None
    date_range_start: datetime | None
    date_range_end: datetime | None


class RunCostVolumeReport(BaseModel):
    """Top-level cost + volume payload persisted as `run_cost_volume.json`.

    `wall_clock_seconds` is the runner end-to-end wall clock measured
    inside `run_spec` — NOT process uptime. `peak_memory_mb` is
    best-effort and may be None when `resource` is unavailable.
    `total_sql_queries` counts EVERY rule that executed SQL on DuckDB
    (aggregation_window, custom_sql, network_pattern, list_match) plus
    the per-alert matched-row-id replay queries, so it tracks load
    rather than just the rule count. `per_rule_seconds` keys on rule_id
    and includes only active rules that were timed.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    wall_clock_seconds: float
    peak_memory_mb: float | None
    tables: dict[str, TableVolume]
    total_sql_queries: int
    per_rule_seconds: dict[str, float]
    generated_at: datetime


def _peak_memory_mb() -> float | None:
    """Best-effort peak resident-set size in MiB. None when unavailable.

    `resource.getrusage(RUSAGE_SELF).ru_maxrss` is KiB on Linux and
    bytes on macOS — the platform branch normalises both to MiB. Windows
    lacks `resource` entirely and returns None.
    """
    try:
        import resource  # POSIX-only stdlib module.
    except ImportError:
        return None
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
    except (OSError, ValueError):  # pragma: no cover — defensive.
        return None
    ru_maxrss = usage.ru_maxrss
    if sys.platform == "darwin":
        # macOS reports bytes.
        return ru_maxrss / 1024.0 / 1024.0
    # Linux + BSD report KiB.
    return ru_maxrss / 1024.0


def summarise_tables(data: dict[str, list[dict[str, Any]]]) -> dict[str, TableVolume]:
    """Reduce the raw input `data` dict to per-table `TableVolume` rows.

    Pure over the input dict — no DuckDB, no I/O. `distinct_customers`
    is computed only when at least one row carries a `customer_id` key;
    the rule_outputs dashboard uses the same convention so this stays
    aligned. `date_range_*` picks the first column whose name ends in
    `_at` or equals `booked_at` / `event_date` / `as_of_date` — the
    framework's de-facto event-timestamp naming. Values that aren't
    `datetime` instances are skipped (str/None tolerated gracefully).
    """
    out: dict[str, TableVolume] = {}
    for table_id, rows in data.items():
        row_count = len(rows)
        distinct: int | None = None
        date_min: datetime | None = None
        date_max: datetime | None = None
        if rows:
            customer_ids = {r.get("customer_id") for r in rows if r.get("customer_id") is not None}
            if customer_ids:
                distinct = len(customer_ids)
            # Pick the first plausible event-timestamp column from the first
            # row's keys, then min/max across all rows. Keeps the column
            # discovery deterministic and avoids a per-row schema scan.
            ts_col = _pick_timestamp_column(rows[0].keys())
            if ts_col is not None:
                for r in rows:
                    val = r.get(ts_col)
                    if isinstance(val, datetime):
                        if date_min is None or val < date_min:
                            date_min = val
                        if date_max is None or val > date_max:
                            date_max = val
        out[table_id] = TableVolume(
            row_count=row_count,
            distinct_customers=distinct,
            date_range_start=date_min,
            date_range_end=date_max,
        )
    return out


def _pick_timestamp_column(keys: Any) -> str | None:
    """Return the first column name that looks like an event timestamp.

    Preference order:
    1. `booked_at` — transaction default in the synthetic generator + every
       example spec.
    2. Any key ending with `_at` (e.g. `event_at`, `created_at`).
    3. `event_date`, `as_of_date`.

    None when no candidate matches. Keeps the discovery deterministic.
    """
    key_list = list(keys)
    if "booked_at" in key_list:
        return "booked_at"
    for k in key_list:
        if isinstance(k, str) and k.endswith("_at"):
            return k
    for candidate in ("event_date", "as_of_date"):
        if candidate in key_list:
            return candidate
    return None


def build_report(
    *,
    wall_clock_seconds: float,
    tables: dict[str, TableVolume],
    total_sql_queries: int,
    per_rule_seconds: dict[str, float],
) -> RunCostVolumeReport:
    """Assemble the final report. Memory + timestamp captured here so the
    runner doesn't have to know the platform branch."""
    return RunCostVolumeReport(
        wall_clock_seconds=wall_clock_seconds,
        peak_memory_mb=_peak_memory_mb(),
        tables=tables,
        total_sql_queries=total_sql_queries,
        per_rule_seconds=per_rule_seconds,
        generated_at=datetime.now(tz=timezone.utc),
    )


def write_report(run_dir: Path, report: RunCostVolumeReport) -> None:
    """Persist `run_cost_volume.json` under the run directory.

    Always writes the file (empty `tables`/`per_rule_seconds` are valid
    payloads — e.g. an empty spec) so downstream consumers can rely on
    its presence rather than guarding on `exists()`. Same audit-integrity
    posture as `dq_exceptions.jsonl` and `field_lineage.jsonl`. Uses
    `sort_keys=True` for byte-stable diffs across re-runs at the JSON
    level (the timing/memory fields themselves are non-deterministic by
    definition).
    """
    import json

    path = run_dir / "run_cost_volume.json"
    path.write_bytes(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True, default=str).encode(
            "utf-8"
        )
    )


class CostVolumeTimer:
    """Tiny context-manager helper for measuring per-rule SQL elapsed.

    Usage in `runner.py`:

        with timer.rule("r_agg"):
            con.execute(sql)
        timer.increment_queries()

    Keeps the call-site terse so we don't litter `run_spec` with
    `time.monotonic()` deltas. The runner owns the timer instance for
    the whole run.
    """

    def __init__(self) -> None:
        self.per_rule_seconds: dict[str, float] = {}
        self.total_sql_queries: int = 0
        self._start = time.monotonic()

    def wall_clock(self) -> float:
        return time.monotonic() - self._start

    def increment_queries(self, n: int = 1) -> None:
        self.total_sql_queries += n

    def rule(self, rule_id: str) -> "_RuleTimerCM":
        return _RuleTimerCM(self, rule_id)


class _RuleTimerCM:
    """Per-rule context manager — accumulates elapsed seconds into the
    parent `CostVolumeTimer.per_rule_seconds[rule_id]`. Re-entry on the
    same rule_id (shouldn't happen in practice, but is defensive)
    accumulates rather than overwrites."""

    def __init__(self, parent: CostVolumeTimer, rule_id: str) -> None:
        self._parent = parent
        self._rule_id = rule_id
        self._t0 = 0.0

    def __enter__(self) -> "_RuleTimerCM":
        self._t0 = time.monotonic()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        elapsed = time.monotonic() - self._t0
        prior = self._parent.per_rule_seconds.get(self._rule_id, 0.0)
        self._parent.per_rule_seconds[self._rule_id] = prior + elapsed
