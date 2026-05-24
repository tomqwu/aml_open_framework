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
    """Malformed thresholds → row kept as placeholder + warning emitted."""
    path = tmp_path / "bad_json.csv"
    _write_csv(
        path,
        ["rule_id", "name", "thresholds"],
        [["R008", "bad", "{not json"], ["R009", "good", '{"a": 1}']],
    )
    result = parse_legacy_csv_with_warnings(path)
    # Both rows present; R008's threshold is None (dropped + warned).
    assert [r.rule_id for r in result.rows] == ["R008", "R009"]
    assert result.rows[0].threshold_block is None
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
    """A bare threshold block (no 'having' wrapper) uses the metric directly."""
    row = LegacyRuleRow(rule_id="r3", name="n", threshold_block={"sum_amount": {"gte": 9500}})
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["having"] == {"sum_amount": {"gte": 9500}}


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
        classify_row(LegacyRuleRow(rule_id="a", name="a", threshold_block={"count": {"gte": 1}}))
        == "ready_threshold"
    )
    assert classify_row(LegacyRuleRow(rule_id="a", name="a", narrative="x")) == "needs_manual"
    assert classify_row(LegacyRuleRow(rule_id="a", name="a")) == "needs_manual"


def test_inventory_summary_rollup() -> None:
    rows = [
        LegacyRuleRow(rule_id="a", name="a", legacy_sql="x"),
        LegacyRuleRow(rule_id="b", name="b", threshold_block={"count": {"gte": 10}}),
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


def test_cli_import_legacy_aborts_on_empty_parse(tmp_path: Path, runner: CliRunner) -> None:
    """`import-legacy` exits non-zero when no rows parse.

    Regression for codex review P2: previously the CLI would write
    an empty `rules: []` skeleton and exit successfully, hiding the
    migration workload until someone noticed the "0 rule(s)" message.
    """
    path = tmp_path / "no_headers.csv"
    _write_csv(path, ["foo", "bar"], [["1", "2"]])
    out = tmp_path / "skeleton.yaml"
    result = runner.invoke(app, ["import-legacy", str(path), "--output", str(out)])
    assert result.exit_code == 1
    assert "No legacy rules parsed" in result.output
    # Must NOT have written the empty skeleton.
    assert not out.exists()


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
    """JSON list (not object) in thresholds cell → placeholder row + warning."""
    path = tmp_path / "thresh_list.csv"
    _write_csv(path, ["rule_id", "name", "thresholds"], [["R401", "n", "[1, 2, 3]"]])
    result = parse_legacy_csv_with_warnings(path)
    # Row kept as a placeholder so migration completeness is preserved.
    assert [r.rule_id for r in result.rows] == ["R401"]
    assert result.rows[0].threshold_block is None
    assert any("JSON object" in w.reason for w in result.warnings)


def test_threshold_unsupported_type_via_json(tmp_path: Path) -> None:
    """A numeric thresholds field → placeholder row + warning."""
    path = tmp_path / "thresh_num.json"
    path.write_text(
        json.dumps([{"rule_id": "R402", "name": "n", "threshold_block": 12345}]),
        encoding="utf-8",
    )
    result = parse_legacy_json_with_warnings(path)
    assert [r.rule_id for r in result.rows] == ["R402"]
    assert result.rows[0].threshold_block is None
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
    """JSON entry with non-dict threshold → placeholder row + warning."""
    path = tmp_path / "bad_thresh.json"
    path.write_text(
        json.dumps([{"rule_id": "R407", "name": "n", "threshold_block": "not-a-dict"}]),
        encoding="utf-8",
    )
    result = parse_legacy_json_with_warnings(path)
    # Row kept as placeholder so the legacy rule_id doesn't disappear.
    assert [r.rule_id for r in result.rows] == ["R407"]
    assert result.rows[0].threshold_block is None
    assert any(w.rule_id == "R407" for w in result.warnings)


def test_sql_row_with_bad_threshold_is_preserved(tmp_path: Path) -> None:
    """A row with both SQL and a malformed threshold keeps the SQL.

    Regression for codex review P2: previously, a bad threshold blob
    next to a usable SQL string would drop the entire row. Legacy
    dumps frequently ship parameters alongside SQL, so the SQL must
    win and the bad threshold is surfaced as a warning.
    """
    path = tmp_path / "mixed.csv"
    _write_csv(
        path,
        ["rule_id", "name", "sql", "thresholds"],
        [["R500", "Structuring", "SELECT * FROM txn", "{not json"]],
    )
    result = parse_legacy_csv_with_warnings(path)
    assert len(result.rows) == 1
    assert result.rows[0].legacy_sql == "SELECT * FROM txn"
    assert result.rows[0].threshold_block is None
    assert len(result.warnings) == 1
    assert "kept SQL" in result.warnings[0].reason


def test_stub_sanitises_uppercase_legacy_id() -> None:
    """`R001` → `r001` so the emitted spec passes `aml validate`.

    Regression for codex review P2: AML spec requires
    `^[a-z][a-z0-9_]*$` for `Rule.id`. `R001` lowercases cleanly to
    `r001` which matches the pattern, but the original is preserved
    as a `legacy_id:` tag for traceability.
    """
    row = LegacyRuleRow(rule_id="R001", name="n", legacy_sql="SELECT 1")
    stub = to_aml_rule_stub(row)
    assert stub["id"] == "r001"
    assert "legacy_id:R001" in stub["tags"]


def test_stub_sanitises_dotted_legacy_id() -> None:
    """`CASH.STRUCT.01` → `cash_struct_01` with original preserved as tag."""
    row = LegacyRuleRow(rule_id="CASH.STRUCT.01", name="n", legacy_sql="SELECT 1")
    stub = to_aml_rule_stub(row)
    assert stub["id"] == "cash_struct_01"
    assert "legacy_id:CASH.STRUCT.01" in stub["tags"]


def test_stub_keeps_double_underscore_id_untouched() -> None:
    """`cash__struct_01` already matches the safe pattern — preserve it.

    Regression for codex review P2: previously collapsed `__` → `_`,
    which would create an artificial collision with a different
    legitimate ID like `cash_struct_01`.
    """
    row = LegacyRuleRow(rule_id="cash__struct_01", name="n", legacy_sql="SELECT 1")
    stub = to_aml_rule_stub(row)
    assert stub["id"] == "cash__struct_01"
    # No `legacy_id:` tag — the ID wasn't rewritten.
    assert not any(t.startswith("legacy_id:") for t in stub["tags"])


def test_stub_keeps_trailing_underscore_id_untouched() -> None:
    """`rule_` already matches the safe pattern — preserve it."""
    row = LegacyRuleRow(rule_id="rule_", name="n", legacy_sql="SELECT 1")
    stub = to_aml_rule_stub(row)
    assert stub["id"] == "rule_"


def test_stub_keeps_already_safe_id_untouched() -> None:
    row = LegacyRuleRow(rule_id="structuring_below_threshold", name="n", legacy_sql="SELECT 1")
    stub = to_aml_rule_stub(row)
    assert stub["id"] == "structuring_below_threshold"
    # No `legacy_id:` tag when the ID wasn't rewritten.
    assert not any(t.startswith("legacy_id:") for t in stub["tags"])


def test_stub_sanitises_dash_separated_id() -> None:
    """`scenario-1` (dashes + digit) sanitises and gets the `legacy_` prefix."""
    row = LegacyRuleRow(rule_id="scenario-1", name="n", narrative="x")
    stub = to_aml_rule_stub(row)
    assert stub["id"] == "scenario_1"
    # `scenario_1` already matches the safe pattern (lowercase + underscore),
    # so no `legacy_` prefix needed — but the original had a `-` so we tag it.
    assert "legacy_id:scenario-1" in stub["tags"]


def test_stub_sanitises_pure_digit_id() -> None:
    """A digit-only ID `42` becomes `legacy_42` since it can't start with a digit."""
    row = LegacyRuleRow(rule_id="42", name="n", legacy_sql="SELECT 1")
    stub = to_aml_rule_stub(row)
    assert stub["id"] == "legacy_42"
    assert "legacy_id:42" in stub["tags"]


def test_stub_sanitises_unrecoverable_id_to_legacy_unknown() -> None:
    """A pathological ID with nothing extractable falls back to `legacy_unknown`."""
    row = LegacyRuleRow(rule_id="!!!!", name="n", legacy_sql="SELECT 1")
    stub = to_aml_rule_stub(row)
    assert stub["id"] == "legacy_unknown"


def test_stub_preserves_threshold_siblings() -> None:
    """A threshold blob with `having` + other keys keeps the full blob.

    Regression for codex review P2: previously only the inner `having`
    was extracted, dropping siblings like `window`, `source`, etc. Now
    the legacy keys are lifted into the logic block where they map
    cleanly and the full blob is preserved as a JSON-serialised tag
    so the stub stays schema-valid (Rule disallows extra fields).
    """
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={
            "window": "7d",
            "source": "wire_txn",
            "group_by": ["account_id"],
            "having": {"sum": {"gte": 100000}},
            "vendor_param": "legacy_only",
        },
    )
    stub = to_aml_rule_stub(row)
    # `having` extracted; sibling legacy keys lifted into the logic block.
    assert stub["logic"]["having"] == {"sum": {"gte": 100000}}
    assert stub["logic"]["window"] == "7d"
    assert stub["logic"]["source"] == "wire_txn"
    assert stub["logic"]["group_by"] == ["account_id"]
    # The full blob is preserved as a tag for reconciliation.
    threshold_tags = [t for t in stub["tags"] if t.startswith("legacy_threshold_block:")]
    assert len(threshold_tags) == 1
    blob_json = threshold_tags[0].removeprefix("legacy_threshold_block:")
    assert json.loads(blob_json)["vendor_param"] == "legacy_only"


