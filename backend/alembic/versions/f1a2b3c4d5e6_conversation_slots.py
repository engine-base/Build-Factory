"""conversation_slots

Revision ID: f1a2b3c4d5e6
Revises: e9f0a1b2c3d4
Create Date: 2026-04-30 13:30:00.000000

スレッド単位で「会話のスロット状態」を保持する。
（Claude/ChatGPT が暗黙的にやっている slot tracking を明示化）

例: フルネーム漢字推測中
  slot_name = "苗字（たかもと）" → confirmed_value = "高本"
  slot_name = "名前（まさと）"   → rejected = ["雅人"], hints = ["キリスト→聖書", "7つの星→北斗七星"]
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'e9f0a1b2c3d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversation_slots",
        sa.Column("id",              sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("thread_id",       sa.Integer(), nullable=False),
        sa.Column("goal",            sa.Text()),                        # 「フルネーム漢字推測」等
        sa.Column("slot_name",       sa.Text(), nullable=False),        # 「苗字」「名前」「役職」等
        sa.Column("confirmed_value", sa.Text()),                        # 確定値
        sa.Column("rejected",        sa.Text(), server_default="[]"),   # JSON: 不採用仮説
        sa.Column("hints",           sa.Text(), server_default="[]"),   # JSON: ヒント・解釈
        sa.Column("history",         sa.Text(), server_default="[]"),   # JSON: 全提案履歴
        sa.Column("position",        sa.Integer(), server_default="0"),
        sa.Column("is_resolved",     sa.Integer(), server_default="0"), # 1=確定済
        sa.Column("last_updated",    sa.Text(), server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("thread_id", "slot_name", name="uq_slots_thread_name"),
    )
    op.create_index("ix_slots_thread", "conversation_slots", ["thread_id"])


def downgrade() -> None:
    op.drop_index("ix_slots_thread", table_name="conversation_slots")
    op.drop_table("conversation_slots")
