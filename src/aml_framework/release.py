"""Release identifiers — version string + git SHA exposed to UI + API.

Resolved with this precedence:

1. ``AML_BUILD_SHA`` env var — set by the Docker build to the short git
   SHA of the source tree it baked in. This is the authoritative value
   in production: the Container App's running image carries it, so the
   topbar shows what's actually deployed (not what was on `main` when
   the page was rendered).
2. ``git rev-parse --short HEAD`` — fallback for local dev (`make
   dashboard`, pytest fixtures). Best-effort; returns ``"dev"`` if git
   isn't on PATH or the cwd isn't a repo.

Version comes from package metadata (single source of truth in
``pyproject.toml``), with ``"dev"`` fallback when the wheel isn't
installed (rare; only happens in some pytest collection paths).

Surfaces:

- ``GET /api/v1/health`` returns ``{"status":"ok", "version":"...", "git_sha":"..."}``.
- Dashboard topbar renders ``v<version> · <git_sha>`` next to the
  wordmark so an operator can confirm at a glance which build is live.
"""

from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version


@lru_cache(maxsize=1)
def get_version() -> str:
    """Package version from installed metadata, or ``"dev"`` if absent."""
    try:
        return version("aml-open-framework")
    except PackageNotFoundError:
        return "dev"


@lru_cache(maxsize=1)
def get_git_sha() -> str:
    """Short git SHA. ``AML_BUILD_SHA`` env wins; falls back to local git."""
    env_sha = os.environ.get("AML_BUILD_SHA", "").strip()
    if env_sha:
        return env_sha
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        sha = result.stdout.strip()
        if sha:
            return sha
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return "dev"


def release_label() -> str:
    """Compact ``v<version> · <sha>`` for UI display."""
    sha = get_git_sha()
    if sha == "dev":
        return f"v{get_version()} · dev"
    return f"v{get_version()} · {sha}"
