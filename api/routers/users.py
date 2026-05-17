"""
User management endpoints — broker credential storage.

All endpoints require JWT authentication (Authorization: Bearer <token>).

POST   /api/users/broker-creds          — save encrypted broker credentials
GET    /api/users/broker-creds/{broker} — check if broker is configured
DELETE /api/users/broker-creds/{broker} — remove broker credentials
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.auth import decrypt_cred, encrypt_cred, get_current_user
from api.db import User, get_db

router = APIRouter(prefix="/api/users", tags=["users"])


# ── Request models ────────────────────────────────────────────────────────────

class CtbcCreds(BaseModel):
    id:       str
    password: str


class MoomooCreds(BaseModel):
    host: str = "127.0.0.1"
    port: str = "11111"


class BrokerCredsBody(BaseModel):
    broker:      Literal["ctbc", "moomoo"]
    credentials: dict


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/broker-creds")
def save_broker_creds(
    body: BrokerCredsBody,
    db:   Session = Depends(get_db),
    user: User    = Depends(get_current_user),
):
    """Encrypt and save broker credentials for the authenticated user."""
    if not encrypt_cred("test"):
        raise HTTPException(503, "Credential encryption is not configured on this server. Set BROKER_ENCRYPTION_KEY in .env.")

    if body.broker == "ctbc":
        creds = CtbcCreds(**body.credentials)
        user.ctbc_id_enc   = encrypt_cred(creds.id)
        user.ctbc_pass_enc = encrypt_cred(creds.password)

    elif body.broker == "moomoo":
        creds = MoomooCreds(**body.credentials)
        user.moomoo_host_enc = encrypt_cred(creds.host)
        user.moomoo_port_enc = encrypt_cred(creds.port)

    db.commit()
    return {"ok": True, "broker": body.broker, "configured": True}


@router.get("/broker-creds/{broker}")
def get_broker_creds_status(
    broker: str,
    user:   User = Depends(get_current_user),
):
    """Check if broker credentials are configured (never returns decrypted values)."""
    if broker == "ctbc":
        return {"broker": "ctbc", "configured": bool(user.ctbc_id_enc)}
    elif broker == "moomoo":
        return {"broker": "moomoo", "configured": bool(user.moomoo_host_enc)}
    raise HTTPException(400, "broker must be 'ctbc' or 'moomoo'")


@router.delete("/broker-creds/{broker}")
def delete_broker_creds(
    broker: str,
    db:     Session = Depends(get_db),
    user:   User    = Depends(get_current_user),
):
    """Remove saved broker credentials."""
    if broker == "ctbc":
        user.ctbc_id_enc   = None
        user.ctbc_pass_enc = None
    elif broker == "moomoo":
        user.moomoo_host_enc = None
        user.moomoo_port_enc = None
    else:
        raise HTTPException(400, "broker must be 'ctbc' or 'moomoo'")
    db.commit()
    return {"ok": True, "broker": broker, "configured": False}
