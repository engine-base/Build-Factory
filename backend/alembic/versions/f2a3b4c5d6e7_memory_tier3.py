"""T-020-02: Memory Tier 3 + audit_logs テーブル

Revision ID: f2a3b4c5d6e7
Revises:
Create Date: 2026-05-10 23:50:00.000000

ADR-010 + CLAUDE.md §3 Memory (3 tier):
  - Short: chat_threads / chat_messages (既存)
  - Mid:   chat_messages 圧縮 + 9-section summary (既存)
  - Long:  Mem0 + Obsidian + Constitution (このマイグレーションで補強)
  - audit_logs: memory_compacted / memory_degraded event 永続化
"""
from typing import Sequence, Union

from alembic import op


revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # audit_logs: 任意の系統横断イベントを蓄積 (memory_compacted / memory_degraded
    # / sandbox_escape / cost_threshold_exceeded 等を含む)
    op.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type      TEXT NOT NULL,
        session_id      INTEGER,
        user_id         TEXT,
        detail_json     TEXT,
        created_at      TEXT DEFAULT (datetime('now','localtime'))
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_event_type ON audit_logs(event_type, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_session ON audit_logs(session_id, created_at)")

    # mem0_collections: Mem0 ベクトル空間の論理コレクション管理 (user 単位)
    op.execute("""
    CREATE TABLE IF NOT EXISTS mem0_collections (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id         TEXT NOT NULL,
        collection_name TEXT NOT NULL,
        item_count      INTEGER DEFAULT 0,
        last_synced_at  TEXT,
        created_at      TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE (user_id, collection_name)
    )""")

    # obsidian_notes: Obsidian Markdown ノートのメタ (パス + 同期状態)
    op.execute("""
    CREATE TABLE IF NOT EXISTS obsidian_notes (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id         TEXT NOT NULL,
        note_path       TEXT NOT NULL,
        title           TEXT,
        content_hash    TEXT,
        last_synced_at  TEXT,
        created_at      TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE (user_id, note_path)
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_obsidian_notes_user ON obsidian_notes(user_id, last_synced_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS obsidian_notes")
    op.execute("DROP TABLE IF EXISTS mem0_collections")
    op.execute("DROP TABLE IF EXISTS audit_logs")
