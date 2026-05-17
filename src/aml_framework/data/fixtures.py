"""Deterministic fixture materialiser for the under-served source types.

The CSV source type ships committed sample files (``data/input/``);
the Parquet and DuckDB loaders are unit-tested but had no
demonstrable on-disk dataset. Parquet/DuckDB files are NOT
byte-deterministic (writers stamp creation time + library metadata),
so committing them would fight this repo's determinism contract and
churn the diff on every regen. Instead this module regenerates them
on demand from the seeded synthetic generator — one command, fully
reproducible, output git-ignored.

    python -m aml_framework.data.fixtures            # → data/fixtures/
    make fixtures

Run output:
    {out}/parquet/{contract_id}.parquet   (one file per data contract)
    {out}/aml.duckdb                      (one table per data contract)

The rows are exactly ``generate_dataset(as_of=_FIXTURE_AS_OF,
seed=seed)`` for the canonical Canadian Schedule I spec's contracts —
so the fixtures carry the same planted positives (incl. the PR-A
rtp / crypto / prepaid rails) the synthetic source does, and
``resolve_source('parquet'|'duckdb', ...)`` over them returns the
same logical data as ``resolve_source('synthetic', ...)``.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Pinned so the fixtures are stable across regens (the dashboard's
# live synthetic path uses datetime.now(); fixtures must NOT, or the
# planted-positive windows would drift every run).
_FIXTURE_AS_OF = datetime(2026, 1, 1, 0, 0, 0)

_DEFAULT_SPEC = "examples/canadian_schedule_i_bank/aml.yaml"
_DEFAULT_OUT = "data/fixtures"


def _project_root() -> Path:
    # src/aml_framework/data/fixtures.py → repo root is parents[3]
    return Path(__file__).resolve().parents[3]


def materialize_fixtures(
    out_dir: str | Path | None = None,
    *,
    spec_path: str | Path | None = None,
    seed: int = 42,
) -> dict[str, Path]:
    """Write parquet + duckdb fixtures from the seeded synthetic data.

    Returns a map of artifact name → written path. Deterministic for a
    given seed (same logical rows every run). Lazy-imports duckdb (a
    dashboard/runtime extra, not a ``[dev]`` dependency) so importing
    this module stays cheap.
    """
    import duckdb
    import pyarrow as pa

    from aml_framework.data import generate_dataset
    from aml_framework.spec.loader import load_spec

    root = _project_root()
    out = Path(out_dir) if out_dir is not None else root / _DEFAULT_OUT
    spec = load_spec(str(spec_path) if spec_path is not None else root / _DEFAULT_SPEC)

    data = generate_dataset(as_of=_FIXTURE_AS_OF, seed=seed)

    parquet_dir = out / "parquet"
    parquet_dir.mkdir(parents=True, exist_ok=True)
    duckdb_path = out / "aml.duckdb"
    if duckdb_path.exists():
        duckdb_path.unlink()  # rebuild clean — no stale tables

    written: dict[str, Path] = {}
    con = duckdb.connect(str(duckdb_path))
    try:
        for contract in spec.data_contracts:
            rows: list[dict[str, Any]] = data.get(contract.id, [])
            # Stable column order = the contract's declared column
            # order (falls back to the first row's keys if a contract
            # declares no columns).
            cols = [c.name for c in contract.columns]
            if not cols and rows:
                cols = list(rows[0].keys())

            if rows:
                # list[dict] → pyarrow Table (duckdb registers Arrow
                # natively + infers faithful types: Decimal→decimal,
                # datetime→timestamp). `.get` so a row omitting a
                # nullable key still aligns to the column.
                table = pa.table({c: [r.get(c) for r in rows] for c in cols})
                con.register("_rows_view", table)
                con.execute(f'CREATE TABLE "{contract.id}" AS SELECT * FROM _rows_view')
                con.unregister("_rows_view")
            else:
                # Preserve an empty, correctly-named table so the
                # duckdb loader returns [] (fail-soft), not an error.
                col_defs = ", ".join(f'"{c}" VARCHAR' for c in cols) or '"_empty" VARCHAR'
                con.execute(f'CREATE TABLE "{contract.id}" ({col_defs})')

            parquet_path = parquet_dir / f"{contract.id}.parquet"
            con.execute(f"COPY \"{contract.id}\" TO '{parquet_path}' (FORMAT PARQUET)")
            written[f"parquet:{contract.id}"] = parquet_path
        written["duckdb"] = duckdb_path
    finally:
        con.close()
    return written


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    out = args[0] if args else None
    written = materialize_fixtures(out)
    print(f"Materialized {len(written)} fixture artifact(s):")
    for name, path in sorted(written.items()):
        print(f"  {name:24s} → {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
