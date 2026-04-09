"""
SQLite database models for the Oracle game.
Tables: users, bets
File: data/oracle_game.db
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey,
    Integer, String, create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH  = BASE_DIR / "data" / "oracle_game.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

engine       = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    device_id  = Column(String, primary_key=True, index=True)
    coins      = Column(Integer, default=10_000, nullable=False)
    nickname   = Column(String, nullable=True)
    push_token = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Subscriber(Base):
    """Telegram subscribers (web / non-app users)."""
    __tablename__ = "subscribers"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id   = Column(String, unique=True, index=True, nullable=False)
    label         = Column(String, nullable=True)   # display name or @handle
    active        = Column(Boolean, default=True, nullable=False)
    subscribed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Bet(Base):
    __tablename__ = "bets"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    device_id  = Column(String, ForeignKey("users.device_id"), nullable=False, index=True)
    date       = Column(String, nullable=False)   # YYYY-MM-DD
    direction  = Column(String, nullable=False)   # "Bull" | "Bear"
    bet_amount = Column(Integer, nullable=False)
    is_correct = Column(Boolean, nullable=True)
    payout     = Column(Integer, nullable=True)   # positive = won, negative = lost
    status     = Column(String, default="pending")  # "pending" | "settled"
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def create_tables():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Create tables on import
create_tables()
