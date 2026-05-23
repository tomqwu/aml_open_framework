"""PR-A2 — `business_intent` + `out_of_scope` on Rule.

Optional in this PR (defaults match additive-compatibility discipline);
a follow-up will populate every example spec and flip to required so
that audit packs + STR narratives have a guaranteed rationale field.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from aml_framework.spec.loader import load_spec

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


class TestRuleBusinessIntent:
    def test_defaults_when_unset(self, tmp_path):
        """Specs that omit these fields still load — additive contract
        holds. `business_intent` defaults None; `out_of_scope` defaults
        `[]` so callers can iterate without a None-check. PR-A2b
        populated every example spec's rules, so we strip the fields
        from a copy of the canonical spec to assert the default path."""
        raw = yaml.safe_load(EXAMPLE.read_text())
        for rule in raw["rules"]:
            rule.pop("business_intent", None)
            rule.pop("out_of_scope", None)
        f = tmp_path / "aml.yaml"
        f.write_text(yaml.safe_dump(raw))
        spec = load_spec(f)
        rule = spec.rules[0]
        assert rule.business_intent is None
        assert rule.out_of_scope == []

    def test_business_intent_round_trips(self, tmp_path):
        raw = yaml.safe_load(EXAMPLE.read_text())
        raw["rules"][0]["business_intent"] = (
            "Detect customers depositing just-under the $10k CTR threshold"
        )
        raw["rules"][0]["out_of_scope"] = ["large institutional cash deposits"]
        f = tmp_path / "aml.yaml"
        f.write_text(yaml.safe_dump(raw))
        spec = load_spec(f)
        assert spec.rules[0].business_intent.startswith("Detect customers")
        assert spec.rules[0].out_of_scope == ["large institutional cash deposits"]

    def test_business_intent_rejects_empty_string(self, tmp_path):
        """JSON schema enforces `minLength=1`; loader raises on the schema
        layer before Pydantic. Empty string is semantically different from
        unset — caller should send None / omit, not ''."""
        raw = yaml.safe_load(EXAMPLE.read_text())
        raw["rules"][0]["business_intent"] = ""
        f = tmp_path / "aml.yaml"
        f.write_text(yaml.safe_dump(raw))
        with pytest.raises(ValueError):
            load_spec(f)

    def test_out_of_scope_accepts_explicit_empty_list(self, tmp_path):
        """`out_of_scope: []` is meaningful — "no known exclusions
        documented". Must round-trip equal to the default-unset shape."""
        raw = yaml.safe_load(EXAMPLE.read_text())
        raw["rules"][0]["out_of_scope"] = []
        f = tmp_path / "aml.yaml"
        f.write_text(yaml.safe_dump(raw))
        spec = load_spec(f)
        assert spec.rules[0].out_of_scope == []


