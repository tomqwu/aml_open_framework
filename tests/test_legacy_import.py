"""Tests for PR-A1 — legacy rule inventory + import wizard.

Issue #362 promise: a CLI that takes a legacy rule export (CSV or
JSON dump from SAS / Oracle / IMS / Actimize / Mantas) and produces a
starter `rules:` block for the AML spec. These tests pin the
behaviour for the three common shapes (SQL / threshold / narrative)
plus the tolerant edge cases (malformed rows, header aliases, mixed
shapes in one dump) so future refactors can't silently drop a row a
real bank's export depends on.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aml_framework.cli import app
from aml_framework.generators.legacy_import import (
    LegacyRuleRow,
    ParseWarning,
    build_spec_skeleton,
    classify_row,
    inventory_summary,
    parse_legacy_csv,
    parse_legacy_csv_with_warnings,
    parse_legacy_json,
    parse_legacy_json_with_warnings,
    to_aml_rule_stub,
)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# Model — frozen / extra=forbid
# ---------------------------------------------------------------------------


def test_legacy_rule_row_is_frozen() -> None:
    row = LegacyRuleRow(rule_id="r1", name="Rule 1")
    with pytest.raises(Exception):  # noqa: PT011 — pydantic ValidationError
        row.name = "mutated"  # type: ignore[misc]


def test_legacy_rule_row_rejects_extra_fields() -> None:
    with pytest.raises(Exception):  # noqa: PT011 — pydantic ValidationError
        LegacyRuleRow(rule_id="r1", name="Rule 1", unknown_field="x")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# CSV parsing — happy paths
# ---------------------------------------------------------------------------


def _write_csv(path: Path, headers: list[str], rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(row)


def test_parse_csv_sql_shape(tmp_path: Path) -> None:
    path = tmp_path / "sas_export.csv"
    _write_csv(
        path,
        ["rule_id", "name", "sql_text"],
        [["R001", "Cash structuring", "SELECT * FROM txn WHERE amount > 9500"]],
    )
    rows = parse_legacy_csv(path)
    assert len(rows) == 1
    assert rows[0].rule_id == "R001"
    assert rows[0].legacy_sql.startswith("SELECT")
    assert rows[0].threshold_block is None


def test_parse_csv_threshold_shape(tmp_path: Path) -> None:
    path = tmp_path / "actimize_export.csv"
    _write_csv(
        path,
        ["rule_id", "name", "threshold_block"],
        [["R002", "Velocity", json.dumps({"having": {"count": {"gte": 10}}})]],
    )
    rows = parse_legacy_csv(path)
    assert rows[0].threshold_block == {"having": {"count": {"gte": 10}}}
    assert rows[0].legacy_sql is None


def test_parse_csv_narrative_shape(tmp_path: Path) -> None:
    path = tmp_path / "ims_export.csv"
    _write_csv(
        path,
        ["rule_id", "name", "description"],
        [["R003", "Round-trip", "Funds in and out within 24h to same counterparty."]],
    )
    rows = parse_legacy_csv(path)
    assert rows[0].narrative.startswith("Funds in")
    assert rows[0].legacy_sql is None
    assert rows[0].threshold_block is None


def test_parse_csv_header_aliases_normalise(tmp_path: Path) -> None:
    """Headers like 'Rule ID' / 'RULE_ID' / 'rule id' all map to rule_id."""
    path = tmp_path / "weird_headers.csv"
    _write_csv(
        path,
        ["Rule ID", "Scenario Name", "SQL", "Regulator Refs"],
        [["R004", "Wire layering", "SELECT 1", "FATF R.10|FATF R.20"]],
    )
    rows = parse_legacy_csv(path)
    assert rows[0].rule_id == "R004"
    assert rows[0].name == "Wire layering"
    assert rows[0].regulator_refs == ["FATF R.10", "FATF R.20"]


def test_parse_csv_ignores_unknown_columns(tmp_path: Path) -> None:
    path = tmp_path / "noisy.csv"
    _write_csv(
        path,
        ["rule_id", "name", "junk", "sql"],
        [["R005", "n", "ignored", "SELECT 1"]],
    )
    rows = parse_legacy_csv(path)
    assert len(rows) == 1
    assert rows[0].legacy_sql == "SELECT 1"


def test_parse_csv_missing_rule_id_warns(tmp_path: Path) -> None:
    path = tmp_path / "no_id.csv"
    _write_csv(
        path,
        ["rule_id", "name", "sql"],
        [["", "no id", "SELECT 1"], ["R006", "ok", "SELECT 2"]],
    )
    result = parse_legacy_csv_with_warnings(path)
    assert len(result.rows) == 1
    assert result.rows[0].rule_id == "R006"
    assert len(result.warnings) == 1
    assert result.warnings[0].reason == "missing rule_id"


def test_parse_csv_missing_name_falls_back_to_rule_id(tmp_path: Path) -> None:
    path = tmp_path / "no_name.csv"
    _write_csv(path, ["rule_id", "name", "sql"], [["R007", "", "SELECT 1"]])
    rows = parse_legacy_csv(path)
    assert rows[0].name == "R007"


def test_parse_csv_malformed_threshold_json_warns(tmp_path: Path) -> None:
    path = tmp_path / "bad_json.csv"
    _write_csv(
        path,
        ["rule_id", "name", "thresholds"],
        [["R008", "bad", "{not json"], ["R009", "good", '{"a": 1}']],
    )
    result = parse_legacy_csv_with_warnings(path)
    assert [r.rule_id for r in result.rows] == ["R009"]
    assert len(result.warnings) == 1
    assert "JSON" in result.warnings[0].reason
    assert result.warnings[0].rule_id == "R008"


def test_parse_csv_empty_file_warns(tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    result = parse_legacy_csv_with_warnings(path)
    assert result.rows == []
    assert result.warnings and "empty CSV" in result.warnings[0].reason


def test_parse_csv_no_recognised_columns_warns(tmp_path: Path) -> None:
    path = tmp_path / "useless.csv"
    _write_csv(path, ["foo", "bar"], [["1", "2"]])
    result = parse_legacy_csv_with_warnings(path)
    assert result.rows == []
    assert any("no recognised columns" in w.reason for w in result.warnings)


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------


def test_parse_json_list_root(tmp_path: Path) -> None:
    path = tmp_path / "dump.json"
    path.write_text(
        json.dumps(
            [
                {"rule_id": "R010", "name": "n", "legacy_sql": "SELECT 1"},
                {
                    "rule_id": "R011",
                    "name": "n2",
                    "threshold_block": {"having": {"sum": {"gte": 100}}},
                },
            ]
        ),
        encoding="utf-8",
    )
    rows = parse_legacy_json(path)
    assert {r.rule_id for r in rows} == {"R010", "R011"}


def test_parse_json_rules_envelope(tmp_path: Path) -> None:
    path = tmp_path / "wrapped.json"
    path.write_text(
        json.dumps({"rules": [{"rule_id": "R012", "name": "n", "narrative": "human prose"}]}),
        encoding="utf-8",
    )
    rows = parse_legacy_json(path)
    assert rows[0].narrative == "human prose"


def test_parse_json_dict_without_rules_key_warns(tmp_path: Path) -> None:
    path = tmp_path / "wrong_shape.json"
    path.write_text(json.dumps({"items": []}), encoding="utf-8")
    result = parse_legacy_json_with_warnings(path)
    assert result.rows == []
    assert any("missing 'rules' key" in w.reason for w in result.warnings)


def test_parse_json_scalar_root_warns(tmp_path: Path) -> None:
    path = tmp_path / "scalar.json"
    path.write_text("42", encoding="utf-8")
    result = parse_legacy_json_with_warnings(path)
    assert result.rows == []
    assert any("JSON root is int" in w.reason for w in result.warnings)


def test_parse_json_non_object_entry_warns(tmp_path: Path) -> None:
    path = tmp_path / "mixed.json"
    path.write_text(
        json.dumps([{"rule_id": "R013", "name": "ok"}, "not an object"]), encoding="utf-8"
    )
    result = parse_legacy_json_with_warnings(path)
    assert [r.rule_id for r in result.rows] == ["R013"]
    assert any("expected object" in w.reason for w in result.warnings)


def test_parse_json_regulator_refs_as_list(tmp_path: Path) -> None:
    path = tmp_path / "refs.json"
    path.write_text(
        json.dumps([{"rule_id": "R014", "name": "n", "regulator_refs": ["FATF R.10", "BSA"]}]),
        encoding="utf-8",
    )
    rows = parse_legacy_json(path)
    assert rows[0].regulator_refs == ["FATF R.10", "BSA"]


# ---------------------------------------------------------------------------
# Stub rendering
# ---------------------------------------------------------------------------


def test_to_stub_sql_row_uses_custom_sql() -> None:
    row = LegacyRuleRow(rule_id="r1", name="n", legacy_sql="SELECT 1")
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["type"] == "custom_sql"
    assert stub["logic"]["sql"] == "SELECT 1"
    assert "legacy_import" in stub["tags"]


def test_to_stub_threshold_row_uses_aggregation_window() -> None:
    row = LegacyRuleRow(
        rule_id="r2", name="n", threshold_block={"having": {"sum": {"gte": 100000}}}
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["type"] == "aggregation_window"
    assert stub["logic"]["having"] == {"sum": {"gte": 100000}}


def test_to_stub_threshold_without_having_key_falls_back() -> None:
    """A bare threshold block (no 'having' wrapper) is still preserved."""
    row = LegacyRuleRow(rule_id="r3", name="n", threshold_block={"min_amount": 9500})
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["having"] == {"min_amount": 9500}


def test_to_stub_narrative_row_emits_todo_placeholder() -> None:
    row = LegacyRuleRow(rule_id="r4", name="n", narrative="Round-trip 24h")
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["type"] == "aggregation_window"
    assert "needs_manual_conversion" in stub["tags"]
    assert "TODO" in stub["business_intent"]
    assert "Round-trip 24h" in stub["business_intent"]


def test_to_stub_empty_row_emits_todo_placeholder() -> None:
    row = LegacyRuleRow(rule_id="r5", name="n")
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["type"] == "aggregation_window"
    assert "needs_manual_conversion" in stub["tags"]
    assert "(none supplied)" in stub["business_intent"]


def test_to_stub_regulator_refs_propagate() -> None:
    row = LegacyRuleRow(rule_id="r6", name="n", legacy_sql="SELECT 1", regulator_refs=["FATF R.10"])
    stub = to_aml_rule_stub(row)
    assert stub["regulation_refs"][0]["citation"] == "FATF R.10"


def test_to_stub_missing_regulator_refs_emits_todo() -> None:
    row = LegacyRuleRow(rule_id="r7", name="n", legacy_sql="SELECT 1")
    stub = to_aml_rule_stub(row)
    assert "TODO" in stub["regulation_refs"][0]["citation"]


# ---------------------------------------------------------------------------
# Summary + classification
# ---------------------------------------------------------------------------


def test_classify_row_buckets() -> None:
    assert classify_row(LegacyRuleRow(rule_id="a", name="a", legacy_sql="x")) == "ready_sql"
    assert (
        classify_row(LegacyRuleRow(rule_id="a", name="a", threshold_block={"x": 1}))
        == "ready_threshold"
    )
    assert classify_row(LegacyRuleRow(rule_id="a", name="a", narrative="x")) == "needs_manual"
    assert classify_row(LegacyRuleRow(rule_id="a", name="a")) == "needs_manual"


def test_inventory_summary_rollup() -> None:
    rows = [
        LegacyRuleRow(rule_id="a", name="a", legacy_sql="x"),
        LegacyRuleRow(rule_id="b", name="b", threshold_block={"x": 1}),
        LegacyRuleRow(rule_id="c", name="c", narrative="x"),
        LegacyRuleRow(rule_id="d", name="d"),
        LegacyRuleRow(rule_id="a", name="dup", legacy_sql="y", regulator_refs=["FATF R.10"]),
    ]
    summary = inventory_summary(rows)
    assert summary["total"] == 5
    assert summary["by_shape"] == {"sql": 2, "threshold": 1, "narrative": 1, "empty": 1}
    assert summary["ready_to_import"] == 3
    assert summary["needs_manual"] == 2
    assert summary["missing_regulator_refs"] == 4
    assert summary["duplicate_rule_ids"] == ["a"]


def test_build_spec_skeleton_wraps_rows() -> None:
    rows = [LegacyRuleRow(rule_id="r1", name="n", legacy_sql="SELECT 1")]
    skeleton = build_spec_skeleton(rows)
    assert skeleton["version"] == 1
    assert skeleton["program"]["name"].startswith("TODO")
    assert len(skeleton["rules"]) == 1
    assert skeleton["rules"][0]["id"] == "r1"


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_cli_inventory_command(tmp_path: Path, runner: CliRunner) -> None:
    path = tmp_path / "dump.csv"
    _write_csv(
        path,
        ["rule_id", "name", "sql"],
        [["R001", "n", "SELECT 1"], ["R002", "n2", ""]],
    )
    result = runner.invoke(app, ["inventory", str(path)])
    assert result.exit_code == 0, result.output
    assert "Total rules parsed" in result.output
    assert "ready" in result.output.lower() or "Ready" in result.output


def test_cli_import_legacy_writes_yaml(tmp_path: Path, runner: CliRunner) -> None:
    path = tmp_path / "dump.csv"
    _write_csv(
        path,
        ["rule_id", "name", "sql"],
        [["R001", "Structuring", "SELECT * FROM txn"]],
    )
    out = tmp_path / "skeleton.yaml"
    result = runner.invoke(app, ["import-legacy", str(path), "--output", str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "R001" in content
    assert "custom_sql" in content


def test_cli_import_legacy_refuses_overwrite(tmp_path: Path, runner: CliRunner) -> None:
    path = tmp_path / "dump.csv"
    _write_csv(path, ["rule_id", "name", "sql"], [["R001", "n", "SELECT 1"]])
    out = tmp_path / "skeleton.yaml"
    out.write_text("# existing\n", encoding="utf-8")
    result = runner.invoke(app, ["import-legacy", str(path), "--output", str(out)])
    assert result.exit_code == 1
    assert "already exists" in result.output


def test_cli_import_legacy_overwrite_flag(tmp_path: Path, runner: CliRunner) -> None:
    path = tmp_path / "dump.csv"
    _write_csv(path, ["rule_id", "name", "sql"], [["R001", "n", "SELECT 1"]])
    out = tmp_path / "skeleton.yaml"
    out.write_text("# existing\n", encoding="utf-8")
    result = runner.invoke(app, ["import-legacy", str(path), "--output", str(out), "--overwrite"])
    assert result.exit_code == 0
    assert "R001" in out.read_text(encoding="utf-8")


def test_cli_import_legacy_unsupported_format(tmp_path: Path, runner: CliRunner) -> None:
    path = tmp_path / "dump.xlsx"
    path.write_bytes(b"not really xlsx")
    result = runner.invoke(app, ["import-legacy", str(path)])
    assert result.exit_code != 0
    assert "Unsupported" in result.output or "unsupported" in result.output.lower()


def test_cli_inventory_with_json_dump(tmp_path: Path, runner: CliRunner) -> None:
    path = tmp_path / "dump.json"
    path.write_text(
        json.dumps(
            {
                "rules": [
                    {"rule_id": "R100", "name": "n", "legacy_sql": "SELECT 1"},
                    {"rule_id": "R101", "name": "n2", "narrative": "Manual rule."},
                ]
            }
        ),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["inventory", str(path)])
    assert result.exit_code == 0
    assert "2" in result.output  # total
    assert "narrative" in result.output


def test_cli_inventory_surfaces_warnings(tmp_path: Path, runner: CliRunner) -> None:
    path = tmp_path / "dirty.csv"
    _write_csv(
        path,
        ["rule_id", "name", "thresholds"],
        [["R200", "n", "{broken"]],
    )
    result = runner.invoke(app, ["inventory", str(path)])
    assert result.exit_code == 0
    assert "warning" in result.output.lower()


# ---------------------------------------------------------------------------
# Coverage-pinning edges (defensive paths)
# ---------------------------------------------------------------------------


def test_regulator_refs_json_list_string() -> None:
    """A regulator_refs CSV cell that's a JSON list string is parsed as a list."""
    row, _ = _row_from_mapping_via_csv("R300", regulator_refs_cell='["FATF R.20", "BSA"]')
    assert row is not None
    assert row.regulator_refs == ["FATF R.20", "BSA"]


