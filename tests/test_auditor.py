"""Tests for `aml auditor-pack` — auditor self-service bundle.

Process invariant guarded: when the regulator walks in, an auditor
unzips one file and finds (1) chain-verified evidence, (2) the
regulator examination pack, (3) a one-page MANIFEST that explains
what each piece is. If any of these break, the next exam goes back to
3 days of IT assembly.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from aml_framework.auditor import (
    AuditorPackResult,
    auditor_dashboard_url,
    build_auditor_pack,
)
from aml_framework.cli import app
from aml_framework.engine import run_spec
from aml_framework.spec import load_spec

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "examples" / "canadian_schedule_i_bank" / "aml.yaml"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def real_run(tmp_path: Path) -> Path:
    """Execute the engine once so we have a real run dir to bundle.

    Costs ~2 seconds but exercises the actual chain we ship; smoke tests
    against a fake run dir would miss real integration breaks.
    """
    from datetime import datetime

    from aml_framework.data import generate_dataset

    spec = load_spec(SPEC_PATH)
    as_of = datetime(2026, 4, 28)
    data = generate_dataset(as_of=as_of, seed=42)
    artifacts = tmp_path / "artifacts"
    result = run_spec(
        spec=spec, spec_path=SPEC_PATH, data=data, as_of=as_of, artifacts_root=artifacts
    )
    return Path(result.manifest["run_dir"])


# ---------------------------------------------------------------------------
# Bundle build — structural invariants
# ---------------------------------------------------------------------------


def test_build_auditor_pack_creates_zip(real_run: Path, tmp_path: Path) -> None:
    spec = load_spec(SPEC_PATH)
    out = tmp_path / "auditor.zip"
    result = build_auditor_pack(spec, real_run, out=out)
    assert isinstance(result, AuditorPackResult)
    assert out.exists()
    assert out.stat().st_size > 1000


def test_bundle_includes_manifest_first(real_run: Path, tmp_path: Path) -> None:
    """MANIFEST.txt must be the first entry the auditor sees on extract.
    Streaming-extract clients read entries in archive order; the first
    one is the user's mental anchor."""
    spec = load_spec(SPEC_PATH)
    out = tmp_path / "auditor.zip"
    build_auditor_pack(spec, real_run, out=out)
    with zipfile.ZipFile(out) as z:
        names = z.namelist()
    assert names[0] == "MANIFEST.txt"


def test_bundle_includes_chain_verified_audit_log(real_run: Path, tmp_path: Path) -> None:
    spec = load_spec(SPEC_PATH)
    out = tmp_path / "auditor.zip"
    result = build_auditor_pack(spec, real_run, out=out)
    assert result.chain_verified, result.chain_message
    with zipfile.ZipFile(out) as z:
        assert "decisions.jsonl" in z.namelist()
        assert "manifest.json" in z.namelist()


def test_bundle_includes_audit_pack_zip(real_run: Path, tmp_path: Path) -> None:
    spec = load_spec(SPEC_PATH)
    out = tmp_path / "auditor.zip"
    build_auditor_pack(spec, real_run, out=out)
    with zipfile.ZipFile(out) as z:
        assert "audit_pack.zip" in z.namelist()


def test_bundle_includes_spec_snapshot(real_run: Path, tmp_path: Path) -> None:
    """Replay-equivalence depends on knowing what spec actually ran.
    Without the snapshot, an auditor can't reproduce the bytes."""
    spec = load_spec(SPEC_PATH)
    out = tmp_path / "auditor.zip"
    build_auditor_pack(spec, real_run, out=out)
    with zipfile.ZipFile(out) as z:
        assert "spec_snapshot.yaml" in z.namelist()


def test_manifest_describes_every_component(real_run: Path, tmp_path: Path) -> None:
    spec = load_spec(SPEC_PATH)
    out = tmp_path / "auditor.zip"
    result = build_auditor_pack(spec, real_run, out=out)
    with zipfile.ZipFile(out) as z:
        manifest = z.read("MANIFEST.txt").decode("utf-8")
    for component in result.components:
        assert component in manifest, f"MANIFEST should mention {component!r}"


