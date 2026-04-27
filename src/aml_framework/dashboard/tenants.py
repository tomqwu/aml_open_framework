"""Multi-tenant configuration for the dashboard.

Round-6 PR #2. The REST API has full tenant isolation
(`api/auth.py:create_token` carries a `tenant` claim; every
`api/db.py` query filters by `tenant_id`), but the Streamlit
dashboard historically hardcoded a single spec path. This module
adds a lightweight registry so a single dashboard process can
surface multiple programs (e.g. EU bank + Canadian bank + cyber-
fraud spec) and let the operator switch between them.

Scope and trust model
- **Display-only multi-tenancy.** The dashboard runs the engine
  locally per selected tenant — there is no server-side
  authorization here. Whoever can launch the dashboard process
  sees every configured tenant. Real per-user authorization lives
  in the REST API path (`api/auth.py`), not here.
- The plan note for this PR was "API has it, dashboard doesn't" —
  this module brings the dashboard up to surface parity with the
  API's tenant model, not to enforce isolation.

Configuration
- A YAML file at the path in `$AML_TENANTS_CONFIG`, falling back
  to `<project>/dashboard_tenants.yaml`. Schema:

      tenants:
        - id: bank_a
          display_name: "Bank A — EU operations"
          spec_path: examples/eu_bank/aml.yaml
          jurisdiction: EU
        - id: bank_b
          display_name: "Bank B — US operations"
          spec_path: examples/us_community_bank/aml.yaml
          jurisdiction: US

- When no config file exists, returns a single `default` tenant
  pointing at `examples/community_bank/aml.yaml` (preserves the
  previous single-spec behavior — existing dashboard launches
  keep working with no migration).

- A second fallback: if the config file exists but the selected
  tenant's spec path is missing, the loader raises a clear
  `TenantConfigError` instead of silently picking the first
  available tenant — that would mask deployment misconfiguration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from aml_framework.paths import PROJECT_ROOT

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "dashboard_tenants.yaml"
DEFAULT_TENANT_ID = "default"
_DEFAULT_SPEC_PATH = PROJECT_ROOT / "examples" / "community_bank" / "aml.yaml"


class TenantConfigError(ValueError):
    """Raised on malformed tenant configuration."""


@dataclass(frozen=True)
class TenantConfig:
    """One tenant entry."""

    id: str
    display_name: str
    spec_path: Path
    jurisdiction: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "spec_path": str(self.spec_path),
            "jurisdiction": self.jurisdiction,
        }


def _config_path() -> Path:
    env = os.environ.get("AML_TENANTS_CONFIG")
    if env:
        return Path(env)
    return DEFAULT_CONFIG_PATH


def _default_tenant() -> TenantConfig:
    return TenantConfig(
        id=DEFAULT_TENANT_ID,
        display_name="Default — Community Bank (US)",
        spec_path=_DEFAULT_SPEC_PATH,
        jurisdiction="US",
    )


def _resolve_spec_path(raw: str) -> Path:
    """Tenant configs may use relative paths; resolve against the project root."""
    p = Path(raw)
    if p.is_absolute():
        return p
    return PROJECT_ROOT / p


def _parse_tenants(payload: dict[str, Any]) -> list[TenantConfig]:
    tenants_raw = payload.get("tenants")
    if not isinstance(tenants_raw, list) or not tenants_raw:
        raise TenantConfigError("tenants config must contain a non-empty 'tenants:' list")
    seen_ids: set[str] = set()
    out: list[TenantConfig] = []
    for entry in tenants_raw:
        if not isinstance(entry, dict):
            raise TenantConfigError(f"tenant entry must be a mapping, got {type(entry).__name__}")
        tid = entry.get("id")
        if not isinstance(tid, str) or not tid:
            raise TenantConfigError("every tenant entry needs a non-empty string 'id'")
        if tid in seen_ids:
            raise TenantConfigError(f"duplicate tenant id {tid!r}")
        seen_ids.add(tid)
        spec_raw = entry.get("spec_path")
        if not isinstance(spec_raw, str) or not spec_raw:
            raise TenantConfigError(f"tenant {tid!r} needs a non-empty string 'spec_path'")
        out.append(
            TenantConfig(
                id=tid,
                display_name=entry.get("display_name") or tid,
                spec_path=_resolve_spec_path(spec_raw),
                jurisdiction=entry.get("jurisdiction") or "",
            )
        )
    return out


def load_tenants(*, config_path: Path | None = None) -> list[TenantConfig]:
    """Load the tenant registry. Returns the default tenant when no config exists.

    Args:
        config_path: optional explicit path. Defaults to `$AML_TENANTS_CONFIG`
            then `<project>/dashboard_tenants.yaml`.

    Returns:
        Sorted list of TenantConfig (deterministic order: by id).
    """
    path = config_path or _config_path()
    if not path.exists():
        return [_default_tenant()]
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise TenantConfigError(f"tenant config at {path} is not valid YAML: {e}") from e
    if not isinstance(payload, dict):
        raise TenantConfigError(f"tenant config at {path} must be a YAML mapping at the top level")
    tenants = _parse_tenants(payload)
    return sorted(tenants, key=lambda t: t.id)


def resolve_tenant(
    tenant_id: str | None,
    *,
    config_path: Path | None = None,
) -> TenantConfig:
    """Look up one tenant by id, or return the first when `tenant_id` is None.

    Raises TenantConfigError when an explicit id is requested but not found —
    silent fallback would mask deployment misconfiguration.
    """
    tenants = load_tenants(config_path=config_path)
    if tenant_id is None:
        return tenants[0]
    for t in tenants:
        if t.id == tenant_id:
            return t
    available = sorted(t.id for t in tenants)
    raise TenantConfigError(f"tenant {tenant_id!r} not in config; available: {available}")
