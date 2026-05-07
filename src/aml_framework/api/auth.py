"""JWT authentication for the AML API — demo users only."""

from __future__ import annotations

import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.request import urlopen

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_logger = logging.getLogger("aml.auth")

_MIN_SECRET_BYTES = 32
_ALGORITHM = "HS256"
_EXPIRY_HOURS = 24
_OIDC_CACHE_SECONDS = int(os.environ.get("OIDC_CACHE_SECONDS", "300"))


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def is_production_mode() -> bool:
    """Return True when the API is explicitly running outside local/dev mode."""
    mode = (os.environ.get("AML_ENV") or os.environ.get("API_ENV") or "").strip().lower()
    return mode in {"prod", "production"}


def is_demo_auth_enabled() -> bool:
    """Demo users are enabled by default only outside production mode."""
    if is_production_mode():
        return _truthy_env("ALLOW_DEMO_AUTH")
    return not _truthy_env("DISABLE_DEMO_AUTH")


def _resolve_secret() -> str:
    # PR-AZ-2: route through SecretsProvider so JWT_SECRET can live in
    # Azure Key Vault on AKS deployments. Behaviorally identical to
    # `os.environ.get("JWT_SECRET")` when AZURE_KEY_VAULT_NAME is unset.
    from aml_framework.secrets import SECRETS

    env = SECRETS.get("JWT_SECRET")
    if env is not None:
        if len(env.encode("utf-8")) < _MIN_SECRET_BYTES:
            raise RuntimeError(
                f"JWT_SECRET is set but shorter than {_MIN_SECRET_BYTES} bytes. "
                "Generate a strong value: python -c 'import secrets; print(secrets.token_urlsafe(48))'"
            )
        return env
    if is_production_mode():
        raise RuntimeError(
            "JWT_SECRET is required in production mode. "
            "Generate a strong value: python -c 'import secrets; print(secrets.token_urlsafe(48))'"
        )
    _logger.warning(
        "JWT_SECRET is not set; using a random per-process secret. "
        "Issued tokens will not survive a restart. Set JWT_SECRET in any non-dev deployment."
    )
    return secrets.token_urlsafe(48)


_SECRET = _resolve_secret()

# Demo users — production MUST use OIDC_ISSUER_URL for real authentication.
# Passwords default to username for local development only.
# PR-AZ-2: passwords resolve through SecretsProvider so production can
# pin them to Key Vault when running with demo-auth in stage envs.
from aml_framework.secrets import SECRETS as _SECRETS  # noqa: E402

_DEMO_USERS: dict[str, dict[str, Any]] = {
    "admin": {
        "password": _SECRETS.get("DEMO_ADMIN_PASSWORD", "admin"),
        "role": "admin",
        "audience": "svp",
        "tenant": "bank_a",
    },
    "analyst": {
        "password": _SECRETS.get("DEMO_ANALYST_PASSWORD", "analyst"),
        "role": "analyst",
        "audience": "analyst",
        "tenant": "bank_a",
    },
    "auditor": {
        "password": _SECRETS.get("DEMO_AUDITOR_PASSWORD", "auditor"),
        "role": "auditor",
        "audience": "auditor",
        "tenant": "bank_a",
    },
    "manager": {
        "password": _SECRETS.get("DEMO_MANAGER_PASSWORD", "manager"),
        "role": "manager",
        "audience": "manager",
        "tenant": "bank_a",
    },
    "bank_b_admin": {
        "password": _SECRETS.get("DEMO_BANK_B_PASSWORD", "admin"),
        "role": "admin",
        "audience": "svp",
        "tenant": "bank_b",
    },
}
DEMO_USERS: dict[str, dict[str, Any]] = _DEMO_USERS if is_demo_auth_enabled() else {}
if is_production_mode() and DEMO_USERS:
    _logger.warning("Demo API users are enabled in production because ALLOW_DEMO_AUTH is set.")

# Role-based permissions.
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {"read", "write", "admin", "run", "configure"},
    "manager": {"read", "write", "run"},
    "analyst": {"read", "run"},
    "auditor": {"read"},
}


def require_role(*allowed_roles: str):
    """Dependency that checks the user has one of the allowed roles."""

    async def _check(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        role = user.get("role", "")
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' not authorized. Requires: {allowed_roles}",
            )
        return user

    return _check