def test_regulator_refs_semicolon_separated() -> None:
    row, _ = _row_from_mapping_via_csv("R301", regulator_refs_cell="FATF R.10; FATF R.20")
    assert row is not None
    assert row.regulator_refs == ["FATF R.10", "FATF R.20"]


def test_regulator_refs_single_value_no_separator() -> None:
    row, _ = _row_from_mapping_via_csv("R302", regulator_refs_cell="FATF R.10")
    assert row is not None
    assert row.regulator_refs == ["FATF R.10"]


def test_parse_warning_dataclass_is_frozen() -> None:
    """ParseWarning is frozen so callers can't mutate the surfaced warning."""
    warning = ParseWarning(row_index=1, rule_id="R1", reason="x")
    with pytest.raises(Exception):  # noqa: PT011 — dataclass FrozenInstanceError
        warning.reason = "mutated"  # type: ignore[misc]


def test_threshold_empty_string_coerces_to_none(tmp_path: Path) -> None:
    """An empty thresholds cell is treated as None, not parsed."""
    path = tmp_path / "empty_thresh.csv"
    _write_csv(path, ["rule_id", "name", "thresholds", "sql"], [["R400", "n", "   ", "SELECT 1"]])
    rows = parse_legacy_csv(path)
    assert rows[0].threshold_block is None


