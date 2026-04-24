"""Data source abstraction — load real data from CSV, Parquet, or warehouses.

The engine contract is dict[str, list[dict]] keyed by data contract ID.
DataSource implementations convert any external source to this format at
the CLI/API boundary so the engine doesn't need to know about connectors.
"""

from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from aml_framework.spec.models import AMLSpec, ColumnType

# Type parsers for CSV string values.
_PARSERS: dict[ColumnType, Any] = {
    "string": str,
    "integer": int,
    "decimal": lambda v: Decimal(v).quantize(Decimal("0.01")),
    "boolean": lambda v: v.lower() in ("true", "1", "yes"),
    "date": lambda v: datetime.strptime(v, "%Y-%m-%d").date() if v else None,
    "timestamp": lambda v: datetime.fromisoformat(v) if v else None,
}


def _parse_value(value: str, col_type: ColumnType, nullable: bool) -> Any:
    """Parse a CSV string value to the appropriate Python type."""
    if not value or value.strip() == "":
        if nullable:
            return None
        return "" if col_type == "string" else 0
    try:
        return _PARSERS[col_type](value.strip())
    except (ValueError, InvalidOperation, KeyError):
        return value


def validate_csv(csv_path: Path, spec: AMLSpec, contract_id: str) -> list[str]:
    """Validate a CSV file against a data contract. Returns error list."""
    errors: list[str] = []
    contract = next((c for c in spec.data_contracts if c.id == contract_id), None)
    if not contract:
        errors.append(f"No data contract '{contract_id}' in spec")
        return errors

    if not csv_path.exists():
        errors.append(f"File not found: {csv_path}")
        return errors

    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = set(reader.fieldnames or [])

        # Check required columns.
        required = {c.name for c in contract.columns if not c.nullable}
        missing = required - headers
        if missing:
            errors.append(f"Missing required columns: {sorted(missing)}")

        # Check declared columns exist.
        declared = {c.name for c in contract.columns}
        extra = headers - declared
        if extra:
            errors.append(f"Extra columns not in contract: {sorted(extra)} (will be ignored)")

    return errors


def load_csv_source(
    data_dir: Path,
    spec: AMLSpec,
    as_of: datetime | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Load data from CSV files in a directory.

    Convention: one file per data contract, named {contract_id}.csv.
    """
    data: dict[str, list[dict[str, Any]]] = {}
    col_types: dict[str, dict[str, tuple[ColumnType, bool]]] = {}

    for contract in spec.data_contracts:
        col_types[contract.id] = {c.name: (c.type, c.nullable) for c in contract.columns}

        csv_path = data_dir / f"{contract.id}.csv"
        if not csv_path.exists():
            data[contract.id] = []
            continue

        rows: list[dict[str, Any]] = []
        types = col_types[contract.id]
        with csv_path.open("r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                parsed: dict[str, Any] = {}
                for col_name, (col_type, nullable) in types.items():
                    raw = row.get(col_name, "")
                    parsed[col_name] = _parse_value(raw, col_type, nullable)
                rows.append(parsed)
        data[contract.id] = rows

    return data


def load_parquet_source(
    data_dir: Path,
    spec: AMLSpec,
) -> dict[str, list[dict[str, Any]]]:
    """Load data from Parquet files via DuckDB (no pandas needed)."""
    import duckdb

    data: dict[str, list[dict[str, Any]]] = {}
    con = duckdb.connect(":memory:")

    for contract in spec.data_contracts:
        parquet_path = data_dir / f"{contract.id}.parquet"
        if not parquet_path.exists():
            data[contract.id] = []
            continue

        rows = con.execute(f"SELECT * FROM '{parquet_path}'").fetchall()
        cols = [d[0] for d in con.description] if con.description else []
        data[contract.id] = [dict(zip(cols, r)) for r in rows]

    con.close()
    return data


def load_duckdb_source(
    db_path: str,
    spec: AMLSpec,
    queries: dict[str, str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Load data from an external DuckDB database.

    If queries is provided, use custom SQL per contract.
    Otherwise, assume table names match contract IDs.
    """
    import duckdb

    data: dict[str, list[dict[str, Any]]] = {}
    con = duckdb.connect(db_path, read_only=True)

    for contract in spec.data_contracts:
        sql = (queries or {}).get(contract.id, f"SELECT * FROM {contract.id}")
        try:
            rows = con.execute(sql).fetchall()
            cols = [d[0] for d in con.description] if con.description else []
            data[contract.id] = [dict(zip(cols, r)) for r in rows]
        except Exception:
            data[contract.id] = []

    con.close()
    return data


def resolve_source(
    source_type: str,
    spec: AMLSpec,
    as_of: datetime,
    seed: int = 42,
    data_dir: str | None = None,
    db_path: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Resolve a data source by type string. Used by CLI and API."""
    if source_type == "synthetic":
        from aml_framework.data import generate_dataset

        return generate_dataset(as_of=as_of, seed=seed)

    if source_type == "csv":
        if not data_dir:
            raise ValueError("--data-dir required for csv source")
        return load_csv_source(Path(data_dir), spec, as_of)

    if source_type == "parquet":
        if not data_dir:
            raise ValueError("--data-dir required for parquet source")
        return load_parquet_source(Path(data_dir), spec)

    if source_type == "duckdb":
        if not db_path:
            raise ValueError("--db-path required for duckdb source")
        return load_duckdb_source(db_path, spec)

    raise ValueError(f"Unknown data source: {source_type}")