# --- OIDC support ---
# Set OIDC_ISSUER_URL to enable OIDC token validation instead of local JWT.
# Example: OIDC_ISSUER_URL=https://login.microsoftonline.com/{tenant}/v2.0
_OIDC_ISSUER = os.environ.get("OIDC_ISSUER_URL", "")
_OIDC_CONFIG_CACHE: tuple[float, dict[str, Any]] | None = None
_OIDC_JWKS_CACHE: tuple[float, dict[str, Any]] | None = None


def is_oidc_enabled() -> bool:
    return bool(_OIDC_ISSUER)


def _json_url(url: str) -> dict[str, Any]:
    import json

    with urlopen(url, timeout=5) as resp:
        payload = resp.read()
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError("OIDC endpoint did not return an object")
    return parsed


def _oidc_config() -> dict[str, Any]:
    global _OIDC_CONFIG_CACHE
    now = time.time()
    if _OIDC_CONFIG_CACHE and now - _OIDC_CONFIG_CACHE[0] < _OIDC_CACHE_SECONDS:
        return _OIDC_CONFIG_CACHE[1]
    issuer = _OIDC_ISSUER.rstrip("/")
    config = _json_url(f"{issuer}/.well-known/openid-configuration")
    _OIDC_CONFIG_CACHE = (now, config)
    return config


def _oidc_jwks() -> dict[str, Any]:
    global _OIDC_JWKS_CACHE
    now = time.time()
    if _OIDC_JWKS_CACHE and now - _OIDC_JWKS_CACHE[0] < _OIDC_CACHE_SECONDS:
        return _OIDC_JWKS_CACHE[1]
    config = _oidc_config()
    jwks_uri = config.get("jwks_uri")
    if not isinstance(jwks_uri, str) or not jwks_uri:
        raise ValueError("OIDC discovery document has no jwks_uri")
    jwks = _json_url(jwks_uri)
    _OIDC_JWKS_CACHE = (now, jwks)
    return jwks


def _claim(payload: dict[str, Any], name: str, default: Any = None) -> Any:
    current: Any = payload
    for part in name.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def _first_role(raw: Any) -> str:
    if isinstance(raw, list) and raw:
        return str(raw[0])
    if isinstance(raw, str) and raw:
        # Azure app roles are arrays; some IdPs send scope-like strings.
        return raw.split()[0]
    return os.environ.get("OIDC_DEFAULT_ROLE", "analyst")


def _oidc_audience() -> str | None:
    audience = os.environ.get("OIDC_AUDIENCE", "").strip()
    if audience:
        return audience
    if _truthy_env("OIDC_ALLOW_MISSING_AUDIENCE") and not is_production_mode():
        _logger.warning(
            "OIDC_AUDIENCE is unset; audience verification is disabled because "
            "OIDC_ALLOW_MISSING_AUDIENCE is set outside production mode."
        )
        return None
    raise ValueError("OIDC_AUDIENCE is required when OIDC token validation is enabled")


def _verify_oidc_token(token: str) -> dict[str, Any]:  # pragma: no cover
    """Validate a token against an OIDC identity provider."""
    try:
        from jose import jwt as jose_jwt

        audience = _oidc_audience()
        payload = jose_jwt.decode(
            token,
            _oidc_jwks(),
            algorithms=["RS256"],
            audience=audience,
            issuer=_OIDC_ISSUER.rstrip("/"),
            options={"verify_aud": audience is not None},
        )
        role = _first_role(_claim(payload, os.environ.get("OIDC_ROLE_CLAIM", "roles"), []))
        tenant = str(_claim(payload, os.environ.get("OIDC_TENANT_CLAIM", "tid"), "default"))
        allowed_tenants = {
            t.strip() for t in os.environ.get("OIDC_ALLOWED_TENANTS", "").split(",") if t.strip()
        }
        if allowed_tenants and tenant not in allowed_tenants:
            raise ValueError("OIDC tenant is not allowed")
        subject = str(payload.get("sub") or "")
        if not subject:
            raise ValueError("OIDC token has no subject")
        return {
            "sub": subject,
            "role": role,
            "tenant": tenant,
        }
    except Exception as e:
        _logger.warning("OIDC token validation failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC validation failed",
        ) from e


_security = HTTPBearer()


def create_token(username: str, role: str, tenant: str = "default") -> str:
    payload = {
        "sub": username,
        "role": role,
        "tenant": tenant,
        "exp": datetime.now(tz=timezone.utc) + timedelta(hours=_EXPIRY_HOURS),
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def verify_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> dict[str, Any]:
    if _OIDC_ISSUER:
        return _verify_oidc_token(credentials.credentials)  # pragma: no cover
    return verify_token(credentials.credentials)
