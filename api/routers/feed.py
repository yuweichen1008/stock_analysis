"""
Community feed endpoints.

GET  /api/feed                   → paginated public posts with reaction counts
POST /api/feed                   → create a post (auth required)
POST /api/feed/{post_id}/react   → toggle reaction (auth required)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func
from sqlalchemy.orm import Session

limiter = Limiter(key_func=get_remote_address)

from api.auth import get_current_user, get_optional_user
from api.db import Post, Reaction, User, get_db

router = APIRouter(prefix="/api/feed", tags=["feed"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class CreatePostBody(BaseModel):
    ticker:      Optional[str] = None
    market:      Optional[str] = None
    content:     str = Field(..., min_length=1, max_length=280)
    signal_type: Optional[str] = None   # "bull" | "bear" | "neutral"


class ReactBody(BaseModel):
    emoji_type: str   # "bull" | "bear" | "fire"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _reaction_counts(post_id: int, db: Session) -> dict:
    rows = (
        db.query(Reaction.emoji_type, func.count(Reaction.id))
        .filter(Reaction.post_id == post_id)
        .group_by(Reaction.emoji_type)
        .all()
    )
    counts = {"bull": 0, "bear": 0, "fire": 0}
    for emoji, cnt in rows:
        if emoji in counts:
            counts[emoji] = cnt
    return counts


def _post_dict(post: Post, db: Session, viewer: Optional[User] = None) -> dict:
    user = db.get(User, post.user_id)
    reactions = _reaction_counts(post.id, db)

    viewer_reaction = None
    if viewer:
        r = (
            db.query(Reaction)
            .filter(Reaction.post_id == post.id, Reaction.user_id == viewer.id)
            .first()
        )
        viewer_reaction = r.emoji_type if r else None

    return {
        "id":              post.id,
        "user": {
            "id":           user.id if user else None,
            "display_name": (user.display_name or user.nickname or f"Player{user.id}") if user else "Unknown",
            "avatar_url":   user.avatar_url if user else None,
        },
        "ticker":          post.ticker,
        "market":          post.market,
        "content":         post.content,
        "signal_type":     post.signal_type,
        "created_at":      post.created_at.isoformat() if post.created_at else None,
        "reactions":       reactions,
        "viewer_reaction": viewer_reaction,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/")
def list_feed(
    market: str = Query("all", description="Filter by market: TW | US | all"),
    limit:  int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    viewer: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    q = db.query(Post).order_by(Post.created_at.desc())
    if market.lower() != "all":
        q = q.filter(Post.market == market.upper())
    posts = q.offset(offset).limit(limit).all()
    return [_post_dict(p, db, viewer) for p in posts]


@router.post("/")
@limiter.limit("10/hour")
def create_post(
    request: Request,
    body: CreatePostBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.signal_type and body.signal_type not in ("bull", "bear", "neutral"):
        raise HTTPException(400, "signal_type must be bull, bear, or neutral")

    post = Post(
        user_id=current_user.id,
        ticker=body.ticker.upper() if body.ticker else None,
        market=body.market.upper() if body.market else None,
        content=body.content,
        signal_type=body.signal_type,
        created_at=datetime.now(timezone.utc),
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return _post_dict(post, db, current_user)


@router.post("/{post_id}/react")
def react_to_post(
    post_id: int,
    body: ReactBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.emoji_type not in ("bull", "bear", "fire"):
        raise HTTPException(400, "emoji_type must be bull, bear, or fire")

    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(404, "Post not found")

    existing = (
        db.query(Reaction)
        .filter(Reaction.post_id == post_id, Reaction.user_id == current_user.id)
        .first()
    )

    if existing:
        if existing.emoji_type == body.emoji_type:
            # Toggle off
            db.delete(existing)
            db.commit()
            return {"ok": True, "action": "removed", "emoji_type": body.emoji_type}
        else:
            # Switch reaction
            existing.emoji_type = body.emoji_type
            db.commit()
            return {"ok": True, "action": "updated", "emoji_type": body.emoji_type}
    else:
        reaction = Reaction(
            user_id=current_user.id,
            post_id=post_id,
            emoji_type=body.emoji_type,
        )
        db.add(reaction)
        db.commit()
        return {"ok": True, "action": "added", "emoji_type": body.emoji_type}
