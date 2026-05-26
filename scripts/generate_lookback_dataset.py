"""Generate a multi-year synthetic dataset for the 5-year lookback demo.

PR-LOOKBACK-1. Wraps `aml_framework.data.synthetic.generate_dataset()`
in a per-month loop so an operator can run a single command and get a
60-month Gold-shaped dataset ready to feed `aml run --data-source parquet
--data-dir <slice>`.

The underlying generator produces ±59 days of data per call, so a single
invocation is one month. We loop 60 times (or `--years * 12`) with each
month's `as_of` set to the last second of that month. The seed stays
pinned across the loop so the planted-positive customers (C0001–C0059)
keep their typology assignments month over month — that's what makes
the equivalence demo's MATCH/NEW_ONLY/LEGACY_ONLY/DIFF outcomes
reproducible.

Outputs (per month):

    <out>/parquet/<YYYY-MM>/{customer,txn,txn_return,hs_code_baseline}.parquet
    <out>/csv/<YYYY-MM>/{customer,txn,txn_return,hs_code_baseline}.csv

Both formats are written so operators can pick the path that matches
their warehouse export (Parquet is recommended; CSV is the no-pyarrow
alternative for the runbook's "CSV alternative" callout).

Usage:

    python scripts/generate_lookback_dataset.py \\
        --years 5 \\
        --end 2025-12-31 \\
        --out examples/community_bank_lookback/data/

Run from the repo root. The script does NOT commit the bulk output —
that's `.gitignore`d under `examples/community_bank_lookback/data/`.
"""

from __future__ import annotations

import argparse
import csv as _csv
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from aml_framework.data.synthetic import generate_dataset
from aml_framework.spec.loader import load_spec


def _is_month_end(d: date) -> bool:
    """True if `d` is the last day of its month."""
    return (d + timedelta(days=1)).day == 1


def _month_ends(end_date: date, months: int) -> list[datetime]:
    """Return `months` month-end timestamps, oldest first, ending at `end_date`.

    Each entry is `YYYY-MM-LAST_DAY T23:59:59` — the last second of the
    month, matching how `aml run --as-of` is conventionally pinned for
    a month-end backfill. Codex P3: caller must pre-validate that
    `end_date` is itself a month-end; otherwise the manifest's `end` and
    the actual last slice silently disagree.
    """
    # Walk back month-by-month from end_date, then reverse.
    cur = end_date.replace(day=1)
    stops: list[date] = []
    for _ in range(months):
        # Last day of `cur`'s month = (next month, day 1) - 1 day.
        nxt = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
        last = nxt - timedelta(days=1)
        stops.append(last)
        # Step back one month.
        cur = (cur - timedelta(days=1)).replace(day=1)
    stops.reverse()
    return [datetime.combine(s, datetime.max.time().replace(microsecond=0)) for s in stops]


def _contract_shape(
    spec_path: Path,
) -> dict[str, tuple[list[str], dict[str, list[str]]]]:
    """Load `spec_path` and return `{contract_id: ([col_names], {col: enum})}`.

    Codex P2 (round 1): synthetic.generate_dataset() emits rows carrying
    every optional field a typology might need (purpose_code, debtor_bic,
    BOI flags, etc.) — far more keys than the lookback spec declares.
    `aml validate-data` treats extras as errors, so we project each
    contract down to its declared column set.

    Codex P2 (round 2): the same generator also emits enum *values* the
    spec doesn't declare — e.g. `txn.channel` includes `rtp`, `crypto`,
    `prepaid`, `e_transfer`, `faster_payments` while the lookback spec
    declares only `[cash, wire, ach, card]`. Those out-of-contract rows
    are then consumed by all-channel custom SQL rules and produce
    alerts the spec source-of-truth says are invalid. Carry the enum
    map back so callers can filter rows down to declared values.
    """
    spec = load_spec(spec_path)
    out: dict[str, tuple[list[str], dict[str, list[str]]]] = {}
    for c in spec.data_contracts:
        cols = [col.name for col in c.columns]
        enums = {col.name: list(col.enum) for col in c.columns if col.enum}
        out[c.id] = (cols, enums)
    return out


def _project_and_filter(
    rows: list[dict],
    cols: list[str],
    enums: dict[str, list[str]],
) -> list[dict]:
    """Project rows to `cols` order, then drop rows that violate any enum.

    Enum violation = a value outside the declared allowed list. Null
    values pass through (nullability is a separate column-level rule).
    """
    out: list[dict] = []
    for r in rows:
        if any(
            r.get(col) is not None and r.get(col) not in allowed
            for col, allowed in enums.items()
        ):
            continue
        out.append({k: r.get(k) for k in cols})
    return out


