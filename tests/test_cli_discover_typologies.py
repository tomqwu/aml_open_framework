"""CLI tests for `aml discover-typologies` (#496).

Offline candidate-typology proposal command: loads the spec's data,
computes per-customer features, reads a run's alerts (who's already
caught), calls `discover_candidates`, and writes a human-gated
`candidate_typologies.yaml` of PROPOSED rule stubs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from aml_framework.cli import app

SPEC = Path("examples/canadian_schedule_i_bank/aml.yaml")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _make_run_dir(tmp_path: Path, alerted: list[str]) -> Path:
    """Build a minimal run dir with one alerts/*.jsonl file.

    Mirrors the on-disk layout `unmask_alerts()` reads: per-rule
    `<run_dir>/alerts/<rule_id>.jsonl`, one alert per line, each carrying
    a `customer_id`.
    """
    run_dir = tmp_path / "run-test"
    alerts_dir = run_dir / "alerts"
    alerts_dir.mkdir(parents=True)
    lines = "\n".join(json.dumps({"customer_id": cid, "rule_id": "demo_rule"}) for cid in alerted)
    (alerts_dir / "demo_rule.jsonl").write_text(lines + "\n", encoding="utf-8")
    return run_dir


def test_discover_typologies_happy_path(runner: CliRunner, tmp_path: Path) -> None:
    """On synthetic data with no customers caught, the unexplained
    population is large enough to surface at least one candidate; the
    written YAML must parse and every rule stub must be governance-gated
    (`status: pending_promotion`)."""
    run_dir = _make_run_dir(tmp_path, alerted=[])
    out = tmp_path / "candidate_typologies.yaml"

    result = runner.invoke(
        app,
        [
            "discover-typologies",
            str(SPEC),
            str(run_dir),
            "--output",
            str(out),
            "--seed",
            "42",
            "--as-of",
            "2024-01-01",
            # The synthetic feature distribution surfaces a heavy-tailed
            # sum_amount cohort at z>=1.5 (z=2.0 is empty for this dataset).
            "--anomaly-z",
            "1.5",
        ],
    )

    assert result.exit_code == 0, result.output
    assert out.exists(), result.output
    doc = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert doc["candidates"], "expected at least one candidate"
    for cand in doc["candidates"]:
        assert cand["rule"]["status"] == "pending_promotion"
        assert cand["metadata"]["discovered_from"] == run_dir.name
        assert cand["metadata"]["size"] >= 1
        assert isinstance(cand["metadata"]["anomalous_features"], list)
    # Governance language is surfaced to the operator.
    assert "pending_promotion" in result.output
    assert "PROPOSAL" in result.output.upper()


def test_discover_typologies_zero_candidates_writes_nothing(
    runner: CliRunner, tmp_path: Path
) -> None:
    """When the discovery threshold is unreachable (impossibly high z),
    no candidate is found, no file is written, and the command exits 0
    with a clear message."""
    run_dir = _make_run_dir(tmp_path, alerted=[])
    out = tmp_path / "candidate_typologies.yaml"

    result = runner.invoke(
        app,
        [
            "discover-typologies",
            str(SPEC),
            str(run_dir),
            "--output",
            str(out),
            "--anomaly-z",
            "999",
            "--seed",
            "42",
            "--as-of",
            "2024-01-01",
        ],
    )

    assert result.exit_code == 0, result.output
    assert not out.exists()
    assert "No candidate typologies" in result.output


def test_discover_typologies_reads_as_of_from_manifest_when_not_passed(
    runner: CliRunner, tmp_path: Path
) -> None:
    """Determinism (codex P1): without `--as-of`, the command anchors to the
    run's `as_of` from manifest.json (not the wall clock). The same run dir +
    seed must yield a byte-identical candidate_typologies.yaml, and that output
    must match an explicit `--as-of` equal to the manifest value."""
    run_dir = _make_run_dir(tmp_path, alerted=[])
    (run_dir / "manifest.json").write_text(
        json.dumps({"as_of": "2024-01-01T00:00:00"}), encoding="utf-8"
    )
    no_flag = tmp_path / "from_manifest.yaml"
    explicit = tmp_path / "from_flag.yaml"

    base_args = [
        "discover-typologies",
        str(SPEC),
        str(run_dir),
        "--seed",
        "42",
        "--anomaly-z",
        "1.5",
    ]
    r1 = runner.invoke(app, [*base_args, "--output", str(no_flag)])
    r2 = runner.invoke(
        app,
        [*base_args, "--output", str(explicit), "--as-of", "2024-01-01T00:00:00"],
    )

    assert r1.exit_code == 0, r1.output
    assert r2.exit_code == 0, r2.output
    assert no_flag.read_text(encoding="utf-8") == explicit.read_text(encoding="utf-8")


def test_discover_typologies_default_output_under_run_dir(
    runner: CliRunner, tmp_path: Path
) -> None:
    """Without `--output`, the proposals land at
    `<run_dir>/candidate_typologies.yaml`."""
    run_dir = _make_run_dir(tmp_path, alerted=[])

    result = runner.invoke(
        app,
        [
            "discover-typologies",
            str(SPEC),
            str(run_dir),
            "--seed",
            "42",
            "--as-of",
            "2024-01-01",
            "--anomaly-z",
            "1.5",
        ],
    )

    assert result.exit_code == 0, result.output
    default_out = run_dir / "candidate_typologies.yaml"
    # Either candidates were written here, or none were found (no file).
    if "No candidate typologies" not in result.output:
        assert default_out.exists()
        doc = yaml.safe_load(default_out.read_text(encoding="utf-8"))
        assert all(c["rule"]["status"] == "pending_promotion" for c in doc["candidates"])
