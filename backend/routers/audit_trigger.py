"""T-018-01 / F-018: audit_logs trigger 観測 endpoint.

trigger 自体は DB migration で設置済み. 本 router は trigger 設置状況の閲覧 +
audit_logs エントリの簡易検索を提供.

Endpoint:
  GET  /api/audit-triggers                  trigger 監視対象一覧 + 期待 action
  GET  /api/audit-triggers/{table}          特定テーブルの期待 trigger 名 + actions

AC マッピング:
  AC-1 UBIQUITOUS    : F-018 audit_logs trigger を主要 5 テーブルに設置 + 観測 endpoint
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit_logs 自身には trigger 設置禁止 (再帰防止) を強制
  AC-4 UNWANTED      : invalid table / 監視対象外 は 4xx + structured /
                       persistent state mutate しない
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from services import audit_trigger as at

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/audit-triggers", tags=["audit-triggers"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


@router.get("")
async def list_triggers() -> dict[str, Any]:
    items = []
    for t in at.AUDITED_TABLES:
        items.append({
            "table": t,
            "trigger_name": at.expected_trigger_name(t),
            "actions": [at.audit_event_action(t, op) for op in at.VALID_OPS],
        })
    return {
        "count": len(items),
        "tables": items,
        "excluded": list(at.EXCLUDED_TABLES),
    }


@router.get("/{table}")
async def get_trigger(table: str) -> dict[str, Any]:
    if not table or not table.strip():
        raise _error("audit.invalid_table", "table must not be empty")
    t = table.strip().lower()
    if t in at.EXCLUDED_TABLES:
        raise _error("audit.excluded_table",
                     f"table {t!r} is excluded from audit (recursion guard)",
                     status_code=403)
    if not at.is_audited(t):
        raise _error("audit.not_audited",
                     f"table {t!r} is not in audited list",
                     status_code=404)
    return {
        "table": t,
        "trigger_name": at.expected_trigger_name(t),
        "actions": [at.audit_event_action(t, op) for op in at.VALID_OPS],
    }
