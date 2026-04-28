"""options_signals and options_iv_snapshots tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "options_iv_snapshots",
        sa.Column("id",          sa.Integer(),   primary_key=True),
        sa.Column("ticker",      sa.String(20),  nullable=False),
        sa.Column("snapshot_at", sa.DateTime(),  nullable=False),
        sa.Column("avg_iv",      sa.Float(),     nullable=True),
    )
    op.create_index("ix_options_iv_snapshots_ticker",      "options_iv_snapshots", ["ticker"])
    op.create_index("ix_options_iv_snapshots_snapshot_at", "options_iv_snapshots", ["snapshot_at"])

    op.create_table(
        "options_signals",
        sa.Column("id",              sa.Integer(),    primary_key=True),
        sa.Column("ticker",          sa.String(20),   nullable=False),
        sa.Column("snapshot_at",     sa.DateTime(),   nullable=False),
        sa.Column("price",           sa.Float(),      nullable=True),
        sa.Column("price_change_1d", sa.Float(),      nullable=True),
        sa.Column("rsi_14",          sa.Float(),      nullable=True),
        sa.Column("pcr",             sa.Float(),      nullable=True),
        sa.Column("pcr_label",       sa.String(20),   nullable=True),
        sa.Column("put_volume",      sa.BigInteger(), nullable=True),
        sa.Column("call_volume",     sa.BigInteger(), nullable=True),
        sa.Column("avg_iv",          sa.Float(),      nullable=True),
        sa.Column("iv_rank",         sa.Float(),      nullable=True),
        sa.Column("total_oi",        sa.BigInteger(), nullable=True),
        sa.Column("volume_oi_ratio", sa.Float(),      nullable=True),
        sa.Column("signal_type",     sa.String(20),   nullable=True),
        sa.Column("signal_score",    sa.Float(),      nullable=True),
        sa.Column("signal_reason",   sa.String(255),  nullable=True),
        sa.Column("executed",        sa.Boolean(),    nullable=False, server_default="false"),
        sa.Column("created_at",      sa.DateTime(),   nullable=False),
    )
    op.create_index("ix_options_signals_ticker",      "options_signals", ["ticker"])
    op.create_index("ix_options_signals_snapshot_at", "options_signals", ["snapshot_at"])
    op.create_index("ix_options_signals_signal_type", "options_signals", ["signal_type"])
    op.create_unique_constraint(
        "uq_options_ticker_snap", "options_signals", ["ticker", "snapshot_at"]
    )


def downgrade():
    op.drop_table("options_signals")
    op.drop_table("options_iv_snapshots")
