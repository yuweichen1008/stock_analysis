"""
Authentication utilities.

- JWT creation / verification
- FastAPI dependency: get_current_user
- FastAPI dependency: require_internal  (X-API-Secret header)
- Apple identity_token verification (JWKS)
- Google id_token verification
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from api.config import settings
from api.db import User, get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/device", auto_error=False)

# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def _decode_token(token: str) -> int:
    """Decode JWT and return user_id (int). Raises 401 on any error."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
        return int(user_id)
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")


# ── FastAPI dependencies ──────────────────────────────────────────────────────

def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    user_id = _decode_token(token)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


def get_optional_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Like get_current_user but returns None instead of 401 (for public endpoints)."""
    if not token:
        return None
    try:
        user_id = _decode_token(token)
        return db.get(User, user_id)
    except HTTPException:
        return None


def require_internal(x_api_secret: str = Header(..., alias="X-API-Secret")) -> None:
    """Dependency that blocks access unless the correct internal secret is provided."""
    if x_api_secret != settings.INTERNAL_API_SECRET:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")


# ── Apple Sign-In verification ────────────────────────────────────────────────

_APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
_apple_jwks_cache: dict = {"keys": None, "fetched_at": 0.0}
_JWKS_TTL = 3600  # 1 hour


def _get_apple_jwks() -> list:
    now = time.time()
    if _apple_jwks_cache["keys"] and now - _apple_jwks_cache["fetched_at"] < _JWKS_TTL:
        return _apple_jwks_cache["keys"]
    resp = httpx.get(_APPLE_JWKS_URL, timeout=10)
    resp.raise_for_status()
    keys = resp.json()["keys"]
    _apple_jwks_cache.update({"keys": keys, "fetched_at": now})
    return keys


def verify_apple_token(identity_token: str) -> dict:
    """
    Verify an Apple identity_token and return the decoded claims.
    Raises HTTPException(401) on failure.
    """
    from jose import jwk as jose_jwk

    try:
        unverified_header = jwt.get_unverified_header(identity_token)
        kid = unverified_header.get("kid")
        jwks = _get_apple_jwks()
        matching = [k for k in jwks if k.get("kid") == kid]
        if not matching:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Apple JWKS key not found")

        public_key = jose_jwk.construct(matching[0])
        claims = jwt.decode(
            identity_token,
            public_key,
            algorithms=["RS256"],
            audience=settings.APPLE_CLIENT_ID or None,
            options={"verify_aud": bool(settings.APPLE_CLIENT_ID)},
        )
        return claims
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Apple token invalid: {e}")


# ── Google Sign-In verification ───────────────────────────────────────────────

def verify_google_token(id_token: str) -> dict:
    """
    Verify a Google id_token and return the decoded claims.
    Raises HTTPException(401) on failure.
    """
    try:
        from google.oauth2 import id_token as google_id_token
        from google.auth.transport import requests as google_requests

        request = google_requests.Request()
        claims = google_id_token.verify_oauth2_token(
            id_token,
            request,
            audience=settings.GOOGLE_CLIENT_ID or None,
        )
        return claims
    except Exception as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Google token invalid: {e}")
