"""Add news_items and news_pcr_snapshots tables.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-24
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "news_items",
        sa.Column("id",              sa.Integer(),     primary_key=True, autoincrement=True),
        sa.Column("external_id",     sa.String(128),   nullable=False, unique=True),
        sa.Column("ticker",          sa.String(20),    nullable=True),
        sa.Column("market",          sa.String(10),    nullable=False),
        sa.Column("headline",        sa.String(512),   nullable=False),
        sa.Column("source",          sa.String(128),   nullable=True),
        sa.Column("url",             sa.String(1024),  nullable=True),
        sa.Column("published_at",    sa.DateTime(),    nullable=False),
        sa.Column("fetched_at",      sa.DateTime(),    nullable=False),
        sa.Column("sentiment_score", sa.Float(),       nullable=True),
        sa.Column("related_ids",     sa.Text(),        nullable=True),
    )
    op.create_index("ix_news_items_external_id",  "news_items", ["external_id"])
    op.create_index("ix_news_items_published_at", "news_items", ["published_at"])
    op.create_index("ix_news_items_ticker",        "news_items", ["ticker"])

    op.create_table(
        "news_pcr_snapshots",
        sa.Column("id",           sa.Integer(),     primary_key=True, autoincrement=True),
        sa.Column("news_item_id", sa.Integer(),     sa.ForeignKey("news_items.id"), nullable=False),
        sa.Column("ticker",       sa.String(20),    nullable=False),
        sa.Column("snapshot_at",  sa.DateTime(),    nullable=False),
        sa.Column("put_volume",   sa.BigInteger(),  nullable=True),
        sa.Column("call_volume",  sa.BigInteger(),  nullable=True),
        sa.Column("pcr",          sa.Float(),       nullable=True),
        sa.Column("pcr_label",    sa.String(20),    nullable=True),
    )
    op.create_index("ix_news_pcr_news_item_id", "news_pcr_snapshots", ["news_item_id"])
    op.create_index("ix_news_pcr_snapshot_at",  "news_pcr_snapshots", ["snapshot_at"])


def downgrade() -> None:
    op.drop_table("news_pcr_snapshots")
    op.drop_table("news_items")
