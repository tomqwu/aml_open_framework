"""JWT authentication for the AML API — demo users only."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_SECRET = os.environ.get("JWT_SECRET", "aml-framework-dev-secret")
_ALGORITHM = "HS256"
_EXPIRY_HOURS = 24

# Demo users — production MUST use OIDC_ISSUER_URL for real authentication.
# Passwords default to username for local development only.
DEMO_USERS: dict[str, dict[str, Any]] = {
    "admin": {
        "password": os.environ.get("DEMO_ADMIN_PASSWORD", "admin"),
        "role": "admin",
        "audience": "svp",
        "tenant": "bank_a",
    },
    "analyst": {
        "password": os.environ.get("DEMO_ANALYST_PASSWORD", "analyst"),
        "role": "analyst",
        "audience": "analyst",
        "tenant": "bank_a",
    },
    "auditor": {
        "password": os.environ.get("DEMO_AUDITOR_PASSWORD", "auditor"),
        "role": "auditor",
        "audience": "auditor",
        "tenant": "bank_a",
    },
    "manager": {
        "password": os.environ.get("DEMO_MANAGER_PASSWORD", "manager"),
        "role": "manager",
        "audience": "manager",
        "tenant": "bank_a",
    },
    "bank_b_admin": {
        "password": os.environ.get("DEMO_BANK_B_PASSWORD", "admin"),
        "role": "admin",
        "audience": "svp",
        "tenant": "bank_b",
    },
}

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


# --- OIDC support stub ---
# Set OIDC_ISSUER_URL to enable OIDC token validation instead of local JWT.
# Example: OIDC_ISSUER_URL=https://login.microsoftonline.com/{tenant}/v2.0
_OIDC_ISSUER = os.environ.get("OIDC_ISSUER_URL", "")


def _verify_oidc_token(token: str) -> dict[str, Any]:  # pragma: no cover
    """Validate a token against an OIDC identity provider.

    Requires: pip install python-jose[cryptography]
    In production, fetch JWKS from {issuer}/.well-known/openid-configuration.
    """
    try:
        from jose import jwt as jose_jwt

        # Fetch JWKS keys from the issuer's well-known endpoint.
        import urllib.request

        well_known_url = f"{_OIDC_ISSUER}/.well-known/openid-configuration"
        config = json.loads(urllib.request.urlopen(well_known_url, timeout=5).read())
        jwks_url = config["jwks_uri"]
        jwks = json.loads(urllib.request.urlopen(jwks_url, timeout=5).read())

        payload = jose_jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            audience=os.environ.get("OIDC_AUDIENCE", ""),
            issuer=_OIDC_ISSUER,
        )
        return {
            "sub": payload.get("sub", ""),
            "role": payload.get("roles", ["analyst"])[0] if payload.get("roles") else "analyst",
            "tenant": payload.get("tid", "default"),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"OIDC validation failed: {e}",
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
