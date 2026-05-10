"""staff_hierarchy_personas

Revision ID: d7e8f9a0b1c2
Revises: c1a2b3d4e5f6
Create Date: 2026-04-30 00:00:00.000000

AI社員の階層化（秘書 / リーダー / メンバー）+ 個性 + ナレッジスコープ対応。

- ai_employee_config に階層・個性・スコープ列を追加
- knowledge_base に assigned_employee_id 追加
- knowledge_transfer_log テーブル新設（採用・退職時のナレッジ移動を全件記録）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd7e8f9a0b1c2'
down_revision: Union[str, Sequence[str], None] = 'c1a2b3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── ai_employee_config 拡張 ──────────────────
    with op.batch_alter_table("ai_employee_config") as batch:
        # 階層
        batch.add_column(sa.Column("parent_id",   sa.Integer()))                       # NULL=リーダー or 秘書
        batch.add_column(sa.Column("role_level",  sa.Text(), server_default="leader")) # 'secretary' / 'leader' / 'member'

        # 個性
        batch.add_column(sa.Column("persona_name",  sa.Text()))   # 田中 太郎
        batch.add_column(sa.Column("personality",   sa.Text()))   # 性格
        batch.add_column(sa.Column("tone_style",    sa.Text()))   # 口調
        batch.add_column(sa.Column("catchphrase",   sa.Text()))   # 口癖
        batch.add_column(sa.Column("avatar_emoji",  sa.Text()))   # avatar identifier (text only)
        batch.add_column(sa.Column("specialty",     sa.Text()))   # 特化分野（メンバーのみ）
        batch.add_column(sa.Column("handles",       sa.Text()))   # 担当範囲（自然文）

        # ナレッジスコープ（JSON配列で md_path 接頭辞リスト）
        batch.add_column(sa.Column("knowledge_folders", sa.Text()))

        # ライフサイクル（created_at は既存・retired_at 系のみ追加）
        batch.add_column(sa.Column("retired_at",    sa.Text()))
        batch.add_column(sa.Column("retire_reason", sa.Text()))
        batch.add_column(sa.Column("inherited_to",  sa.Integer()))   # 退職時の主たる引継先

    op.create_index("ix_ai_employee_parent",     "ai_employee_config", ["parent_id"])
    op.create_index("ix_ai_employee_role_level", "ai_employee_config", ["role_level"])
    op.create_index("ix_ai_employee_retired_at", "ai_employee_config", ["retired_at"])

    # ── knowledge_base にメンバー専属化用の列を追加 ──
    with op.batch_alter_table("knowledge_base") as batch:
        batch.add_column(sa.Column("assigned_employee_id", sa.Integer()))
    op.create_index("ix_knowledge_assigned_emp", "knowledge_base", ["assigned_employee_id"])

    # ── knowledge_transfer_log 新規 ─────────────
    op.create_table(
        "knowledge_transfer_log",
        sa.Column("id",             sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("knowledge_id",   sa.Integer(), nullable=False),
        sa.Column("from_employee",  sa.Integer()),                                      # NULL=共通
        sa.Column("to_employee",    sa.Integer()),                                      # NULL=共通
        sa.Column("reason",         sa.Text()),                                         # 'hire'/'retire'/'edit'/'rebalance'/'manual'
        sa.Column("triggered_by",   sa.Text(), server_default="staff_management"),      # 'masato'/'ai_auto'/...
        sa.Column("transferred_at", sa.Text(), server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_kt_knowledge", "knowledge_transfer_log", ["knowledge_id"])
    op.create_index("ix_kt_to",        "knowledge_transfer_log", ["to_employee"])

    # ── 既存5社員に role_level + persona seed ──────
    # 秘書はsecretary・他4名は leader として設定し、persona も入れておく
    op.execute("""
        UPDATE ai_employee_config SET role_level='secretary',
            persona_name = COALESCE(persona_name, '鈴木 由美'),
            personality  = COALESCE(personality, '落ち着いて全体を把握・寄り添い型・気配り上手'),
            tone_style   = COALESCE(tone_style, 'です・ます調・敬語・短く要点'),
            catchphrase  = COALESCE(catchphrase, '承知しました'),
            avatar_emoji = COALESCE(avatar_emoji, ''),
            handles      = COALESCE(handles, 'まさととの全窓口・全社俯瞰・タスク振分・組織の最適化'),
            knowledge_folders = COALESCE(knowledge_folders,
                '["00_まさとの思考・価値観","01_会社・事業","02_共通ナレッジ"]')
        WHERE employee_name = 'secretary'
    """)
    op.execute("""
        UPDATE ai_employee_config SET role_level='leader',
            persona_name = COALESCE(persona_name, '田中 太郎'),
            personality  = COALESCE(personality, '受注ハンター気質・前のめり・ポジティブ'),
            tone_style   = COALESCE(tone_style, 'ビジネスカジュアル「〜しましょう！」「いきましょう！」'),
            catchphrase  = COALESCE(catchphrase, 'これチャンスですね'),
            avatar_emoji = COALESCE(avatar_emoji, ''),
            handles      = COALESCE(handles, '営業全般の統括・パイプライン管理・案件振分・受注最大化'),
            knowledge_folders = COALESCE(knowledge_folders,
                '["00_まさとの思考・価値観","01_会社・事業","02_共通ナレッジ","03_スキル別ナレッジ/営業"]')
        WHERE employee_name = 'sales_01'
    """)
    op.execute("""
        UPDATE ai_employee_config SET role_level='leader',
            persona_name = COALESCE(persona_name, '佐藤 美咲'),
            personality  = COALESCE(personality, '慎重・数字に厳しい・冷静沈着'),
            tone_style   = COALESCE(tone_style, 'です・ます調・丁寧・ロジカル'),
            catchphrase  = COALESCE(catchphrase, '数字で確認しましょう'),
            avatar_emoji = COALESCE(avatar_emoji, ''),
            handles      = COALESCE(handles, '経理全般の統括・PL/CF管理・請求/支払い・税務サポート'),
            knowledge_folders = COALESCE(knowledge_folders,
                '["00_まさとの思考・価値観","01_会社・事業","02_共通ナレッジ","03_スキル別ナレッジ/経理"]')
        WHERE employee_name = 'finance_02'
    """)
    op.execute("""
        UPDATE ai_employee_config SET role_level='leader',
            persona_name = COALESCE(persona_name, '山田 蓮'),
            personality  = COALESCE(personality, 'クリエイティブ・トレンド大好き・スピード感'),
            tone_style   = COALESCE(tone_style, 'カジュアル・絵文字多め・テンション高め'),
            catchphrase  = COALESCE(catchphrase, 'これバズらせましょう'),
            avatar_emoji = COALESCE(avatar_emoji, ''),
            handles      = COALESCE(handles, 'マーケ全般の統括・SNS/コンテンツ/広告/SEOの戦略設計'),
            knowledge_folders = COALESCE(knowledge_folders,
                '["00_まさとの思考・価値観","01_会社・事業","02_共通ナレッジ","03_スキル別ナレッジ/マーケティング"]')
        WHERE employee_name = 'marketing_03'
    """)
    op.execute("""
        UPDATE ai_employee_config SET role_level='leader',
            persona_name = COALESCE(persona_name, '鈴木 花'),
            personality  = COALESCE(personality, '共感型・聞き上手・寄り添い'),
            tone_style   = COALESCE(tone_style, '柔らかい・ですます調・お気持ち重視'),
            catchphrase  = COALESCE(catchphrase, 'お気持ちわかります'),
            avatar_emoji = COALESCE(avatar_emoji, ''),
            handles      = COALESCE(handles, 'CS全般の統括・問い合わせ対応・FAQ管理・顧客満足度'),
            knowledge_folders = COALESCE(knowledge_folders,
                '["00_まさとの思考・価値観","01_会社・事業","02_共通ナレッジ","03_スキル別ナレッジ/CS"]')
        WHERE employee_name = 'cs_04'
    """)


def downgrade() -> None:
    op.drop_index("ix_kt_to",        table_name="knowledge_transfer_log")
    op.drop_index("ix_kt_knowledge", table_name="knowledge_transfer_log")
    op.drop_table("knowledge_transfer_log")

    op.drop_index("ix_knowledge_assigned_emp", table_name="knowledge_base")
    with op.batch_alter_table("knowledge_base") as batch:
        batch.drop_column("assigned_employee_id")

    op.drop_index("ix_ai_employee_retired_at", table_name="ai_employee_config")
    op.drop_index("ix_ai_employee_role_level", table_name="ai_employee_config")
    op.drop_index("ix_ai_employee_parent",     table_name="ai_employee_config")

    with op.batch_alter_table("ai_employee_config") as batch:
        for col in [
            "inherited_to", "retire_reason", "retired_at",
            "knowledge_folders", "handles", "specialty", "avatar_emoji",
            "catchphrase", "tone_style", "personality", "persona_name",
            "role_level", "parent_id",
        ]:
            batch.drop_column(col)
