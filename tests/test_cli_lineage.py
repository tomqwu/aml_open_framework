"""PR-LIN-19: CLI commands `aml lineage` + `aml verify-decisions`.

Smoke tests that the new commands wire walk_lineage() and
AuditLedger.verify_decisions() correctly. End-to-end shape:

  1. Run the engine to produce a real run dir.
  2. Invoke `aml lineage <case_id>` and parse the JSON output.
  3. Invoke `aml verify-decisions` and assert exit 0 on a clean chain.
  4. Tamper with decisions.jsonl and assert exit 1.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aml_framework.cli import app
from aml_framework.data.synthetic import generate_dataset
from aml_framework.engine.runner import run_spec
from aml_framework.spec.loader import load_spec

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = REPO_ROOT / "examples" / "community_bank" / "aml.yaml"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def fresh_run(tmp_path: Path) -> tuple[Path, str]:
    """Run the engine once and return (artifacts_dir, sample_case_id)."""
    spec = load_spec(SPEC)
    data = generate_dataset(as_of=datetime(2026, 5, 1, tzinfo=timezone.utc), seed=42)
    result = run_spec(
        spec=spec,
        spec_path=SPEC,
        data=data,
        as_of=datetime(2026, 5, 1, tzinfo=timezone.utc),
        artifacts_root=tmp_path,
    )
    assert result.case_ids, "community_bank spec should produce at least one case"
    return tmp_path, result.case_ids[0]


class TestLineageCommand:
    def test_lineage_json_round_trips_case_id(
        self, runner: CliRunner, fresh_run: tuple[Path, str]
    ) -> None:
        artifacts, case_id = fresh_run
        result = runner.invoke(
            app,
            ["lineage", case_id, "--artifacts", str(artifacts), "--format", "json"],
        )
        assert result.exit_code == 0, f"lineage cmd crashed:\n{result.output}"
        # Strip Rich's syntax highlighting markers; the JSON itself must
        # parse and carry the case_id.
        chain = json.loads(result.output)
        assert chain["case_id"] == case_id
        assert chain["rule_id"]
        assert chain["rule_version"]

    def test_lineage_table_format_renders_anchors(
        self, runner: CliRunner, fresh_run: tuple[Path, str]
    ) -> None:
        artifacts, case_id = fresh_run
        result = runner.invoke(
            app,
            ["lineage", case_id, "--artifacts", str(artifacts), "--format", "table"],
        )
        assert result.exit_code == 0
        assert "rule_id" in result.output
        assert "rule_version" in result.output
        assert "matched source rows" in result.output

    def test_lineage_unknown_case_exits_non_zero(
        self, runner: CliRunner, fresh_run: tuple[Path, str]
    ) -> None:
        artifacts, _ = fresh_run
        result = runner.invoke(
            app,
            ["lineage", "C-DOES-NOT-EXIST", "--artifacts", str(artifacts)],
        )
        assert result.exit_code == 1


class TestVerifyDecisionsCommand:
    def test_clean_run_exits_zero(self, runner: CliRunner, fresh_run: tuple[Path, str]) -> None:
        artifacts, _ = fresh_run
        result = runner.invoke(app, ["verify-decisions", "--artifacts", str(artifacts)])
        assert result.exit_code == 0
        assert "verified" in result.output.lower() or "ok" in result.output.lower()

    def test_tampered_run_exits_non_zero(
        self, runner: CliRunner, fresh_run: tuple[Path, str]
    ) -> None:
        artifacts, _ = fresh_run
        # Corrupt decisions.jsonl in the latest run dir.
        run_dirs = sorted(artifacts.glob("run-*"))
        decisions_path = run_dirs[-1] / "decisions.jsonl"
        with decisions_path.open("ab") as f:
            f.write(b'{"event":"tamper","case_id":"INJECTED","rule_id":"x","schema_version":2}\n')
        result = runner.invoke(app, ["verify-decisions", "--artifacts", str(artifacts)])
        assert result.exit_code == 1
        assert "tamper" in result.output.lower()
