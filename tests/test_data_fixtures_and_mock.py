"""Data Integration PR-B — deterministic parquet/duckdb fixtures +
the explicit local-mock path for the cloud/warehouse source types.

duckdb + pyarrow are runtime/dashboard extras absent from the lean
``[dev]`` unit-test install. The skip-guard is PER-TEST (the
``duckdb_env`` fixture), not module-level, so the pure-Python mock
sentinel-safety tests and the stdlib ISO-XML parse test still run on
lean CI (Codex PR-B review nit 2).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

# NOTE: duckdb/pyarrow are runtime/dashboard extras absent from the
# lean [dev] unit-test install. The skip-guard is per-test (via the
# `duckdb_env` fixture), NOT module-level, so the pure-Python sentinel
# safety tests (`_is_mock_target` — the security-relevant "a real
# conn string is never mocked" guard) and the stdlib ISO-XML parse
# test still run on lean CI (Codex PR-B nit 2). These module imports
# are all lazy-internally, so importing them on [dev] is safe.
from aml_framework.data.fixtures import materialize_fixtures
from aml_framework.data.sources import (
    _is_mock_target,
    load_duckdb_source,
    load_parquet_source,
    resolve_source,
)
from aml_framework.spec.loader import load_spec

_SPEC = "examples/canadian_schedule_i_bank/aml.yaml"
_NEW_RAILS = {"rtp", "crypto", "prepaid"}


@pytest.fixture
def duckdb_env():
    """Skip a test that needs the duckdb+pyarrow runtime extras."""
    pytest.importorskip("duckdb")
    pytest.importorskip("pyarrow")


@pytest.fixture(scope="module")
def spec():
    return load_spec(_SPEC)


def _channels(rows):
    return {r.get("channel") for r in rows}


# --- fixture generator ----------------------------------------------------


def test_materialize_writes_parquet_and_duckdb(duckdb_env, tmp_path, spec):
    written = materialize_fixtures(tmp_path)
    assert (tmp_path / "parquet" / "txn.parquet").exists()
    assert (tmp_path / "parquet" / "customer.parquet").exists()
    assert (tmp_path / "aml.duckdb").exists()
    assert written["duckdb"] == tmp_path / "aml.duckdb"
    assert "parquet:txn" in written and "parquet:customer" in written


def test_parquet_and_duckdb_resolve_to_same_logical_data(duckdb_env, tmp_path, spec):
    materialize_fixtures(tmp_path)
    pq = load_parquet_source(tmp_path / "parquet", spec)
    db = load_duckdb_source(str(tmp_path / "aml.duckdb"), spec)

    assert len(pq["txn"]) == len(db["txn"]) > 0
    assert len(pq["customer"]) == len(db["customer"]) == 30
    # The PR-A rails must survive the parquet/duckdb round-trip.
    assert _NEW_RAILS.issubset(_channels(pq["txn"]))
    assert _NEW_RAILS.issubset(_channels(db["txn"]))


def test_fixtures_are_deterministic(duckdb_env, tmp_path, spec):
    a, b = tmp_path / "a", tmp_path / "b"
    materialize_fixtures(a)
    materialize_fixtures(b)
    da = load_duckdb_source(str(a / "aml.duckdb"), spec)["txn"]
    db = load_duckdb_source(str(b / "aml.duckdb"), spec)["txn"]

    def key(rows):
        return sorted((r.get("txn_id"), str(r.get("amount")), r.get("channel")) for r in rows)

    assert key(da) == key(db), "same seed must yield byte-stable logical rows"


# --- explicit local-mock path --------------------------------------------


@pytest.mark.parametrize(
    ("arg", "expected"),
    [
        ("mock", True),
        ("MOCK", True),
        ("mock:", True),
        ("mock:demo", True),
        ("local-mock", True),
        ("localmock", True),
        ("  Mock  ", True),
        ("snowflake://acct/db", False),
        ("abfss://c@a.dfs.core.windows.net/p", False),
        ("", False),
        (None, False),
    ],
)
def test_is_mock_target(arg, expected):
    assert _is_mock_target(arg) is expected


_CLOUD_TYPES = [
    "snowflake",
    "bigquery",
    "s3",
    "gcs",
    "azure_blob",
    "adls",
    "synapse",
    "azuresql",
]


@pytest.mark.parametrize("source_type", _CLOUD_TYPES)
def test_cloud_source_mock_serves_synthetic(duckdb_env, source_type, spec):
    as_of = datetime(2026, 1, 1)
    out = resolve_source(source_type, spec, as_of, seed=42, data_dir="mock")
    assert len(out["txn"]) > 0
    assert len(out["customer"]) == 30
    # Demonstrable rails incl. the PR-A additions, no live creds used.
    assert _NEW_RAILS.issubset(_channels(out["txn"]))


def test_cloud_mock_is_deterministic_and_matches_synthetic(duckdb_env, spec):
    as_of = datetime(2026, 1, 1)
    mock = resolve_source("snowflake", spec, as_of, seed=42, data_dir="mock")
    synth = resolve_source("synthetic", spec, as_of, seed=42)
    assert len(mock["txn"]) == len(synth["txn"])
    assert len(mock["customer"]) == len(synth["customer"])


def test_real_conn_string_never_hits_mock():
    # A real-looking connection arg must NOT be treated as the mock
    # sentinel (production paths stay untouched).
    assert _is_mock_target("snowflake://user:pw@acct/db/schema") is False
    assert _is_mock_target("s3://bucket/prefix") is False


# --- new ISO 20022 sample -------------------------------------------------


def test_new_pacs008_rtp_crypto_sample_parses():
    from aml_framework.data.iso20022 import parse_iso20022_xml

    sample = (
        Path(__file__).resolve().parents[1]
        / "src/aml_framework/data/iso20022/sample_pacs008_rtp_crypto.xml"
    )
    rows = parse_iso20022_xml(sample.read_bytes())
    assert len(rows) == 2  # two CdtTrfTxInf legs (funding + off-ramp)
    amounts = sorted(str(r.get("amount")) for r in rows)
    assert amounts == ["40000.00", "42000.00"]
    # Semantic shape, not just counts (Codex PR-B nit 1): both legs
    # are the CAD pacs.008 RTP→VASP off-ramp typology, and the
    # counterparties are the VASP / off-ramp exchange.
    for r in rows:
        assert r["currency"] == "CAD"
        assert r["msg_kind"] == "pacs.008"
        assert r["msg_id"] == "SAMPLE-RTP-CRYPTO-2026-05-17-001"
        assert r["counterparty_country"] == "MT"
    names = sorted(r["counterparty_name"] for r in rows)
    assert names == ["OFFRAMP EXCHANGE MT", "SWIFTCHAIN VASP LTD"]
