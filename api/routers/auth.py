"""
Authentication endpoints.

POST /api/auth/apple    — verify Apple identity_token → JWT
POST /api/auth/google   — verify Google id_token → JWT
POST /api/auth/device   — legacy device-ID → JWT (anonymous / backwards compat)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

limiter = Limiter(key_func=get_remote_address)

from api.auth import create_access_token, verify_apple_token, verify_google_token
from api.db import User, get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Response shape ────────────────────────────────────────────────────────────

def _user_response(user: User, db: Session) -> dict:
    return {
        "access_token": create_access_token(user.id),
        "token_type":   "bearer",
        "user": {
            "id":           user.id,
            "display_name": user.display_name or user.nickname or f"Player{user.id}",
            "email":        user.email,
            "coins":        user.coins,
            "avatar_url":   user.avatar_url,
            "auth_provider": user.auth_provider,
        },
    }


def _upsert_user(
    db: Session,
    *,
    auth_provider: str,
    auth_id: str,
    email: Optional[str] = None,
    display_name: Optional[str] = None,
    avatar_url: Optional[str] = None,
) -> User:
    user = (
        db.query(User)
        .filter(User.auth_provider == auth_provider, User.auth_id == auth_id)
        .first()
    )
    if user:
        # Update mutable fields
        if email and not user.email:
            user.email = email
        if display_name and not user.display_name:
            user.display_name = display_name
        if avatar_url and not user.avatar_url:
            user.avatar_url = avatar_url
    else:
        user = User(
            auth_provider=auth_provider,
            auth_id=auth_id,
            email=email,
            display_name=display_name,
            avatar_url=avatar_url,
            coins=10_000,
            created_at=datetime.now(timezone.utc),
        )
        db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ── Apple ─────────────────────────────────────────────────────────────────────

class AppleBody(BaseModel):
    identity_token: str
    full_name: Optional[str] = None   # only sent on first sign-in


@router.post("/apple")
@limiter.limit("20/minute")
def apple_auth(request: Request, body: AppleBody, db: Session = Depends(get_db)):
    claims = verify_apple_token(body.identity_token)
    auth_id = claims.get("sub")
    if not auth_id:
        raise HTTPException(400, "Apple token missing 'sub'")

    user = _upsert_user(
        db,
        auth_provider="apple",
        auth_id=auth_id,
        email=claims.get("email"),
        display_name=body.full_name,
    )
    return _user_response(user, db)


# ── Google ────────────────────────────────────────────────────────────────────

class GoogleBody(BaseModel):
    id_token: str


@router.post("/google")
@limiter.limit("20/minute")
def google_auth(request: Request, body: GoogleBody, db: Session = Depends(get_db)):
    claims = verify_google_token(body.id_token)
    auth_id = claims.get("sub")
    if not auth_id:
        raise HTTPException(400, "Google token missing 'sub'")

    user = _upsert_user(
        db,
        auth_provider="google",
        auth_id=auth_id,
        email=claims.get("email"),
        display_name=claims.get("name"),
        avatar_url=claims.get("picture"),
    )
    return _user_response(user, db)


# ── Device (anonymous / legacy) ───────────────────────────────────────────────

class DeviceBody(BaseModel):
    device_id: str
    nickname:  Optional[str] = None


@router.post("/device")
@limiter.limit("20/minute")
def device_auth(request: Request, body: DeviceBody, db: Session = Depends(get_db)):
    """
    Legacy endpoint — used by existing anonymous app users and as fallback.
    Creates / retrieves user by device_id, issues JWT.
    """
    user = db.query(User).filter(User.device_id == body.device_id).first()
    if not user:
        user = User(
            device_id=body.device_id,
            auth_provider="device",
            auth_id=body.device_id,
            display_name=body.nickname,
            nickname=body.nickname,
            coins=10_000,
            created_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    return _user_response(user, db)
