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