def test_stub_threshold_block_without_having_uses_blob_as_having() -> None:
    """A threshold blob without a `having` key uses metric-only fields."""
    row = LegacyRuleRow(rule_id="r1", name="n", threshold_block={"count": {"gte": 5}})
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["having"] == {"count": {"gte": 5}}
    # Blob still preserved as tag.
    assert any(t.startswith("legacy_threshold_block:") for t in stub["tags"])


def test_stub_threshold_block_metadata_excluded_from_having() -> None:
    """A no-having blob with metadata keys excludes them from the fallback having.

    Regression for codex review P2: previously
    `{'source': 'txn', 'window': '7d', 'group_by': [...], 'count': {'gte': 10}}`
    copied the entire blob into `logic.having`, making the engine
    treat `source`/`window`/`group_by` as aggregate metrics and
    crashing `compile_rule_sql` at runtime.
    """
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={
            "source": "txn",
            "window": "7d",
            "group_by": ["customer_id"],
            "count": {"gte": 10},
        },
    )
    stub = to_aml_rule_stub(row)
    # `count` is the only metric → lifted to having.
    assert stub["logic"]["having"] == {"count": {"gte": 10}}
    # Metadata mapped into logic block.
    assert stub["logic"]["source"] == "txn"
    assert stub["logic"]["window"] == "7d"
    assert stub["logic"]["group_by"] == ["customer_id"]


