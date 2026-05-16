"""T-V3-B-15 / F-010: Sessions backend service.

list / detail / kill / kill-all のビジネスロジックを SessionStore (抽象) 経由で
実装する. 永続化は ClaudeAgentRunner.store (T-S0-08 で実装済) を REUSE する.

公開 API:
  - list_sessions_for_workspace(store, workspace_id, *, status_filter=None)
  - get_session_detail(store, session_id)
  - kill_session(store, session_id, *, actor_user_id=None)
  - kill_all_sessions(store, workspace_id, *, actor_user_id=None)

該当 AC:
  AC-F1  pause (T-V3-B-16 で実装)
  AC-F2  resume 409 (T-V3-B-16 で実装)
  AC-F3  rollback + audit (T-V3-B-16 で実装)
  AC-F4  list 2xx + sessions shape
  AC-F7  detail 2xx + session shape
  AC-F10 kill 2xx + killed_at
  AC-F12 kill-all 2xx + killed_count
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from integrations.claude_agent_runner import SessionRecord, SessionStore


class SessionNotFoundError(LookupError):
    """対象 session が存在しない (404)."""


class SessionAlreadyTerminatedError(RuntimeError):
    """session が既に terminal 状態 (done / cancelled) — kill 不可 (409)."""


class SessionStateConflictError(RuntimeError):
    """session が要求された遷移を許す状態ではない (409).

    例:
      - pause: running 以外を pause しようとした
      - resume: paused / crashed 以外を resume しようとした (AC-F2)
    """


class CheckpointNotFoundError(LookupError):
    """指定された checkpoint_id が存在しない (rollback 時 409 にマップ)."""


# DDL CHECK と一致: running / done / crashed / cancelled / paused
# OpenAPI status filter (running / paused / crashed / completed) は内部で
# "completed" -> "done" にマップする (entities.json の状態名は "done" だが
# UI 側は "completed" を使うため互換のため両受け).
_API_STATUS_TO_DB: dict[str, str] = {
    "running": "running",
    "paused": "paused",
    "crashed": "crashed",
    "completed": "done",
    "done": "done",
    "cancelled": "cancelled",
}


def _map_status_filter(api_status: str) -> str:
    """OpenAPI status filter を DB status 値に正規化."""
    db_status = _API_STATUS_TO_DB.get(api_status)
    if db_status is None:
        raise ValueError(
            f"invalid status filter: {api_status!r} "
            f"(allowed: {tuple(_API_STATUS_TO_DB.keys())})"
        )
    return db_status


def serialize_session(rec: SessionRecord) -> dict:
    """SessionRecord → dict (OpenAPI #Session shape).

    AC-F4 / AC-F7: sessions / session のレスポンス契約.
    """
    return {
        "id": rec.id,
        "sdk_session_id": rec.sdk_session_id or None,
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


# Module-level state for InMemorySessionStore に list / kill_all を追加するための
# helper. 本番 DB では DbSessionStore がオーバーライドする.


async def _list_all_records(store: SessionStore) -> list[SessionRecord]:
    """SessionStore から全 SessionRecord を取り出す.

    InMemorySessionStore は内部 dict を持つので getattr で取得する.
    DbSessionStore は明示的な list メソッドが無いため list_all を別途実装する
    必要がある (本タスクで service 側に分離).
    """
    # InMemorySessionStore は _sessions: dict[int, SessionRecord] を持つ
    sessions_dict = getattr(store, "_sessions", None)
    if sessions_dict is not None:
        return list(sessions_dict.values())

    # DbSessionStore の場合は list_sessions_db を呼ぶ
    list_fn = getattr(store, "list_sessions", None)
    if list_fn is not None:
        result = await list_fn()
        return list(result)

    raise RuntimeError(
        "SessionStore lacks both `_sessions` dict and `list_sessions()` "
        "method — cannot enumerate sessions"
    )


# ─────────────────────────────────────────────────────────────────────────────
# AC-F4: list (workspace scoped + optional status filter)
# ─────────────────────────────────────────────────────────────────────────────


async def list_sessions_for_workspace(
    store: SessionStore,
    workspace_id: int,
    *,
    status_filter: Optional[str] = None,
) -> list[dict]:
    """workspace に属する session の一覧を返す.

    AC-F4 (EVENT-DRIVEN): When GET /api/workspaces/{id}/sessions is called
    with valid inputs by an authorized caller, the system shall return 2xx
    with the contract defined in features.json#F-010 (incl. sessions).

    AC-F6 (UNWANTED): If GET /api/workspaces/{id}/sessions receives a
    request body failing validation, the system shall return 422 with a
    field-level error map. → status_filter が enum 外の場合 ValueError.
    """
    if not isinstance(workspace_id, int) or workspace_id <= 0:
        raise ValueError(f"workspace_id must be > 0, got {workspace_id!r}")

    db_status: Optional[str] = None
    if status_filter is not None:
        db_status = _map_status_filter(status_filter)

    records = await _list_all_records(store)
    out: list[dict] = []
    for rec in records:
        if rec.workspace_id != workspace_id:
            continue
        if db_status is not None and rec.status != db_status:
            continue
        out.append(serialize_session(rec))
    # 開始が新しい順 (started_at desc, fallback to id desc)
    out.sort(
        key=lambda d: (
            d.get("started_at") or 0,
            d.get("id") or 0,
        ),
        reverse=True,
    )
    return out


# ─────────────────────────────────────────────────────────────────────────────
# AC-F7: detail
# ─────────────────────────────────────────────────────────────────────────────


async def get_session_detail(
    store: SessionStore,
    session_id: int,
) -> dict:
    """session detail (+ logs_tail_url) を返す.

    AC-F7 (EVENT-DRIVEN): When GET /api/sessions/{id} is called with valid
    inputs by an authorized caller, the system shall return 2xx with the
    contract defined in features.json#F-010 (incl. session).

    AC-F9 (UNWANTED): invalid session_id → ValueError (-> 422).
    not_found → SessionNotFoundError (-> 404).
    """
    if not isinstance(session_id, int) or session_id <= 0:
        raise ValueError(f"session_id must be > 0, got {session_id!r}")
    rec = await store.get_session(session_id)
    if rec is None:
        raise SessionNotFoundError(f"session not found: {session_id}")
    return {
        "session": serialize_session(rec),
        "logs_tail_url": f"/ws/sessions/{session_id}/log",
    }


# ─────────────────────────────────────────────────────────────────────────────
# AC-F10: kill single session
# ─────────────────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_TERMINAL_DB_STATUSES = frozenset({"done", "cancelled"})


async def kill_session(
    store: SessionStore,
    session_id: int,
    *,
    actor_user_id: Optional[str] = None,
) -> dict:
    """session を kill (status -> cancelled) して killed_at を返す.

    AC-F10 (EVENT-DRIVEN): 2xx + killed_at を返す.
    AC-F11 (UNWANTED): unauthorized → caller 側で 401 を起こす.
    409 (already terminated): SessionAlreadyTerminatedError.
    """
    if not isinstance(session_id, int) or session_id <= 0:
        raise ValueError(f"session_id must be > 0, got {session_id!r}")
    if actor_user_id is not None and (
        not isinstance(actor_user_id, str) or not actor_user_id.strip()
    ):
        raise ValueError("actor_user_id must be non-empty string when provided")

    rec = await store.get_session(session_id)
    if rec is None:
        raise SessionNotFoundError(f"session not found: {session_id}")
    if rec.status in _TERMINAL_DB_STATUSES:
        raise SessionAlreadyTerminatedError(
            f"session {session_id} already terminated (status={rec.status!r})"
        )

    rec.status = "cancelled"
    rec.crash_reason = (
        f"killed by {actor_user_id}" if actor_user_id else "killed via API"
    )
    await store.finalize_session(rec)
    return {"killed_at": _now_iso()}


# ─────────────────────────────────────────────────────────────────────────────
# AC-F12: kill all sessions in a workspace
# ─────────────────────────────────────────────────────────────────────────────


async def kill_all_sessions(
    store: SessionStore,
    workspace_id: int,
    *,
    actor_user_id: Optional[str] = None,
) -> dict:
    """workspace の running / paused / crashed session を全部 kill する.

    AC-F12 (EVENT-DRIVEN): 2xx + killed_count を返す.
    AC-F13 (UNWANTED): unauthorized → caller 側で 401.
    """
    if not isinstance(workspace_id, int) or workspace_id <= 0:
        raise ValueError(f"workspace_id must be > 0, got {workspace_id!r}")
    if actor_user_id is not None and (
        not isinstance(actor_user_id, str) or not actor_user_id.strip()
    ):
        raise ValueError("actor_user_id must be non-empty string when provided")

    records = await _list_all_records(store)
    killed = 0
    for rec in records:
        if rec.workspace_id != workspace_id:
            continue
        if rec.status in _TERMINAL_DB_STATUSES:
            continue
        rec.status = "cancelled"
        rec.crash_reason = (
            f"kill-all by {actor_user_id}"
            if actor_user_id
            else "kill-all via API"
        )
        await store.finalize_session(rec)
        killed += 1

    return {"killed_count": killed}


# ─────────────────────────────────────────────────────────────────────────────
# T-V3-B-16: pause / resume / rollback
# ─────────────────────────────────────────────────────────────────────────────
#
# Checkpoint は SessionRecord.metadata["checkpoints"] に dict として格納する.
#   metadata = {
#       "checkpoints": {
#           "<uuid>": {
#               "checkpoint_id": "<uuid>",
#               "created_at": "<iso>",
#               "status_at_checkpoint": "running",
#               "actor_user_id": "<uid or None>",
#           },
#           ...
#       },
#       "active_checkpoint_id": "<uuid>",  # 直近 pause 時の checkpoint
#   }
#
# rollback は metadata["checkpoints"][checkpoint_id] を読み戻し、session の
# status / crash_reason / resume_choice を復元する.
# ─────────────────────────────────────────────────────────────────────────────


_PAUSABLE_DB_STATUSES = frozenset({"running"})
_RESUMABLE_DB_STATUSES = frozenset({"paused", "crashed"})


def _ensure_checkpoint_store(rec: SessionRecord) -> dict[str, dict]:
    """SessionRecord.metadata["checkpoints"] を必要に応じて初期化して返す."""
    meta = rec.metadata
    cps = meta.get("checkpoints")
    if not isinstance(cps, dict):
        cps = {}
        meta["checkpoints"] = cps
    return cps


async def pause_session(
    store: SessionStore,
    session_id: int,
    *,
    actor_user_id: Optional[str] = None,
) -> dict:
    """running session を pause し checkpoint を作って返す.

    AC-F1 (EVENT-DRIVEN): When POST /api/sessions/{id}/pause is called for a
        running session, the system shall save a checkpoint and transition
        status to 'paused' within 5 seconds.
    AC-F4 (EVENT-DRIVEN): 2xx + paused_at (+ checkpoint_id) を返す.
    409 (state conflict): pause 対象が running ではない場合 → SessionStateConflictError.

    Returns:
        {"paused_at": "<iso>", "checkpoint_id": "<uuid>"}
    """
    if not isinstance(session_id, int) or session_id <= 0:
        raise ValueError(f"session_id must be > 0, got {session_id!r}")
    if actor_user_id is not None and (
        not isinstance(actor_user_id, str) or not actor_user_id.strip()
    ):
        raise ValueError("actor_user_id must be non-empty string when provided")

    rec = await store.get_session(session_id)
    if rec is None:
        raise SessionNotFoundError(f"session not found: {session_id}")
    if rec.status in _TERMINAL_DB_STATUSES:
        raise SessionAlreadyTerminatedError(
            f"session {session_id} already terminated (status={rec.status!r})"
        )
    if rec.status not in _PAUSABLE_DB_STATUSES:
        # AC-F1 由来: running 以外は pause できない (paused → 409)
        raise SessionStateConflictError(
            f"session {session_id} is not pausable (status={rec.status!r}; "
            f"expected one of {sorted(_PAUSABLE_DB_STATUSES)})"
        )

    now_iso = _now_iso()
    checkpoint_id = str(uuid.uuid4())
    cps = _ensure_checkpoint_store(rec)
    cps[checkpoint_id] = {
        "checkpoint_id": checkpoint_id,
        "created_at": now_iso,
        "status_at_checkpoint": rec.status,
        "actor_user_id": actor_user_id,
        "sdk_session_id": rec.sdk_session_id,
    }
    rec.metadata["active_checkpoint_id"] = checkpoint_id

    rec.status = "paused"
    rec.resume_choice = None
    await store.finalize_session(rec)

    return {"paused_at": now_iso, "checkpoint_id": checkpoint_id}


async def resume_session(
    store: SessionStore,
    session_id: int,
    *,
    checkpoint_id: Optional[str] = None,
    actor_user_id: Optional[str] = None,
) -> dict:
    """paused / crashed session を resume (-> running).

    AC-F2 (UNWANTED): If POST /api/sessions/{id}/resume is called for a
        session that is not in paused or crashed state, the system shall
        return 409 → SessionStateConflictError.
    AC-F6 (EVENT-DRIVEN): 2xx + resumed_at.

    Returns:
        {"resumed_at": "<iso>"}
    """
    if not isinstance(session_id, int) or session_id <= 0:
        raise ValueError(f"session_id must be > 0, got {session_id!r}")
    if actor_user_id is not None and (
        not isinstance(actor_user_id, str) or not actor_user_id.strip()
    ):
        raise ValueError("actor_user_id must be non-empty string when provided")
    if checkpoint_id is not None and (
        not isinstance(checkpoint_id, str) or not checkpoint_id.strip()
    ):
        raise ValueError("checkpoint_id must be non-empty string when provided")

    rec = await store.get_session(session_id)
    if rec is None:
        raise SessionNotFoundError(f"session not found: {session_id}")
    if rec.status not in _RESUMABLE_DB_STATUSES:
        # AC-F2 (UNWANTED): paused / crashed 以外 → 409
        raise SessionStateConflictError(
            f"session {session_id} is not resumable (status={rec.status!r}; "
            f"expected one of {sorted(_RESUMABLE_DB_STATUSES)})"
        )

    # checkpoint 指定が存在し、かつ unknown UUID なら 409
    if checkpoint_id is not None:
        cps = _ensure_checkpoint_store(rec)
        if checkpoint_id not in cps:
            raise CheckpointNotFoundError(
                f"checkpoint_id {checkpoint_id!r} not found for session "
                f"{session_id}"
            )
        rec.metadata["active_checkpoint_id"] = checkpoint_id

    now_iso = _now_iso()
    rec.status = "running"
    rec.crash_reason = None
    rec.resume_choice = "from_checkpoint" if checkpoint_id else "rerun_full"
    await store.finalize_session(rec)
    return {"resumed_at": now_iso}


async def rollback_session(
    store: SessionStore,
    session_id: int,
    *,
    checkpoint_id: str,
    actor_user_id: Optional[str] = None,
) -> dict:
    """workspace_admin が指定 checkpoint まで session 状態を巻き戻す.

    AC-F3 (EVENT-DRIVEN): When POST /api/sessions/{id}/rollback is called by
        workspace_admin, the system shall restore the session state to the
        given checkpoint and emit audit log.
    AC-F8: 2xx + rolled_back_at を返す.
    404: session_id 不存在.
    409: checkpoint_id が session 配下に無い (OpenAPI x-bf-error-seeds).

    Returns:
        {"rolled_back_at": "<iso>", "restored_status": "<str>"}
    """
    if not isinstance(session_id, int) or session_id <= 0:
        raise ValueError(f"session_id must be > 0, got {session_id!r}")
    if not isinstance(checkpoint_id, str) or not checkpoint_id.strip():
        raise ValueError("checkpoint_id is required (non-empty string)")
    if actor_user_id is not None and (
        not isinstance(actor_user_id, str) or not actor_user_id.strip()
    ):
        raise ValueError("actor_user_id must be non-empty string when provided")

    rec = await store.get_session(session_id)
    if rec is None:
        raise SessionNotFoundError(f"session not found: {session_id}")

    cps = _ensure_checkpoint_store(rec)
    cp = cps.get(checkpoint_id)
    if cp is None:
        raise CheckpointNotFoundError(
            f"checkpoint_id {checkpoint_id!r} not found for session "
            f"{session_id}"
        )

    now_iso = _now_iso()
    restored_status = str(cp.get("status_at_checkpoint", "running"))
    rec.status = restored_status
    rec.crash_reason = None
    rec.resume_choice = "from_checkpoint"
    rec.metadata["active_checkpoint_id"] = checkpoint_id
    rec.metadata["last_rollback_at"] = now_iso
    rec.metadata["last_rollback_actor"] = actor_user_id
    await store.finalize_session(rec)

    return {
        "rolled_back_at": now_iso,
        "restored_status": restored_status,
    }


__all__ = (
    "SessionNotFoundError",
    "SessionAlreadyTerminatedError",
    "SessionStateConflictError",
    "CheckpointNotFoundError",
    "serialize_session",
    "list_sessions_for_workspace",
    "get_session_detail",
    "kill_session",
    "kill_all_sessions",
    "pause_session",
    "resume_session",
    "rollback_session",
)
