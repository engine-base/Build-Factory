"""T-V3-B-15 / T-V3-B-16 / F-010: Sessions backend router.

OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml
  T-V3-B-15:
  - GET  /api/workspaces/{id}/sessions          (workspaces.py 経由で別途登録)
  - GET  /api/sessions/{id}
  - POST /api/sessions/{id}/kill
  - POST /api/workspaces/{id}/sessions/kill-all (workspaces.py 経由で別途登録)
  T-V3-B-16:
  - POST /api/sessions/{id}/pause
  - POST /api/sessions/{id}/resume
  - POST /api/sessions/{id}/rollback

Entity:
  - E-024 Session (table: sessions)
  - E-025 SessionLog (table: session_logs, AC-F7 logs_tail_url で参照)

該当 AC (T-V3-B-15 audit MD):
  AC-F4  GET /api/workspaces/{id}/sessions 2xx + sessions
  AC-F5  401 if no auth
  AC-F6  422 if validation failure
  AC-F7  GET /api/sessions/{id} 2xx + session + logs_tail_url
  AC-F8  401 if no auth
  AC-F9  422 if validation failure
  AC-F10 POST /api/sessions/{id}/kill 2xx + killed_at
  AC-F11 401 if no auth
  AC-F12 POST /api/workspaces/{id}/sessions/kill-all 2xx + killed_count
  AC-F13 401 if no auth

該当 AC (T-V3-B-16 audit MD):
  AC-F1 EVENT-DRIVEN: pause → status=paused + checkpoint within 5 s
  AC-F2 UNWANTED   : resume not in paused/crashed → 409
  AC-F3 EVENT-DRIVEN: rollback (workspace_admin) → restore + audit log
  AC-F4 EVENT-DRIVEN: pause 2xx + paused_at
  AC-F5 UNWANTED   : pause 401
  AC-F6 EVENT-DRIVEN: resume 2xx + resumed_at
  AC-F7 UNWANTED   : resume 401
  AC-F8 EVENT-DRIVEN: rollback 2xx + rolled_back_at
  AC-F9 UNWANTED   : rollback 401
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Body, Header, HTTPException, Query

from schemas.sessions import (
    RollbackRequest,
    VALID_SESSION_STATUS_FILTER,
)
from services import sessions_v3

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/sessions", tags=["sessions"])


# ─────────────────────────────────────────────────────────────────────────────
# helpers (error contract + audit emit / auth gate)
# ─────────────────────────────────────────────────────────────────────────────


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover — best-effort
        logger.warning("sessions audit emit failed: %s -- %s", event_type, e)


def _get_runner_store():
    """agent_runner singleton 経由で SessionStore を解決する.

    test では monkeypatch で runner._store を InMemorySessionStore に差し替え可能.
    """
    from routers import agent_runner as ar
    return ar.get_runner().store


def _require_auth(authorization: Optional[str]) -> str:
    """Bearer auth トークン検証 (AC-F5 / AC-F8 / AC-F11 / AC-F13).

    本番では Supabase JWT を検証するが、本タスクの範囲では「Bearer + 非空」を
    最低限の境界条件として強制する. JWT 完全検証は F-001 (T-V3-B-01) が担当.
    """
    if not authorization or not authorization.strip():
        raise _error(
            "sessions.unauthorized",
            "missing Authorization header",
            status_code=401,
        )
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise _error(
            "sessions.unauthorized",
            "invalid Authorization header (expected `Bearer <token>`)",
            status_code=401,
        )
    return parts[1].strip()


# ─────────────────────────────────────────────────────────────────────────────
# AC-F7 / AC-F8 / AC-F9: GET /api/sessions/{id}
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/{session_id}")
async def get_session_detail_endpoint(
    session_id: int,
    authorization: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    """session の詳細 + logs_tail_url を返す (AC-F7)."""
    _require_auth(authorization)  # AC-F8
    if session_id <= 0:
        # AC-F9 (UNWANTED): validation → 422
        raise _error(
            "sessions.invalid_session_id",
            "session_id must be > 0",
            status_code=422,
        )
    store = _get_runner_store()
    try:
        return await sessions_v3.get_session_detail(store, session_id)
    except sessions_v3.SessionNotFoundError as e:
        raise _error("sessions.not_found", str(e), status_code=404)
    except ValueError as e:
        raise _error("sessions.invalid", str(e), status_code=422)


# ─────────────────────────────────────────────────────────────────────────────
# AC-F10 / AC-F11: POST /api/sessions/{id}/kill
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/{session_id}/kill")
async def kill_session_endpoint(
    session_id: int,
    authorization: Optional[str] = Header(default=None),
    actor_user_id: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    """session を kill (status -> cancelled) して killed_at を返す (AC-F10)."""
    _require_auth(authorization)  # AC-F11
    if session_id <= 0:
        raise _error(
            "sessions.invalid_session_id",
            "session_id must be > 0",
            status_code=422,
        )
    store = _get_runner_store()
    try:
        result = await sessions_v3.kill_session(
            store, session_id, actor_user_id=actor_user_id,
        )
    except sessions_v3.SessionNotFoundError as e:
        raise _error("sessions.not_found", str(e), status_code=404)
    except sessions_v3.SessionAlreadyTerminatedError as e:
        raise _error("sessions.already_terminated", str(e), status_code=409)
    except ValueError as e:
        raise _error("sessions.invalid", str(e), status_code=422)

    await _audit(
        "sessions.killed",
        user_id=actor_user_id,
        detail={
            "session_id": session_id,
            "killed_at": result["killed_at"],
        },
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# AC-F4 / AC-F5 / AC-F6: GET /api/workspaces/{id}/sessions
# ─────────────────────────────────────────────────────────────────────────────
#
# OpenAPI implementation_path は backend/routers/workspaces.py を指す.
# workspaces.py は既に存在し巨大なため、本ファイルから sub-router として
# `/api/workspaces` 配下の関連 endpoint を登録する.
# ─────────────────────────────────────────────────────────────────────────────


workspace_sessions_router = APIRouter(
    prefix="/api/workspaces", tags=["sessions"],
)


@workspace_sessions_router.get("/{workspace_id}/sessions")
async def list_workspace_sessions_endpoint(
    workspace_id: int,
    status: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    """workspace 配下の session 一覧を返す (AC-F4)."""
    _require_auth(authorization)  # AC-F5
    if workspace_id <= 0:
        raise _error(
            "sessions.invalid_workspace_id",
            "workspace_id must be > 0",
            status_code=422,
        )
    if status is not None and status not in VALID_SESSION_STATUS_FILTER:
        # AC-F6 (UNWANTED): validation → 422
        raise _error(
            "sessions.invalid_status_filter",
            (
                f"status must be one of {VALID_SESSION_STATUS_FILTER}, "
                f"got {status!r}"
            ),
            status_code=422,
        )
    store = _get_runner_store()
    try:
        sessions = await sessions_v3.list_sessions_for_workspace(
            store, workspace_id, status_filter=status,
        )
    except ValueError as e:
        raise _error("sessions.invalid", str(e), status_code=422)
    return {"sessions": sessions}


@workspace_sessions_router.post("/{workspace_id}/sessions/kill-all")
async def kill_all_workspace_sessions_endpoint(
    workspace_id: int,
    authorization: Optional[str] = Header(default=None),
    actor_user_id: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    """workspace 内の active session を全 kill し killed_count を返す (AC-F12)."""
    _require_auth(authorization)  # AC-F13
    if workspace_id <= 0:
        raise _error(
            "sessions.invalid_workspace_id",
            "workspace_id must be > 0",
            status_code=422,
        )
    store = _get_runner_store()
    try:
        result = await sessions_v3.kill_all_sessions(
            store, workspace_id, actor_user_id=actor_user_id,
        )
    except ValueError as e:
        raise _error("sessions.invalid", str(e), status_code=422)

    await _audit(
        "sessions.kill_all",
        user_id=actor_user_id,
        detail={
            "workspace_id": workspace_id,
            "killed_count": result["killed_count"],
        },
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# T-V3-B-16: POST /api/sessions/{id}/pause
# AC-F1 EVENT / AC-F4 EVENT / AC-F5 UNWANTED
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/{session_id}/pause")
async def pause_session_endpoint(
    session_id: int,
    authorization: Optional[str] = Header(default=None),
    actor_user_id: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    """running session を pause し checkpoint を返す.

    AC-F1: 5s 以内に checkpoint 保存 + status='paused' 遷移.
    AC-F4: 2xx + paused_at + checkpoint_id (OpenAPI contract).
    AC-F5: auth なし → 401.
    """
    _require_auth(authorization)  # AC-F5
    if session_id <= 0:
        raise _error(
            "sessions.invalid_session_id",
            "session_id must be > 0",
            status_code=422,
        )
    store = _get_runner_store()
    try:
        result = await sessions_v3.pause_session(
            store, session_id, actor_user_id=actor_user_id,
        )
    except sessions_v3.SessionNotFoundError as e:
        raise _error("sessions.not_found", str(e), status_code=404)
    except sessions_v3.SessionAlreadyTerminatedError as e:
        raise _error("sessions.already_terminated", str(e), status_code=409)
    except sessions_v3.SessionStateConflictError as e:
        # OpenAPI: 409 if session not running (pause)
        raise _error("sessions.not_pausable", str(e), status_code=409)
    except ValueError as e:
        raise _error("sessions.invalid", str(e), status_code=422)

    await _audit(
        "sessions.paused",
        user_id=actor_user_id,
        detail={
            "session_id": session_id,
            "paused_at": result["paused_at"],
            "checkpoint_id": result["checkpoint_id"],
        },
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# T-V3-B-16: POST /api/sessions/{id}/resume
# AC-F2 UNWANTED / AC-F6 EVENT / AC-F7 UNWANTED
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/{session_id}/resume")
async def resume_session_endpoint(
    session_id: int,
    authorization: Optional[str] = Header(default=None),
    actor_user_id: Optional[str] = Query(default=None),
    body: Optional[dict[str, Any]] = Body(default=None),
) -> dict[str, Any]:
    """paused / crashed session を resume → status=running.

    AC-F2 UNWANTED: paused / crashed 以外 → 409.
    AC-F6: 2xx + resumed_at.
    AC-F7: auth なし → 401.
    """
    _require_auth(authorization)  # AC-F7
    if session_id <= 0:
        raise _error(
            "sessions.invalid_session_id",
            "session_id must be > 0",
            status_code=422,
        )
    # body は optional. checkpoint_id 指定なら from_checkpoint resume.
    checkpoint_id: Optional[str] = None
    if body:
        raw_cp = body.get("checkpoint_id")
        if raw_cp is not None:
            if not isinstance(raw_cp, str) or not raw_cp.strip():
                raise _error(
                    "sessions.invalid",
                    "checkpoint_id must be non-empty string",
                    status_code=422,
                )
            checkpoint_id = raw_cp.strip()

    store = _get_runner_store()
    try:
        result = await sessions_v3.resume_session(
            store,
            session_id,
            checkpoint_id=checkpoint_id,
            actor_user_id=actor_user_id,
        )
    except sessions_v3.SessionNotFoundError as e:
        raise _error("sessions.not_found", str(e), status_code=404)
    except sessions_v3.SessionStateConflictError as e:
        # AC-F2: paused / crashed 以外 → 409
        raise _error("sessions.not_resumable", str(e), status_code=409)
    except sessions_v3.CheckpointNotFoundError as e:
        raise _error("sessions.checkpoint_not_found", str(e), status_code=409)
    except ValueError as e:
        raise _error("sessions.invalid", str(e), status_code=422)

    await _audit(
        "sessions.resumed",
        user_id=actor_user_id,
        detail={
            "session_id": session_id,
            "resumed_at": result["resumed_at"],
            "checkpoint_id": checkpoint_id,
        },
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# T-V3-B-16: POST /api/sessions/{id}/rollback
# AC-F3 EVENT / AC-F8 EVENT / AC-F9 UNWANTED
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/{session_id}/rollback")
async def rollback_session_endpoint(
    session_id: int,
    body: RollbackRequest,
    authorization: Optional[str] = Header(default=None),
    actor_user_id: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    """指定 checkpoint まで session 状態を巻き戻す (workspace_admin).

    AC-F3: workspace_admin による rollback + audit log emit.
    AC-F8: 2xx + rolled_back_at.
    AC-F9: auth なし → 401.

    NOTE: workspace_admin role の検証は F-001 (auth middleware) が担当.
    本タスクの範囲では bearer token 必須 + audit emit までを保証する.
    """
    _require_auth(authorization)  # AC-F9
    if session_id <= 0:
        raise _error(
            "sessions.invalid_session_id",
            "session_id must be > 0",
            status_code=422,
        )

    cp_id = (body.checkpoint_id or "").strip()
    if not cp_id:
        raise _error(
            "sessions.invalid",
            "checkpoint_id is required (non-empty string)",
            status_code=422,
        )

    store = _get_runner_store()
    try:
        result = await sessions_v3.rollback_session(
            store,
            session_id,
            checkpoint_id=cp_id,
            actor_user_id=actor_user_id,
        )
    except sessions_v3.SessionNotFoundError as e:
        raise _error("sessions.not_found", str(e), status_code=404)
    except sessions_v3.CheckpointNotFoundError as e:
        # OpenAPI x-bf-error-seeds: 409 if checkpoint not found
        raise _error("sessions.checkpoint_not_found", str(e), status_code=409)
    except ValueError as e:
        raise _error("sessions.invalid", str(e), status_code=422)

    # AC-F3: rollback は必ず audit log を残す
    await _audit(
        "sessions.rolled_back",
        user_id=actor_user_id,
        detail={
            "session_id": session_id,
            "checkpoint_id": cp_id,
            "rolled_back_at": result["rolled_back_at"],
            "restored_status": result.get("restored_status"),
        },
    )
    return result


__all__ = ("router", "workspace_sessions_router")
