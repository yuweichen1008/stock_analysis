"""
SQLAlchemy models — PostgreSQL (production) or SQLite (local dev fallback).
Schema is managed by Alembic; never call create_tables() in production.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Float, ForeignKey,
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


# ── News feed ─────────────────────────────────────────────────────────────────

class NewsItem(Base):
    __tablename__ = "news_items"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    external_id     = Column(String(128), unique=True, nullable=False, index=True)  # sha1 dedup key
    ticker          = Column(String(20), nullable=True, index=True)   # None = market-wide
    market          = Column(String(10), nullable=False)              # "US" | "TW" | "MARKET"
    headline        = Column(String(512), nullable=False)
    source          = Column(String(128), nullable=True)
    url             = Column(String(1024), nullable=True)
    published_at    = Column(DateTime, nullable=False, index=True)
    fetched_at      = Column(DateTime, nullable=False)
    sentiment_score = Column(Float, nullable=True)                    # VADER -1..+1
    related_ids     = Column(Text, nullable=True)                     # JSON "[3, 17, 42]"


class NewsPcrSnapshot(Base):
    __tablename__ = "news_pcr_snapshots"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    news_item_id = Column(Integer, ForeignKey("news_items.id"), nullable=False, index=True)
    ticker       = Column(String(20), nullable=False)
    snapshot_at  = Column(DateTime, nullable=False, index=True)
    put_volume   = Column(BigInteger, nullable=True)
    call_volume  = Column(BigInteger, nullable=True)
    pcr          = Column(Float, nullable=True)        # put_volume / call_volume
    pcr_label    = Column(String(20), nullable=True)   # extreme_fear/fear/neutral/greed/extreme_greed


# ── Weekly contrarian signals ─────────────────────────────────────────────────

class WeeklySignal(Base):
    __tablename__ = "weekly_signals"
    __table_args__ = (UniqueConstraint("ticker", "week_ending", name="uq_weekly_ticker_week"),)

    id          = Column(Integer, primary_key=True, autoincrement=True)
    ticker      = Column(String(20), nullable=False, index=True)
    week_ending = Column(String(10), nullable=False, index=True)  # "YYYY-MM-DD"
    return_pct  = Column(Float, nullable=False)
    signal_type = Column(String(10), nullable=True)               # "buy" | "sell" | None
    last_price  = Column(Float, nullable=True)
    pcr         = Column(Float, nullable=True)
    pcr_label   = Column(String(20), nullable=True)
    put_volume  = Column(BigInteger, nullable=True)
    call_volume = Column(BigInteger, nullable=True)
    executed    = Column(Boolean, nullable=False, default=False)  # True if order placed
    order_side  = Column(String(10), nullable=True)               # "BUY" | "SELL"
    order_qty   = Column(Float, nullable=True)
    created_at  = Column(DateTime, nullable=False)


# ── Options screener ─────────────────────────────────────────────────────────

class OptionsIvSnapshot(Base):
    """Daily avg implied-volatility per ticker; accumulates for IV Rank computation."""
    __tablename__ = "options_iv_snapshots"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    ticker      = Column(String(20), nullable=False, index=True)
    snapshot_at = Column(DateTime, nullable=False, index=True)
    avg_iv      = Column(Float, nullable=True)   # mean IV across liquid strikes (decimal, e.g. 0.35)


class OptionsSignal(Base):
    """One row per ticker per pipeline run; only written when a signal fires."""
    __tablename__ = "options_signals"
    __table_args__ = (UniqueConstraint("ticker", "snapshot_at", name="uq_options_ticker_snap"),)

    id               = Column(Integer, primary_key=True, autoincrement=True)
    ticker           = Column(String(20), nullable=False, index=True)
    snapshot_at      = Column(DateTime, nullable=False, index=True)
    # Price
    price            = Column(Float, nullable=True)
    price_change_1d  = Column(Float, nullable=True)   # percent
    rsi_14           = Column(Float, nullable=True)
    # Options sentiment
    pcr              = Column(Float, nullable=True)
    pcr_label        = Column(String(20), nullable=True)
    put_volume       = Column(BigInteger, nullable=True)
    call_volume      = Column(BigInteger, nullable=True)
    # Volatility
    avg_iv           = Column(Float, nullable=True)
    iv_rank          = Column(Float, nullable=True)   # 0-100; null when < 30 days of history
    # Activity
    total_oi         = Column(BigInteger, nullable=True)
    volume_oi_ratio  = Column(Float, nullable=True)
    # Signal
    signal_type      = Column(String(20), nullable=True, index=True)  # buy_signal|sell_signal|unusual_activity
    signal_score     = Column(Float, nullable=True)   # 0-10
    signal_reason    = Column(String(255), nullable=True)
    # Execution
    executed         = Column(Boolean, nullable=False, default=False)
    created_at       = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


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