def test_manifest_records_chain_status(real_run: Path, tmp_path: Path) -> None:
    spec = load_spec(SPEC_PATH)
    out = tmp_path / "auditor.zip"
    build_auditor_pack(spec, real_run, out=out)
    with zipfile.ZipFile(out) as z:
        manifest = z.read("MANIFEST.txt").decode("utf-8")
    assert "Chain integrity" in manifest
    assert "verified" in manifest.lower()


def test_manifest_includes_bundle_sha256(real_run: Path, tmp_path: Path) -> None:
    """Auditor verifies the bundle wasn't tampered with after build by
    checking the SHA-256 — has to be in the manifest."""
    spec = load_spec(SPEC_PATH)
    out = tmp_path / "auditor.zip"
    build_auditor_pack(spec, real_run, out=out)
    with zipfile.ZipFile(out) as z:
        manifest = z.read("MANIFEST.txt").decode("utf-8")
    assert "Bundle SHA-256" in manifest
    # 64-char hex on the same line as the label
    import re

    m = re.search(r"Bundle SHA-256:\s*([a-f0-9]{64})", manifest)
    assert m, "Bundle SHA-256 not present in manifest in expected shape"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_build_raises_on_missing_run_dir(tmp_path: Path) -> None:
    spec = load_spec(SPEC_PATH)
    with pytest.raises(FileNotFoundError):
        build_auditor_pack(spec, tmp_path / "does-not-exist", out=tmp_path / "out.zip")


def test_build_creates_parent_dir_for_output(real_run: Path, tmp_path: Path) -> None:
    spec = load_spec(SPEC_PATH)
    out = tmp_path / "nested" / "deep" / "auditor.zip"
    build_auditor_pack(spec, real_run, out=out)
    assert out.exists()


# ---------------------------------------------------------------------------
# Auditor dashboard URL
# ---------------------------------------------------------------------------


def test_auditor_dashboard_url_carries_persona_and_page() -> None:
    url = auditor_dashboard_url(SPEC_PATH)
    assert "audience=auditor" in url
    assert "Audit" in url and "Evidence" in url


def test_auditor_dashboard_url_uses_spec_filename_not_full_path() -> None:
    """An exposed corporate portal shouldn't leak the developer's full
    home-directory path. Only the spec filename should appear."""
    url = auditor_dashboard_url(SPEC_PATH)
    assert "/home" not in url
    assert SPEC_PATH.name in url


def test_auditor_dashboard_url_respects_custom_host() -> None:
    url = auditor_dashboard_url(SPEC_PATH, host="https://compliance.bank.com")
    assert url.startswith("https://compliance.bank.com")


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_cli_auditor_pack_writes_zip(runner: CliRunner, real_run: Path, tmp_path: Path) -> None:
    out = tmp_path / "auditor.zip"
    result = runner.invoke(
        app,
        [
            "auditor-pack",
            str(SPEC_PATH),
            "--run-dir",
            str(real_run),
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()


def test_cli_auditor_pack_renders_component_table(
    runner: CliRunner, real_run: Path, tmp_path: Path
) -> None:
    out = tmp_path / "auditor.zip"
    result = runner.invoke(
        app,
        [
            "auditor-pack",
            str(SPEC_PATH),
            "--run-dir",
            str(real_run),
            "--out",
            str(out),
        ],
    )
    assert "Auditor pack" in result.output
    assert "MANIFEST.txt" in result.output
    assert "audit_pack.zip" in result.output


def test_cli_auditor_pack_print_link_emits_url(
    runner: CliRunner, real_run: Path, tmp_path: Path
) -> None:
    out = tmp_path / "auditor.zip"
    result = runner.invoke(
        app,
        [
            "auditor-pack",
            str(SPEC_PATH),
            "--run-dir",
            str(real_run),
            "--out",
            str(out),
            "--print-link",
        ],
    )
    assert "audience=auditor" in result.output
