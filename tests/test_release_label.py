"""Release-identifier resolution (PR for dashboard version display).

`aml_framework.release` exposes `get_version()`, `get_git_sha()`, and a
compact `release_label()` for UI. Resolution precedence:

1. `AML_BUILD_SHA` env (Docker build-arg) — wins.
2. `git rev-parse --short HEAD` in cwd.
3. Literal "dev" fallback.

These tests pin that order so an operator viewing the dashboard topbar
or curling /api/v1/health can trust the value matches the running image.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture(autouse=True)
def _clear_caches(monkeypatch):
    """Flush `lru_cache` between tests so env changes take effect."""
    monkeypatch.delenv("AML_BUILD_SHA", raising=False)
    import aml_framework.release as rel

    rel.get_version.cache_clear()
    rel.get_git_sha.cache_clear()
    yield
    rel.get_version.cache_clear()
    rel.get_git_sha.cache_clear()


def test_env_sha_wins(monkeypatch):
    monkeypatch.setenv("AML_BUILD_SHA", "abc1234")
    import aml_framework.release as rel

    rel.get_git_sha.cache_clear()
    assert rel.get_git_sha() == "abc1234"


def test_falls_back_to_local_git(monkeypatch):
    """When no env override and we're in a git repo, we resolve from
    `git rev-parse --short HEAD`. The docker-build CI job runs pytest
    INSIDE the built image, where there's no .git directory — in that
    environment the fallback to "dev" is the expected behaviour, so we
    skip rather than assert SHA shape there.
    """
    from pathlib import Path

    import pytest

    repo_root = Path(__file__).resolve().parents[1]
    if not (repo_root / ".git").exists():
        pytest.skip("no .git directory (e.g. running inside docker-build job)")
    import aml_framework.release as rel

    rel.get_git_sha.cache_clear()
    sha = rel.get_git_sha()
    assert sha != "dev", "expected git rev-parse to succeed in repo"
    assert all(c in "0123456789abcdef" for c in sha), f"expected hex SHA, got {sha!r}"


def test_dev_fallback_when_git_unavailable(monkeypatch):
    """If git is somehow not on PATH (CI in a stripped container, etc.),
    fall back to "dev" instead of raising."""
    import subprocess

    def _fail_run(*_a, **_kw):
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(subprocess, "run", _fail_run)
    import aml_framework.release as rel

    rel.get_git_sha.cache_clear()
    assert rel.get_git_sha() == "dev"


def test_release_label_includes_version_and_sha(monkeypatch):
    monkeypatch.setenv("AML_BUILD_SHA", "deadbee")
    import aml_framework.release as rel

    rel.get_git_sha.cache_clear()
    rel.get_version.cache_clear()
    label = rel.release_label()
    assert label.startswith("v")
    assert "deadbee" in label
    assert "·" in label  # the separator pinned by the UI


def test_release_label_marks_dev_when_no_sha(monkeypatch):
    monkeypatch.setenv("AML_BUILD_SHA", "")

    # Force git to fail so we get the dev fallback.
    import subprocess

    monkeypatch.setattr(
        subprocess, "run", lambda *_a, **_kw: (_ for _ in ()).throw(FileNotFoundError)
    )
    import aml_framework.release as rel

    rel.get_git_sha.cache_clear()
    assert rel.release_label().endswith("· dev")


def test_module_reimport_picks_up_env_change(monkeypatch):
    """Defensive: even if some downstream caller reimports the module,
    behavior stays consistent with the documented precedence."""
    monkeypatch.setenv("AML_BUILD_SHA", "fac3fee")
    import aml_framework.release as rel

    importlib.reload(rel)
    assert rel.get_git_sha() == "fac3fee"
