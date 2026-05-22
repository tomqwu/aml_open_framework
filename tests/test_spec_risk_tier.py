"""PR-RISK-1 — optional `risk_tier` on Rule.

Closes the Pillar 5 (Risk-based controls) gap on
`pages/43_North_Star_Coverage.py`: until now the rule-side priority
signal was `severity` (alert urgency) and the routing signal was
`escalate_to` (queue name), neither of which is a first-class risk
attribute. This PR is additive-only — schema/model/diff/hash wire-in;
engine-time routing wire-in ships separately.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from aml_framework.spec.loader import load_spec

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


class TestRuleRiskTier:
    def test_default_is_none(self):
        """Existing specs without `risk_tier` keep loading — additive
        contract holds. Default None means "no risk-tier signal
        authored" (different from any of the three enum values)."""
        spec = load_spec(EXAMPLE)
        rule = spec.rules[0]
        assert rule.risk_tier is None

    def test_valid_tier_round_trips(self, tmp_path):
        raw = yaml.safe_load(EXAMPLE.read_text())
        raw["rules"][0]["risk_tier"] = "high"
        f = tmp_path / "aml.yaml"
        f.write_text(yaml.safe_dump(raw))
        spec = load_spec(f)
        assert spec.rules[0].risk_tier == "high"

    @pytest.mark.parametrize("tier", ["low", "medium", "high"])
    def test_all_enum_values_accepted(self, tmp_path, tier):
        """All three enum values round-trip — guards against a typo
        in the schema enum / model Literal causing one tier to be
        silently rejected."""
        raw = yaml.safe_load(EXAMPLE.read_text())
        raw["rules"][0]["risk_tier"] = tier
        f = tmp_path / "aml.yaml"
        f.write_text(yaml.safe_dump(raw))
        spec = load_spec(f)
        assert spec.rules[0].risk_tier == tier

    def test_invalid_tier_rejected(self, tmp_path):
        """Schema enum constrains to low/medium/high — anything else
        is a hard reject at load time so a typo can't ship as a
        valid-looking but unhandled value."""
        raw = yaml.safe_load(EXAMPLE.read_text())
        raw["rules"][0]["risk_tier"] = "critical"  # not in the enum
        f = tmp_path / "aml.yaml"
        f.write_text(yaml.safe_dump(raw))
        with pytest.raises(ValueError):
            load_spec(f)


class TestRuleVersionStability:
    """Additive-schema discipline (mirrors PR-A2): the schema bump
    alone must NOT churn `rule_version_hash` for existing specs that
    don't author `risk_tier` — otherwise historical lineage diffs
    falsely show every rule as "modified" the day this schema lands.

    Once authored, an explicit risk-tier change IS a rule-version
    change (the alert population it implies is different)."""

    def test_rule_version_unchanged_when_risk_tier_at_default(self):
        from aml_framework.engine.audit import rule_version_hash
        from aml_framework.spec.models import (
            AggregationWindowLogic,
            RegulationRef,
            Rule,
        )

        # Two rules identical except the second explicitly sets
        # `risk_tier=None`. Hash must be the same so a `.from_yaml()`
        # rule (unset field) matches a programmatically built rule
        # (explicit default).
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
            risk_tier=None,  # explicit default
        )
        assert rule_version_hash(rule_a) == rule_version_hash(rule_b)

    def test_rule_version_stable_for_dict_callers_at_default(self):
        """Dict callers (e.g. `rule.model_dump()`) must get the same
        hash as a Pydantic model with the unset default. Otherwise
        the dict path still churns rule_version on the schema bump."""
        from aml_framework.engine.audit import rule_version_hash

        rule_dict_no_new_field = {
            "id": "r1",
            "name": "R1",
            "severity": "medium",
            "logic": {"type": "aggregation_window", "source": "txn"},
            "escalate_to": "q",
        }
        rule_dict_with_default_new_field = {
            **rule_dict_no_new_field,
            "risk_tier": None,
        }
        assert rule_version_hash(rule_dict_no_new_field) == rule_version_hash(
            rule_dict_with_default_new_field
        )

    def test_rule_version_changes_when_risk_tier_authored(self):
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
        authored = Rule(**base_kwargs, risk_tier="high")
        assert rule_version_hash(unauthored) != rule_version_hash(authored), (
            "authoring risk_tier IS a rule-version change"
        )


class TestSpecDiffSurfacesRiskTier:
    """Schema description promised risk_tier would be visible to
    risk-based-controls reviewers. As a minimum wire-in,
    `compute_spec_diff` should surface changes to risk_tier so an
    `aml diff` reviewer sees re-tiering events, not just mechanical
    fields."""

    def test_risk_tier_change_surfaces_in_rule_diff(self, tmp_path):
        from aml_framework.diff import compute_spec_diff

        raw = yaml.safe_load(EXAMPLE.read_text())
        raw_a = {**raw, "rules": [dict(raw["rules"][0]), *raw["rules"][1:]]}
        raw_a["rules"][0] = {**raw_a["rules"][0], "risk_tier": "low"}
        raw_b = {**raw, "rules": [dict(raw["rules"][0]), *raw["rules"][1:]]}
        raw_b["rules"][0] = {**raw_b["rules"][0], "risk_tier": "high"}
        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        a.write_text(yaml.safe_dump(raw_a))
        b.write_text(yaml.safe_dump(raw_b))
        result = compute_spec_diff(a, b)
        rule_id = raw_a["rules"][0]["id"]
        modified = next((m for m in result.rules_modified if m.id == rule_id), None)
        assert modified is not None, "expected the modified rule in rules_modified"
        assert "risk_tier: low -> high" in modified.changes, (
            f"risk_tier edit must surface as a value transition; got {modified.changes}"
        )

    def test_risk_tier_authoring_surfaces_in_rule_diff(self, tmp_path):
        """Going from unset (None) to authored is itself a risk-based
        control change — must surface in the diff so a reviewer sees
        the first-time tiering event."""
        from aml_framework.diff import compute_spec_diff

        raw = yaml.safe_load(EXAMPLE.read_text())
        a = tmp_path / "a.yaml"
        b = tmp_path / "b.yaml"
        a.write_text(yaml.safe_dump(raw))
        raw_b = {**raw, "rules": [dict(raw["rules"][0]), *raw["rules"][1:]]}
        raw_b["rules"][0] = {**raw_b["rules"][0], "risk_tier": "medium"}
        b.write_text(yaml.safe_dump(raw_b))
        result = compute_spec_diff(a, b)
        rule_id = raw["rules"][0]["id"]
        modified = next((m for m in result.rules_modified if m.id == rule_id), None)
        assert modified is not None
        assert "risk_tier: None -> medium" in modified.changes
