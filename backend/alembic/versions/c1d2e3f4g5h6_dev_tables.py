"""dev-specific tables: repos / pull_requests / reviews

Revision ID: c1d2e3f4g5h6
Revises: b1c2d3e4f5a6
Create Date: 2026-05-01 22:00:00.000000

開発フロー特化テーブル:
- repos              リポジトリ登録（GitHub 連携）
- pull_requests      PR 追跡
- reviews            レビュー記録（リン AI の壁打ち履歴）

projects と tasks は既に company-dashboard 由来でテーブル存在するため、
ここでは作らない（流用）。
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'c1d2e3f4g5h6'
down_revision: Union[str, Sequence[str], None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "repos",
        sa.Column("id",                sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("workspace_id",      sa.Integer()),
        sa.Column("name",              sa.Text(), nullable=False),
        sa.Column("github_full_name",  sa.Text()),
        sa.Column("local_path",        sa.Text()),
        sa.Column("default_branch",    sa.Text(), server_default="main"),
        sa.Column("created_at",        sa.Text(), server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_repos_workspace", "repos", ["workspace_id"])

    op.create_table(
        "pull_requests",
        sa.Column("id",                sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("repo_id",           sa.Integer(), nullable=False),
        sa.Column("number",            sa.Integer(), nullable=False),
        sa.Column("title",             sa.Text(), nullable=False),
        sa.Column("author",            sa.Text()),
        sa.Column("status",            sa.Text()),
        sa.Column("head_branch",       sa.Text()),
        sa.Column("base_branch",       sa.Text()),
        sa.Column("url",               sa.Text()),
        sa.Column("ai_review_status",  sa.Text()),
        sa.Column("created_at",        sa.Text(), server_default=sa.func.current_timestamp()),
        sa.Column("updated_at",        sa.Text(), server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_pr_repo",    "pull_requests", ["repo_id"])
    op.create_index("ix_pr_status",  "pull_requests", ["status"])

    op.create_table(
        "reviews",
        sa.Column("id",                  sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("pr_id",               sa.Integer()),
        sa.Column("task_id",             sa.Integer()),
        sa.Column("workspace_id",        sa.Integer()),
        sa.Column("reviewer_employee_id", sa.Integer()),
        sa.Column("verdict",             sa.Text()),  # pending/approve/changes_requested/needs_human_escalation/failed
        sa.Column("summary",             sa.Text()),
        sa.Column("findings_json",       sa.Text(), server_default="[]"),
        sa.Column("created_at",          sa.Text(), server_default=sa.func.current_timestamp()),
        sa.Column("updated_at",          sa.Text(), server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_reviews_workspace", "reviews", ["workspace_id"])
    op.create_index("ix_reviews_verdict",   "reviews", ["verdict"])


def downgrade() -> None:
    op.drop_index("ix_reviews_verdict",   table_name="reviews")
    op.drop_index("ix_reviews_workspace", table_name="reviews")
    op.drop_table("reviews")
    op.drop_index("ix_pr_status", table_name="pull_requests")
    op.drop_index("ix_pr_repo",   table_name="pull_requests")
    op.drop_table("pull_requests")
    op.drop_index("ix_repos_workspace", table_name="repos")
    op.drop_table("repos")
