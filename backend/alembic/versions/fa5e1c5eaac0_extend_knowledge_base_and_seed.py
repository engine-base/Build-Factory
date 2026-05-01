"""extend_knowledge_base_and_seed

Revision ID: fa5e1c5eaac0
Revises: d83319c25a4f
Create Date: 2026-04-29 12:04:01.465104

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fa5e1c5eaac0'
down_revision: Union[str, Sequence[str], None] = 'd83319c25a4f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # knowledge_base 拡張（tags はすでに存在するためスキップ）
    with op.batch_alter_table("knowledge_base") as batch_op:
        batch_op.add_column(sa.Column("knowledge_type", sa.Text(), server_default="pattern"))
        batch_op.add_column(sa.Column("confirmed_by_user", sa.Integer(), server_default="0"))
        batch_op.add_column(sa.Column("use_count", sa.Integer(), server_default="0"))
        batch_op.add_column(sa.Column("source_execution_id", sa.Integer()))

    # ai_employee_config 初期データ
    op.execute("""
    INSERT OR IGNORE INTO ai_employee_config
        (employee_name, display_name, category, primary_skill, knowledge_tags, llm_provider, llm_model)
    VALUES
        ('secretary', '総括AI秘書', '総括', 'secretary', '["#共通","#全社"]', 'ollama', 'qwen2.5:7b'),
        ('sales_01',  '01_営業AI',  '01_営業', '01_sales', '["#01_営業","#02_CRM","#共通"]', 'ollama', 'qwen2.5:7b')
    """)

    # task_schedule デフォルトスケジュール
    op.execute("""
    INSERT OR IGNORE INTO task_schedule
        (task_name, skill_name, description, frequency, run_time, is_active, autonomy)
    VALUES
        ('朝ブリーフィング', 'secretary', '毎朝の業務サマリー生成', 'daily', '08:00', 1, 'auto'),
        ('統合インボックス確認(朝)', 'secretary', 'メール重要度チェック', 'daily', '08:00', 1, 'confirm'),
        ('統合インボックス確認(昼)', 'secretary', 'メール重要度チェック', 'daily', '12:00', 1, 'confirm'),
        ('統合インボックス確認(夕)', 'secretary', 'メール重要度チェック', 'daily', '18:00', 1, 'confirm')
    """)


def downgrade() -> None:
    with op.batch_alter_table("knowledge_base") as batch_op:
        batch_op.drop_column("source_execution_id")
        batch_op.drop_column("use_count")
        batch_op.drop_column("confirmed_by_user")
        batch_op.drop_column("knowledge_type")
    op.execute("DELETE FROM ai_employee_config WHERE employee_name IN ('secretary','sales_01')")
    op.execute("DELETE FROM task_schedule WHERE skill_name = 'secretary'")