def test_stub_threshold_block_metadata_only_falls_back_to_count() -> None:
    """A blob with ONLY metadata (no metric) gets a safe placeholder."""
    row = LegacyRuleRow(rule_id="r1", name="n", threshold_block={"source": "txn", "window": "1d"})
    stub = to_aml_rule_stub(row)
    # No real metric → safe placeholder so the stub is engine-compatible.
    assert stub["logic"]["having"] == {"count": {"gte": 1}}


def test_stub_with_threshold_validates_through_pydantic_rule() -> None:
    """The threshold-bearing stub round-trips through the Rule model.

    Pins that the stub stays schema-valid: a real spec author only
    has to fix the `TODO_source_contract` placeholder + add an
    `escalate_to` queue + a regulation citation, not also strip
    extra fields the importer left behind.
    """
    from aml_framework.spec.models import Rule

    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"window": "7d", "having": {"count": {"gte": 10}}},
        regulator_refs=["FATF R.10"],
    )
    stub = to_aml_rule_stub(row)
    # Patch the `TODO_source_contract` placeholder — the Pydantic
    # Rule model has no constraint on the source string, but engine
    # compilation would fail without a real contract. For schema
    # validation it's fine as-is.
    Rule.model_validate(stub)


def test_stub_threshold_with_filter_lifts_into_logic() -> None:
    """A threshold block with a `filter` key lifts it into `logic.filter`.

    Regression for codex review P2: previously the `filter` key was
    either silently dropped (when `having` was explicit) or shoved
    into `having` (causing the engine to crash with "unsupported
    having metric 'filter'").
    """
    row = LegacyRuleRow(
        rule_id="r1",
        name="cash-only structuring",
        threshold_block={
            "filter": {"channel": "cash", "amount": {"gte": 9500}},
            "having": {"count": {"gte": 3}},
        },
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["filter"] == {"channel": "cash", "amount": {"gte": 9500}}
    assert stub["logic"]["having"] == {"count": {"gte": 3}}


def test_stub_threshold_filter_excluded_from_derived_having() -> None:
    """A no-having blob with a `filter` key keeps it out of derived having."""
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"filter": {"channel": "cash"}, "count": {"gte": 5}},
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["having"] == {"count": {"gte": 5}}
    assert stub["logic"]["filter"] == {"channel": "cash"}


def test_row_with_only_bad_threshold_still_imports_as_placeholder(tmp_path: Path) -> None:
    """A row with rule_id + bad threshold (no SQL, no narrative) still imports.

    Regression for codex review P2: previously a corrupted threshold
    cell could silently delete a legacy rule from the skeleton.
    Migration completeness requires the placeholder + a warning so
    the operator sees every legacy rule_id in the output.
    """
    path = tmp_path / "only_bad.csv"
    _write_csv(
        path,
        ["rule_id", "name", "thresholds"],
        [["R_ONLY_BAD", "n", "{broken"]],
    )
    result = parse_legacy_csv_with_warnings(path)
    assert len(result.rows) == 1
    assert result.rows[0].rule_id == "R_ONLY_BAD"
    assert result.rows[0].threshold_block is None
    assert any("kept rule_id only" in w.reason for w in result.warnings)


def test_narrative_row_kept_when_threshold_parsing_fails(tmp_path: Path) -> None:
    """A narrative-bearing row with a bad threshold still imports.

    Regression for codex review P2: previously a row with usable
    narrative but a malformed threshold cell was dropped entirely
    from the skeleton because the threshold-parse failure short-
    circuited before reading the narrative.
    """
    path = tmp_path / "mixed.csv"
    _write_csv(
        path,
        ["rule_id", "name", "description", "thresholds"],
        [["R900", "Round-trip", "Funds in and out within 24h", "{not json"]],
    )
    result = parse_legacy_csv_with_warnings(path)
    assert len(result.rows) == 1
    assert result.rows[0].narrative.startswith("Funds in")
    assert result.rows[0].threshold_block is None
    assert any("kept narrative" in w.reason for w in result.warnings)


def test_sql_row_with_narrative_preserves_rationale() -> None:
    """A row with both SQL and narrative carries the narrative as business_intent.

    Regression for codex review P3: previously the SQL-row early
    return dropped the narrative, losing the legacy rule rationale.
    """
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        legacy_sql="SELECT 1",
        narrative="Flags wires above $10k to high-risk countries.",
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["type"] == "custom_sql"
    assert stub["business_intent"].startswith("Flags wires")


def test_threshold_row_with_narrative_preserves_rationale() -> None:
    """A threshold + narrative row carries the narrative into business_intent."""
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"having": {"count": {"gte": 5}}},
        narrative="Velocity rule from SAS scenario library.",
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["type"] == "aggregation_window"
    assert "Velocity rule" in stub["business_intent"]


