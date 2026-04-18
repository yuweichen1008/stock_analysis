"""
SQLAlchemy models — PostgreSQL (production) or SQLite (local dev fallback).
Schema is managed by Alembic; never call create_tables() in production.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text, UniqueConstraint, create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from api.config import settings

# ── Engine ────────────────────────────────────────────────────────────────────
_connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    connect_args=_connect_args,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


# ── Users ─────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    # Legacy device-ID (anonymous) — kept for backwards compat
    device_id     = Column(String(255), unique=True, nullable=True, index=True)
    # OAuth
    auth_provider = Column(String(50), nullable=True)   # "apple" | "google" | "device"
    auth_id       = Column(String(255), nullable=True, index=True)  # sub from JWT
    email         = Column(String(255), nullable=True)
    display_name  = Column(String(255), nullable=True)
    avatar_url    = Column(String(1024), nullable=True)
    # Game
    coins         = Column(Integer, default=10_000, nullable=False)
    nickname      = Column(String(255), nullable=True)   # legacy alias
    push_token    = Column(String(512), nullable=True)
    created_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ── Telegram subscribers ──────────────────────────────────────────────────────

class Subscriber(Base):
    __tablename__ = "subscribers"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id   = Column(String(255), unique=True, index=True, nullable=False)
    label         = Column(String(255), nullable=True)
    active        = Column(Boolean, default=True, nullable=False)
    subscribed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ── Bets (Oracle daily Bull/Bear) ─────────────────────────────────────────────

class Bet(Base):
    __tablename__ = "bets"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    # New FK — set after auth migration; legacy rows keep device_id only
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    device_id  = Column(String(255), nullable=True, index=True)   # legacy
    date       = Column(String(10), nullable=False)   # YYYY-MM-DD
    direction  = Column(String(10), nullable=False)   # "Bull" | "Bear"
    bet_amount = Column(Integer, nullable=False)
    is_correct = Column(Boolean, nullable=True)
    payout     = Column(Integer, nullable=True)
    status     = Column(String(20), default="pending")  # "pending" | "settled"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ── Stock bets (Finviz movers) ────────────────────────────────────────────────

class StockBet(Base):
    __tablename__ = "stock_bets"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    device_id    = Column(String(255), nullable=True, index=True)   # legacy
    ticker       = Column(String(20), nullable=False, index=True)
    bet_date     = Column(String(10), nullable=False)
    direction    = Column(String(10), nullable=False)
    bet_amount   = Column(Integer, nullable=False)
    entry_price  = Column(Float, nullable=True)
    exit_price   = Column(Float, nullable=True)
    is_correct   = Column(Boolean, nullable=True)
    payout       = Column(Integer, nullable=True)
    status       = Column(String(20), default="pending")
    category     = Column(String(50), nullable=True)
    created_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ── Watchlist ─────────────────────────────────────────────────────────────────

class Watchlist(Base):
    __tablename__ = "watchlist"
    __table_args__ = (UniqueConstraint("user_id", "ticker", "market", name="uq_watchlist_user_ticker_market"),)

    id       = Column(Integer, primary_key=True, autoincrement=True)
    user_id  = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    ticker   = Column(String(20), nullable=False)
    market   = Column(String(10), nullable=False)   # "TW" | "US"
    notes    = Column(String(512), nullable=True)
    added_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ── Community feed ────────────────────────────────────────────────────────────

class Post(Base):
    __tablename__ = "posts"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    ticker      = Column(String(20), nullable=True)
    market      = Column(String(10), nullable=True)
    content     = Column(String(280), nullable=False)
    signal_type = Column(String(20), nullable=True)   # "bull" | "bear" | "neutral"
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class Reaction(Base):
    __tablename__ = "reactions"
    __table_args__ = (UniqueConstraint("user_id", "post_id", name="uq_reaction_user_post"),)

    id         = Column(Integer, primary_key=True, autoincrement=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    post_id    = Column(Integer, ForeignKey("posts.id"), nullable=False, index=True)
    emoji_type = Column(String(20), nullable=False)   # "bull" | "bear" | "fire"


# ── Session dependency ────────────────────────────────────────────────────────

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Local dev fallback: create tables when using SQLite ───────────────────────

def create_tables():
    """Only used in local SQLite dev; Alembic owns production schema."""
    if settings.DATABASE_URL.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)


create_tables()