def _write_parquet(rows: list[dict], path: Path) -> None:
    """Write rows as Parquet. Requires pyarrow (already in [dashboard] extras)."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    if not rows:
        # Empty contract — write a single-row empty table so the loader
        # doesn't blow up on "missing file."
        pq.write_table(pa.Table.from_pylist([]), path)
        return
    pq.write_table(pa.Table.from_pylist(rows), path)


def _write_csv(rows: list[dict], path: Path) -> None:
    """Write rows as CSV. ISO-8601 datetime serialization, sorted-key order."""
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    # Stable column order: union of all keys, then sort.
    cols = sorted({k for row in rows for k in row})
    with path.open("w", encoding="utf-8", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for row in rows:
            w.writerow(
                {
                    k: (v.isoformat() if hasattr(v, "isoformat") else "" if v is None else v)
                    for k, v in row.items()
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--years",
        type=int,
        default=5,
        help="How many years of monthly slices to generate (default 5 = 60 months). "
        "Ignored when `--months` is set.",
    )
    parser.add_argument(
        "--months",
        type=int,
        default=None,
        help="Explicit month count override (smoke-test convenience). When set, "
        "`--years` is ignored.",
    )
    parser.add_argument(
        "--end",
        type=lambda s: date.fromisoformat(s),
        default=date(2025, 12, 31),
        help="Last month-end to include, YYYY-MM-DD (default 2025-12-31).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Synthetic-generator seed; pinned across the loop so planted "
        "positives stay reproducible (default 42).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("examples/community_bank_lookback/data"),
        help="Output root. Will create <out>/parquet/<YYYY-MM>/ and "
        "<out>/csv/<YYYY-MM>/ subdirectories.",
    )
    parser.add_argument(
        "--formats",
        choices=["parquet", "csv", "both"],
        default="both",
        help="Which formats to emit. Default both.",
    )
    parser.add_argument(
        "--spec",
        # Codex P3: argparse's `type=Path` would convert `--spec ""` to
        # `Path('.')` (not `None`), and the documented "empty to disable"
        # escape hatch would then crash inside `load_spec`. Treat the
        # empty string as the explicit "no projection" sentinel.
        type=lambda s: None if s == "" else Path(s),
        default=Path("examples/community_bank_lookback/aml.yaml"),
        help="Spec used to project rows down to declared contract columns "
        "(so `aml validate-data` accepts the output). Pass an empty string "
        "(`--spec ''`) to skip projection and write every key the synthetic "
        "generator emits.",
    )
    args = parser.parse_args()

    months = args.months if args.months is not None else args.years * 12
    if months < 1:
        parser.error("--years or --months must yield at least 1 month")
    # Codex P3: a non-month-end `--end` would silently extend the replay
    # past the requested cutoff (the loop always lands on the last day
    # of `--end`'s month). Reject it up front so the manifest's `end:`
    # and the actual last slice can't disagree.
    if not _is_month_end(args.end):
        # Suggest the last day of the user's month: (first of next month) - 1.
        next_month_first = (args.end.replace(day=28) + timedelta(days=4)).replace(day=1)
        suggestion = (next_month_first - timedelta(days=1)).isoformat()
        parser.error(
            f"--end must be a month-end date (last day of the month); "
            f"got {args.end.isoformat()}. Try --end {suggestion}."
        )
    stops = _month_ends(args.end, months)
    args.out.mkdir(parents=True, exist_ok=True)

    # Load spec column projection + enum filter (or empty to disable).
    contract_shape: dict[str, tuple[list[str], dict[str, list[str]]]] = {}
    if args.spec is not None:
        if not args.spec.exists():
            parser.error(f"--spec not found: {args.spec}")
        contract_shape = _contract_shape(args.spec)

    print(f"Generating {months} months × ~1300 txns ending {args.end} → {args.out}")
    summary: list[dict] = []
    for i, as_of in enumerate(stops, 1):
        ym = as_of.strftime("%Y-%m")
        data = generate_dataset(as_of=as_of, seed=args.seed)
        # Project to spec-declared columns AND filter rows that violate
        # the spec's column enums when `--spec` is set. Applies to BOTH
        # Parquet and CSV — same contract, same shape, or one format
        # would pass validate-data while the other fails.
        projected = {
            contract: _project_and_filter(rows, *contract_shape[contract])
            if contract in contract_shape
            else rows
            for contract, rows in data.items()
        }
        contracts = list(projected.keys())
        row_counts = {c: len(projected[c]) for c in contracts}
        for fmt in (["parquet", "csv"] if args.formats == "both" else [args.formats]):
            slice_dir = args.out / fmt / ym
            slice_dir.mkdir(parents=True, exist_ok=True)
            for contract, rows in projected.items():
                ext = "parquet" if fmt == "parquet" else "csv"
                target = slice_dir / f"{contract}.{ext}"
                if fmt == "parquet":
                    _write_parquet(rows, target)
                else:
                    _write_csv(rows, target)
        summary.append({"month": ym, **row_counts})
        sys.stdout.write(
            f"  [{i:3d}/{months}] {ym}: "
            + " ".join(f"{c}={n}" for c, n in row_counts.items())
            + "\n"
        )
        sys.stdout.flush()

    # Write a manifest so the runbook can show "what got generated."
    # Codex P2: record the effective span, NOT the raw `--years` flag.
    # With `--months N` override, `args.years` is meaningless (default 5),
    # so writing it would mislead audit consumers reading `_manifest.json`
    # for a smoke-test or partial-replay dataset.
    manifest: dict[str, object] = {
        "month_count": months,
        "span_first_month": summary[0]["month"] if summary else None,
        "span_last_month": summary[-1]["month"] if summary else None,
        "end": args.end.isoformat(),
        "seed": args.seed,
        "months": [s["month"] for s in summary],
        "formats": args.formats,
        "row_counts": summary,
    }
    # Only include `years` when the user actually passed --years (i.e.,
    # `--months` was NOT used). That way the field always means what it
    # looks like.
    if args.months is None:
        manifest["years"] = args.years
    (args.out / "_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"Done. Manifest: {args.out / '_manifest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
