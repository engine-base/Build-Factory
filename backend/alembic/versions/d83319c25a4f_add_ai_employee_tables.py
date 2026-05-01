"""add_ai_employee_tables

Revision ID: d83319c25a4f
Revises: 
Create Date: 2026-04-29 12:03:04.723596

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd83319c25a4f'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS task_schedule (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        task_name    TEXT NOT NULL,
        skill_name   TEXT NOT NULL,
        description  TEXT,
        frequency    TEXT NOT NULL,
        day_of_week  TEXT,
        day_of_month INTEGER,
        run_time     TEXT NOT NULL,
        timezone     TEXT DEFAULT 'Asia/Tokyo',
        is_active    INTEGER DEFAULT 1,
        autonomy     TEXT DEFAULT 'confirm',
        params       TEXT,
        last_run_at  TEXT,
        next_run_at  TEXT,
        created_at   TEXT DEFAULT (datetime('now','localtime')),
        updated_at   TEXT DEFAULT (datetime('now','localtime'))
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_schedule_active ON task_schedule(is_active, next_run_at)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS approval_queue (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        action_type         TEXT NOT NULL,
        title               TEXT NOT NULL,
        content             TEXT NOT NULL,
        metadata            TEXT,
        status              TEXT DEFAULT 'pending',
        channel_notified    TEXT,
        slack_ts            TEXT,
        source_skill        TEXT,
        source_execution_id INTEGER,
        revision_memo       TEXT,
        expires_at          TEXT,
        resolved_at         TEXT,
        created_at          TEXT DEFAULT (datetime('now','localtime'))
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_approval_queue_status ON approval_queue(status, expires_at)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS execution_log (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        skill_name      TEXT NOT NULL,
        triggered_by    TEXT NOT NULL,
        trigger_id      INTEGER,
        status          TEXT NOT NULL,
        input_context   TEXT,
        result_summary  TEXT,
        result_path     TEXT,
        approval_id     INTEGER,
        error_message   TEXT,
        duration_sec    REAL,
        llm_provider    TEXT,
        llm_model       TEXT,
        started_at      TEXT DEFAULT (datetime('now','localtime')),
        completed_at    TEXT
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_execution_log_skill  ON execution_log(skill_name, started_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_execution_log_status ON execution_log(status, started_at)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS communication_log (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        channel        TEXT NOT NULL,
        channel_id     TEXT,
        direction      TEXT NOT NULL,
        sender_name    TEXT,
        sender_id      TEXT,
        subject        TEXT,
        body           TEXT,
        body_summary   TEXT,
        importance     TEXT DEFAULT 'low',
        status         TEXT DEFAULT 'unread',
        reply_draft_id INTEGER,
        external_id    TEXT,
        received_at    TEXT,
        created_at     TEXT DEFAULT (datetime('now','localtime'))
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_comm_log_channel ON communication_log(channel, importance, status)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_comm_log_external ON communication_log(channel, external_id)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS ai_employee_config (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        employee_name      TEXT NOT NULL UNIQUE,
        display_name       TEXT,
        category           TEXT,
        primary_skill      TEXT,
        knowledge_tags     TEXT,
        autonomy_settings  TEXT,
        llm_provider       TEXT DEFAULT 'ollama',
        llm_model          TEXT DEFAULT 'qwen2.5:7b',
        is_active          INTEGER DEFAULT 1,
        created_at         TEXT DEFAULT (datetime('now','localtime')),
        updated_at         TEXT DEFAULT (datetime('now','localtime'))
    )""")


def downgrade() -> None:
    for tbl in ["ai_employee_config", "communication_log", "execution_log", "approval_queue", "task_schedule"]:
        op.execute(f"DROP TABLE IF EXISTS {tbl}")
