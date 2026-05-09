"""account_settings: 発行者情報・テンプレ設定・実績・プラン

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4g5h6
Create Date: 2026-05-08 18:00:00.000000

各 account に紐づく「自社情報」テーブル。
提案書・見積書フェーズで発行者情報・振込先・ブランド・実績・テンプレ構成を
ここから取得して動的に流し込む。

template_config (JSON) はテンプレビルダースキルが対話的に組み立てた構造を保持。
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4g5h6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "account_settings",
        sa.Column("account_id",            sa.Integer(), primary_key=True),

        # ── 会社基本情報 ─────────────────────────────
        sa.Column("company_name",          sa.Text(),    nullable=False),
        sa.Column("company_name_kana",     sa.Text()),
        sa.Column("representative_name",   sa.Text()),
        sa.Column("representative_title",  sa.Text()),  # 代表取締役 / CEO etc.
        sa.Column("postal_code",           sa.Text()),
        sa.Column("address",               sa.Text()),
        sa.Column("phone",                 sa.Text()),
        sa.Column("email",                 sa.Text()),
        sa.Column("website",               sa.Text()),

        # ── 振込先 (主要 1 つ) ───────────────────────
        sa.Column("bank_name",             sa.Text()),
        sa.Column("bank_branch",           sa.Text()),
        sa.Column("bank_account_type",     sa.Text(),    server_default="普通"),
        sa.Column("bank_account_number",   sa.Text()),
        sa.Column("bank_account_holder",   sa.Text()),

        # ── ブランド ─────────────────────────────────
        sa.Column("logo_url",              sa.Text()),
        sa.Column("stamp_url",             sa.Text()),
        sa.Column("stamp_text",            sa.Text()),  # "EB" 等の印文字
        sa.Column("primary_color",         sa.Text(),    server_default="#004CD9"),
        sa.Column("secondary_color",       sa.Text()),
        sa.Column("font_family",           sa.Text(),    server_default="Noto Sans JP"),

        # ── 実績・事例 (JSON 配列) ─────────────────
        # achievement_stats: [{"value":"30+", "label":"開発実績"}, ...]
        # case_studies: [{"type":"EC","title":"...","desc":"...","image_url":""}, ...]
        sa.Column("achievement_stats",     sa.Text(),    server_default="[]"),
        sa.Column("case_studies",          sa.Text(),    server_default="[]"),

        # ── デフォルト条件 ─────────────────────────
        sa.Column("payment_terms_default", sa.Text(),    server_default="30/30/40"),
        sa.Column("warranty_days",         sa.Integer(), server_default="90"),
        sa.Column("monthly_maintenance_yen", sa.Integer()),
        sa.Column("estimate_validity_days", sa.Integer(), server_default="30"),
        sa.Column("tax_rate",              sa.Float(),   server_default="0.10"),

        # ── 採番ルール ─────────────────────────────
        sa.Column("estimate_prefix",       sa.Text(),    server_default="EST"),
        sa.Column("proposal_prefix",       sa.Text(),    server_default="PROP"),

        # ── 任意の備考デフォルト (JSON 配列) ────────
        sa.Column("default_notes",         sa.Text(),    server_default="[]"),

        # ── テンプレ設定 (JSON) ─────────────────────
        # template-builder スキルが組み立てる JSONB 構造
        # {
        #   "design": {...},
        #   "sections": [{"type":"cover","enabled":true,"config":{...}}, ...],
        #   "plans": [...],
        #   "extra_pages": [...]
        # }
        sa.Column("template_config",       sa.Text(),    server_default="{}"),

        # ── タイムスタンプ ─────────────────────────
        sa.Column("created_at",            sa.Text(),    server_default=sa.func.current_timestamp()),
        sa.Column("updated_at",            sa.Text(),    server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_account_settings_account", "account_settings", ["account_id"], unique=True)

    # account_id=1 のデフォルト ENGINE BASE 行をシード (BF dev workspace 用)
    op.execute("""
        INSERT OR IGNORE INTO account_settings (
            account_id, company_name, company_name_kana,
            representative_name, representative_title,
            postal_code, address, phone, email, website,
            bank_name, bank_branch, bank_account_type, bank_account_number, bank_account_holder,
            primary_color, stamp_text,
            achievement_stats, case_studies,
            payment_terms_default, warranty_days, monthly_maintenance_yen, estimate_validity_days,
            estimate_prefix, proposal_prefix
        ) VALUES (
            1, '株式会社ENGINE BASE', 'カブシキガイシャ エンジン ベース',
            '高本 聖斗', '代表取締役',
            '150-0002', '東京都渋谷区渋谷1-2-3', '03-XXXX-XXXX',
            'info@engine-base.com', 'https://engine-base.com',
            '三菱UFJ銀行', '渋谷支店', '普通', '1234567', 'カ) エンジンベース',
            '#004CD9', 'EB',
            '[{"value":"30+","label":"開発実績件数"},{"value":"1.8か月","label":"平均納期"},{"value":"4.7","label":"顧客満足度"}]',
            '[]',
            '30/30/40', 90, 50000, 30,
            'EST', 'PROP'
        )
    """)


def downgrade() -> None:
    op.drop_index("ix_account_settings_account", "account_settings")
    op.drop_table("account_settings")
