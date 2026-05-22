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
    def test_defaults_when_unset(self):
        """Existing specs without these fields keep loading — additive
        contract holds. `business_intent` defaults None; `out_of_scope`
        defaults `[]` so callers can iterate without a None-check."""
        spec = load_spec(EXAMPLE)
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
