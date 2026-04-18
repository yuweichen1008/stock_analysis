"""Initial schema — full Oracle app tables on PostgreSQL.

Revision ID: 0001
Revises:
Create Date: 2026-04-18
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id",            sa.Integer(),     primary_key=True, autoincrement=True),
        sa.Column("device_id",     sa.String(255),   nullable=True,    unique=True),
        sa.Column("auth_provider", sa.String(50),    nullable=True),
        sa.Column("auth_id",       sa.String(255),   nullable=True),
        sa.Column("email",         sa.String(255),   nullable=True),
        sa.Column("display_name",  sa.String(255),   nullable=True),
        sa.Column("avatar_url",    sa.String(1024),  nullable=True),
        sa.Column("coins",         sa.Integer(),     nullable=False, server_default="10000"),
        sa.Column("nickname",      sa.String(255),   nullable=True),
        sa.Column("push_token",    sa.String(512),   nullable=True),
        sa.Column("created_at",    sa.DateTime(),    nullable=True),
    )
    op.create_index("ix_users_device_id", "users", ["device_id"])
    op.create_index("ix_users_auth_id",   "users", ["auth_id"])

    op.create_table(
        "subscribers",
        sa.Column("id",            sa.Integer(),     primary_key=True, autoincrement=True),
        sa.Column("telegram_id",   sa.String(255),   nullable=False, unique=True),
        sa.Column("label",         sa.String(255),   nullable=True),
        sa.Column("active",        sa.Boolean(),     nullable=False, server_default="true"),
        sa.Column("subscribed_at", sa.DateTime(),    nullable=True),
    )
    op.create_index("ix_subscribers_telegram_id", "subscribers", ["telegram_id"])

    op.create_table(
        "bets",
        sa.Column("id",         sa.Integer(),    primary_key=True, autoincrement=True),
        sa.Column("user_id",    sa.Integer(),    sa.ForeignKey("users.id"), nullable=True),
        sa.Column("device_id",  sa.String(255),  nullable=True),
        sa.Column("date",       sa.String(10),   nullable=False),
        sa.Column("direction",  sa.String(10),   nullable=False),
        sa.Column("bet_amount", sa.Integer(),    nullable=False),
        sa.Column("is_correct", sa.Boolean(),    nullable=True),
        sa.Column("payout",     sa.Integer(),    nullable=True),
        sa.Column("status",     sa.String(20),   nullable=True, server_default="pending"),
        sa.Column("created_at", sa.DateTime(),   nullable=True),
    )
    op.create_index("ix_bets_user_id",   "bets", ["user_id"])
    op.create_index("ix_bets_device_id", "bets", ["device_id"])

    op.create_table(
        "stock_bets",
        sa.Column("id",           sa.Integer(),   primary_key=True, autoincrement=True),
        sa.Column("user_id",      sa.Integer(),   sa.ForeignKey("users.id"), nullable=True),
        sa.Column("device_id",    sa.String(255), nullable=True),
        sa.Column("ticker",       sa.String(20),  nullable=False),
        sa.Column("bet_date",     sa.String(10),  nullable=False),
        sa.Column("direction",    sa.String(10),  nullable=False),
        sa.Column("bet_amount",   sa.Integer(),   nullable=False),
        sa.Column("entry_price",  sa.Float(),     nullable=True),
        sa.Column("exit_price",   sa.Float(),     nullable=True),
        sa.Column("is_correct",   sa.Boolean(),   nullable=True),
        sa.Column("payout",       sa.Integer(),   nullable=True),
        sa.Column("status",       sa.String(20),  nullable=True, server_default="pending"),
        sa.Column("category",     sa.String(50),  nullable=True),
        sa.Column("created_at",   sa.DateTime(),  nullable=True),
    )
    op.create_index("ix_stock_bets_user_id",  "stock_bets", ["user_id"])
    op.create_index("ix_stock_bets_device_id","stock_bets", ["device_id"])
    op.create_index("ix_stock_bets_ticker",   "stock_bets", ["ticker"])

    op.create_table(
        "watchlist",
        sa.Column("id",       sa.Integer(),   primary_key=True, autoincrement=True),
        sa.Column("user_id",  sa.Integer(),   sa.ForeignKey("users.id"), nullable=False),
        sa.Column("ticker",   sa.String(20),  nullable=False),
        sa.Column("market",   sa.String(10),  nullable=False),
        sa.Column("notes",    sa.String(512), nullable=True),
        sa.Column("added_at", sa.DateTime(),  nullable=True),
        sa.UniqueConstraint("user_id", "ticker", "market", name="uq_watchlist_user_ticker_market"),
    )
    op.create_index("ix_watchlist_user_id", "watchlist", ["user_id"])

    op.create_table(
        "posts",
        sa.Column("id",          sa.Integer(),    primary_key=True, autoincrement=True),
        sa.Column("user_id",     sa.Integer(),    sa.ForeignKey("users.id"), nullable=False),
        sa.Column("ticker",      sa.String(20),   nullable=True),
        sa.Column("market",      sa.String(10),   nullable=True),
        sa.Column("content",     sa.String(280),  nullable=False),
        sa.Column("signal_type", sa.String(20),   nullable=True),
        sa.Column("created_at",  sa.DateTime(),   nullable=True),
    )
    op.create_index("ix_posts_user_id",    "posts", ["user_id"])
    op.create_index("ix_posts_created_at", "posts", ["created_at"])

    op.create_table(
        "reactions",
        sa.Column("id",         sa.Integer(),  primary_key=True, autoincrement=True),
        sa.Column("user_id",    sa.Integer(),  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("post_id",    sa.Integer(),  sa.ForeignKey("posts.id"), nullable=False),
        sa.Column("emoji_type", sa.String(20), nullable=False),
        sa.UniqueConstraint("user_id", "post_id", name="uq_reaction_user_post"),
    )
    op.create_index("ix_reactions_user_id", "reactions", ["user_id"])
    op.create_index("ix_reactions_post_id", "reactions", ["post_id"])


def downgrade() -> None:
    op.drop_table("reactions")
    op.drop_table("posts")
    op.drop_table("watchlist")
    op.drop_table("stock_bets")
    op.drop_table("bets")
    op.drop_table("subscribers")
    op.drop_table("users")
