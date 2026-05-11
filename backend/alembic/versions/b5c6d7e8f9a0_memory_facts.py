"""T-AI-01: memory_facts table + retry queue + deletion audit

Revision ID: b5c6d7e8f9a0
Revises: f2a3b4c5d6e7
Create Date: 2026-05-11 02:00:00.000000

CLAUDE.md §3「自前実装必須 8 項目」T-AI-01。
- memory_facts: source_session_id + confidence_score + status (pending/synced/failed)
- 失敗時の retry 用 retry_count + last_error
- fingerprint で重複排除 (同 user 内 UNIQUE)
- deleted_at で soft-delete (24h 内に Memory API/Mem0/Obsidian 削除タスク用)
"""
from typing import Sequence, Union

from alembic import op


revision: str = "b5c6d7e8f9a0"
down_revision: Union[str, Sequence[str], None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS memory_facts (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id             TEXT NOT NULL,
        workspace_id        TEXT,
        fact_text           TEXT NOT NULL,
        kind                TEXT NOT NULL DEFAULT 'durable',
        source_session_id   INTEGER,
        confidence_score    REAL NOT NULL DEFAULT 0.7
                              CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
        fingerprint         TEXT NOT NULL,
        status              TEXT NOT NULL DEFAULT 'pending'
                              CHECK (status IN ('pending','synced','failed','deleted')),
        retry_count         INTEGER NOT NULL DEFAULT 0,
        last_error          TEXT,
        memory_api_id       TEXT,
        mem0_id             TEXT,
        created_at          TEXT DEFAULT (datetime('now','localtime')),
        synced_at           TEXT,
        deleted_at          TEXT,
        UNIQUE (user_id, fingerprint)
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_memory_facts_user_status ON memory_facts(user_id, status, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_memory_facts_workspace ON memory_facts(workspace_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_memory_facts_session ON memory_facts(source_session_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_memory_facts_pending ON memory_facts(status, retry_count) WHERE status = 'pending' OR status = 'failed'")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS memory_facts")
