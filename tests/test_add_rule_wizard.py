"""Tests for `aml add-rule` — interactive new-typology wizard.

The 60-second new-typology promise this guards: an analyst adds a
detection rule via prompts (not by hand-editing YAML), and the spec
stays valid throughout. If the splice ever produces a spec that
fails `load_spec`, the analyst sees a half-broken file on disk.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aml_framework.add_rule_wizard import (
    HighRiskJurisdictionConfig,
    StructuringConfig,
    VelocityBurstConfig,
    render_high_risk_jurisdiction,
    render_structuring,
    render_velocity_burst,
    splice_rule,
    validate_country_codes,
    validate_rule_id,
)
from aml_framework.cli import app
from aml_framework.spec import load_spec

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMUNITY_BANK_SPEC = REPO_ROOT / "examples" / "community_bank" / "aml.yaml"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def working_spec(tmp_path: Path) -> Path:
    """Copy a real spec into tmp so each test mutates its own copy."""
    out = tmp_path / "aml.yaml"
    shutil.copy(COMMUNITY_BANK_SPEC, out)
    return out


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rid,existing,expected_err_substring",
    [
        ("structuring_v2", set(), None),
        ("Structuring", set(), "lowercase"),
        ("9_starts_with_digit", set(), "lowercase"),
        ("with-dash", set(), "lowercase"),
        ("", set(), "empty"),
        ("dup", {"dup"}, "already exists"),
    ],
)
def test_validate_rule_id(rid: str, existing: set[str], expected_err_substring: str | None) -> None:
    err = validate_rule_id(rid, existing)
    if expected_err_substring is None:
        assert err is None
    else:
        assert err is not None
        assert expected_err_substring in err.lower()


@pytest.mark.parametrize(
    "raw,expected",
    [
        (["us", "ca", "gb"], ["US", "CA", "GB"]),
        (["IR", "KP"], ["IR", "KP"]),
        (["", "  "], []),
        (["NotACountry", "USA"], []),  # invalid lengths filtered
        (["us", "USA", "iran"], ["US"]),  # mixed valid + invalid
    ],
)
def test_validate_country_codes(raw: list[str], expected: list[str]) -> None:
    assert validate_country_codes(raw) == expected


# ---------------------------------------------------------------------------
# Renderers — output must satisfy the loader after splice
# ---------------------------------------------------------------------------


def test_render_structuring_produces_valid_rule(working_spec: Path) -> None:
    cfg = StructuringConfig(
        rule_id="test_struct",
        name="Test Structuring",
        severity="high",
        threshold_amount=9500.0,
        window_days=30,
        min_count=3,
        channel="cash",
        direction="in",
        citation="FATF R.20",
        citation_description="Reporting suspicious activity.",
        escalate_to="l2_investigator",
    )
    yaml = render_structuring(cfg)
    splice_rule(working_spec, yaml, "test_struct")
    spec = load_spec(working_spec)
    assert "test_struct" in {r.id for r in spec.rules}


def test_render_velocity_burst_produces_valid_rule(working_spec: Path) -> None:
    cfg = VelocityBurstConfig(
        rule_id="test_velocity",
        name="Test Velocity",
        severity="medium",
        min_count=5,
        window_hours=1,
        direction="in",
        citation="FATF R.20",
        citation_description="Reporting suspicious activity.",
        escalate_to="l2_investigator",
    )
    yaml = render_velocity_burst(cfg)
    splice_rule(working_spec, yaml, "test_velocity")
    spec = load_spec(working_spec)
    assert "test_velocity" in {r.id for r in spec.rules}


def test_render_high_risk_jurisdiction_produces_valid_rule(working_spec: Path) -> None:
    cfg = HighRiskJurisdictionConfig(
        rule_id="test_juris",
        name="Test High-Risk Jurisdiction",
        severity="high",
        countries=["IR", "KP", "RU"],
        amount_floor=1000.0,
        citation="FATF R.19",
        citation_description="Higher-risk countries.",
        escalate_to="l2_investigator",
    )
    yaml = render_high_risk_jurisdiction(cfg)
    splice_rule(working_spec, yaml, "test_juris")
    spec = load_spec(working_spec)
    rule = next(r for r in spec.rules if r.id == "test_juris")
    assert rule.severity == "high"


# ---------------------------------------------------------------------------
# Splice — mutate spec safely
# ---------------------------------------------------------------------------


def test_splice_increases_rule_count(working_spec: Path) -> None:
    before = load_spec(working_spec)
    cfg = StructuringConfig(
        rule_id="splice_test",
        name="Splice Test",
        severity="medium",
        threshold_amount=5000.0,
        window_days=14,
        min_count=2,
        channel="cash",
        direction="in",
        citation="FATF R.20",
        citation_description="x",
        escalate_to="l2_investigator",
    )
    splice_rule(working_spec, render_structuring(cfg), "splice_test")
    after = load_spec(working_spec)
    assert len(after.rules) == len(before.rules) + 1


def test_splice_preserves_existing_workflow_block(working_spec: Path) -> None:
    """Splice should NOT modify `workflow:` content. If the wizard
    damages the workflow block, every queue lookup starts failing
    silently. Compares the parsed workflow object before/after rather
    than raw bytes (the splice may add blank lines for readability)."""
    before = load_spec(working_spec)
    before_workflow = before.workflow.model_dump()

    cfg = StructuringConfig(
        rule_id="preserves_below",
        name="x",
        severity="low",
        threshold_amount=1.0,
        window_days=1,
        min_count=1,
        channel="cash",
        direction="in",
        citation="FATF R.20",
        citation_description="x",
        escalate_to="l2_investigator",
    )
    splice_rule(working_spec, render_structuring(cfg), "preserves_below")

    after = load_spec(working_spec)
    assert after.workflow.model_dump() == before_workflow


def test_splice_rolls_back_on_invalid_yaml(working_spec: Path, tmp_path: Path) -> None:
    """Force the splice to produce an invalid spec — the original file
    must be restored, not left in a half-broken state."""
    bad_yaml = """  - id: bad_rule
    name: Bad
    severity: high
    logic:
      type: not_a_real_logic_type
      source: txn
