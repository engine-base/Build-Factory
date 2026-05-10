"""T-021-03: swarm_pools / swarm_cells tables

Revision ID: e1f2a3b4c5d6
Revises:
Create Date: 2026-05-10 23:30:00.000000

Swarm 並列実行基盤 (4/9/16/64 cells、claude-agent-sdk Subagent + git worktree)。
T-021-03 AC:
  - UBIQUITOUS: Swarm が 4/9/16/64 parallel sessions を起動する
  - EVENT: 起動時に各セッションへ .worktrees/swarm_{pool_id}/cell_{n} を割り当てる
  - STATE: 実行中は per-cell logs と集計 stats (queued/running/done/failed/crashed)
  - OPTIONAL: 同ファイル衝突時は file-level lock で serialize
  - UNWANTED: sandbox escape 検知 → kill + redline event
"""
from typing import Sequence, Union

from alembic import op


revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS swarm_pools (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT NOT NULL,
        size            INTEGER NOT NULL CHECK (size IN (4, 9, 16, 64)),
        status          TEXT NOT NULL DEFAULT 'queued'
                          CHECK (status IN ('queued','running','done','failed','cancelled')),
        base_branch     TEXT NOT NULL DEFAULT 'main',
        task_prompt     TEXT,
        created_by      TEXT,
        created_at      TEXT DEFAULT (datetime('now','localtime')),
        started_at      TEXT,
        completed_at    TEXT,
        stats_json      TEXT
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_swarm_pools_status ON swarm_pools(status, created_at)")

    op.execute("""
    CREATE TABLE IF NOT EXISTS swarm_cells (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        pool_id         INTEGER NOT NULL,
        cell_index      INTEGER NOT NULL,
        worktree_path   TEXT NOT NULL,
        branch_name     TEXT NOT NULL,
        status          TEXT NOT NULL DEFAULT 'queued'
                          CHECK (status IN ('queued','running','done','failed','crashed','killed')),
        session_id      INTEGER,
        exit_code       INTEGER,
        error_msg       TEXT,
        log_path        TEXT,
        started_at      TEXT,
        completed_at    TEXT,
        FOREIGN KEY (pool_id) REFERENCES swarm_pools(id) ON DELETE CASCADE,
        UNIQUE (pool_id, cell_index)
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_swarm_cells_pool ON swarm_cells(pool_id, status)")

    # file-level lock テーブル (T-021-03 OPTIONAL AC: 同ファイル衝突時に serialize)
    op.execute("""
    CREATE TABLE IF NOT EXISTS swarm_file_locks (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        pool_id         INTEGER NOT NULL,
        cell_id         INTEGER NOT NULL,
        file_path       TEXT NOT NULL,
        acquired_at     TEXT DEFAULT (datetime('now','localtime')),
        released_at     TEXT,
        FOREIGN KEY (pool_id) REFERENCES swarm_pools(id) ON DELETE CASCADE,
        FOREIGN KEY (cell_id) REFERENCES swarm_cells(id) ON DELETE CASCADE
    )""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_swarm_file_locks_active ON swarm_file_locks(file_path, released_at)")

    # UNWANTED AC: sandbox escape redline event
    op.execute("""
    CREATE TABLE IF NOT EXISTS swarm_redline_events (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        pool_id         INTEGER NOT NULL,
        cell_id         INTEGER NOT NULL,
        event_type      TEXT NOT NULL
                          CHECK (event_type IN ('sandbox_escape','cross_cell_access','timeout','oom')),
        detail          TEXT,
        detected_at     TEXT DEFAULT (datetime('now','localtime')),
        FOREIGN KEY (pool_id) REFERENCES swarm_pools(id) ON DELETE CASCADE,
        FOREIGN KEY (cell_id) REFERENCES swarm_cells(id) ON DELETE CASCADE
    )""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS swarm_redline_events")
    op.execute("DROP TABLE IF EXISTS swarm_file_locks")
    op.execute("DROP TABLE IF EXISTS swarm_cells")
    op.execute("DROP TABLE IF EXISTS swarm_pools")
