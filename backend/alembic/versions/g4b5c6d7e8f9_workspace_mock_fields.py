"""S-013 mock 適合: workspaces に client_name / due_date / budget_jpy_monthly /
github_repo / slack_channel / phase_gate_mode / redlines を追加.

Revision ID: g4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-05-11

対応 mock: docs/mocks/2026-05-09_v1/workspace/S-013-workspace-settings.html
- 一般タブ      : 案件名 / クライアント / 納期 / 予算上限
- フェーズゲート : strict / guide / free
- レッドライン   : JSON 配列 (禁止ファイル / コマンド / 等)
- 統合          : GitHub リポジトリ / Slack channel
- 予算 / コスト  : monthly budget (Claude API)

これまで `project_meta` JSON カラムに混在していたが、 検索性 / 単体カラム
更新の容易さから個別カラムに切り出す。
"""
from typing import Sequence, Union
from alembic import op


revision: str = "g4b5c6d7e8f9"
down_revision: Union[str, Sequence[str], None] = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # sqlite は ALTER TABLE ADD COLUMN を 1 つずつ実行する必要あり
    op.execute("ALTER TABLE workspaces ADD COLUMN client_name TEXT")
    op.execute("ALTER TABLE workspaces ADD COLUMN due_date TEXT")
    op.execute("ALTER TABLE workspaces ADD COLUMN budget_jpy_monthly INTEGER")
    op.execute("ALTER TABLE workspaces ADD COLUMN github_repo TEXT")
    op.execute("ALTER TABLE workspaces ADD COLUMN slack_channel TEXT")
    op.execute(
        "ALTER TABLE workspaces ADD COLUMN phase_gate_mode TEXT NOT NULL DEFAULT 'guide'"
    )
    op.execute("ALTER TABLE workspaces ADD COLUMN redlines TEXT NOT NULL DEFAULT '[]'")


def downgrade() -> None:
    # sqlite は DROP COLUMN を 3.35+ でサポート、 対象環境による
    for col in (
        "redlines", "phase_gate_mode", "slack_channel",
        "github_repo", "budget_jpy_monthly", "due_date", "client_name",
    ):
        try:
            op.execute(f"ALTER TABLE workspaces DROP COLUMN {col}")
        except Exception:
            pass
