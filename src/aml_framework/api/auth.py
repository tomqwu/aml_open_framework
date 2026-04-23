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
    "admin": {"password": "admin", "role": "admin", "audience": "svp"},
    "analyst": {"password": "analyst", "role": "analyst", "audience": "analyst"},
    "auditor": {"password": "auditor", "role": "auditor", "audience": "auditor"},
    "manager": {"password": "manager", "role": "manager", "audience": "manager"},
}

_security = HTTPBearer()


def create_token(username: str, role: str) -> str:
    payload = {
        "sub": username,
        "role": role,
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