class TestRuleVersionStability:
    """Codex pass on PR-A2: an additive schema change must NOT churn
    `rule_version_hash` for existing specs that don't author the new
    metadata — otherwise historical lineage diffs falsely show every
    rule as "modified" the day this schema lands.

    The hash is meant to be stable across additive schema bumps and
    only change when authored-content changes."""

    def test_rule_version_unchanged_when_new_fields_at_defaults(self):
        from aml_framework.engine.audit import rule_version_hash
        from aml_framework.spec.models import (
            AggregationWindowLogic,
            RegulationRef,
            Rule,
        )

        # Two rules identical except the second explicitly sets the
        # new fields to their defaults. Hash must be the same so a
        # `.from_yaml()` rule (unset fields) matches a programmatically
        # built rule (explicit defaults).
        rule_a = Rule(
            id="r1",
            name="R1",
            severity="medium",
            regulation_refs=[RegulationRef(citation="x", description="x")],
            logic=AggregationWindowLogic(
                type="aggregation_window",
                source="txn",
                group_by=["customer_id"],
                window="7d",
                having={"count": {"gte": 1}},
            ),
            escalate_to="q",
            evidence=[],
        )
        rule_b = Rule(
            id="r1",
            name="R1",
            severity="medium",
            regulation_refs=[RegulationRef(citation="x", description="x")],
            logic=AggregationWindowLogic(
                type="aggregation_window",
                source="txn",
                group_by=["customer_id"],
                window="7d",
                having={"count": {"gte": 1}},
            ),
            escalate_to="q",
            evidence=[],
            business_intent=None,  # explicit default
            out_of_scope=[],  # explicit default
        )
        assert rule_version_hash(rule_a) == rule_version_hash(rule_b)

    def test_rule_version_stable_for_dict_callers_at_defaults(self):
        # Codex pass on PR-A2: dict callers (e.g. `rule.model_dump()`)
        # must get the same hash as a Pydantic model with unset
        # defaults. Otherwise schema bumps still churn rule_version
        # through the dict path.
        from aml_framework.engine.audit import rule_version_hash

        rule_dict_no_new_fields = {
            "id": "r1",
            "name": "R1",
            "severity": "medium",
            "logic": {"type": "aggregation_window", "source": "txn"},
            "escalate_to": "q",
        }
        rule_dict_with_default_new_fields = {
            **rule_dict_no_new_fields,
            "business_intent": None,
            "out_of_scope": [],
        }
        assert rule_version_hash(rule_dict_no_new_fields) == rule_version_hash(
            rule_dict_with_default_new_fields
        )

    def test_rule_version_changes_when_business_intent_authored(self):
        from aml_framework.engine.audit import rule_version_hash
        from aml_framework.spec.models import (
            AggregationWindowLogic,
            RegulationRef,
            Rule,
        )

        base_kwargs = dict(
            id="r1",
            name="R1",
            severity="medium",
            regulation_refs=[RegulationRef(citation="x", description="x")],
            logic=AggregationWindowLogic(
                type="aggregation_window",
                source="txn",
                group_by=["customer_id"],
                window="7d",
                having={"count": {"gte": 1}},
            ),
            escalate_to="q",
            evidence=[],
        )
        unauthored = Rule(**base_kwargs)
        authored = Rule(**base_kwargs, business_intent="newly documented rationale")
        assert rule_version_hash(unauthored) != rule_version_hash(authored), (
            "authoring business_intent IS a rule-version change"
        )


class TestSpecDiffSurfacesAuthoredRationale:
    """Codex pass on PR-A2: schema description promised these fields
    would be visible to regulator-facing surfaces. As a minimum
    wire-in, `compute_spec_diff` should surface changes to
    business_intent / out_of_scope so an `aml diff` reviewer sees
    authored-rationale changes, not just mechanical fields."""

    def test_business_intent_change_surfaces_in_rule_diff(self, tmp_path):
        from aml_framework.diff import compute_spec_diff

        raw = yaml.safe_load(EXAMPLE.read_text())
        raw_a = {**raw, "rules": [dict(raw["rules"][0]), *raw["rules"][1:]]}
        raw_a["rules"][0] = {**raw_a["rules"][0], "business_intent": "original rationale"}
        raw_b = {**raw, "rules": [dict(raw["rules"][0]), *raw["rules"][1:]]}
        raw_b["rules"][0] = {**raw_b["rules"][0], "business_intent": "updated rationale"}
        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        a.write_text(yaml.safe_dump(raw_a))
        b.write_text(yaml.safe_dump(raw_b))
        result = compute_spec_diff(a, b)
        rule_id = raw_a["rules"][0]["id"]
        modified = next((m for m in result.rules_modified if m.id == rule_id), None)
        assert modified is not None, "expected the modified rule in rules_modified"
        assert "business_intent changed" in modified.changes, (
            f"business_intent edit must surface; got {modified.changes}"
        )

    def test_out_of_scope_change_surfaces_in_rule_diff(self, tmp_path):
        from aml_framework.diff import compute_spec_diff

        raw = yaml.safe_load(EXAMPLE.read_text())
        raw_a = {**raw, "rules": [dict(raw["rules"][0]), *raw["rules"][1:]]}
        raw_a["rules"][0] = {**raw_a["rules"][0], "out_of_scope": ["scenario A"]}
        raw_b = {**raw, "rules": [dict(raw["rules"][0]), *raw["rules"][1:]]}
        raw_b["rules"][0] = {**raw_b["rules"][0], "out_of_scope": ["scenario A", "scenario B"]}
        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        a.write_text(yaml.safe_dump(raw_a))
        b.write_text(yaml.safe_dump(raw_b))
        result = compute_spec_diff(a, b)
        rule_id = raw_a["rules"][0]["id"]
        modified = next((m for m in result.rules_modified if m.id == rule_id), None)
        assert modified is not None
        assert "out_of_scope changed" in modified.changes