def test_sql_row_preserves_threshold_block_as_tag() -> None:
    """A SQL-bearing row with a parameter blob keeps the blob as a tag.

    Regression for codex review P2: previously parameterised SQL
    exports lost their parameter values from the generated YAML
    because the SQL branch returned before adding the
    `legacy_threshold_block:` tag.
    """
    row = LegacyRuleRow(
        rule_id="r1",
        name="parameterised",
        legacy_sql="SELECT * FROM txn WHERE amount > :threshold",
        threshold_block={"threshold": 9500, "lookback_days": 7},
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["type"] == "custom_sql"
    threshold_tags = [t for t in stub["tags"] if t.startswith("legacy_threshold_block:")]
    assert len(threshold_tags) == 1
    blob = json.loads(threshold_tags[0].removeprefix("legacy_threshold_block:"))
    assert blob["threshold"] == 9500
    assert blob["lookback_days"] == 7


def test_threshold_window_int_coerces_to_days() -> None:
    """`window: 30` (integer) → `"30d"` so the spec accepts it."""
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"window": 30, "having": {"count": {"gte": 5}}},
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["window"] == "30d"


def test_threshold_window_float_coerces_to_days() -> None:
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"window": 7.0, "having": {"count": {"gte": 5}}},
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["window"] == "7d"


def test_threshold_window_string_of_int_coerces() -> None:
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"window": "14", "having": {"count": {"gte": 5}}},
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["window"] == "14d"


def test_threshold_window_valid_pattern_passes_through() -> None:
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"window": "6h", "having": {"count": {"gte": 5}}},
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["window"] == "6h"


def test_threshold_window_unrecognised_falls_back() -> None:
    """An unrecognised window value falls back to the default `30d`."""
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"window": True, "having": {"count": {"gte": 5}}},
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["window"] == "30d"


def test_threshold_window_negative_int_falls_back() -> None:
    """A negative `window: -7` falls back to `30d` (would violate spec pattern).

    Regression for codex review P3: previously emitted `-7d`, which
    fails the `^[0-9]+[smhd]$` window pattern.
    """
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"window": -7, "having": {"count": {"gte": 5}}},
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["window"] == "30d"


def test_threshold_window_zero_falls_back() -> None:
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"window": 0, "having": {"count": {"gte": 5}}},
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["window"] == "30d"


def test_threshold_window_negative_float_falls_back() -> None:
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"window": -3.5, "having": {"count": {"gte": 5}}},
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["window"] == "30d"


def test_threshold_window_non_finite_float_falls_back() -> None:
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"window": float("inf"), "having": {"count": {"gte": 5}}},
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["window"] == "30d"


def test_threshold_empty_having_falls_through_to_placeholder() -> None:
    """An explicit but empty `having: {}` falls through to the derived/placeholder.

    Regression for codex review P2: previously `having: {}` was
    assigned to `logic.having`, violating the JSON Schema's
    `minProperties: 1` requirement.
    """
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"having": {}, "count": {"gte": 5}},
    )
    stub = to_aml_rule_stub(row)
    # Falls through to derived metrics → `count` is used.
    assert stub["logic"]["having"] == {"count": {"gte": 5}}


def test_threshold_only_empty_having_uses_placeholder() -> None:
    """A blob with ONLY `having: {}` (no metrics) emits the safe placeholder."""
    row = LegacyRuleRow(rule_id="r1", name="n", threshold_block={"having": {}})
    stub = to_aml_rule_stub(row)
    # Empty having + no other metrics → safe `count: {gte: 1}` placeholder.
    assert stub["logic"]["having"] == {"count": {"gte": 1}}
    # Metric-less blocks must be flagged for manual conversion so the
    # operator doesn't accidentally promote a placeholder to production.
    assert "needs_manual_conversion" in stub["tags"]


def test_threshold_metadata_only_block_flagged_as_manual() -> None:
    """A block with only metadata (no metric, no having) is flagged manual.

    Regression for codex review P2: previously a block like
    `{"source": "txn", "window": "7d", "group_by": ["customer_id"]}`
    emitted a `count >= 1` placeholder while still being classified
    as a ready threshold import, which could fire on every grouped
    entity if the operator merged the stub as-is.
    """
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={
            "source": "txn",
            "window": "7d",
            "group_by": ["customer_id"],
        },
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["having"] == {"count": {"gte": 1}}
    assert "needs_manual_conversion" in stub["tags"]


def test_threshold_having_with_empty_operator_dict_is_manual() -> None:
    """`{"having": {"count": {}}}` is classified as manual.

    Regression for codex review P2: previously the truthy outer
    `{"count": {}}` dict made `metric_less` False, so the stub was
    emitted without `needs_manual_conversion` and `compile_rule_sql`
    later produced a dangling `WHERE`.
    """
    row = LegacyRuleRow(rule_id="r1", name="n", threshold_block={"having": {"count": {}}})
    stub = to_aml_rule_stub(row)
    assert "needs_manual_conversion" in stub["tags"]
    # Stub still emits a safe placeholder so `aml validate` passes.
    assert stub["logic"]["having"] == {"count": {"gte": 1}}


def test_bare_threshold_with_empty_operator_is_manual() -> None:
    """A bare `{"count": {}}` block is classified as manual."""
    row = LegacyRuleRow(rule_id="r1", name="n", threshold_block={"count": {}})
    stub = to_aml_rule_stub(row)
    assert "needs_manual_conversion" in stub["tags"]


