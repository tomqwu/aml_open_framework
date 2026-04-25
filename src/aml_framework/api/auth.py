"""JWT authentication for the AML API — demo users only."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_SECRET = os.environ.get("JWT_SECRET", "aml-framework-dev-secret")
_ALGORITHM = "HS256"
_EXPIRY_HOURS = 24

# Demo users — production would use an identity provider.
DEMO_USERS: dict[str, dict[str, Any]] = {
    "admin": {"password": "admin", "role": "admin", "audience": "svp", "tenant": "bank_a"},
    "analyst": {
        "password": "analyst",
        "role": "analyst",
        "audience": "analyst",
        "tenant": "bank_a",
    },
    "auditor": {
        "password": "auditor",
        "role": "auditor",
        "audience": "auditor",
        "tenant": "bank_a",
    },
    "manager": {
        "password": "manager",
        "role": "manager",
        "audience": "manager",
        "tenant": "bank_a",
    },
    "bank_b_admin": {"password": "admin", "role": "admin", "audience": "svp", "tenant": "bank_b"},
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
    return verify_token(credentials.credentials)