def test_threshold_json_non_object_warns(tmp_path: Path) -> None:
    """JSON list (not object) in thresholds cell → warning, no row."""
    path = tmp_path / "thresh_list.csv"
    _write_csv(path, ["rule_id", "name", "thresholds"], [["R401", "n", "[1, 2, 3]"]])
    result = parse_legacy_csv_with_warnings(path)
    assert result.rows == []
    assert any("JSON object" in w.reason for w in result.warnings)


def test_threshold_unsupported_type_via_json(tmp_path: Path) -> None:
    """A numeric thresholds field (via JSON dump) raises a type warning."""
    path = tmp_path / "thresh_num.json"
    path.write_text(
        json.dumps([{"rule_id": "R402", "name": "n", "threshold_block": 12345}]),
        encoding="utf-8",
    )
    result = parse_legacy_json_with_warnings(path)
    assert result.rows == []
    assert any("unsupported type" in w.reason for w in result.warnings)


def test_regulator_refs_empty_string_returns_empty(tmp_path: Path) -> None:
    path = tmp_path / "empty_refs.csv"
    _write_csv(
        path,
        ["rule_id", "name", "regulator_refs", "sql"],
        [["R403", "n", "   ", "SELECT 1"]],
    )
    rows = parse_legacy_csv(path)
    assert rows[0].regulator_refs == []


