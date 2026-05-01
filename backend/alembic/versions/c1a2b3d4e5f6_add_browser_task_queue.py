"""add_browser_task_queue

Revision ID: c1a2b3d4e5f6
Revises: fa5e1c5eaac0
Create Date: 2026-04-29 23:20:00.000000

ブラウザuseタスクのキュー。基本的に追加するだけで、Claude Desktop等から
バッチ実行する。即時実行はしない（重いから）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1a2b3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'fa5e1c5eaac0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "browser_task_queue",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task", sa.Text(), nullable=False),                      # 何をするか
        sa.Column("service", sa.Text()),                                   # notion/slack/x など
        sa.Column("status", sa.Text(), server_default="pending"),          # pending/running/done/failed/cancelled
        sa.Column("priority", sa.Integer(), server_default="3"),           # 1=高 / 3=中 / 5=低
        sa.Column("max_steps", sa.Integer(), server_default="20"),
        sa.Column("provider", sa.Text(), server_default="openai"),         # openai/claude/ollama
        sa.Column("model", sa.Text(), server_default="gpt-4o-mini"),
        sa.Column("requested_by", sa.Text()),                              # slack/secretary/api 等
        sa.Column("requested_via_thread", sa.Integer()),                   # threads.id（任意）
        sa.Column("result", sa.Text()),                                    # 完了時の最終結果文字列
        sa.Column("error", sa.Text()),                                     # 失敗時のエラー
        sa.Column("screenshot_path", sa.Text()),
        sa.Column("steps_summary", sa.Text()),                             # JSON
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp()),
        sa.Column("started_at", sa.DateTime()),
        sa.Column("finished_at", sa.DateTime()),
    )
    op.create_index("ix_browser_task_queue_status", "browser_task_queue", ["status"])


def downgrade() -> None:
    op.drop_index("ix_browser_task_queue_status", table_name="browser_task_queue")
    op.drop_table("browser_task_queue")
