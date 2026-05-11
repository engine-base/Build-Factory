"""T-023-05: user_clone_optin + user_deletion_requests

Revision ID: a4b5c6d7e8f9
Revises:
Create Date: 2026-05-11 00:30:00.000000

GDPR 削除権 (30 日 grace) + クローン opt-in toggle。
- user_clone_optin: 各 user が AI 社員クローン作成を opt-in しているか
- user_deletion_requests: 削除リクエスト + 30 日後の確定実行日時
"""
from typing import Sequence, Union

from alembic import op


revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS user_clone_optin (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id         TEXT NOT NULL UNIQUE,
        opted_in        INTEGER NOT NULL DEFAULT 0,   -- 0=off, 1=on
        opted_in_at     TEXT,
        opted_out_at    TEXT,
        updated_at      TEXT DEFAULT (datetime('now','localtime'))
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_user_clone_optin_user ON user_clone_optin(user_id)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS user_deletion_requests (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id         TEXT NOT NULL,
        status          TEXT NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending','cancelled','executed')),
        requested_at    TEXT DEFAULT (datetime('now','localtime')),
        execute_after   TEXT NOT NULL,                  -- requested_at + 30 days
        cancelled_at    TEXT,
        executed_at     TEXT,
        reason          TEXT
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_user_deletion_requests_status ON user_deletion_requests(status, execute_after)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_deletion_requests")
    op.execute("DROP TABLE IF EXISTS user_clone_optin")
