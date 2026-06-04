from __future__ import annotations

import json

from aml_framework.generators.model_inventory import (
    build_model_inventory,
    render_model_inventory_markdown,
)
from aml_framework.spec import load_spec

SPEC = "examples/community_bank/aml.yaml"


def test_inventory_has_one_entry_per_rule():
    spec = load_spec(SPEC)
    inv = build_model_inventory(spec)
    rule_keys = {m["model_key"] for m in inv["models"] if m["kind"] in ("rule", "python_ref")}
    assert rule_keys == {r.id for r in spec.rules}


def test_inventory_is_deterministic_byte_stable():
    spec = load_spec(SPEC)
    a = json.dumps(build_model_inventory(spec), sort_keys=True)
    b = json.dumps(build_model_inventory(spec), sort_keys=True)
    assert a == b  # no wall-clock / dict-order dependence


def test_inventory_sorted_by_tier_then_key():
    spec = load_spec(SPEC)
    inv = build_model_inventory(spec)
    order = {"high": 0, "medium": 1, "low": 2}
    keys = [(order[m["tier"]], m["model_key"]) for m in inv["models"]]
    assert keys == sorted(keys)


def test_python_ref_entry_carries_external_model_block():
    spec = load_spec(SPEC)
    inv = build_model_inventory(spec)
    pyrefs = [m for m in inv["models"] if m["kind"] == "python_ref"]
    for m in pyrefs:
        assert m["external_model"] is not None
        assert set(m["external_model"]) == {"model_id", "model_version", "callable"}


def test_summary_counts_match():
    spec = load_spec(SPEC)
    inv = build_model_inventory(spec)
    assert inv["summary"]["total_models"] == len(inv["models"])
    assert sum(inv["summary"]["by_kind"].values()) == len(inv["models"])


def test_markdown_renders_header_and_table():
    spec = load_spec(SPEC)
    md = render_model_inventory_markdown(build_model_inventory(spec))
    assert md.startswith("# Model Inventory")
    assert "| Model | Kind | Tier |" in md


def test_markdown_escapes_pipe_in_cell_values():
    from aml_framework.generators.model_inventory import render_model_inventory_markdown

    inv = {
        "programme": {"name": "p", "jurisdiction": "US", "regulator": "FinCEN", "owner": "o"},
        "_guidance": "g",
        "_guidance_effective": "2026-04-17",
        "summary": {"total_models": 1, "by_kind": {"rule": 1}},
        "models": [
            {
                "model_key": "r1",
                "kind": "rule",
                "tier": "low",
                "cadence_months": 36,
                "owner": "o",
                "purpose": "catch A | B structuring",  # raw pipe must be escaped
                "conceptual_soundness": ["31 CFR 1020 | note"],
            }
        ],
    }
    md = render_model_inventory_markdown(inv)
    row = [ln for ln in md.splitlines() if ln.startswith("| `r1`")][0]
    # one data row = exactly 7 columns => 8 unescaped pipes; raw pipes escaped to \|
    assert row.count("|") - row.count("\\|") == 8
    assert "A \\| B" in row


def _spec_with_prioritization(tmp_path):
    import pathlib

    src = pathlib.Path(SPEC).read_text()
    block = "  effective_date: 2026-01-01\n  prioritization:\n    enabled: true\n"
    src = src.replace("  effective_date: 2026-01-01\n", block, 1)
    p = tmp_path / "prio.yaml"
    p.write_text(src)
    return load_spec(p)


def test_scorer_entry_present_when_prioritization_enabled(tmp_path):
    spec = _spec_with_prioritization(tmp_path)
    inv = build_model_inventory(spec)
    scorer = [m for m in inv["models"] if m["kind"] == "scorer"]
    assert len(scorer) == 1
    assert scorer[0]["model_key"] == "prioritization_scorer"
    assert scorer[0]["logic_type"] == "weighted_linear"
    assert scorer[0]["tier"] == "high"


def test_scorer_absent_when_prioritization_disabled():
    spec = load_spec(SPEC)  # community_bank has no prioritization block -> disabled
    inv = build_model_inventory(spec)
    assert not [m for m in inv["models"] if m["kind"] == "scorer"]


from typer.testing import CliRunner  # noqa: E402

from aml_framework.cli import app  # noqa: E402

_runner = CliRunner()


def test_cli_writes_json(tmp_path):
    out = tmp_path / "inv.json"
    result = _runner.invoke(app, ["model-inventory", SPEC, "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["summary"]["total_models"] >= 1
    assert "models" in data


def test_cli_writes_markdown(tmp_path):
    out_md = tmp_path / "inv.md"
    result = _runner.invoke(app, ["model-inventory", SPEC, "--markdown", str(out_md)])
    assert result.exit_code == 0, result.output
    assert out_md.exists()
    assert out_md.read_text().startswith("# Model Inventory")


def test_cli_prints_summary_to_stdout():
    result = _runner.invoke(app, ["model-inventory", SPEC])
    assert result.exit_code == 0, result.output
    assert "models" in result.output.lower()
