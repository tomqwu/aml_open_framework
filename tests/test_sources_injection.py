"""SQL identifier / path-literal safety in data source loaders (PR-H2).

``DataContract.id`` is schema-constrained to a safe pattern, but
``DataContract.source`` is free-form and the legacy-import wizard populates
it straight from an untrusted CSV dump. These tests pin that table
identifiers are validated and path literals are escaped before they are
interpolated into ``SELECT * FROM ...`` strings.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import duckdb
import pytest

from aml_framework.data.sources import (
    _assert_safe_sql_identifier,
    _sql_str_literal,
    load_duckdb_source,
    load_parquet_source,
)
from aml_framework.spec import load_spec

SPEC = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


def _single_contract_spec():
    """A spec narrowed to one data contract — enough for the loader tests."""
    spec = load_spec(SPEC)
    first = spec.data_contracts[0]
    return spec.model_copy(update={"data_contracts": [first]}), first.id


# --- _assert_safe_sql_identifier -----------------------------------------


@pytest.mark.parametrize(
    "ident",
    [
        "txn",
        "raw.transactions",
        "DB.SCHEMA.TABLE",
        "_private",
        "a1.b2.c3",
        "my-project.raw.transactions",  # BigQuery hyphenated project id
        "`my-project.raw.transactions`",  # BigQuery whole-FQN backtick quote
        '"My Schema"."My Table"',  # quoted Snowflake identifiers (spaces ok)
        "[dbo].[My Table]",  # Azure SQL bracket-quoted identifiers
        "a-b",  # single hyphen is valid
    ],
)
def test_safe_identifier_accepts_warehouse_names(ident):
    assert _assert_safe_sql_identifier(ident, field="x") == ident


@pytest.mark.parametrize(
    "ident",
    [
        "txn; DROP TABLE customers; --",
        "txn UNION SELECT secret FROM s",  # UNION injection (space)
        "a'b",
        "1abc",  # leading digit
        "a b",  # bare space
        "raw.transactions; DELETE",
        "raw..transactions",  # empty segment
        "tbl--comment",  # double hyphen / SQL comment
        "tbl-",  # trailing hyphen
        "`x`; DROP TABLE y",  # quote-break then statement
    ],
)
def test_safe_identifier_rejects_injection(ident):
    with pytest.raises(ValueError, match="not a safe SQL identifier"):
        _assert_safe_sql_identifier(ident, field="data_contract.source")


@pytest.mark.parametrize("ident", ["", "   "])
def test_safe_identifier_rejects_empty(ident):
    with pytest.raises(ValueError, match="non-empty SQL identifier"):
        _assert_safe_sql_identifier(ident, field="data_contract.source")


# --- _sql_str_literal -----------------------------------------------------


def test_sql_str_literal_wraps_in_single_quotes():
    assert _sql_str_literal("/tmp/a.parquet") == "'/tmp/a.parquet'"


def test_sql_str_literal_doubles_embedded_quotes():
    # The escaping that stops a quote in the path breaking out of the literal.
    assert _sql_str_literal("/data/o'brien/txn.parquet") == "'/data/o''brien/txn.parquet'"


def test_sql_str_literal_accepts_path_objects():
    assert _sql_str_literal(Path("/tmp/x.parquet")) == "'/tmp/x.parquet'"


# --- integration: escaping holds end-to-end -------------------------------


def test_parquet_loads_from_path_containing_single_quote(tmp_path):
    """A data dir whose name contains a single quote must still load — proving
    the path literal is escaped, not naively interpolated (which would have
    broken the SQL and raised)."""
    spec, cid = _single_contract_spec()

    clean = tmp_path / f"{cid}.parquet"
    duckdb.connect(":memory:").execute(f"COPY (SELECT 1 AS x) TO '{clean}' (FORMAT PARQUET)")

    quote_dir = tmp_path / "o'brien"
    quote_dir.mkdir()
    shutil.move(str(clean), str(quote_dir / f"{cid}.parquet"))

    data = load_parquet_source(quote_dir, spec)

    assert data[cid] == [{"x": 1}]


def test_duckdb_default_query_loads_real_table(tmp_path):
    """The refactored default-query branch (validated identifier) still loads."""
    spec, cid = _single_contract_spec()
    db_path = str(tmp_path / "test.duckdb")
    con = duckdb.connect(db_path)
    con.execute(f'CREATE TABLE "{cid}" (x INTEGER)')
    con.execute(f'INSERT INTO "{cid}" VALUES (7)')
    con.close()

    data = load_duckdb_source(db_path, spec)

    assert data[cid] == [{"x": 7}]


def test_duckdb_explicit_query_bypasses_identifier_path(tmp_path):
    """Operator-supplied queries are intentional full SQL and are left as-is."""
    spec, cid = _single_contract_spec()
    db_path = str(tmp_path / "test.duckdb")
    con = duckdb.connect(db_path)
    con.execute("CREATE TABLE other (y INTEGER)")
    con.execute("INSERT INTO other VALUES (42)")
    con.close()

    data = load_duckdb_source(db_path, spec, queries={cid: "SELECT y FROM other"})

    assert data[cid] == [{"y": 42}]
