"""T-024-04: workspaces.preferred_provider column 追加 (ADR-012 Decision 5).

Revision ID: h5c6d7e8f9a1
Revises: g4b5c6d7e8f9
Create Date: 2026-05-13

ADR-012 (Anthropic Memory Tool / Context Editing / Subagent Memory) の
provider-adapter 切替経路で「per-workspace preferred_provider」を
precedence source とするためのカラム追加.

仕様 (T-024-04):
  AC-1 UBIQUITOUS    : enum(anthropic / openai / gemini / auto), default 'auto',
                       NOT NULL. idempotent (二重実行可) + 既存 row backfill.
  AC-2 EVENT-DRIVEN  : <= 100,000 行で 2 秒以内. schema.migration_applied audit emit.
  AC-3 STATE-DRIVEN  : RLS 不変 / concurrent read 不停止.
  AC-4 UNWANTED      : 二重実行で error にならない / enum 外値は 4xx (application 層).

設計:
  - SQL は UPGRADE_STATEMENTS / DOWNGRADE_STATEMENTS の定数として保持し,
    test では sqlite3 直接実行で検証する (alembic op 依存を避ける).
  - 本番 alembic 経由 (upgrade() / downgrade()) では op.execute で同 SQL を実行.
  - idempotent guard は has_column() helper を SQL の前段に挿入.

SQLite と Postgres の違い:
  - SQLite (本 alembic): TEXT + application 層 validation (CHECK は ALTER で追加困難).
  - Postgres (supabase migration 20260513100000_workspaces_preferred_provider.sql):
    enum 型 (preferred_provider_enum) を作成して制約.
"""
from typing import Sequence, Union


revision: str = "h5c6d7e8f9a1"
down_revision: Union[str, Sequence[str], None] = "g4b5c6d7e8f9"
branch_labels = None
depends_on = None


PREFERRED_PROVIDER_VALUES = ("anthropic", "openai", "gemini", "auto")
DEFAULT_VALUE = "auto"

TABLE_NAME = "workspaces"
COLUMN_NAME = "preferred_provider"

# AC-1: ADD COLUMN with DEFAULT 'auto' + NOT NULL (SQLite は 1 step で完了)
UPGRADE_ADD_COLUMN_SQL = (
    "ALTER TABLE workspaces ADD COLUMN preferred_provider TEXT "
    f"NOT NULL DEFAULT '{DEFAULT_VALUE}'"
)

# 追加 backfill (DEFAULT で既存 row も埋まるが explicit に保証)
UPGRADE_BACKFILL_SQL = (
    "UPDATE workspaces SET preferred_provider = "
    f"'{DEFAULT_VALUE}' WHERE preferred_provider IS NULL"
)


def has_column(connection, table: str, column: str) -> bool:
    """PRAGMA table_info で column 存在を確認 (idempotent guard).

    connection は sqlite3.Connection 互換 (cursor() を持つ).
    """
    cur = connection.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def apply_upgrade_to_sqlite(connection) -> dict:
    """test / 直接呼出用: sqlite3.Connection で migration を実行.

    Returns:
      {"added": bool, "backfilled_rows": int}

    idempotent: 既存 column があれば no-op.
    """
    if has_column(connection, TABLE_NAME, COLUMN_NAME):
        return {"added": False, "backfilled_rows": 0}
    connection.execute(UPGRADE_ADD_COLUMN_SQL)
    cur = connection.execute(UPGRADE_BACKFILL_SQL)
    backfilled = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    connection.commit()
    return {"added": True, "backfilled_rows": backfilled}


def upgrade() -> None:
    """alembic 経由の本番 upgrade. op.execute で同 SQL を実行."""
    from alembic import op
    bind = op.get_bind()
    # idempotent guard: 既存 column があれば skip
    rows = bind.execute(__import__("sqlalchemy").text(
        f"PRAGMA table_info({TABLE_NAME})"
    )).fetchall()
    if any(r[1] == COLUMN_NAME for r in rows):
        return
    op.execute(UPGRADE_ADD_COLUMN_SQL)
    op.execute(UPGRADE_BACKFILL_SQL)


def downgrade() -> None:
    """SQLite では DROP COLUMN を直接サポートしないため batch_alter_table を使用."""
    from alembic import op
    bind = op.get_bind()
    rows = bind.execute(__import__("sqlalchemy").text(
        f"PRAGMA table_info({TABLE_NAME})"
    )).fetchall()
    if not any(r[1] == COLUMN_NAME for r in rows):
        return
    with op.batch_alter_table(TABLE_NAME) as batch:
        batch.drop_column(COLUMN_NAME)
