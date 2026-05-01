"""user_profile

Revision ID: e9f0a1b2c3d4
Revises: d7e8f9a0b1c2
Create Date: 2026-04-30 12:50:00.000000

ユーザー（まさと等）のプロファイル（名前・固有情報）を保存する。
RAG 自動注入で毎ターン参照する。
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'e9f0a1b2c3d4'
down_revision: Union[str, Sequence[str], None] = 'd7e8f9a0b1c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_profile",
        sa.Column("user_key",     sa.Text(), primary_key=True),  # "masato" 固定（将来の拡張用）
        sa.Column("display_name", sa.Text()),                      # 表示名 例: 高本 まさと
        sa.Column("aliases",      sa.Text()),                      # JSON: ["まさと","聖斗",...]
        sa.Column("preferences",  sa.Text()),                      # JSON: { tone: "...", interests: [...] }
        sa.Column("recent_topics",sa.Text()),                      # JSON: ["漢字当て","採用フロー",...]
        sa.Column("notes",        sa.Text()),                      # 自由記述（口癖・好み等）
        sa.Column("updated_at",   sa.Text(), server_default=sa.func.current_timestamp()),
    )
    # 初期値（まさと）
    op.execute("""
        INSERT INTO user_profile (user_key, display_name, aliases, preferences, recent_topics, notes)
        VALUES (
            'masato',
            '高本 まさと',
            '["まさと","聖斗","Masato"]',
            '{"language":"ja","tone":"casual"}',
            '[]',
            'ENGINE BASE 代表。AI社員システムのオーナー。'
        )
    """)


def downgrade() -> None:
    op.drop_table("user_profile")
