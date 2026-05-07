"""Data source abstraction — load real data from CSV, Parquet, or warehouses.

The engine contract is dict[str, list[dict]] keyed by data contract ID.
DataSource implementations convert any external source to this format at
the CLI/API boundary so the engine doesn't need to know about connectors.
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from aml_framework.spec.models import AMLSpec, ColumnType, DataContract

logger = logging.getLogger("aml.data.sources")


class DataSourceLoadError(RuntimeError):
    """Raised when a declared non-synthetic data contract cannot be loaded."""

    def __init__(self, source_type: str, contract_id: str, cause: str) -> None:
        self.source_type = source_type
        self.contract_id = contract_id
        self.cause = cause
        super().__init__(
            f"Failed to load contract '{contract_id}' from {source_type}: {cause}. "
            "Set allow_empty: true on the data contract only when an empty or "
            "missing source is an intentional, regulator-reviewable condition."
        )


def _empty_or_raise(source_type: str, contract: DataContract, cause: str) -> list[dict[str, Any]]:
    if contract.allow_empty:
        logger.warning(
            "%s: allowed empty data for contract '%s': %s",
            source_type,
            contract.id,
            cause,
        )
        return []
    raise DataSourceLoadError(source_type, contract.id, cause)


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
    """Parse a CSV string value to the appropriate Python type.

    Raises ValueError on blank non-nullable values or parse failures
    so row-level validation can pinpoint the problem.
    """
    if not value or value.strip() == "":
        if nullable:
            return None
        raise ValueError(f"non-nullable column must not be empty (got {value!r})")
    try:
        return _PARSERS[col_type](value.strip())
    except (ValueError, InvalidOperation, KeyError) as e:
        raise ValueError(f"cannot parse {value[:50]!r} as {col_type}: {e}") from e


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

    col_type_map = {c.name: (c.type, c.nullable) for c in contract.columns}

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

        # Row-level type and nullability validation.
        for row_num, row in enumerate(reader, start=2):  # 1-indexed, header is row 1
            for col_name, (col_type, nullable) in col_type_map.items():
                raw = row.get(col_name, "")
                try:
                    _parse_value(raw, col_type, nullable)
                except ValueError as e:
                    errors.append(
                        f"csv {csv_path.name} row {row_num} column '{col_name}' "
                        f"(type={col_type}, nullable={nullable}): {e}"
                    )

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
            data[contract.id] = _empty_or_raise("csv", contract, f"missing file {csv_path}")
            continue

        rows: list[dict[str, Any]] = []
        types = col_types[contract.id]
        with csv_path.open("r", encoding="utf-8") as f:
            for row_num, row in enumerate(csv.DictReader(f), start=2):
                parsed: dict[str, Any] = {}
                for col_name, (col_type, nullable) in types.items():
                    raw = row.get(col_name, "")
                    try:
                        parsed[col_name] = _parse_value(raw, col_type, nullable)
                    except ValueError as e:
                        raise DataSourceLoadError(
                            "csv",
                            contract.id,
                            f"{csv_path.name} row {row_num} column '{col_name}' "
                            f"(type={col_type}, nullable={nullable}): {e}",
                        ) from e
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

    try:
        for contract in spec.data_contracts:
            parquet_path = data_dir / f"{contract.id}.parquet"
            if not parquet_path.exists():
                data[contract.id] = _empty_or_raise(
                    "parquet", contract, f"missing file {parquet_path}"
                )
                continue

            rows = con.execute(f"SELECT * FROM '{parquet_path}'").fetchall()
            cols = [d[0] for d in con.description] if con.description else []
            data[contract.id] = [dict(zip(cols, r)) for r in rows]
    finally:
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

    try:
        for contract in spec.data_contracts:
            sql = (queries or {}).get(contract.id, f"SELECT * FROM {contract.id}")
            try:
                rows = con.execute(sql).fetchall()
                cols = [d[0] for d in con.description] if con.description else []
                data[contract.id] = [dict(zip(cols, r)) for r in rows]
            except Exception as e:
                logger.warning("duckdb: failed to load contract '%s': %s", contract.id, e)
                data[contract.id] = _empty_or_raise("duckdb", contract, str(e))
    finally:
        con.close()
    return data


def infer_source_paths(
    source_type: str,
    spec: AMLSpec,
    data_dir: str | None = None,
    db_path: str | None = None,
) -> dict[str, str]:
    """Mirror the routing in `resolve_source` and return per-contract
    logical source paths (PR-LIN-2). The runner threads these into
    `record_input(source_path=...)` so the lineage walk-back can answer
    "this alert came from /data/input/txn.csv" rather than just "the
    txn contract".

    Per-loader convention:
      - synthetic     → "synthetic"
      - csv/parquet   → {data_dir}/{contract_id}.{ext}
      - duckdb        → "duckdb:{db_path}#{table_or_query}"
      - s3/gcs        → "{bucket}/{contract_id}.csv|parquet"
      - snowflake     → "snowflake:{conn}#{contract.source}"
      - bigquery      → "bigquery:{conn}#{contract.source}"
      - iso20022      → "iso20022:{data_dir}" (txn only)
    """
    paths: dict[str, str] = {}
    for contract in spec.data_contracts:
        if source_type == "synthetic":
            paths[contract.id] = "synthetic"
        elif source_type in ("csv", "parquet"):
            ext = "csv" if source_type == "csv" else "parquet"
            paths[contract.id] = f"{data_dir or ''}/{contract.id}.{ext}".lstrip("/")
        elif source_type == "duckdb":
            paths[contract.id] = f"duckdb:{db_path or ''}#{contract.id}"
        elif source_type in ("s3", "gcs"):
            paths[contract.id] = f"{(data_dir or '').rstrip('/')}/{contract.id}"
        elif source_type in ("snowflake", "bigquery"):
            paths[contract.id] = f"{source_type}:{data_dir or ''}#{contract.source}"
        elif source_type == "iso20022":
            if contract.id == "txn":
                paths[contract.id] = f"iso20022:{data_dir or ''}"
        else:
            paths[contract.id] = source_type
    return paths


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

    if source_type == "snowflake":
        return _load_warehouse_via_duckdb(
            spec,
            "snowflake",
            data_dir or "",
            "DuckDB snowflake extension required: INSTALL snowflake; LOAD snowflake;",
        )

    if source_type == "bigquery":
        return _load_warehouse_via_duckdb(
            spec,
            "bigquery",
            data_dir or "",
            "DuckDB bigquery extension required: INSTALL bigquery; LOAD bigquery;",
        )

    if source_type in ("s3", "gcs"):
        if not data_dir:
            raise ValueError(f"--data-dir required for {source_type} (bucket URI)")
        return _load_cloud_storage(source_type, data_dir, spec)  # pragma: no cover

    if source_type == "iso20022":
        # Round-5 #1: ingest pacs.008 / pacs.009 XML messages from a
        # directory and materialise them as txn rows. Customer rows
        # come from a separate source — typical deployments pair
        # `--data-source iso20022` with a CSV customer file via a
        # follow-up `aml validate-data` pass.
        if not data_dir:
            raise ValueError("--data-dir required for iso20022 (XML directory)")
        from aml_framework.data.iso20022 import load_iso20022_dir

        txns = load_iso20022_dir(data_dir)
        return {"txn": txns, "customer": []}

    raise ValueError(f"Unknown data source: {source_type}")


def _load_warehouse_via_duckdb(  # pragma: no cover
    spec: AMLSpec,
    extension: str,
    connection_string: str,
    error_hint: str,
) -> dict[str, list[dict[str, Any]]]:
    """Connect to cloud warehouses via DuckDB extensions.

    Requires the DuckDB extension to be installed:
      duckdb.install_extension('snowflake')  or  duckdb.install_extension('bigquery')
    """
    import duckdb

    data: dict[str, list[dict[str, Any]]] = {}
    con = duckdb.connect(":memory:")

    try:
        con.execute(f"INSTALL {extension}")
        con.execute(f"LOAD {extension}")
    except Exception as e:
        raise RuntimeError(f"{error_hint}\nError: {e}") from e

    if connection_string:
        try:
            con.execute(f"CALL {extension}_attach('{connection_string}')")
        except Exception:  # pragma: no cover
            logger.debug("%s_attach not required for this connection", extension)

    try:
        for contract in spec.data_contracts:
            try:
                rows = con.execute(
                    f"SELECT * FROM {contract.source}"
                ).fetchall()  # pragma: no cover
                cols = [d[0] for d in con.description] if con.description else []
                data[contract.id] = [dict(zip(cols, r)) for r in rows]
            except Exception as e:
                logger.warning(
                    "warehouse: failed to load contract '%s' via %s: %s",
                    contract.id,
                    extension,
                    e,
                )
                data[contract.id] = _empty_or_raise(extension, contract, str(e))
    finally:
        con.close()
    return data


def _load_cloud_storage(  # pragma: no cover
    provider: str,
    bucket_path: str,
    spec: AMLSpec,
) -> dict[str, list[dict[str, Any]]]:
    """Load CSV/Parquet from S3 or GCS via DuckDB's httpfs extension."""
    import duckdb

    data: dict[str, list[dict[str, Any]]] = {}
    con = duckdb.connect(":memory:")

    try:
        con.execute("INSTALL httpfs")
        con.execute("LOAD httpfs")
    except Exception as e:
        raise RuntimeError(f"DuckDB httpfs extension required for {provider}: {e}") from e

    try:
        for contract in spec.data_contracts:
            for ext in ("csv", "parquet"):
                path = f"{bucket_path.rstrip('/')}/{contract.id}.{ext}"
                try:
                    rows = con.execute(f"SELECT * FROM '{path}'").fetchall()
                    cols = [d[0] for d in con.description] if con.description else []
                    data[contract.id] = [dict(zip(cols, r)) for r in rows]
                    break
                except Exception:  # pragma: no cover
                    logger.debug("cloud: %s.%s not found at %s", contract.id, ext, bucket_path)
                    continue
            if contract.id not in data:
                data[contract.id] = _empty_or_raise(
                    provider,
                    contract,
                    f"no csv or parquet object under {bucket_path.rstrip('/')}",
                )
    finally:
        con.close()
    return data