def test_mixed_having_keeps_real_metrics_drops_empty() -> None:
    """`{"having": {"count": {"gte": 5}, "sum_amount": {}}}` keeps `count`.

    Regression for codex review P2: previously the `all(...)` check
    fell back to the default when ANY metric was empty, silently
    dropping the `count >= 5` requirement.
    """
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"having": {"count": {"gte": 5}, "sum_amount": {}}},
    )
    stub = to_aml_rule_stub(row)
    # Real metric kept, empty operator dropped.
    assert stub["logic"]["having"] == {"count": {"gte": 5}}
    # The block is NOT metric-less — at least one real metric is present.
    assert "needs_manual_conversion" not in stub["tags"]


def test_vendor_dict_sibling_excluded_from_derived_having() -> None:
    """A vendor `parameters: {...}` sibling is preserved as tag, not in having.

    Regression for codex review P2: previously the unknown
    `parameters` dict was lifted into `logic.having`, and the engine
    would later raise `unsupported having metric 'parameters'`.
    """
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={
            "source": "txn",
            "count": {"gte": 5},
            "parameters": {"lookback_days": 7},
        },
    )
    stub = to_aml_rule_stub(row)
    # Only the recognised `count` metric is in having.
    assert stub["logic"]["having"] == {"count": {"gte": 5}}
    assert "parameters" not in stub["logic"]["having"]
    # The vendor blob is still preserved on the legacy_threshold_block tag.
    threshold_tags = [t for t in stub["tags"] if t.startswith("legacy_threshold_block:")]
    assert len(threshold_tags) == 1
    blob = json.loads(threshold_tags[0].removeprefix("legacy_threshold_block:"))
    assert blob["parameters"] == {"lookback_days": 7}


def test_group_by_null_entries_skipped() -> None:
    """`group_by: [null, "customer_id"]` skips the null.

    Regression for codex review P2: previously stringified `None`
    into the literal column name `"None"`, generating a runtime-
    invalid grouping clause.
    """
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={
            "group_by": [None, "customer_id"],
            "having": {"count": {"gte": 5}},
        },
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["group_by"] == ["customer_id"]


def test_group_by_all_nulls_falls_back() -> None:
    """`group_by: [null, null]` falls back to the default."""
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"group_by": [None, None], "having": {"count": {"gte": 5}}},
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["group_by"] == ["customer_id"]


def test_threshold_source_whitespace_stripped() -> None:
    """`source: " txn "` → emitted as `"txn"` so cross-references match.

    Regression for codex review P3: previously the raw unstripped
    value was emitted, so the rule referenced ` txn ` and failed
    cross-reference validation against the `txn` data contract.
    """
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"source": "  txn  ", "having": {"count": {"gte": 5}}},
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["source"] == "txn"


def test_regulator_refs_csv_json_list_with_null_entries(tmp_path: Path) -> None:
    """CSV `regulator_refs: [null, "FATF R.10"]` skips the null.

    Regression for codex review P2 (companion to the real-list null
    skip): the JSON-list path in `_coerce_regulator_refs` also
    skips None entries.
    """
    path = tmp_path / "csv_null.csv"
    _write_csv(
        path,
        ["rule_id", "name", "regulator_refs", "sql"],
        [["R_CSV_NULL", "n", '[null, "FATF R.10"]', "SELECT 1"]],
    )
    rows = parse_legacy_csv(path)
    assert rows[0].regulator_refs == ["FATF R.10"]


def test_threshold_is_metric_less_helper_paths() -> None:
    """Direct cover for `_threshold_is_metric_less` defensive branches."""
    from aml_framework.generators.legacy_import import _threshold_is_metric_less

    # Non-dict input (defensive — caller already type-checks).
    assert _threshold_is_metric_less(None) is True
    # Block with explicit `having` containing a real metric.
    assert _threshold_is_metric_less({"having": {"count": {"gte": 5}}}) is False
    # Block with only sibling metric (no `having`).
    assert _threshold_is_metric_less({"count": {"gte": 5}}) is False
    # Block with only metadata.
    assert _threshold_is_metric_less({"source": "x", "window": "7d"}) is True


def test_classify_metric_less_threshold_is_manual() -> None:
    """A metric-less threshold block classifies as `needs_manual`.

    Regression for codex review P2: previously a block like
    `{"source":"txn","window":"7d","group_by":["customer_id"]}`
    classified as `ready_threshold` even though the stub emitted a
    placeholder + `needs_manual_conversion` tag, mis-reporting the
    real migration workload.
    """
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"source": "txn", "window": "7d", "group_by": ["customer_id"]},
    )
    assert classify_row(row) == "needs_manual"


def test_inventory_counts_metric_less_threshold_as_manual() -> None:
    """`inventory_summary` counts metric-less thresholds in `needs_manual`."""
    rows = [
        LegacyRuleRow(
            rule_id="a",
            name="a",
            threshold_block={"source": "txn", "window": "7d"},  # metric-less
        ),
        LegacyRuleRow(
            rule_id="b",
            name="b",
            threshold_block={"count": {"gte": 10}},  # real metric
        ),
    ]
    summary = inventory_summary(rows)
    assert summary["ready_to_import"] == 1  # only `b`
    assert summary["needs_manual"] == 1  # `a` is manual


