"""build-factory: accounts / workspaces / members

Revision ID: b1c2d3e4f5a6
Revises: a7b8c9d0e1f2
Create Date: 2026-05-01 21:00:00.000000

Build-Factory 固有の階層構造:
  Account (課金単位・AI 社員所有)
    ├─ Owner
    ├─ AI 社員 (account 共通)
    └─ Workspaces (プロジェクト単位)
         └─ Members (workspace 単位で招待・role 個別設定)

既存テーブルに account_id / workspace_id を追加して紐付ける。
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── accounts: 課金単位・AI 社員所有 ──────────────────
    op.create_table(
        "accounts",
        sa.Column("id",          sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name",        sa.Text(),    nullable=False),
        sa.Column("type",        sa.Text(),    server_default="individual"),  # company / individual
        sa.Column("plan",        sa.Text(),    server_default="free"),         # free / pro / business / enterprise
        sa.Column("owner_user_id", sa.Text(),  nullable=False),                # user identifier (email or uuid)
        sa.Column("billing_email", sa.Text()),
        sa.Column("metadata",    sa.Text(),    server_default="{}"),           # JSON
        sa.Column("is_active",   sa.Integer(), server_default="1"),
        sa.Column("created_at",  sa.Text(),    server_default=sa.func.current_timestamp()),
        sa.Column("updated_at",  sa.Text(),    server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_accounts_owner", "accounts", ["owner_user_id"])

    # ── account_members: アカウント内のロール（Owner のみが基本）───
    op.create_table(
        "account_members",
        sa.Column("id",           sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id",   sa.Integer(), nullable=False),
        sa.Column("user_id",      sa.Text(),    nullable=False),
        sa.Column("role",         sa.Text(),    server_default="owner"),  # owner / admin
        sa.Column("created_at",   sa.Text(),    server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("account_id", "user_id", name="uq_account_member"),
    )
    op.create_index("ix_account_members_account", "account_members", ["account_id"])

    # ── workspaces: プロジェクト単位 ───────────────────
    op.create_table(
        "workspaces",
        sa.Column("id",          sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("account_id",  sa.Integer(), nullable=False),
        sa.Column("name",        sa.Text(),    nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status",      sa.Text(),    server_default="active"),  # active / archived / paused
        sa.Column("project_meta", sa.Text(),   server_default="{}"),       # JSON: 案件メタ情報
        sa.Column("client_visibility", sa.Text(), server_default="[]"),    # JSON: client に見せるタブ
        sa.Column("design_system_ref", sa.Text()),                          # data/design-systems/<name>
        sa.Column("created_at",  sa.Text(),    server_default=sa.func.current_timestamp()),
        sa.Column("updated_at",  sa.Text(),    server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_workspaces_account", "workspaces", ["account_id"])
    op.create_index("ix_workspaces_status", "workspaces", ["status"])

    # ── workspace_members: workspace 単位のメンバー＋ロール ──
    op.create_table(
        "workspace_members",
        sa.Column("id",                 sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("workspace_id",       sa.Integer(), nullable=False),
        sa.Column("user_id",            sa.Text(),    nullable=False),
        sa.Column("role",               sa.Text(),    server_default="contributor"),  # admin/contributor/viewer/client
        sa.Column("custom_permissions", sa.Text(),    server_default="{}"),            # JSON: 細かい権限
        sa.Column("invited_by",         sa.Text()),
        sa.Column("created_at",         sa.Text(),    server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),
    )
    op.create_index("ix_workspace_members_workspace", "workspace_members", ["workspace_id"])
    op.create_index("ix_workspace_members_user",      "workspace_members", ["user_id"])

    # ── workspace_invitations: 招待トークン管理 ────────
    op.create_table(
        "workspace_invitations",
        sa.Column("id",            sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("workspace_id",  sa.Integer(), nullable=False),
        sa.Column("email",         sa.Text(),    nullable=False),
        sa.Column("role",          sa.Text(),    server_default="contributor"),
        sa.Column("token",         sa.Text(),    nullable=False, unique=True),
        sa.Column("invited_by",    sa.Text()),
        sa.Column("status",        sa.Text(),    server_default="pending"),  # pending / accepted / expired
        sa.Column("expires_at",    sa.Text()),
        sa.Column("created_at",    sa.Text(),    server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_invitations_workspace", "workspace_invitations", ["workspace_id"])
    op.create_index("ix_invitations_token",     "workspace_invitations", ["token"])

    # ── 既存テーブルへ account_id / workspace_id を追加（互換性のため nullable）──
    # SQLite は ALTER TABLE で列追加時に DEFAULT NULL のみ可
    for table in ("ai_employee_config", "knowledge_base"):
        op.add_column(table, sa.Column("account_id", sa.Integer()))

    for table in ("threads", "artifacts", "conversation_log",
                  "conversation_slots", "knowledge_base", "approval_queue"):
        op.add_column(table, sa.Column("workspace_id", sa.Integer()))

    op.create_index("ix_threads_workspace",    "threads",    ["workspace_id"])
    op.create_index("ix_artifacts_workspace",  "artifacts",  ["workspace_id"])

    # ── Phase 1: デフォルト Account/Workspace を seed する用の関数 ──
    # マイグレーション内では INSERT は副作用が大きいので別途 seed スクリプトで実行


def downgrade() -> None:
    # 列削除は SQLite では batch_alter_table が必要・ここではスキップ
    op.drop_index("ix_artifacts_workspace",  table_name="artifacts")
    op.drop_index("ix_threads_workspace",    table_name="threads")
    op.drop_index("ix_invitations_token",    table_name="workspace_invitations")
    op.drop_index("ix_invitations_workspace", table_name="workspace_invitations")
    op.drop_index("ix_workspace_members_user",      table_name="workspace_members")
    op.drop_index("ix_workspace_members_workspace", table_name="workspace_members")
    op.drop_index("ix_workspaces_status",  table_name="workspaces")
    op.drop_index("ix_workspaces_account", table_name="workspaces")
    op.drop_index("ix_account_members_account", table_name="account_members")
    op.drop_index("ix_accounts_owner",          table_name="accounts")
    op.drop_table("workspace_invitations")
    op.drop_table("workspace_members")
    op.drop_table("workspaces")
    op.drop_table("account_members")
    op.drop_table("accounts")