def test_regulator_refs_invalid_json_list_falls_through(tmp_path: Path) -> None:
    """An opening-bracket string that fails JSON parse falls to delimiter split."""
    path = tmp_path / "bad_list.csv"
    _write_csv(
        path,
        ["rule_id", "name", "regulator_refs", "sql"],
        [["R404", "n", "[broken|FATF R.10", "SELECT 1"]],
    )
    rows = parse_legacy_csv(path)
    # Falls through to pipe split: "[broken" and "FATF R.10".
    assert rows[0].regulator_refs == ["[broken", "FATF R.10"]


def test_regulator_refs_unknown_type_via_json(tmp_path: Path) -> None:
    """A regulator_refs value that's not list/str/None returns []."""
    path = tmp_path / "weird_refs.json"
    path.write_text(
        json.dumps(
            [{"rule_id": "R405", "name": "n", "legacy_sql": "SELECT 1", "regulator_refs": 42}]
        ),
        encoding="utf-8",
    )
    rows = parse_legacy_json(path)
    assert rows[0].regulator_refs == []


def test_csv_none_cell_skipped(tmp_path: Path) -> None:
    """A None cell value (short row) is skipped without crashing.

    csv.DictReader returns None for cells absent when row is shorter
    than the header — this pins that path.
    """
    path = tmp_path / "short_row.csv"
    # Write a row with fewer cells than the header — DictReader fills
    # missing trailing cells as None.
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write("rule_id,name,sql\n")
        fh.write("R406,short\n")
    rows = parse_legacy_csv(path)
    # Row should still parse — just no SQL (missing trailing column).
    assert rows[0].rule_id == "R406"
    assert rows[0].legacy_sql is None