def test_regulator_refs_null_entries_skipped(tmp_path: Path) -> None:
    """JSON `regulator_refs: [null]` is treated as empty, not "None".

    Regression for codex review P2: previously `str(None).strip() ==
    "None"` was kept, emitting a literal `None` citation and hiding
    the missing-coverage flag from `inventory_summary`.
    """
    path = tmp_path / "null_refs.json"
    path.write_text(
        json.dumps(
            [
                {
                    "rule_id": "R_NULL",
                    "name": "n",
                    "legacy_sql": "SELECT 1",
                    "regulator_refs": [None],
                }
            ]
        ),
        encoding="utf-8",
    )
    rows = parse_legacy_json(path)
    assert rows[0].regulator_refs == []


def test_narrative_stub_status_experimental() -> None:
    """Narrative-only stubs are `status: experimental`, not `active`.

    Regression for codex review P2: previously narrative-only stubs
    defaulted to `active`, so a merged skeleton with a real
    `escalate_to` queue would let the runner execute the
    `count >= 1` placeholder and flood alerts.
    """
    row = LegacyRuleRow(rule_id="r1", name="n", narrative="Round-trip 24h")
    stub = to_aml_rule_stub(row)
    assert stub["status"] == "experimental"


def test_metric_less_threshold_stub_status_experimental() -> None:
    """Metric-less threshold stubs are `status: experimental`."""
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"source": "txn", "window": "7d"},  # metric-less
    )
    stub = to_aml_rule_stub(row)
    assert stub["status"] == "experimental"


def test_ready_stub_omits_status_defaulting_active() -> None:
    """A ready SQL or threshold stub does NOT force experimental.

    The Rule model defaults `status` to `active` when absent; we
    only override it for manual-conversion placeholders.
    """
    sql_row = LegacyRuleRow(rule_id="r1", name="n", legacy_sql="SELECT 1")
    sql_stub = to_aml_rule_stub(sql_row)
    assert "status" not in sql_stub  # defaults to active

    threshold_row = LegacyRuleRow(
        rule_id="r2", name="n", threshold_block={"having": {"count": {"gte": 5}}}
    )
    threshold_stub = to_aml_rule_stub(threshold_row)
    assert "status" not in threshold_stub


def test_threshold_with_real_metric_not_flagged_manual() -> None:
    """A block with a real metric is NOT flagged needs_manual_conversion."""
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"source": "txn", "window": "7d", "count": {"gte": 10}},
    )
    stub = to_aml_rule_stub(row)
    assert "needs_manual_conversion" not in stub["tags"]


def test_parse_json_malformed_file_returns_warning(tmp_path: Path) -> None:
    """A malformed `.json` file surfaces a warning, not a JSONDecodeError.

    Regression for codex review P3: previously
    `json.loads(path.read_text(...))` raised before `ParseResult` was
    returned, so the CLI showed a traceback instead of the warn-and-
    abort flow used for other bad inputs.
    """
    path = tmp_path / "broken.json"
    path.write_text("{ not json at all", encoding="utf-8")
    result = parse_legacy_json_with_warnings(path)
    assert result.rows == []
    assert any("JSON decode failed" in w.reason for w in result.warnings)


def test_parse_json_empty_file_returns_warning(tmp_path: Path) -> None:
    path = tmp_path / "empty.json"
    path.write_text("", encoding="utf-8")
    result = parse_legacy_json_with_warnings(path)
    assert result.rows == []
    assert any("JSON decode failed" in w.reason for w in result.warnings)


def test_threshold_window_zero_string_falls_back() -> None:
    """`window: "0d"` falls back to `30d` (zero-length windows never fire)."""
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"window": "0d", "having": {"count": {"gte": 5}}},
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["window"] == "30d"


def test_threshold_window_string_zero_int_falls_back() -> None:
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"window": "0", "having": {"count": {"gte": 5}}},
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["window"] == "30d"


def test_threshold_window_fractional_float_falls_back() -> None:
    """`window: 0.5` truncates to 0 → falls back to `30d`."""
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"window": 0.5, "having": {"count": {"gte": 5}}},
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["window"] == "30d"


def test_threshold_window_positive_fractional_falls_back() -> None:
    """`window: 1.5` (positive but non-integer) falls back to `30d`.

    Regression for codex review P2: previously truncated to `1d`,
    silently shortening the detector window.
    """
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"window": 1.5, "having": {"count": {"gte": 5}}},
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["window"] == "30d"


def test_threshold_window_exact_integer_float_keeps_value() -> None:
    """`window: 30.0` (exact integer float) emits `30d`."""
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"window": 30.0, "having": {"count": {"gte": 5}}},
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["window"] == "30d"


def test_threshold_group_by_delimiter_only_string_falls_back() -> None:
    """`group_by: ","` (no items) falls back to the default."""
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"group_by": ",", "having": {"count": {"gte": 5}}},
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["group_by"] == ["customer_id"]


def test_threshold_group_by_whitespace_delim_only_falls_back() -> None:
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"group_by": " ; ", "having": {"count": {"gte": 5}}},
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["group_by"] == ["customer_id"]


def test_threshold_window_garbage_string_falls_back() -> None:
    """A string that's neither digits nor a valid pattern falls back."""
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"window": "weekly", "having": {"count": {"gte": 5}}},
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["window"] == "30d"


