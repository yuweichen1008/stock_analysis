"""add trades table

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-06
"""
from alembic import op
import sqlalchemy as sa

revision  = "0005"
down_revision = "0004"
branch_labels = None
depends_on    = None


def upgrade():
    op.create_table(
        "trades",
        sa.Column("id",              sa.Integer(),     primary_key=True, autoincrement=True),
        sa.Column("broker",          sa.String(20),    nullable=False),
        sa.Column("ticker",          sa.String(20),    nullable=False),
        sa.Column("market",          sa.String(10),    nullable=False),
        sa.Column("side",            sa.String(10),    nullable=False),
        sa.Column("qty",             sa.Float(),       nullable=False),
        sa.Column("order_type",      sa.String(20),    nullable=True),
        sa.Column("limit_price",     sa.Float(),       nullable=True),
        sa.Column("broker_order_id", sa.String(100),   nullable=True),
        sa.Column("status",          sa.String(20),    nullable=True),
        sa.Column("filled_qty",      sa.Float(),       nullable=True),
        sa.Column("filled_price",    sa.Float(),       nullable=True),
        sa.Column("commission",      sa.Float(),       nullable=True),
        sa.Column("realized_pnl",    sa.Float(),       nullable=True),
        sa.Column("signal_source",   sa.String(50),    nullable=True),
        sa.Column("executed_at",     sa.DateTime(),    nullable=True),
        sa.Column("created_at",      sa.DateTime(),    nullable=True),
        sa.UniqueConstraint("broker", "broker_order_id", name="uq_trade_broker_order"),
    )
    op.create_index("ix_trades_ticker", "trades", ["ticker"])


def downgrade():
    op.drop_index("ix_trades_ticker", table_name="trades")
    op.drop_table("trades")
