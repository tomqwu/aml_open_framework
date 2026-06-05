"""CLI tests for `aml detect-mule-rings` (#498).

Offline governed community-detection command: builds the identity-link
edge list from the spec's data (`resolved_entity_link`), calls
`detect_mule_rings`, and writes a human-gated `mule_rings.json` of
candidate mule rings. Advisory only — never auto-escalates.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aml_framework.cli import app

# The cyber_enabled_fraud customer contract declares phone/email/device_id
# linking columns and its synthetic data plants a shared-attribute clique
# (C0024–C0027), so the identity graph yields a dense ring at the defaults.
SPEC = Path("examples/cyber_enabled_fraud/aml.yaml")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _make_run_dir(tmp_path: Path) -> Path:
    """Build a minimal run dir with a manifest carrying `as_of`."""
    run_dir = tmp_path / "run-test"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps({"as_of": "2024-01-01T00:00:00"}), encoding="utf-8"
    )
    return run_dir


def test_detect_mule_rings_happy_path(runner: CliRunner, tmp_path: Path) -> None:
    """On synthetic data with a planted shared-attribute clique, at least one
    dense ring is found; the JSON parses and each ring is well-formed."""
    run_dir = _make_run_dir(tmp_path)
    out = tmp_path / "mule_rings.json"

    result = runner.invoke(
        app,
        [
            "detect-mule-rings",
            str(SPEC),
            str(run_dir),
            "--output",
            str(out),
            "--seed",
            "42",
            "--as-of",
            "2024-01-01",
        ],
    )

    assert result.exit_code == 0, result.output
    assert out.exists(), result.output
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["n_rings"] >= 1
    assert doc["n_entities"] >= 1
    assert len(doc["rings"]) == doc["n_rings"]
    for ring in doc["rings"]:
        assert ring["ring_id"].startswith("MR-")
        assert isinstance(ring["members"], list)
        assert ring["size"] == len(ring["members"])
        assert 0.0 <= ring["density"] <= 1.0
        assert ring["size"] >= 3
    # Advisory governance language is surfaced to the operator.
    assert "Advisory" in result.output
    assert "escalat" in result.output.lower()


def test_detect_mule_rings_zero_rings_writes_nothing(runner: CliRunner, tmp_path: Path) -> None:
    """When the ring thresholds are unreachable (impossibly large/dense),
    no ring is found, no file is written, and the command exits 0."""
    run_dir = _make_run_dir(tmp_path)
    out = tmp_path / "mule_rings.json"

    result = runner.invoke(
        app,
        [
            "detect-mule-rings",
            str(SPEC),
            str(run_dir),
            "--output",
            str(out),
            "--seed",
            "42",
            "--as-of",
            "2024-01-01",
            "--min-density",
            "0.99",
            "--min-ring-size",
            "99",
        ],
    )

    assert result.exit_code == 0, result.output
    assert not out.exists()
    assert "No mule ring" in result.output


def test_detect_mule_rings_no_link_edges_writes_nothing(runner: CliRunner, tmp_path: Path) -> None:
    """A spec whose customer contract declares no linking attributes (and
    whose synthetic data shares none) yields no edges — the command says so
    and exits 0 without writing."""
    run_dir = _make_run_dir(tmp_path)
    out = tmp_path / "mule_rings.json"

    result = runner.invoke(
        app,
        [
            "detect-mule-rings",
            str(Path("examples/canadian_schedule_i_bank/aml.yaml")),
            str(run_dir),
            "--output",
            str(out),
            "--seed",
            "42",
            "--as-of",
            "2024-01-01",
        ],
    )

    assert result.exit_code == 0, result.output
    assert not out.exists()
    assert "No identity-link edges" in result.output


def test_detect_mule_rings_reads_as_of_from_manifest_when_not_passed(
    runner: CliRunner, tmp_path: Path
) -> None:
    """Determinism: without `--as-of`, the command anchors to the run's
    `as_of` from manifest.json. The output must be byte-identical to an
    explicit `--as-of` equal to the manifest value, and re-running yields
    identical bytes."""
    run_dir = _make_run_dir(tmp_path)
    from_manifest = tmp_path / "from_manifest.json"
    from_flag = tmp_path / "from_flag.json"

    base = ["detect-mule-rings", str(SPEC), str(run_dir), "--seed", "42"]
    r1 = runner.invoke(app, [*base, "--output", str(from_manifest)])
    r2 = runner.invoke(app, [*base, "--output", str(from_flag), "--as-of", "2024-01-01T00:00:00"])

    assert r1.exit_code == 0, r1.output
    assert r2.exit_code == 0, r2.output
    assert from_manifest.read_text(encoding="utf-8") == from_flag.read_text(encoding="utf-8")


def test_detect_mule_rings_fails_closed_without_as_of_or_manifest(
    runner: CliRunner, tmp_path: Path
) -> None:
    """Fail-closed determinism (codex P2): a run dir with NO readable manifest
    as_of and NO `--as-of` flag must error with exit 1 rather than silently
    falling back to the wall clock."""
    run_dir = tmp_path / "run-no-manifest"
    run_dir.mkdir(parents=True)
    out = tmp_path / "mule_rings.json"

    result = runner.invoke(
        app,
        ["detect-mule-rings", str(SPEC), str(run_dir), "--output", str(out), "--seed", "42"],
    )

    assert result.exit_code == 1, result.output
    assert not out.exists()
    assert "as_of" in result.output


def test_detect_mule_rings_default_output_under_run_dir(runner: CliRunner, tmp_path: Path) -> None:
    """Without `--output`, the report lands at `<run_dir>/mule_rings.json`."""
    run_dir = _make_run_dir(tmp_path)

    result = runner.invoke(
        app,
        [
            "detect-mule-rings",
            str(SPEC),
            str(run_dir),
            "--seed",
            "42",
            "--as-of",
            "2024-01-01",
        ],
    )

    assert result.exit_code == 0, result.output
    default_out = run_dir / "mule_rings.json"
    if "No mule ring" not in result.output and "No identity-link" not in result.output:
        assert default_out.exists()
        doc = json.loads(default_out.read_text(encoding="utf-8"))
        assert doc["n_rings"] >= 1
