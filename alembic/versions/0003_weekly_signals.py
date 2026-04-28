"""weekly_signals table

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "weekly_signals",
        sa.Column("id",          sa.Integer(),   primary_key=True),
        sa.Column("ticker",      sa.String(20),  nullable=False),
        sa.Column("week_ending", sa.String(10),  nullable=False),
        sa.Column("return_pct",  sa.Float(),     nullable=False),
        sa.Column("signal_type", sa.String(10),  nullable=True),
        sa.Column("last_price",  sa.Float(),     nullable=True),
        sa.Column("pcr",         sa.Float(),     nullable=True),
        sa.Column("pcr_label",   sa.String(20),  nullable=True),
        sa.Column("put_volume",  sa.BigInteger(), nullable=True),
        sa.Column("call_volume", sa.BigInteger(), nullable=True),
        sa.Column("executed",    sa.Boolean(),   nullable=False, server_default="false"),
        sa.Column("order_side",  sa.String(10),  nullable=True),
        sa.Column("order_qty",   sa.Float(),     nullable=True),
        sa.Column("created_at",  sa.DateTime(),  nullable=False),
    )
    op.create_index("ix_weekly_signals_ticker",      "weekly_signals", ["ticker"])
    op.create_index("ix_weekly_signals_week_ending", "weekly_signals", ["week_ending"])
    op.create_unique_constraint(
        "uq_weekly_ticker_week", "weekly_signals", ["ticker", "week_ending"]
    )


def downgrade():
    op.drop_table("weekly_signals")
