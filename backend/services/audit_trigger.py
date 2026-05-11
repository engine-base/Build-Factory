"""T-018-01: audit_logs trigger setup helper.

主要テーブルの INSERT/UPDATE/DELETE 時に audit_logs を自動 emit する trigger は
migration 20260513000000_audit_logs_triggers.sql で設置済み.

trigger function は SECURITY DEFINER として:
  - current_setting('bf.actor_user_id') から actor を取得
  - current_setting('bf.workspace_id') から workspace を取得

本 service は app 側のリクエスト境界で session-local GUC を設定する helper を提供.

公開 API:
  - list_audited_tables() -> list[str]    監視対象テーブル
  - audit_event_action(table, op) -> str  期待される action 文字列
  - parse_changed_columns(payload) -> dict UPDATE 時の changed cols 抽出
"""
from __future__ import annotations

import logging
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


class AuditTriggerError(RuntimeError):
    pass


# T-018-01: trigger 監視対象 (migration と一致させる)
AUDITED_TABLES = (
    "workspaces",
    "bf_projects",
    "bf_tasks",
    "skill_definitions",
    "ai_employees",
)
VALID_OPS = ("insert", "update", "delete")
EXCLUDED_TABLES = ("audit_logs",)  # 再帰防止のため絶対設置しない


def list_audited_tables() -> list[str]:
    return list(AUDITED_TABLES)


def audit_event_action(table: str, op: str) -> str:
    """audit_logs.action が trigger により生成される文字列を返す.

    例: ('workspaces', 'update') -> 'workspaces.update'
    """
    if not isinstance(table, str) or not table.strip():
        raise AuditTriggerError("table must not be empty")
    t = table.strip().lower()
    if t in EXCLUDED_TABLES:
        raise AuditTriggerError(
            f"table {t!r} is excluded from audit triggers (recursion guard)"
        )
    if t not in AUDITED_TABLES:
        raise AuditTriggerError(
            f"table {t!r} is not in audited list {AUDITED_TABLES}"
        )
    if not isinstance(op, str):
        raise AuditTriggerError("op must be a string")
    o = op.strip().lower()
    if o not in VALID_OPS:
        raise AuditTriggerError(
            f"op must be one of {VALID_OPS}, got {op!r}"
        )
    return f"{t}.{o}"


def parse_changed_columns(payload: Optional[dict]) -> dict:
    """UPDATE 時の payload から changed columns を取り出す.

    trigger は payload = {"changed": {...}, "before_id": N} を生成する.
    """
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise AuditTriggerError("payload must be a dict")
    changed = payload.get("changed") or {}
    if not isinstance(changed, dict):
        raise AuditTriggerError("payload.changed must be a dict")
    return dict(changed)


def is_audited(table: str) -> bool:
    if not isinstance(table, str):
        return False
    return table.strip().lower() in AUDITED_TABLES


def is_excluded(table: str) -> bool:
    """audit_logs 自身 (or 他の trigger 不要 table) を判定."""
    if not isinstance(table, str):
        return False
    return table.strip().lower() in EXCLUDED_TABLES


# ──────────────────────────────────────────────────────────────────────────
# Static migration verification (test 側で利用)
# ──────────────────────────────────────────────────────────────────────────


def expected_trigger_name(table: str) -> str:
    if not is_audited(table):
        raise AuditTriggerError(f"not an audited table: {table}")
    return f"trg_audit_{table.strip().lower()}"
