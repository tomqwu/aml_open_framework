"""Smoke tests for `aml demo` — the 5-minute guided CLI demo.

The story this command tells is the product. If it ever fails, a buyer's
first encounter with the framework breaks. These tests guard the
narrative invariants:

- the command runs end-to-end without throwing
- it emits each of the five guided steps in order
- it tailors the closing next-steps to the chosen persona
- it gracefully skips next-step suggestions whose target file was not
  produced (e.g. effectiveness pack on a spec without aml_priority)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from aml_framework.cli import app

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_SPEC = REPO_ROOT / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _invoke_demo(runner: CliRunner, tmp_path: Path, persona: str = "cco") -> str:
    artifacts = tmp_path / "demo"
    result = runner.invoke(
        app,
        [
            "demo",
            str(DEMO_SPEC),
            "--persona",
            persona,
            "--artifacts",
            str(artifacts),
            "--no-launch",
        ],
    )
    assert result.exit_code == 0, f"demo crashed:\n{result.output}\n{result.exception}"
    return result.output


def test_demo_walks_all_five_steps(runner: CliRunner, tmp_path: Path) -> None:
    output = _invoke_demo(runner, tmp_path)
    assert "1." in output and "Reading the spec" in output
    assert "2." in output and "Running the engine" in output
    assert "3." in output and "Sealing the audit chain" in output
    assert "4." in output and "regulator pack" in output
    assert "Next 5 minutes for a CCO" in output


def test_demo_produces_audit_pack(runner: CliRunner, tmp_path: Path) -> None:
    _invoke_demo(runner, tmp_path)
    audit_zip = tmp_path / "demo" / "audit-pack.zip"
    assert audit_zip.exists(), "audit-pack.zip should be created"
    assert audit_zip.stat().st_size > 1000, "audit pack should not be empty"


@pytest.mark.parametrize("persona", ["cco", "mlro", "analyst", "auditor"])
def test_demo_supports_all_personas(runner: CliRunner, tmp_path: Path, persona: str) -> None:
    output = _invoke_demo(runner, tmp_path, persona=persona)
    assert f"Next 5 minutes for a {persona.upper()}" in output


def test_demo_rejects_unknown_persona(runner: CliRunner, tmp_path: Path) -> None:
    artifacts = tmp_path / "demo"
    result = runner.invoke(
        app,
        [
            "demo",
            str(DEMO_SPEC),
            "--persona",
            "ceo",
            "--artifacts",
            str(artifacts),
            "--no-launch",
        ],
    )
    assert result.exit_code != 0
    assert "Unknown persona" in result.output


def test_demo_skips_next_step_for_missing_file(runner: CliRunner, tmp_path: Path) -> None:
    """If effectiveness.json was not produced, the CCO 'Read the
    effectiveness pack' next-step must not be suggested. The current
    canonical demo spec has no aml_priority so this is the live case."""
    output = _invoke_demo(runner, tmp_path, persona="cco")
    assert "FinCEN-aligned effectiveness pack" not in output
    assert "audit pack you'd hand a regulator" in output


def test_demo_persona_steps_reference_correct_artifacts_dir(
    runner: CliRunner, tmp_path: Path
) -> None:
    """Persona next-steps must reference the user-supplied --artifacts
    path, not a hardcoded .artifacts/demo. This matters when the demo
    is invoked from outside the repo."""
    output = _invoke_demo(runner, tmp_path, persona="auditor")
    # Rich may wrap long temp paths across lines, so compare without
    # presentation whitespace.
    assert str(tmp_path / "demo") in "".join(output.split())