def test_json_entry_with_unknown_keys_only(tmp_path: Path) -> None:
    """JSON entry with only unrecognised keys → missing rule_id warning."""
    path = tmp_path / "junk.json"
    path.write_text(json.dumps([{"unknown_field": "x", "other": "y"}]), encoding="utf-8")
    result = parse_legacy_json_with_warnings(path)
    assert result.rows == []
    assert any("missing rule_id" in w.reason for w in result.warnings)


def test_json_entry_with_bad_threshold_warns_and_skips(tmp_path: Path) -> None:
    """JSON entry with non-dict threshold → row warning surfaced."""
    path = tmp_path / "bad_thresh.json"
    path.write_text(
        json.dumps([{"rule_id": "R407", "name": "n", "threshold_block": "not-a-dict"}]),
        encoding="utf-8",
    )
    result = parse_legacy_json_with_warnings(path)
    # Non-dict string that isn't JSON object → warning, no row.
    assert result.rows == []
    assert any("R407" == w.rule_id for w in result.warnings)


def _row_from_mapping_via_csv(
    rule_id: str, *, regulator_refs_cell: str
) -> tuple[LegacyRuleRow | None, ParseWarning | None]:
    """Helper: round-trip a regulator_refs cell through the CSV parser."""
    import io

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["rule_id", "name", "regulator_refs", "sql"])
    writer.writerow([rule_id, "n", regulator_refs_cell, "SELECT 1"])
    path = Path("/tmp/_legacy_import_test.csv")  # noqa: S108 — test scratch
    path.write_text(buf.getvalue(), encoding="utf-8")
    result = parse_legacy_csv_with_warnings(path)
    return (
        result.rows[0] if result.rows else None,
        result.warnings[0] if result.warnings else None,
    )