def test_threshold_group_by_string_coerces_to_list() -> None:
    """`group_by: "customer_id"` (string) → `["customer_id"]`."""
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"group_by": "customer_id", "having": {"count": {"gte": 5}}},
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["group_by"] == ["customer_id"]


def test_threshold_group_by_comma_separated_string_splits() -> None:
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={
            "group_by": "customer_id, account_id",
            "having": {"count": {"gte": 5}},
        },
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["group_by"] == ["customer_id", "account_id"]


def test_threshold_group_by_unrecognised_type_falls_back() -> None:
    """A non-list/non-string group_by falls back to the default."""
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"group_by": 42, "having": {"count": {"gte": 5}}},
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["group_by"] == ["customer_id"]


def test_threshold_group_by_empty_list_falls_back() -> None:
    """An empty `group_by` list falls back to the default."""
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"group_by": [], "having": {"count": {"gte": 5}}},
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["group_by"] == ["customer_id"]


def test_threshold_group_by_empty_string_falls_back() -> None:
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"group_by": "   ", "having": {"count": {"gte": 5}}},
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["group_by"] == ["customer_id"]


def test_threshold_source_empty_string_falls_back_to_todo() -> None:
    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={"source": "   ", "having": {"count": {"gte": 5}}},
    )
    stub = to_aml_rule_stub(row)
    assert stub["logic"]["source"] == "TODO_source_contract"


def test_stub_with_coerced_metadata_validates_through_pydantic() -> None:
    """Even with scalar legacy metadata, the stub validates as a Rule."""
    from aml_framework.spec.models import Rule

    row = LegacyRuleRow(
        rule_id="r1",
        name="n",
        threshold_block={
            "window": 30,  # int — coerces to "30d"
            "group_by": "customer_id",  # str — coerces to list
            "having": {"sum": {"gte": 100000}},
        },
        regulator_refs=["FATF R.10"],
    )
    stub = to_aml_rule_stub(row)
    Rule.model_validate(stub)


def test_stub_legacy_threshold_block_is_tag_not_extra_field() -> None:
    """The preserved blob never appears as a top-level rule extra field.

    Regression for codex review P2: previously `legacy_threshold_block`
    was set at the rule level, which `aml validate` rejected because
    `Rule` has `extra="forbid"`. Now it lives under `tags`.
    """
    row = LegacyRuleRow(rule_id="r1", name="n", threshold_block={"count": {"gte": 1}})
    stub = to_aml_rule_stub(row)
    # Must NOT be a top-level field on the rule dict.
    assert "legacy_threshold_block" not in stub
    # Allowed-field set: only fields the AML Rule schema accepts.
    allowed = {
        "id",
        "name",
        "severity",
        "regulation_refs",
        "escalate_to",
        "evidence",
        "tags",
        "logic",
        "status",
        "evaluation_mode",
        "tuning_grid",
        "aml_priority",
        "model_tier",
        "validation_cadence_months",
        "business_intent",
    }
    assert set(stub.keys()).issubset(allowed)


def test_build_spec_skeleton_disambiguates_duplicate_ids() -> None:
    """Two rows sanitising to the same ID get `_<n>` suffixes.

    Regression for codex review P2: the runner uses `rule.id` as a
    dict key and in alert filenames, so collisions would silently
    overwrite one rule with another.
    """
    rows = [
        LegacyRuleRow(rule_id="R-1", name="a", legacy_sql="SELECT 1"),
        LegacyRuleRow(rule_id="R_1", name="b", legacy_sql="SELECT 2"),
        LegacyRuleRow(rule_id="R 1", name="c", legacy_sql="SELECT 3"),
    ]
    skeleton = build_spec_skeleton(rows)
    ids = [r["id"] for r in skeleton["rules"]]
    assert len(set(ids)) == 3
    assert ids[0] == "r_1"
    assert ids[1] == "r_1_2"
    assert ids[2] == "r_1_3"
    # The duplicates get a `legacy_dup_of:` tag pointing at the original.
    assert any(t == "legacy_dup_of:r_1" for t in skeleton["rules"][1]["tags"])


def test_build_spec_skeleton_disambiguation_skips_existing_suffix() -> None:
    """If a `_2` suffix already exists, disambiguation jumps past it."""
    rows = [
        LegacyRuleRow(rule_id="r_1", name="a", legacy_sql="SELECT 1"),
        LegacyRuleRow(rule_id="r_1_2", name="pre-existing", legacy_sql="SELECT 2"),
        LegacyRuleRow(rule_id="r-1", name="dup of first", legacy_sql="SELECT 3"),
    ]
    skeleton = build_spec_skeleton(rows)
    ids = [r["id"] for r in skeleton["rules"]]
    assert len(set(ids)) == 3
    assert ids == ["r_1", "r_1_2", "r_1_3"]


def test_inventory_surfaces_sanitised_collisions() -> None:
    """Sanitised-ID collisions show up in the inventory summary too.

    Regression for codex review P2: previously `inventory_summary`
    only counted raw rule_id duplicates, so a dump with `R-1` and
    `R_1` (both sanitising to `r_1`) passed the pre-import check
    even though the importer would have to rename them.
    """
    rows = [
        LegacyRuleRow(rule_id="R-1", name="a", legacy_sql="x"),
        LegacyRuleRow(rule_id="R_1", name="b", legacy_sql="y"),
    ]
    summary = inventory_summary(rows)
    # Surface format: `<safe_id> ← <raw_a>, <raw_b>` so the operator
    # sees both the post-import name and the source IDs.
    assert summary["duplicate_rule_ids"]
    label = summary["duplicate_rule_ids"][0]
    assert "r_1" in label
    assert "R-1" in label and "R_1" in label


