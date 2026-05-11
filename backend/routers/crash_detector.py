"""T-010c-05 / F-010c: crash detection REST endpoint.

Endpoint:
  POST /api/crash-detector/sessions               register
  POST /api/crash-detector/sessions/{id}/heartbeat  heartbeat (with memory)
  POST /api/crash-detector/sessions/{id}/exit       record exit
  GET  /api/crash-detector/sessions/{id}            session status
  GET  /api/crash-detector/sessions                 list
  POST /api/crash-detector/scan                     detect_crashes 実行
  POST /api/crash-detector/sessions/{id}/reset      unregister

AC マッピング:
  AC-1 UBIQUITOUS    : F-010c crash detection 3 観点 (heartbeat/memory/exit) + endpoint
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit emit (crash detected) + state 遷移ルール強制
  AC-4 UNWANTED      : invalid input は 4xx + structured / persistent state mutate しない
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services import crash_detector as cd

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crash-detector", tags=["crash-detector"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("crash-detector audit emit failed: %s -- %s", event_type, e)


class RegisterRequest(BaseModel):
    session_id: int
    heartbeat_timeout: float = Field(cd.DEFAULT_HEARTBEAT_TIMEOUT_SEC, gt=0,
                                       le=cd.MAX_HEARTBEAT_TIMEOUT_SEC)
    memory_limit_mb: int = Field(cd.DEFAULT_MEMORY_LIMIT_MB, gt=0,
                                   le=cd.MAX_MEMORY_LIMIT_MB)
    actor_user_id: Optional[str] = None


class HeartbeatRequest(BaseModel):
    memory_mb: Optional[float] = Field(None, ge=0)
    actor_user_id: Optional[str] = None


class ExitRequest(BaseModel):
    exit_code: int
    actor_user_id: Optional[str] = None


class ResetRequest(BaseModel):
    actor_user_id: Optional[str] = None


class ScanRequest(BaseModel):
    actor_user_id: Optional[str] = None


@router.post("/sessions")
async def register(req: RegisterRequest) -> dict[str, Any]:
    if req.session_id <= 0:
        raise _error("crash.invalid_session_id", "session_id must be > 0")
    if req.actor_user_id is not None and not req.actor_user_id.strip():
        raise _error("crash.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    try:
        watch = cd.get_detector().register_session(
            req.session_id,
            heartbeat_timeout=req.heartbeat_timeout,
            memory_limit_mb=req.memory_limit_mb,
        )
    except cd.CrashDetectorError as e:
        msg = str(e)
        if "already registered" in msg:
            raise _error("crash.already_registered", msg, status_code=409)
        raise _error("crash.invalid", msg)
    await _audit(
        "crash.session.registered",
        user_id=req.actor_user_id,
        detail={
            "session_id": req.session_id,
            "heartbeat_timeout": req.heartbeat_timeout,
            "memory_limit_mb": req.memory_limit_mb,
        },
    )
    return watch.to_dict()


@router.post("/sessions/{session_id}/heartbeat")
async def heartbeat(session_id: int, body: HeartbeatRequest) -> dict[str, Any]:
    if session_id <= 0:
        raise _error("crash.invalid_session_id", "session_id must be > 0")
    if body.actor_user_id is not None and not body.actor_user_id.strip():
        raise _error("crash.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    try:
        watch = cd.get_detector().record_heartbeat(
            session_id, memory_mb=body.memory_mb,
        )
    except cd.CrashDetectorError as e:
        msg = str(e)
        if "not registered" in msg:
            raise _error("crash.session_not_found", msg, status_code=404)
        if "not in 'running'" in msg:
            raise _error("crash.invalid_state", msg, status_code=409)
        raise _error("crash.invalid", msg)
    return watch.to_dict()


@router.post("/sessions/{session_id}/exit")
async def record_exit(session_id: int, body: ExitRequest) -> dict[str, Any]:
    if session_id <= 0:
        raise _error("crash.invalid_session_id", "session_id must be > 0")
    if body.actor_user_id is not None and not body.actor_user_id.strip():
        raise _error("crash.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    try:
        watch = cd.get_detector().record_exit(session_id, body.exit_code)
    except cd.CrashDetectorError as e:
        msg = str(e)
        if "not registered" in msg:
            raise _error("crash.session_not_found", msg, status_code=404)
        raise _error("crash.invalid", msg)
    if body.exit_code != 0:
        await _audit(
            "crash.unexpected_exit",
            user_id=body.actor_user_id,
            detail={"session_id": session_id, "exit_code": body.exit_code},
        )
    return watch.to_dict()


@router.get("/sessions/{session_id}")
async def get_session(session_id: int) -> dict[str, Any]:
    if session_id <= 0:
        raise _error("crash.invalid_session_id", "session_id must be > 0")
    info = cd.get_detector().get_session(session_id)
    if info is None:
        raise _error("crash.session_not_found",
                     f"session not found: {session_id}", status_code=404)
    return info


@router.get("/sessions")
async def list_sessions() -> dict[str, Any]:
    items = cd.get_detector().list_sessions()
    return {"count": len(items), "sessions": items}


@router.post("/scan")
async def scan(req: ScanRequest) -> dict[str, Any]:
    if req.actor_user_id is not None and not req.actor_user_id.strip():
        raise _error("crash.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    reports = cd.get_detector().detect_crashes()
    serialized = [r.to_dict() for r in reports]
    for r in reports:
        await _audit(
            f"crash.{r.reason}",
            user_id=req.actor_user_id,
            detail={"session_id": r.session_id, "detail": r.detail},
        )
    return {"count": len(serialized), "crashes": serialized}


@router.post("/sessions/{session_id}/reset")
async def reset_session(session_id: int, body: ResetRequest) -> dict[str, Any]:
    if session_id <= 0:
        raise _error("crash.invalid_session_id", "session_id must be > 0")
    if body.actor_user_id is not None and not body.actor_user_id.strip():
        raise _error("crash.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    ok = cd.get_detector().reset(session_id)
    if not ok:
        raise _error("crash.session_not_found",
                     f"session not found: {session_id}", status_code=404)
    await _audit(
        "crash.session.reset",
        user_id=body.actor_user_id,
        detail={"session_id": session_id},
    )
    return {"reset": True, "session_id": session_id}
