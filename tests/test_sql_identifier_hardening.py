"""Security: spec authors must never reach generated SQL through an
identifier position (group_by columns, filter field names).

Two layers are tested:
  1. spec-load — pydantic + JSON Schema reject bad identifiers in aml.yaml.
  2. SQL compile — the generator re-checks, so a Rule built programmatically
     (bypassing the loader) still can't emit unsafe SQL.

Also covers the python_ref fail-before-work gate: a disallowed callable on
any active rule aborts the whole run before any rule executes.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
import yaml as _yaml

from aml_framework.data import generate_dataset
from aml_framework.engine import run_spec
from aml_framework.generators.sql import compile_rule_sql
from aml_framework.spec import load_spec
from aml_framework.spec.models import AggregationWindowLogic, Rule

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "community_bank" / "aml.yaml"


def _injection_spec(tmp_path: Path, *, group_by=None, filter_=None) -> Path:
    raw = _yaml.safe_load(EXAMPLE.read_text())
    rule = next(r for r in raw["rules"] if r["logic"]["type"] == "aggregation_window")
    if group_by is not None:
        rule["logic"]["group_by"] = group_by
    if filter_ is not None:
        rule["logic"]["filter"] = filter_
    p = tmp_path / "aml.yaml"
    p.write_text(_yaml.safe_dump(raw))
    return p


class TestSpecLoadRejectsBadIdentifiers:
    def test_group_by_injection_rejected_at_load(self, tmp_path):
        bad = _injection_spec(tmp_path, group_by=["customer_id); DROP TABLE customer; --"])
        with pytest.raises(ValueError):
            load_spec(bad)

    def test_filter_field_injection_rejected_at_load(self, tmp_path):
        bad = _injection_spec(tmp_path, filter_={"amount) OR 1=1 --": {"gte": 1}})
        with pytest.raises(ValueError):
            load_spec(bad)

    def test_uppercase_group_by_rejected(self, tmp_path):
        # Identifiers are lowercase-only by contract; reject CamelCase too.
        bad = _injection_spec(tmp_path, group_by=["CustomerId"])
        with pytest.raises(ValueError):
            load_spec(bad)

    def test_valid_spec_still_loads(self, tmp_path):
        ok = _injection_spec(tmp_path, group_by=["customer_id"], filter_={"channel": "cash"})
        spec = load_spec(ok)
        assert spec.rules


class TestGeneratorRejectsBadIdentifiers:
    """Defense-in-depth: a Rule object built in code bypasses the loader,
    so the SQL generator itself must refuse unsafe identifiers."""

    def _rule(self, logic: AggregationWindowLogic) -> Rule:
        return Rule.model_construct(
            id="r",
            name="r",
            severity="low",
            status="active",
            regulation_refs=[],
            logic=logic,
            escalate_to="q",
            evidence=[],
            tags=[],
        )

    def test_group_by_injection_rejected_at_compile(self):
        logic = AggregationWindowLogic.model_construct(
            type="aggregation_window",
            source="txn",
            filter=None,
            group_by=["customer_id); DROP TABLE txn; --"],
            window="30d",
            having={"count": {"gte": 1}},
            enrich=None,
        )
        with pytest.raises(ValueError, match="unsafe SQL identifier"):
            compile_rule_sql(self._rule(logic), as_of=datetime(2026, 4, 23), source_table="txn")

    def test_filter_field_injection_rejected_at_compile(self):
        logic = AggregationWindowLogic.model_construct(
            type="aggregation_window",
            source="txn",
            filter={"amount) OR 1=1 --": "x"},
            group_by=["customer_id"],
            window="30d",
            having={"count": {"gte": 1}},
            enrich=None,
        )
        with pytest.raises(ValueError, match="unsafe SQL identifier"):
            compile_rule_sql(self._rule(logic), as_of=datetime(2026, 4, 23), source_table="txn")

    def test_clean_rule_compiles(self):
        logic = AggregationWindowLogic.model_construct(
            type="aggregation_window",
            source="txn",
            filter={"channel": "cash"},
            group_by=["customer_id"],
            window="30d",
            having={"count": {"gte": 1}},
            enrich=None,
        )
        sql = compile_rule_sql(self._rule(logic), as_of=datetime(2026, 4, 23), source_table="txn")
        assert "GROUP BY customer_id" in sql


class TestPythonRefFailsBeforeWork:
    def test_disallowed_pyref_aborts_before_any_alert(self, tmp_path):
        """A python_ref outside the allowlist must abort the run up front —
        not after other rules have already written to the ledger."""
        raw = _yaml.safe_load(EXAMPLE.read_text())
        raw["rules"].append(
            {
                "id": "evil_scorer",
                "name": "evil",
                "severity": "low",
                "risk_tier": "low",
                "regulation_refs": [{"citation": "x", "description": "y"}],
                "logic": {
                    "type": "python_ref",
                    "callable": "os:getcwd",
                    "model_id": "m",
                    "model_version": "1",
                },
                "escalate_to": "l1_analyst",
            }
        )
        bad = tmp_path / "aml.yaml"
        bad.write_text(_yaml.safe_dump(raw))
        spec = load_spec(bad)
        as_of = datetime(2026, 4, 23, 12, 0, 0)
        data = generate_dataset(as_of=as_of, seed=42)
        run_dir = tmp_path / "art"
        with pytest.raises(ValueError, match="not under an allowed prefix"):
            run_spec(spec=spec, spec_path=bad, data=data, as_of=as_of, artifacts_root=run_dir)
