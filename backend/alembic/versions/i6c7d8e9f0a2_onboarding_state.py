"""T-V3-B-29 / F-027: user_onboarding_state table.

Revision ID: i6c7d8e9f0a2
Revises:
Create Date: 2026-05-16 00:00:00.000000

3 step onboarding (welcome / workspace_setup / ai_employee_intro) の
進行状態をローカル DB に永続化する.

- current_step:    現在の active step
- completed_steps: 完了済 step ID の JSON 配列
- skipped_steps:   skip された optional step ID の JSON 配列
- completed_at:    全 step 完了タイムスタンプ (NULL なら未完了)
- skipped_at:      最後の skip タイムスタンプ
"""
from typing import Sequence, Union

from alembic import op


revision: str = "i6c7d8e9f0a2"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS user_onboarding_state (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id         TEXT NOT NULL UNIQUE,
        current_step    TEXT NOT NULL DEFAULT 'welcome',
        completed_steps TEXT NOT NULL DEFAULT '[]',
        skipped_steps   TEXT NOT NULL DEFAULT '[]',
        completed_at    TEXT,
        skipped_at      TEXT,
        payload         TEXT NOT NULL DEFAULT '{}',
        updated_at      TEXT DEFAULT (datetime('now','localtime')),
        created_at      TEXT DEFAULT (datetime('now','localtime'))
    )""")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_onboarding_state_user "
        "ON user_onboarding_state(user_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_user_onboarding_state_user")
    op.execute("DROP TABLE IF EXISTS user_onboarding_state")
