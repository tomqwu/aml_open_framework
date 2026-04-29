"""Tests for `aml init` — the new-bank scaffolding wizard.

The day-one developer-onboarding promise this guards: 5 questions →
working spec + sample data + smoke-test in <60 seconds. If any of
these fail, a developer's first encounter with the framework breaks.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from aml_framework.cli import app
from aml_framework.init_wizard import (
    JURISDICTION_DEFAULTS,
    InitConfig,
    normalise_archetype,
    normalise_jurisdiction,
    render_readme,
    render_spec,
    validate_program_name,
    write_scaffold,
)
from aml_framework.spec import load_spec


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# Pure-function helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,ok",
    [
        ("acme_aml", True),
        ("acme_us_aml", True),
        ("a", True),
        ("acme123", True),
        ("Acme", False),  # uppercase rejected
        ("9_starts_with_digit", False),
        ("", False),
        ("with-dash", False),
        ("with space", False),
    ],
)
def test_validate_program_name(name: str, ok: bool) -> None:
    err = validate_program_name(name)
    assert (err is None) is ok


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("US", "US"),
        ("usa", "US"),
        ("uk", "GB"),
        ("Britain", "GB"),
        ("Europe", "EU"),
        ("singapore", "SG"),
        ("nowhere", "OTHER"),
    ],
)
def test_normalise_jurisdiction(raw: str, expected: str) -> None:
    assert normalise_jurisdiction(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("community_bank", "community_bank"),
        ("schedule_i_bank", "schedule_i_bank"),
        ("schedule-i", "schedule_i_bank"),
        ("schedule1", "schedule_i_bank"),
        ("Tier 1", "schedule_i_bank"),
        ("vasp", "vasp"),
        ("Crypto", "vasp"),
        ("exchange", "vasp"),
        ("fintech", "fintech"),
        ("neobank", "fintech"),
        ("anything-else", "community_bank"),
    ],
)
def test_normalise_archetype(raw: str, expected: str) -> None:
    assert normalise_archetype(raw) == expected


def test_jurisdiction_defaults_cover_every_known_key() -> None:
    """Every jurisdiction the wizard offers must have a (regulator, currency)
    default — otherwise the pipeline crashes after the user picks one."""
    for code in ("US", "CA", "GB", "EU", "AU", "SG", "OTHER"):
        assert code in JURISDICTION_DEFAULTS
        regulator, currency = JURISDICTION_DEFAULTS[code]
        assert regulator and len(currency) == 3


# ---------------------------------------------------------------------------
# Spec rendering — must validate and run end-to-end
# ---------------------------------------------------------------------------


def _config(tmp_path: Path, **overrides) -> InitConfig:
    base = dict(
        program_name="acme_aml",
        jurisdiction="US",
        regulator="FinCEN",
        archetype="community_bank",
        target_dir=tmp_path,
        currency="USD",
    )
    base.update(overrides)
    return InitConfig(**base)


def test_render_spec_validates_against_real_loader(tmp_path: Path) -> None:
    """The output must satisfy the same JSON Schema + Pydantic checks the
    engine uses at runtime — anything else means a half-broken scaffold."""
    cfg = _config(tmp_path)
    spec_path = tmp_path / "aml.yaml"
    spec_path.write_text(render_spec(cfg), encoding="utf-8")
    spec = load_spec(spec_path)
    assert spec.program.name == "acme_aml"
    assert spec.program.jurisdiction == "US"
    assert len(spec.rules) >= 3
    assert len(spec.workflow.queues) >= 3


@pytest.mark.parametrize("archetype", ["community_bank", "schedule_i_bank", "vasp", "fintech"])
def test_render_spec_validates_for_every_archetype(tmp_path: Path, archetype: str) -> None:
    cfg = _config(tmp_path, archetype=archetype)
    spec_path = tmp_path / "aml.yaml"
    spec_path.write_text(render_spec(cfg), encoding="utf-8")
    load_spec(spec_path)  # raises on failure


@pytest.mark.parametrize("juris", ["US", "CA", "GB", "EU", "AU", "SG", "OTHER"])
def test_render_spec_validates_for_every_jurisdiction(tmp_path: Path, juris: str) -> None:
    regulator, currency = JURISDICTION_DEFAULTS[juris]
    cfg = _config(tmp_path, jurisdiction=juris, regulator=regulator, currency=currency)
    spec_path = tmp_path / "aml.yaml"
    spec_path.write_text(render_spec(cfg), encoding="utf-8")
    load_spec(spec_path)


def test_render_readme_includes_next_steps(tmp_path: Path) -> None:
    cfg = _config(tmp_path)
    readme = render_readme(cfg)
    assert "aml validate" in readme
    assert "aml run" in readme
    assert "aml dashboard" in readme


# ---------------------------------------------------------------------------
# Disk writer
# ---------------------------------------------------------------------------


def test_write_scaffold_creates_both_files(tmp_path: Path) -> None:
    cfg = _config(tmp_path / "scaffold")
    out = write_scaffold(cfg)
    assert out.spec_path.exists()
    assert out.readme_path.exists()
    assert out.spec_path.parent == tmp_path / "scaffold"


def test_write_scaffold_refuses_to_overwrite_by_default(tmp_path: Path) -> None:
    cfg = _config(tmp_path / "scaffold")
    write_scaffold(cfg)
    with pytest.raises(FileExistsError):
        write_scaffold(cfg)


def test_write_scaffold_replaces_when_overwrite_true(tmp_path: Path) -> None:
    cfg = _config(tmp_path / "scaffold")
    write_scaffold(cfg)
    # Mutate target spec then re-run with overwrite — should restore.
    (tmp_path / "scaffold" / "aml.yaml").write_text("garbage", encoding="utf-8")
    out = write_scaffold(cfg, overwrite=True)
    assert "version: 1" in out.spec_path.read_text()


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_cli_init_non_interactive_works(runner: CliRunner, tmp_path: Path) -> None:
    target = tmp_path / "myacme"
    result = runner.invoke(app, ["init", str(target), "--non-interactive"])
    assert result.exit_code == 0, result.output
    assert (target / "aml.yaml").exists()
    assert (target / "README.md").exists()


def test_cli_init_with_archetype_flag(runner: CliRunner, tmp_path: Path) -> None:
    target = tmp_path / "myvasp"
    result = runner.invoke(
        app,
        [
            "init",
            str(target),
            "--non-interactive",
            "--archetype",
            "vasp",
            "--jurisdiction",
            "GB",
        ],
    )
    assert result.exit_code == 0, result.output
    spec = load_spec(target / "aml.yaml")
    assert spec.program.jurisdiction == "GB"
    assert spec.program.regulator == "FCA"
    # Crypto channel should appear in the txn contract enum (VASP archetype)
    txn = next(c for c in spec.data_contracts if c.id == "txn")
    channel_col = next(col for col in txn.columns if col.name == "channel")
    assert "crypto" in (channel_col.enum or [])


def test_cli_init_rejects_invalid_program_name(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "init",
            str(tmp_path / "bad"),
            "--non-interactive",
            "--program",
            "Has Spaces",
        ],
    )
    assert result.exit_code == 2
    assert "Program name must" in result.output


def test_cli_init_refuses_existing_dir_without_overwrite(runner: CliRunner, tmp_path: Path) -> None:
    target = tmp_path / "twice"
    runner.invoke(app, ["init", str(target), "--non-interactive"])
    result = runner.invoke(app, ["init", str(target), "--non-interactive"])
    assert result.exit_code == 1
    assert "already exists" in result.output


def test_cli_init_overwrite_flag_replaces_existing(runner: CliRunner, tmp_path: Path) -> None:
    target = tmp_path / "again"
    runner.invoke(app, ["init", str(target), "--non-interactive"])
    result = runner.invoke(app, ["init", str(target), "--non-interactive", "--overwrite"])
    assert result.exit_code == 0, result.output


def test_cli_init_prints_next_step_commands(runner: CliRunner, tmp_path: Path) -> None:
    """The whole point of the wizard is the developer knows what to type
    next. If we ever stop printing those commands, the onboarding promise
    breaks."""
    target = tmp_path / "nextsteps"
    result = runner.invoke(app, ["init", str(target), "--non-interactive"])
    assert "aml validate" in result.output
    assert "aml run" in result.output
    assert "aml dashboard" in result.output
