"""CLI smoke tests for `aml queue-rank` — PR-PROC-2.

These tests guard the operator-facing surface, not the math (the math
lives in test_cases_triage.py). They check that the command finds a run
dir, prints a ranking table, exits cleanly when there's nothing to rank,
and bails with a useful message when the operator hasn't run the engine.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aml_framework.cli import app
from aml_framework.data import generate_dataset
from aml_framework.engine import run_spec
from aml_framework.spec import load_spec

SPEC_CA = Path(__file__).resolve().parents[1] / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


@pytest.fixture(scope="module")
def run_artifacts(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Run the engine once per test module and reuse the artifacts dir."""
    artifacts = tmp_path_factory.mktemp("queue-rank-artifacts")
    spec = load_spec(SPEC_CA)
    # Naive UTC matches the engine's case-timestamp serialisation; mixing
    # would crash compute_sla_status with aware/naive subtraction errors.
    as_of = datetime(2026, 4, 23, 12, 0, 0)
    run_spec(
        spec=spec,
        spec_path=SPEC_CA,
        data=generate_dataset(as_of=as_of, seed=42),
        as_of=as_of,
        artifacts_root=artifacts,
    )
    return artifacts


def _newest_run(artifacts: Path) -> Path:
    return sorted(artifacts.glob("run-*"), reverse=True)[0]


class TestQueueRankCli:
    def test_prints_ranked_table(self, run_artifacts: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "queue-rank",
                str(SPEC_CA),
                "--run-dir",
                str(_newest_run(run_artifacts)),
                "--top",
                "3",
            ],
        )
        assert result.exit_code == 0, result.output
        # Table title + score column header are stable strings rendered by
        # Rich. Check both — header alone could match an unrelated table.
        assert "Triage rank" in result.output
        assert "Score" in result.output

    def test_top_n_caps_rendered_rows(self, run_artifacts: Path) -> None:
        runner = CliRunner()
        run_dir = _newest_run(run_artifacts)
        cases_count = sum(
            1 for p in (run_dir / "cases").glob("*.json") if not p.name.endswith("__filing.json")
        )
        assert cases_count >= 2, "demo spec should produce at least 2 cases for this test"

        result = runner.invoke(
            app,
            ["queue-rank", str(SPEC_CA), "--run-dir", str(run_dir), "--top", "1"],
        )
        assert result.exit_code == 0, result.output
        assert f"top 1 of {cases_count}" in result.output

    def test_artifacts_arg_finds_newest_run(self, run_artifacts: Path) -> None:
        # Operator runs `aml queue-rank spec.yaml` without --run-dir from
        # the project root — should pick up the newest run under
        # .artifacts/. Pass our tmp artifacts root via --artifacts.
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["queue-rank", str(SPEC_CA), "--artifacts", str(run_artifacts)],
        )
        assert result.exit_code == 0, result.output
        assert "Triage rank" in result.output

    def test_missing_artifacts_dir_exits_with_actionable_error(self, tmp_path: Path) -> None:
        runner = CliRunner()
        empty_artifacts = tmp_path / "empty"
        empty_artifacts.mkdir()
        result = runner.invoke(
            app,
            ["queue-rank", str(SPEC_CA), "--artifacts", str(empty_artifacts)],
        )
        assert result.exit_code == 1
        assert "No run dirs" in result.output
        assert "aml run" in result.output  # tells operator what to do next

    def test_run_dir_without_cases_dir_exits_with_error(self, tmp_path: Path) -> None:
        # A run dir that exists but has no cases/ subdir — point at it
        # explicitly so the operator gets told why nothing ranked.
        run_dir = tmp_path / "run-bogus"
        run_dir.mkdir()
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["queue-rank", str(SPEC_CA), "--run-dir", str(run_dir)],
        )
        assert result.exit_code == 1
        assert "No cases dir" in result.output

    def test_empty_cases_dir_yields_friendly_message(self, tmp_path: Path) -> None:
        run_dir = tmp_path / "run-empty"
        (run_dir / "cases").mkdir(parents=True)
        runner = CliRunner()
        result = runner.invoke(
            app,
            ["queue-rank", str(SPEC_CA), "--run-dir", str(run_dir)],
        )
        # Empty cases is a not-an-error condition: the operator did the
        # right thing, the engine just emitted nothing this run.
        assert result.exit_code == 0
        assert "No cases" in result.output

    def test_filing_sidecars_skipped(self, run_artifacts: Path, tmp_path: Path) -> None:
        # Drop a fake __filing.json into a cases dir alongside one real
        # case — the sidecar is PR-DATA-9's filing-latency artifact and
        # must not be ranked as a case.
        run_dir = tmp_path / "run-sidecar"
        cases_dir = run_dir / "cases"
        cases_dir.mkdir(parents=True)

        real = next(p for p in (_newest_run(run_artifacts) / "cases").glob("*.json"))
        (cases_dir / real.name).write_text(real.read_text(encoding="utf-8"), encoding="utf-8")
        (cases_dir / "C9999__filing.json").write_text(
            json.dumps({"case_id": "C9999", "filed_at": "2026-04-24T00:00:00Z"}),
            encoding="utf-8",
        )

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["queue-rank", str(SPEC_CA), "--run-dir", str(run_dir)],
        )
        assert result.exit_code == 0, result.output
        # Only the real case should be in the count.
        assert "of 1 cases" in result.output
        assert "C9999" not in result.output