"""
    before = working_spec.read_text(encoding="utf-8")
    with pytest.raises(Exception):
        splice_rule(working_spec, bad_yaml, "bad_rule")
    after = working_spec.read_text(encoding="utf-8")
    assert before == after, "Splice should have rolled back on failure"


def test_splice_rejects_spec_without_rules_block(tmp_path: Path) -> None:
    p = tmp_path / "no-rules.yaml"
    p.write_text("version: 1\nprogram:\n  name: x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no top-level `rules:`"):
        splice_rule(p, "  - id: x\n", "x")


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_cli_add_rule_structuring_non_interactive(runner: CliRunner, working_spec: Path) -> None:
    result = runner.invoke(
        app,
        [
            "add-rule",
            str(working_spec),
            "--pattern",
            "structuring",
            "--id",
            "cli_struct",
            "--threshold",
            "9000",
            "--window",
            "30",
            "--min-count",
            "3",
            "--non-interactive",
        ],
    )
    assert result.exit_code == 0, result.output
    spec = load_spec(working_spec)
    assert "cli_struct" in {r.id for r in spec.rules}


def test_cli_add_rule_velocity_burst_non_interactive(runner: CliRunner, working_spec: Path) -> None:
    result = runner.invoke(
        app,
        [
            "add-rule",
            str(working_spec),
            "--pattern",
            "velocity_burst",
            "--id",
            "cli_velocity",
            "--window",
            "2",
            "--min-count",
            "10",
            "--non-interactive",
        ],
    )
    assert result.exit_code == 0, result.output


def test_cli_add_rule_high_risk_jurisdiction(runner: CliRunner, working_spec: Path) -> None:
    result = runner.invoke(
        app,
        [
            "add-rule",
            str(working_spec),
            "--pattern",
            "high_risk_jurisdiction",
            "--id",
            "cli_juris",
            "--countries",
            "RU,KP,IR",
            "--threshold",
            "1000",
            "--non-interactive",
        ],
    )
    assert result.exit_code == 0, result.output


def test_cli_add_rule_rejects_duplicate_id(runner: CliRunner, working_spec: Path) -> None:
    """Use an id that actually exists in community_bank — picks up the
    'rule id already exists' validator at the source."""
    result = runner.invoke(
        app,
        [
            "add-rule",
            str(working_spec),
            "--id",
            "structuring_cash_deposits",  # real existing rule in community_bank
            "--non-interactive",
        ],
    )
    assert result.exit_code == 2
    assert "already exists" in result.output.lower()


def test_cli_add_rule_auto_detects_queue_when_default_missing(
    runner: CliRunner, working_spec: Path
) -> None:
    """The default --escalate-to is `l2_review` but the community_bank
    spec has `l2_investigator`. The CLI must auto-pick a sensible queue
    from the spec rather than failing validation."""
    result = runner.invoke(
        app,
        [
            "add-rule",
            str(working_spec),
            "--pattern",
            "structuring",
            "--id",
            "auto_queue_test",
            "--threshold",
            "5000",
            "--window",
            "14",
            "--min-count",
            "3",
            "--non-interactive",
        ],
    )
    assert result.exit_code == 0, result.output
    spec = load_spec(working_spec)
    rule = next(r for r in spec.rules if r.id == "auto_queue_test")
    assert rule.escalate_to == "l2_investigator"


def test_cli_add_rule_unknown_pattern(runner: CliRunner, working_spec: Path) -> None:
    result = runner.invoke(
        app,
        [
            "add-rule",
            str(working_spec),
            "--pattern",
            "ml_scoring",
            "--id",
            "x",
            "--non-interactive",
        ],
    )
    assert result.exit_code == 2
    assert "Unknown pattern" in result.output


def test_cli_add_rule_requires_id_in_non_interactive(runner: CliRunner, working_spec: Path) -> None:
    result = runner.invoke(
        app,
        ["add-rule", str(working_spec), "--non-interactive"],
    )
    assert result.exit_code == 2
    assert "id is required" in result.output.lower()
