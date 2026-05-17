"""add password_hash and encrypted broker credentials to users

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash",   sa.String(255), nullable=True))
    op.add_column("users", sa.Column("ctbc_id_enc",     sa.Text(),      nullable=True))
    op.add_column("users", sa.Column("ctbc_pass_enc",   sa.Text(),      nullable=True))
    op.add_column("users", sa.Column("moomoo_host_enc", sa.Text(),      nullable=True))
    op.add_column("users", sa.Column("moomoo_port_enc", sa.Text(),      nullable=True))


def downgrade() -> None:
    op.drop_column("users", "moomoo_port_enc")
    op.drop_column("users", "moomoo_host_enc")
    op.drop_column("users", "ctbc_pass_enc")
    op.drop_column("users", "ctbc_id_enc")
    op.drop_column("users", "password_hash")
