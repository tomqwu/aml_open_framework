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

- ``GET /api/v1/health`` returns
  ``{"status":"ok", "version":"...", "git_sha":"...", "build_time":"..."}``.
- Dashboard topbar renders ``v<version> · <git_sha> · <build_time>``
  next to the wordmark so an operator can confirm at a glance which
  build is live and when it was deployed.
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


@lru_cache(maxsize=1)
def get_build_time() -> str:
    """UTC timestamp the running image was built/deployed.

    Sourced from ``AML_BUILD_TIME`` env, set by the Docker build-arg
    the Azure deploy passes (``date -u +%Y-%m-%dT%H:%MZ``). There is no
    local-git fallback — build time is a property of the image, not the
    source tree — so this returns ``"dev"`` for any non-deployed run
    (local ``make dashboard``, pytest). Callers must treat ``"dev"`` as
    "unknown" and not render it as a real timestamp.
    """
    return os.environ.get("AML_BUILD_TIME", "").strip() or "dev"


def release_label() -> str:
    """Compact ``v<version> · <sha>[ · <build_time>]`` for UI display.

    Build time is appended only when known (a real deployed image);
    local/dev runs keep the historical ``v… · sha`` / ``v… · dev``
    shape so nothing downstream that string-matched the old format
    breaks.
    """
    sha = get_git_sha()
    base = f"v{get_version()} · dev" if sha == "dev" else f"v{get_version()} · {sha}"
    build_time = get_build_time()
    if build_time != "dev":
        return f"{base} · {build_time}"
    return base
