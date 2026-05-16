"""add tws_stock_cache table

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tws_stock_cache",
        sa.Column("id",             sa.Integer(),     nullable=False),
        sa.Column("ticker",         sa.String(20),    nullable=False),
        sa.Column("name",           sa.String(200),   nullable=True),
        sa.Column("industry",       sa.String(100),   nullable=True),
        sa.Column("price",          sa.Float(),       nullable=True),
        sa.Column("open_price",     sa.Float(),       nullable=True),
        sa.Column("high_52w",       sa.Float(),       nullable=True),
        sa.Column("low_52w",        sa.Float(),       nullable=True),
        sa.Column("volume",         sa.BigInteger(),  nullable=True),
        sa.Column("market_cap",     sa.Float(),       nullable=True),
        sa.Column("pe_ratio",       sa.Float(),       nullable=True),
        sa.Column("roe",            sa.Float(),       nullable=True),
        sa.Column("dividend_yield", sa.Float(),       nullable=True),
        sa.Column("rsi_14",         sa.Float(),       nullable=True),
        sa.Column("ma20",           sa.Float(),       nullable=True),
        sa.Column("ma120",          sa.Float(),       nullable=True),
        sa.Column("bias",           sa.Float(),       nullable=True),
        sa.Column("fetched_at",     sa.DateTime(),    nullable=True),
        sa.Column("updated_at",     sa.DateTime(),    nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker", name="uq_tws_stock_cache_ticker"),
    )
    op.create_index("ix_tws_stock_cache_ticker", "tws_stock_cache", ["ticker"])


def downgrade() -> None:
    op.drop_index("ix_tws_stock_cache_ticker", table_name="tws_stock_cache")
    op.drop_table("tws_stock_cache")
