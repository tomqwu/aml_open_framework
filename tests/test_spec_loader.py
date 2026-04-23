from pathlib import Path

import pytest
import yaml

from aml_framework.spec import load_spec


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"


def test_example_spec_loads():
    spec = load_spec(EXAMPLE)
    assert spec.program.name == "community_bank_aml"
    assert any(r.id == "structuring_cash_deposits" for r in spec.rules)


def test_rule_references_unknown_contract_fails(tmp_path):
    raw = yaml.safe_load(EXAMPLE.read_text())
    raw["rules"][0]["logic"]["source"] = "nonexistent"
    bad = tmp_path / "aml.yaml"
    bad.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="unknown data_contract"):
        load_spec(bad)


def test_rule_escalates_to_unknown_queue_fails(tmp_path):
    raw = yaml.safe_load(EXAMPLE.read_text())
    raw["rules"][0]["escalate_to"] = "does_not_exist"
    bad = tmp_path / "aml.yaml"
    bad.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="unknown queue"):
        load_spec(bad)


def test_missing_required_field_fails_schema(tmp_path):
    raw = yaml.safe_load(EXAMPLE.read_text())
    del raw["program"]["regulator"]
    bad = tmp_path / "aml.yaml"
    bad.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="JSON Schema validation"):
        load_spec(bad)