def test_disambiguation_reserves_natural_ids_first() -> None:
    """A later row with natural `r_1_2` keeps that ID even if `R-1`/`R_1` come first.

    Regression for codex review P2: previously the wizard appended
    `_2` to the second `r_1` collision before checking whether
    `r_1_2` was a later natural ID, forcing that legitimate row to
    `r_1_2_2`. Now the pre-pass reserves natural IDs so disambiguation
    skips suffixes that would collide with them.
    """
    rows = [
        LegacyRuleRow(rule_id="R-1", name="a", legacy_sql="x"),
        LegacyRuleRow(rule_id="R_1", name="b", legacy_sql="y"),
        LegacyRuleRow(rule_id="r_1_2", name="c", legacy_sql="z"),
    ]
    skeleton = build_spec_skeleton(rows)
    ids = [r["id"] for r in skeleton["rules"]]
    assert ids == ["r_1", "r_1_3", "r_1_2"]
    # The natural `r_1_2` row is NOT tagged as a duplicate.
    assert not any(t.startswith("legacy_dup_of:") for t in skeleton["rules"][2]["tags"])


def test_csv_canonical_column_wins_over_later_alias(tmp_path: Path) -> None:
    """`rule_id` + later `id` column → canonical wins.

    Regression for codex review P2: previously a later generic `id`
    column overwrote the canonical `rule_id`, corrupting traceability
    and duplicate-detection.
    """
    path = tmp_path / "alias_collision.csv"
    _write_csv(
        path,
        ["rule_id", "name", "sql", "id"],
        [["R_CANONICAL", "n", "SELECT 1", "wrong_id_from_alias"]],
    )
    rows = parse_legacy_csv(path)
    assert rows[0].rule_id == "R_CANONICAL"


def test_csv_first_non_empty_alias_wins(tmp_path: Path) -> None:
    """When both columns are aliases (no canonical), first non-empty wins."""
    path = tmp_path / "two_aliases.csv"
    # Both `id` and `scenario_id` are aliases for `rule_id`; no canonical
    # column present. First non-empty wins.
    _write_csv(
        path,
        ["id", "scenario_id", "name", "sql"],
        [["first_alias", "second_alias", "n", "SELECT 1"]],
    )
    rows = parse_legacy_csv(path)
    assert rows[0].rule_id == "first_alias"


def test_csv_empty_alias_falls_through_to_next(tmp_path: Path) -> None:
    """An empty value in the first alias yields to the next non-empty alias."""
    path = tmp_path / "alias_empty.csv"
    _write_csv(
        path,
        ["id", "scenario_id", "name", "sql"],
        [["", "fallback_id", "n", "SELECT 1"]],
    )
    rows = parse_legacy_csv(path)
    assert rows[0].rule_id == "fallback_id"


def test_csv_strips_utf8_bom_from_header(tmp_path: Path) -> None:
    """Excel-saved CSVs have a BOM on the first header — must still parse.

    Regression for codex review P2: previously `﻿rule_id` (with
    BOM) didn't match the `rule_id` alias, breaking the first row of
    every Excel-emitted dump.
    """
    path = tmp_path / "excel.csv"
    # Write the BOM byte explicitly so the parser sees it.
    path.write_bytes("﻿rule_id,name,sql\nR_BOM,n,SELECT 1\n".encode("utf-8"))
    rows = parse_legacy_csv(path)
    assert len(rows) == 1
    assert rows[0].rule_id == "R_BOM"


def test_coerce_threshold_block_empty_string_is_none() -> None:
    """Direct cover for the empty-string path in `_coerce_threshold_block`."""
    from aml_framework.generators.legacy_import import _coerce_threshold_block

    assert _coerce_threshold_block("   ") is None


def test_coerce_regulator_refs_empty_string() -> None:
    """Direct cover for the empty-string path in `_coerce_regulator_refs`."""
    from aml_framework.generators.legacy_import import _coerce_regulator_refs

    assert _coerce_regulator_refs("   ") == []


def test_json_rule_id_as_integer_is_coerced() -> None:
    """A non-string `rule_id` (common in JSON dumps) is stringified."""
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump([{"rule_id": 12345, "name": "n", "legacy_sql": "x"}], fh)
        path = Path(fh.name)
    try:
        rows = parse_legacy_json(path)
        assert rows[0].rule_id == "12345"
    finally:
        path.unlink()


def test_json_canonical_key_wins_over_alias() -> None:
    """JSON object with both `rule_id` and `id` → canonical wins."""
    # Use a tmp path via fixture in a parameterized test would be cleaner;
    # for inline simplicity write to tmp via the local helper.
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump([{"id": "wrong", "rule_id": "R_CANONICAL", "name": "n", "legacy_sql": "x"}], fh)
        path = Path(fh.name)
    try:
        rows = parse_legacy_json(path)
        assert rows[0].rule_id == "R_CANONICAL"
    finally:
        path.unlink()


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
