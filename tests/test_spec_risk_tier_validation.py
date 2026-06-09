"""risk_tier coverage validation — issue #529 (Sub-feature B, Pillars 4+5).

The `risk_tier` field stays OPTIONAL on the pydantic model (a legacy
spec without it still loads — pinned by `tests/test_spec_risk_tier.py`).
This suite pins the *validation pass* that enforces the expectation:

  * an active rule missing risk_tier -> WARN (non-strict), ERROR (strict);
  * non-active rules carry no expectation;
  * every bundled example spec is fully tiered (validates clean, even
    under --strict);
  * the `aml validate --strict` CLI exits 1 on a missing tier, 0 clean.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from aml_framework.cli import app
from aml_framework.spec.loader import load_spec
from aml_framework.spec.validation import (
    SpecValidationError,
    collect_risk_tier_warnings,
    validate_risk_tier_coverage,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = sorted((ROOT / "examples").glob("*/aml.yaml"))
EXAMPLE = ROOT / "examples" / "crypto_vasp" / "aml.yaml"

runner = CliRunner()


def _spec_missing_one_tier(tmp_path: Path) -> Path:
    raw = yaml.safe_load(EXAMPLE.read_text())
    # The first rule is active; strip its risk_tier to create a gap.
    raw["rules"][0].pop("risk_tier", None)
    f = tmp_path / "aml.yaml"
    f.write_text(yaml.safe_dump(raw))
    return f


class TestRiskTierWarnings:
    def test_missing_tier_on_active_rule_warns(self, tmp_path):
        spec = load_spec(_spec_missing_one_tier(tmp_path))
        warnings = collect_risk_tier_warnings(spec)
        assert len(warnings) == 1
        assert spec.rules[0].id in warnings[0]

    def test_non_active_rule_not_flagged(self, tmp_path):
        raw = yaml.safe_load(EXAMPLE.read_text())
        raw["rules"][0].pop("risk_tier", None)
        raw["rules"][0]["status"] = "experimental"
        f = tmp_path / "aml.yaml"
        f.write_text(yaml.safe_dump(raw))
        spec = load_spec(f)
        # An experimental rule with no risk_tier is NOT a governance gap.
        assert collect_risk_tier_warnings(spec) == []

    def test_non_strict_returns_warnings_without_raising(self, tmp_path):
        spec = load_spec(_spec_missing_one_tier(tmp_path))
        warnings = validate_risk_tier_coverage(spec, strict=False)
        assert len(warnings) == 1

    def test_strict_raises_on_gap(self, tmp_path):
        spec = load_spec(_spec_missing_one_tier(tmp_path))
        with pytest.raises(SpecValidationError):
            validate_risk_tier_coverage(spec, strict=True)

    def test_strict_passes_when_fully_tiered(self):
        spec = load_spec(EXAMPLE)
        # No gap -> strict returns the empty warning list, never raises.
        assert validate_risk_tier_coverage(spec, strict=True) == []


class TestExampleSpecsFullyTiered:
    @pytest.mark.parametrize("spec_path", EXAMPLES, ids=lambda p: p.parent.name)
    def test_every_active_rule_is_tiered(self, spec_path):
        spec = load_spec(spec_path)
        # Each bundled example carries risk_tier on every active rule, so
        # the strict pass must pass clean.
        assert validate_risk_tier_coverage(spec, strict=True) == []


class TestValidateCLIStrict:
    def test_cli_strict_passes_on_tiered_example(self):
        result = runner.invoke(app, ["validate", str(EXAMPLE), "--strict"])
        assert result.exit_code == 0, result.output

    def test_cli_strict_fails_on_missing_tier(self, tmp_path):
        bad = _spec_missing_one_tier(tmp_path)
        result = runner.invoke(app, ["validate", str(bad), "--strict"])
        assert result.exit_code == 1
        assert "missing risk_tier" in result.output

    def test_cli_non_strict_warns_but_passes(self, tmp_path):
        bad = _spec_missing_one_tier(tmp_path)
        result = runner.invoke(app, ["validate", str(bad)])
        assert result.exit_code == 0, result.output
        assert "WARN" in result.output
