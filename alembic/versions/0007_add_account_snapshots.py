"""add account_snapshots table

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_snapshots",
        sa.Column("id",             sa.Integer(),     nullable=False),
        sa.Column("market",         sa.String(10),    nullable=False),
        sa.Column("snapshot_date",  sa.String(10),    nullable=False),
        sa.Column("cash",           sa.Float(),       nullable=True),
        sa.Column("total_value",    sa.Float(),       nullable=True),
        sa.Column("unrealized_pnl", sa.Float(),       nullable=True),
        sa.Column("currency",       sa.String(10),    nullable=True),
        sa.Column("created_at",     sa.DateTime(),    nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("market", "snapshot_date", name="uq_account_snapshot_market_date"),
    )
    op.create_index("ix_account_snapshots_market",        "account_snapshots", ["market"])
    op.create_index("ix_account_snapshots_snapshot_date", "account_snapshots", ["snapshot_date"])


def downgrade() -> None:
    op.drop_index("ix_account_snapshots_snapshot_date", table_name="account_snapshots")
    op.drop_index("ix_account_snapshots_market",        table_name="account_snapshots")
    op.drop_table("account_snapshots")
