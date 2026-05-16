"""build-factory: account_invitations table (F-004 / T-V3-B-05)

Revision ID: i6d7e8f9a1b2
Revises: h5c6d7e8f9a1
Create Date: 2026-05-16 14:00:00.000000

T-V3-B-05: account 単位の招待 (POST /api/accounts/{id}/invitations) を支える表。
workspace_invitations と並列の構造 (token / status / expires_at) を持つ。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "i6d7e8f9a1b2"
down_revision: Union[str, Sequence[str], None] = "h5c6d7e8f9a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "account_invitations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), server_default="member"),
        sa.Column("token", sa.Text(), nullable=False, unique=True),
        sa.Column("invited_by", sa.Text()),
        sa.Column(
            "status", sa.Text(), server_default="pending"
        ),  # pending / accepted / expired / revoked
        sa.Column("expires_at", sa.Text()),
        sa.Column(
            "created_at",
            sa.Text(),
            server_default=sa.func.current_timestamp(),
        ),
    )
    op.create_index(
        "ix_account_invitations_account",
        "account_invitations",
        ["account_id"],
    )
    op.create_index(
        "ix_account_invitations_token",
        "account_invitations",
        ["token"],
    )


def downgrade() -> None:
    op.drop_index("ix_account_invitations_token", table_name="account_invitations")
    op.drop_index("ix_account_invitations_account", table_name="account_invitations")
    op.drop_table("account_invitations")
