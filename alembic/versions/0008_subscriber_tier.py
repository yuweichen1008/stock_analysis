"""add tier + editorial columns to subscribers

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subscribers", sa.Column("tier",            sa.String(10),  nullable=False, server_default="free"))
    op.add_column("subscribers", sa.Column("tier_expires_at", sa.DateTime(),  nullable=True))
    op.add_column("subscribers", sa.Column("editorial_note",  sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column("subscribers", "editorial_note")
    op.drop_column("subscribers", "tier_expires_at")
    op.drop_column("subscribers", "tier")
