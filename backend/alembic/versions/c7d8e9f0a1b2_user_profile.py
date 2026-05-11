"""T-023-01: user_profiles table (display_name / role_text / bio / theme)

Revision ID: c7d8e9f0a1b2
Revises: b5c6d7e8f9a0
Create Date: 2026-05-11 04:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, Sequence[str], None] = "b5c6d7e8f9a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS user_profiles (
        user_id        TEXT PRIMARY KEY,
        display_name   TEXT,
        role_text      TEXT,
        bio            TEXT,
        theme          TEXT NOT NULL DEFAULT 'light'
                         CHECK (theme IN ('light','dark','system')),
        avatar_url     TEXT,
        updated_at     TEXT DEFAULT (datetime('now','localtime'))
    )""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_profiles")
