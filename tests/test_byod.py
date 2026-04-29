"""Tests for `aml byod` — bring-your-own-data warehouse mapper.

The first-week-engineer onboarding promise this guards: pointing the
framework at a real warehouse should be a 5-minute review of
suggested mappings, not 3 days of hand-translation. False positives
in mapping silently break detection (the rule never fires), so the
matcher is conservative on purpose; these tests pin that behaviour.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from aml_framework.byod import (
    COLUMN_ALIASES,
    ColumnProfile,
    map_spec_to_data_dir,
    profile_csv,
    render_mapping_yaml,
    suggest_mapping,
)
from aml_framework.cli import app
from aml_framework.spec import load_spec


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def warehouse_csvs(tmp_path: Path) -> Path:
    """Realistic warehouse with non-canonical column names — exercises
    the alias path, which is the whole point of the wizard."""
    txn = tmp_path / "txn.csv"
    txn.write_text(
        "trx_id,cif,amt,ccy,product,dr_cr,booking_date\n"
        "T1,C001,100.50,USD,wire,in,2026-01-15\n"
        "T2,C002,5000.00,USD,wire,out,2026-01-16\n",
        encoding="utf-8",
    )
    customer = tmp_path / "customer.csv"
    customer.write_text(
        "cif,client_name,country_code,risk_tier,onboarding_date\n"
        "C001,Alice,US,low,2024-01-01\n"
        "C002,Bob,DE,medium,2024-03-15\n",
        encoding="utf-8",
    )
    return tmp_path


# ---------------------------------------------------------------------------
# CSV profiling
# ---------------------------------------------------------------------------


def test_profile_csv_detects_column_types(warehouse_csvs: Path) -> None:
    profiles = profile_csv(warehouse_csvs / "txn.csv")
    assert profiles["trx_id"].inferred_type == "string"
    assert profiles["amt"].inferred_type == "decimal"
    assert profiles["booking_date"].inferred_type == "timestamp"


def test_profile_csv_computes_null_rate(tmp_path: Path) -> None:
    p = tmp_path / "x.csv"
    p.write_text("a,b\n1,\n2,foo\n,baz\n", encoding="utf-8")
    profiles = profile_csv(p)
    # Column 'a' has 1 of 3 nulls = 0.333
    assert 0.3 < profiles["a"].null_rate < 0.4
    assert profiles["b"].null_rate > 0.3


def test_profile_csv_returns_empty_when_header_missing(tmp_path: Path) -> None:
    p = tmp_path / "empty.csv"
    p.write_text("", encoding="utf-8")
    assert profile_csv(p) == {}


def test_profile_csv_caps_sample_at_max_rows(tmp_path: Path) -> None:
    p = tmp_path / "big.csv"
    p.write_text("a\n" + "\n".join(f"{i}" for i in range(10_000)) + "\n", encoding="utf-8")
    profiles = profile_csv(p, max_rows=100)
    # n_unique caps at the sample, not the file size
    assert profiles["a"].n_unique <= 100


# ---------------------------------------------------------------------------
# Mapping suggestion
# ---------------------------------------------------------------------------


def _profile(name: str, t: str = "string") -> ColumnProfile:
    return ColumnProfile(name=name, inferred_type=t, null_rate=0.0, sample_values=[])


def test_exact_name_match_is_full_confidence() -> None:
    src = {"customer_id": _profile("customer_id")}
    m = suggest_mapping("customer_id", "string", src)
    assert m.confidence == 1.0
    assert m.suggested_source_column == "customer_id"


def test_alias_match_uses_known_synonyms() -> None:
    src = {"cif": _profile("cif")}
    m = suggest_mapping("customer_id", "string", src)
    assert m.suggested_source_column == "cif"
    assert m.confidence == 0.85
    assert "synonym" in m.reason.lower()


def test_substring_match_drops_to_medium_confidence() -> None:
    src = {"customer_id_legacy": _profile("customer_id_legacy")}
    m = suggest_mapping("customer_id", "string", src)
    assert m.suggested_source_column == "customer_id_legacy"
    assert m.confidence == 0.6


def test_type_only_match_is_low_confidence_and_only_when_unique() -> None:
    src = {
        "weird_field_with_no_signal": ColumnProfile(
            name="weird_field_with_no_signal",
            inferred_type="decimal",
            null_rate=0.0,
            sample_values=[],
        )
    }
    m = suggest_mapping("amount", "decimal", src)
    assert m.suggested_source_column == "weird_field_with_no_signal"
    assert m.confidence == 0.3
    assert "verify" in m.reason.lower()


def test_no_suggestion_when_multiple_typed_candidates() -> None:
    src = {
        "f1": ColumnProfile(name="f1", inferred_type="decimal", null_rate=0.0, sample_values=[]),
        "f2": ColumnProfile(name="f2", inferred_type="decimal", null_rate=0.0, sample_values=[]),
    }
    m = suggest_mapping("amount", "decimal", src)
    assert m.suggested_source_column is None
    assert m.confidence == 0.0


def test_no_match_returns_explicit_null() -> None:
    """No name signal AND no type-only escape hatch → explicit null."""
    src = {
        # Two typed candidates → type-only match doesn't fire (ambiguous).
        "some_unrelated_decimal": _profile("some_unrelated_decimal", "decimal"),
        "another_decimal": _profile("another_decimal", "decimal"),
    }
    m = suggest_mapping("customer_id", "string", src)
    assert m.suggested_source_column is None
    assert m.confidence == 0.0


@pytest.mark.parametrize(
    "spec_col,known_alias",
    [
        ("customer_id", "cif"),
        ("amount", "amt"),
        ("currency", "ccy"),
        ("channel", "product"),
        ("booked_at", "booking_date"),
        ("full_name", "client_name"),
        ("country", "country_code"),
        ("risk_rating", "risk_tier"),
    ],
)
def test_aliases_resolve_for_canonical_names(spec_col: str, known_alias: str) -> None:
    """If a real warehouse uses a known alias, the wizard must map it.
    Catches accidental removal from `COLUMN_ALIASES`."""
    assert known_alias in COLUMN_ALIASES.get(spec_col, [])


# ---------------------------------------------------------------------------
# End-to-end: spec + warehouse → mapping report
# ---------------------------------------------------------------------------


def test_map_spec_to_data_dir_with_realistic_warehouse(warehouse_csvs: Path) -> None:
    spec = load_spec(
        Path(__file__).resolve().parent.parent / "examples" / "community_bank" / "aml.yaml"
    )
    reports = map_spec_to_data_dir(spec, warehouse_csvs)
    assert {r.contract_id for r in reports} >= {"txn", "customer"}
    txn_report = next(r for r in reports if r.contract_id == "txn")
    # Every column should get a mapping (alias path catches the non-canonical names)
    for m in txn_report.mappings:
        assert m.suggested_source_column is not None, f"Failed to map {m.spec_column!r}: {m.reason}"


def test_map_spec_to_data_dir_when_file_missing(tmp_path: Path) -> None:
    """Empty data_dir → every column reported as 'no source file'."""
    spec = load_spec(
        Path(__file__).resolve().parent.parent / "examples" / "community_bank" / "aml.yaml"
    )
    reports = map_spec_to_data_dir(spec, tmp_path)
    assert reports
    for r in reports:
        assert r.unmapped_required == r.mappings
        assert all("No source file" in m.reason for m in r.mappings)


def test_render_mapping_yaml_round_trips(warehouse_csvs: Path) -> None:
    spec = load_spec(
        Path(__file__).resolve().parent.parent / "examples" / "community_bank" / "aml.yaml"
    )
    reports = map_spec_to_data_dir(spec, warehouse_csvs)
    yaml_text = render_mapping_yaml(reports)
    assert "version: 1" in yaml_text
    assert "contracts:" in yaml_text
    assert "spec_column: customer_id" in yaml_text
    # Alias mapping should be visible in the output
    assert "source_column: cif" in yaml_text


def test_render_mapping_yaml_marks_unmapped_with_FILL_marker(tmp_path: Path) -> None:
    spec = load_spec(
        Path(__file__).resolve().parent.parent / "examples" / "community_bank" / "aml.yaml"
    )
    reports = map_spec_to_data_dir(spec, tmp_path)  # empty dir → no mappings
    yaml_text = render_mapping_yaml(reports)
    assert "FILL THIS IN" in yaml_text


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


SPEC_PATH = Path(__file__).resolve().parent.parent / "examples" / "community_bank" / "aml.yaml"


def test_cli_byod_writes_mapping_yaml(
    runner: CliRunner, warehouse_csvs: Path, tmp_path: Path
) -> None:
    out = tmp_path / "data_mapping.yaml"
    result = runner.invoke(app, ["byod", str(SPEC_PATH), str(warehouse_csvs), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert "version: 1" in out.read_text()


def test_cli_byod_warns_about_unmapped_columns(runner: CliRunner, tmp_path: Path) -> None:
    out = tmp_path / "data_mapping.yaml"
    result = runner.invoke(app, ["byod", str(SPEC_PATH), str(tmp_path), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "no suggestion" in result.output.lower()


def test_cli_byod_renders_summary_table(
    runner: CliRunner, warehouse_csvs: Path, tmp_path: Path
) -> None:
    out = tmp_path / "data_mapping.yaml"
    result = runner.invoke(app, ["byod", str(SPEC_PATH), str(warehouse_csvs), "--out", str(out)])
    assert "Mapping report" in result.output
    assert "txn" in result.output
    assert "customer" in result.output
