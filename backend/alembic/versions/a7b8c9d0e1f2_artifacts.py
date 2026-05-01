"""artifacts and artifact_events

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-05-01 09:00:00.000000

Artifact = チャット出力を view 化したオブジェクト。
スキル/AI 社員はこの存在を知らない。出力プロセッサが生成・更新する。

15 view 型: list / table / kanban / kpi-card / markdown-doc /
            gantt / calendar / chart / compare / workflow /
            gallery / matrix / form / slide / mindmap

User も AI も更新可能（mutable）。差分は artifact_events に記録。
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── artifacts: 出力された view オブジェクト ──────────────
    op.create_table(
        "artifacts",
        sa.Column("id",            sa.Text(),    primary_key=True),       # uuid
        sa.Column("type",          sa.Text(),    nullable=False),         # list/kanban/...
        sa.Column("title",         sa.Text(),    nullable=False, server_default=""),
        sa.Column("data",          sa.Text(),    server_default="{}"),    # JSON
        sa.Column("category_tags", sa.Text(),    server_default="[]"),    # JSON array
        sa.Column("pinned_by",     sa.Text(),    server_default="[]"),    # JSON array of user_id
        sa.Column("thread_id",     sa.Integer()),                          # 元になったチャット
        sa.Column("employee_id",   sa.Integer()),                          # 出力した AI 社員
        sa.Column("created_by",    sa.Text(),    server_default="ai"),    # "user" or "ai" or "skill:<name>"
        sa.Column("is_archived",   sa.Integer(), server_default="0"),
        sa.Column("created_at",    sa.Text(),    server_default=sa.func.current_timestamp()),
        sa.Column("updated_at",    sa.Text(),    server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_artifacts_thread",   "artifacts", ["thread_id"])
    op.create_index("ix_artifacts_type",     "artifacts", ["type"])
    op.create_index("ix_artifacts_archived", "artifacts", ["is_archived"])

    # ── artifact_events: 変更履歴（user / AI 両方）─────────
    op.create_table(
        "artifact_events",
        sa.Column("id",            sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("artifact_id",   sa.Text(),    nullable=False),
        sa.Column("actor",         sa.Text(),    nullable=False),  # "user:masato" or "ai:secretary"
        sa.Column("action",        sa.Text(),    nullable=False),  # create/update/delete/pin/...
        sa.Column("diff",          sa.Text(),    server_default="{}"),  # JSON Patch
        sa.Column("note",          sa.Text(),    server_default=""),
        sa.Column("ts",            sa.Text(),    server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_events_artifact", "artifact_events", ["artifact_id"])
    op.create_index("ix_events_ts",       "artifact_events", ["ts"])


def downgrade() -> None:
    op.drop_index("ix_events_ts",       table_name="artifact_events")
    op.drop_index("ix_events_artifact", table_name="artifact_events")
    op.drop_table("artifact_events")
    op.drop_index("ix_artifacts_archived", table_name="artifacts")
    op.drop_index("ix_artifacts_type",     table_name="artifacts")
    op.drop_index("ix_artifacts_thread",   table_name="artifacts")
    op.drop_table("artifacts")
