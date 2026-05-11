"""T-010b-01 / F-010b: claude-agent-sdk REST integration (REFACTOR).

既存 `integrations/claude_agent_runner.py` (ClaudeAgentRunner) を REST 経由で利用可能にする
ためのラッパー router. T-S0-08 で実装済みの runner contract は不変 (AC-3 backwards compat).

Endpoint:
  POST /api/agent/sessions                    新規 session 作成 (2s 以内に id 返却)
  GET  /api/agent/sessions/{session_id}       session status 取得
  POST /api/agent/sessions/{session_id}/resume  4-choice resume (from_checkpoint /
                                              rerun_full / manual_fix / cancel)

T-010b-01 AC:
  AC-1 UBIQUITOUS    : claude-agent-sdk 統合 endpoint 公開
  AC-2 EVENT-DRIVEN  : 全 endpoint で 2 秒以内に success or {detail:{code,message}}
                       (run_task は背景タスクへ投げて即時 id 返却)
  AC-3 STATE-DRIVEN  : 既存 ClaudeAgentRunner / SessionRecord contract 不変
  AC-4 UNWANTED      : invalid input / unknown session / 不正 resume choice は 4xx +
                       {detail:{code,message}} かつ persistent state mutate しない
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from integrations.claude_agent_runner import (
    ClaudeAgentRunner,
    SessionRecord,
    VALID_RESUME_CHOICES,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent-runner"])


# ──────────────────────────────────────────────────────────────────────────
# Module-level runner (test では monkeypatch で差し替え可能)
# ──────────────────────────────────────────────────────────────────────────


_runner: Optional[ClaudeAgentRunner] = None


def get_runner() -> ClaudeAgentRunner:
    """singleton runner (test で reset_runner)."""
    global _runner
    if _runner is None:
        _runner = ClaudeAgentRunner()
    return _runner


def reset_runner() -> None:
    """test 用 reset."""
    global _runner
    _runner = None


# ──────────────────────────────────────────────────────────────────────────
# Helpers (AC-2 / AC-4)
# ──────────────────────────────────────────────────────────────────────────


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover — best-effort
        logger.warning("agent audit emit failed: %s -- %s", event_type, e)


def _serialize(rec: SessionRecord) -> dict[str, Any]:
    """SessionRecord → dict (AC-3 backwards compat shape)."""
    return {
        "id": rec.id,
        "sdk_session_id": rec.sdk_session_id,
        "workspace_id": rec.workspace_id,
        "project_id": rec.project_id,
        "bf_task_id": rec.bf_task_id,
        "agent_persona": rec.agent_persona,
        "skill_name": rec.skill_name,
        "prompt": rec.prompt,
        "status": rec.status,
        "resume_choice": rec.resume_choice,
        "crash_reason": rec.crash_reason,
        "started_at": rec.started_at,
        "completed_at": rec.completed_at,
    }


# ──────────────────────────────────────────────────────────────────────────
# AC-1 / AC-2: POST /api/agent/sessions
# ──────────────────────────────────────────────────────────────────────────


class CreateSessionRequest(BaseModel):
    prompt: str = Field(..., description="prompt (空文字 NG)")
    workspace_id: Optional[int] = None
    project_id: Optional[int] = None
    bf_task_id: Optional[int] = None
    agent_persona: Optional[str] = Field(None, description="mary/devon/quinn 等")
    skill_name: Optional[str] = None
    model: str = Field("claude-sonnet-4-6", description="model id")
    sdk_session_id: Optional[str] = Field(None, description="既存 sdk session の resume")
    user_id: Optional[str] = Field(None, description="actor user_id (audit log 用)")
    run_in_background: bool = Field(True, description="True: 即時 id 返却 / False: 完了まで wait")


@router.post("/sessions")
async def create_session(req: CreateSessionRequest) -> dict[str, Any]:
    """AC-1 + AC-2: claude-agent-sdk session を spawn し、2 秒以内に session_id を返す."""
    if not req.prompt or not req.prompt.strip():
        raise _error("agent.invalid_prompt", "prompt must not be empty")
    if req.user_id is not None and not req.user_id.strip():
        raise _error("agent.unauthorized", "user_id must not be empty when provided", status_code=401)
    if req.agent_persona is not None and not req.agent_persona.strip():
        raise _error("agent.invalid_agent_persona", "agent_persona must not be empty when provided")
    if not req.model or not req.model.strip():
        raise _error("agent.invalid_model", "model must not be empty")

    runner = get_runner()

    if req.run_in_background:
        # AC-2: 即時 placeholder record を作成し、SDK 呼び出しは asyncio.create_task で背景
        placeholder = SessionRecord(
            prompt=req.prompt,
            workspace_id=req.workspace_id,
            project_id=req.project_id,
            bf_task_id=req.bf_task_id,
            agent_persona=req.agent_persona,
            skill_name=req.skill_name,
            status="queued",
        )
        placeholder = await runner.store.create_session(placeholder)

        async def _bg():
            try:
                await runner.run_task(
                    prompt=req.prompt,
                    sdk_session_id=req.sdk_session_id,
                    workspace_id=req.workspace_id,
                    project_id=req.project_id,
                    bf_task_id=req.bf_task_id,
                    agent_persona=req.agent_persona,
                    skill_name=req.skill_name,
                    model=req.model,
                )
            except Exception as e:  # pragma: no cover — background task error path
                logger.warning("agent runner background failed: %s", e)

        asyncio.create_task(_bg())
        await _audit(
            "agent.session.queued",
            user_id=req.user_id,
            detail={"session_id": placeholder.id, "agent_persona": req.agent_persona},
        )
        return {"status": "queued", "session": _serialize(placeholder)}

    # synchronous mode (test 用) — 2s 制約は呼び出し側責任
    try:
        rec = await runner.run_task(
            prompt=req.prompt,
            sdk_session_id=req.sdk_session_id,
            workspace_id=req.workspace_id,
            project_id=req.project_id,
            bf_task_id=req.bf_task_id,
            agent_persona=req.agent_persona,
            skill_name=req.skill_name,
            model=req.model,
        )
    except Exception as e:
        raise _error("agent.run_failed", f"runner failed: {e}", status_code=500)

    await _audit(
        "agent.session.completed",
        user_id=req.user_id,
        detail={"session_id": rec.id, "status": rec.status},
    )
    return {"status": rec.status, "session": _serialize(rec)}


# ──────────────────────────────────────────────────────────────────────────
# AC-1 / AC-2 / AC-3: GET /api/agent/sessions/{id}
# ──────────────────────────────────────────────────────────────────────────


@router.get("/sessions/{session_id}")
async def get_session(session_id: int) -> dict[str, Any]:
    """既存 store.get_session を REUSE (AC-3 backwards compat)."""
    if session_id <= 0:
        raise _error("agent.invalid_session_id", "session_id must be > 0")
    runner = get_runner()
    rec = await runner.store.get_session(session_id)
    if rec is None:
        raise _error("agent.session_not_found", f"session {session_id} not found", status_code=404)
    return {"session": _serialize(rec)}


# ──────────────────────────────────────────────────────────────────────────
# AC-1 / AC-2 / AC-3: POST /api/agent/sessions/{id}/resume
# ──────────────────────────────────────────────────────────────────────────


class ResumeRequest(BaseModel):
    choice: str = Field(..., description="from_checkpoint / rerun_full / manual_fix / cancel")
    user_id: Optional[str] = Field(None, description="actor user_id (audit log 用)")


@router.post("/sessions/{session_id}/resume")
async def resume_session(session_id: int, req: ResumeRequest) -> dict[str, Any]:
    """既存 handle_resume を REUSE (AC-3 backwards compat)."""
    if session_id <= 0:
        raise _error("agent.invalid_session_id", "session_id must be > 0")
    if req.choice not in VALID_RESUME_CHOICES:
        raise _error(
            "agent.invalid_resume_choice",
            f"choice must be one of {VALID_RESUME_CHOICES}, got {req.choice!r}",
        )
    if req.user_id is not None and not req.user_id.strip():
        raise _error("agent.unauthorized", "user_id must not be empty when provided", status_code=401)

    runner = get_runner()
    try:
        rec = await runner.handle_resume(session_id, req.choice)
    except LookupError as e:
        raise _error("agent.session_not_found", str(e), status_code=404)
    except ValueError as e:
        raise _error("agent.invalid_resume_choice", str(e))
    except Exception as e:
        raise _error("agent.resume_failed", f"resume failed: {e}", status_code=500)

    await _audit(
        "agent.session.resumed",
        user_id=req.user_id,
        detail={"session_id": session_id, "choice": req.choice, "new_status": rec.status},
    )
    return {"status": rec.status, "choice": req.choice, "session": _serialize(rec)}
