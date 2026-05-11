"""T-003-02: AI 社員召喚 API (REFACTOR)

既存 staff_service (社員 CRUD) と claude_agent_runner (claude-agent-sdk) を統合し、
「社員を名前 / ID で召喚して 1 タスクを実行する」唯一の API を提供する。

ADR-010 で LangGraph を排除済みのため、本サービスは ClaudeAgentRunner を
直接呼び出す (元 ticket title の "LangGraph 統合" は無効化)。

公開 API:
  - summon(employee_id_or_name, prompt, *, workspace_id, user_id) -> dict
"""
from __future__ import annotations

from typing import Any, Optional, Union


def _runner_module():
    """ClaudeAgentRunner を lazy import (テスト環境互換)。"""
    from integrations.claude_agent_runner import ClaudeAgentRunner
    return ClaudeAgentRunner


async def _resolve_employee(employee_id_or_name: Union[int, str]) -> Optional[dict]:
    """ID または name から社員 dict を引く (DB 不在時は None)。"""
    try:
        from services.staff_service import get_employee, get_employee_by_name
    except ImportError:
        return None
    try:
        if isinstance(employee_id_or_name, int):
            return await get_employee(employee_id_or_name)
        # str: 先に name で検索、ダメなら int として再試行
        emp = await get_employee_by_name(employee_id_or_name)
        if emp:
            return emp
        try:
            return await get_employee(int(employee_id_or_name))
        except (ValueError, TypeError):
            return None
    except Exception:
        # DB 接続失敗 / table 不在 → None (= not found 同等)
        return None


async def summon(
    employee_id_or_name: Union[int, str],
    prompt: str,
    *,
    workspace_id: Optional[int] = None,
    user_id: Optional[str] = None,
    model: str = "claude-sonnet-4-6",
    cwd: Optional[str] = None,
) -> dict:
    """AI 社員を召喚して 1 タスクを実行する。

    Returns:
      {
        "ok": bool,
        "session_id": int | None,
        "sdk_session_id": str | None,
        "status": str,            # done / crashed / paused
        "crash_reason": str | None,
        "employee": dict | None,
      }
    """
    emp = await _resolve_employee(employee_id_or_name)
    if not emp:
        return {
            "ok": False,
            "session_id": None,
            "sdk_session_id": None,
            "status": "not_found",
            "crash_reason": f"employee not found: {employee_id_or_name}",
            "employee": None,
        }

    try:
        Runner = _runner_module()
    except ImportError as e:
        return {
            "ok": False,
            "session_id": None,
            "sdk_session_id": None,
            "status": "sdk_unavailable",
            "crash_reason": str(e),
            "employee": emp,
        }

    runner = Runner()
    persona_name = emp.get("persona_name") or emp.get("name") or "secretary"
    skill_name = emp.get("primary_skill")

    record = await runner.run_task(
        prompt=prompt,
        workspace_id=workspace_id,
        agent_persona=persona_name,
        skill_name=skill_name,
        model=model,
        cwd=cwd,
    )

    status = getattr(record, "status", "done") if record else "done"
    return {
        "ok": status in ("done", "running"),
        "session_id": getattr(record, "id", None),
        "sdk_session_id": getattr(record, "sdk_session_id", None) or None,
        "status": status,
        "crash_reason": getattr(record, "crash_reason", None),
        "employee": {
            "id": emp.get("id"),
            "persona_name": persona_name,
            "primary_skill": skill_name,
            "role_level": emp.get("role_level"),
        },
    }
