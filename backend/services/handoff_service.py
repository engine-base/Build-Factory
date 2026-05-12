"""T-M27-03: Agent / Role Selector + handoff (SDK Task tool activation + ai_employees lookup wrapper).

M-27 Intent Router の handoff 段 (mary -> devon -> quinn 等 AI ペルソナ間の引き継ぎ).

## ADR-010 整合 (REUSE 必須)

ADR-010 では handoff (Subagent / Task tool) は **claude-agent-sdk の内蔵機能**
として明示されている. アプリケーションコードで再実装することを禁じる
(tickets.json T-M27-03 §UNWANTED).

本 module は:
  1. ai_employee_store から target persona を lookup
  2. claude-agent-sdk Task tool を呼ぶ thin wrapper を提供 (register_handoff_backend
     経由で差替可能)
  3. m27.handoff audit_logs event を emit

を行うだけの軽量 wrapper. 自前 routing / orchestration / message bus 機能は
**実装しない** (ADR-010 §UNWANTED).

## SDK 未インストール期の挙動 (Phase 1 stub)

T-S0-08 (claude-agent-sdk runner 基盤) マージ前は SDK が利用不可なため、
backend hook 未登録時は **scheduled status を返す stub** として動作:

  status="scheduled"  : audit emit のみ. 実際の SDK Task tool 呼出は
                        T-S0-08 / T-AI-* で SDK 接続後.
  status="dispatched" : register_handoff_backend で SDK backend 登録済の時.

## Spec gap closure (PR #128 G1-G6 / PR #129 G7-G10 / PR #130 G11-G14 /
                     PR #131 lint UNWANTED / T-M27-02 G18-G21 と同じ精神 / G22-G25)

- **G22** SDK Task tool backend hook : register_handoff_backend(callable)
       で T-S0-08 マージ後の SDK Task tool 差替点を確保.
- **G23** Phase 1 stub mode          : backend 未登録時は scheduled status を
       返し audit emit のみ. T-S0-08 マージ前でも本 module は動作・テスト可能.
- **G24** ai_employee_store symbol 不変 : get_persona_by_key / list_employees の
       symbol surface 不変保証. cross-module assert.
- **G25** audit emit 必須             : handoff invoke 時に必ず m27.handoff
       audit_logs event を emit. emit 失敗時は handoff 自体を fail させる
       (silent failure 防止).
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class HandoffError(RuntimeError):
    """Handoff service の入力 / 不変条件違反 (router 層で 4xx 変換)."""


# ──────────────────────────────────────────────────────────────────────
# 制約定数
# ──────────────────────────────────────────────────────────────────────

MAX_MESSAGE_CHARS = 10_000
MAX_CONTEXT_CHARS = 50_000
MAX_PERSONA_KEY_LEN = 100
MAX_ACTOR_USER_ID_LEN = 200
MAX_SESSION_ID_LEN = 200

VALID_STATUSES = ("scheduled", "dispatched", "failed")


# ──────────────────────────────────────────────────────────────────────
# Validation (AC-4 UNWANTED)
# ──────────────────────────────────────────────────────────────────────


def _validate_persona_key(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HandoffError(f"{field_name} must not be empty")
    s = value.strip()
    if len(s) > MAX_PERSONA_KEY_LEN:
        raise HandoffError(
            f"{field_name} must be <= {MAX_PERSONA_KEY_LEN} chars"
        )
    # persona_key は ai_employee_store と整合: alnum + _ -
    if not all(c.isalnum() or c in "-_" for c in s):
        raise HandoffError(
            f"{field_name} must contain only alphanumeric, '-', '_'"
        )
    return s


def _validate_message(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HandoffError("message must not be empty")
    s = value.strip()
    if len(s) > MAX_MESSAGE_CHARS:
        raise HandoffError(f"message must be <= {MAX_MESSAGE_CHARS} chars")
    return s


def _validate_context(value: Any) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise HandoffError("context must be a dict or null")
    # 全体サイズ check (粗い概算)
    try:
        import json
        if len(json.dumps(value)) > MAX_CONTEXT_CHARS:
            raise HandoffError(
                f"context serialized must be <= {MAX_CONTEXT_CHARS} chars"
            )
    except (TypeError, ValueError):
        raise HandoffError("context must be JSON-serializable")
    return value


def _validate_session_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise HandoffError("session_id must be string or null")
    s = value.strip()
    if not s:
        raise HandoffError("session_id must not be empty when provided")
    if len(s) > MAX_SESSION_ID_LEN:
        raise HandoffError(
            f"session_id must be <= {MAX_SESSION_ID_LEN} chars"
        )
    return s


def _validate_actor_user_id(actor: Optional[str]) -> Optional[str]:
    if actor is None:
        return None
    if not isinstance(actor, str):
        raise HandoffError("actor_user_id must be string or null")
    s = actor.strip()
    if not s:
        raise HandoffError(
            "actor_user_id must not be empty when provided"
        )
    if len(s) > MAX_ACTOR_USER_ID_LEN:
        raise HandoffError(
            f"actor_user_id must be <= {MAX_ACTOR_USER_ID_LEN} chars"
        )
    return s


# ──────────────────────────────────────────────────────────────────────
# G22: SDK Task tool backend hook (T-S0-08 マージ後の差替点)
# ──────────────────────────────────────────────────────────────────────

HandoffBackend = Callable[..., dict]
"""backend(*, source, target, message, session_id, context) -> dict.

Phase 2 (T-S0-08 後) では claude-agent-sdk の Task tool を呼ぶ implementation を
register_handoff_backend で差し込む. 戻り dict には少なくとも
  {"status": "dispatched", "task_id": "...", "...": ...}
を含むこと.
"""

_HANDOFF_BACKEND: Optional[HandoffBackend] = None


def register_handoff_backend(backend: Optional[HandoffBackend]) -> None:
    """G22: claude-agent-sdk Task tool 差替点.

    backend が callable でない場合 raise. None で clear.
    例外 / 不正出力時は本 module の Phase 1 stub に fallback (G23).
    """
    global _HANDOFF_BACKEND
    if backend is not None and not callable(backend):
        raise HandoffError("handoff backend must be callable or None")
    _HANDOFF_BACKEND = backend


def get_handoff_backend() -> Optional[HandoffBackend]:
    return _HANDOFF_BACKEND


def _validate_backend_output(out: object) -> dict:
    """backend 戻り dict の不変条件確認. 不正なら raise (caller が fallback)."""
    if not isinstance(out, dict):
        raise HandoffError("backend must return a dict")
    status = out.get("status")
    if status not in VALID_STATUSES:
        raise HandoffError(
            f"backend output status must be one of {VALID_STATUSES}, got {status!r}"
        )
    return out


# ──────────────────────────────────────────────────────────────────────
# G24: ai_employee_store thin lookup (symbol 不変 + Phase 2 でも互換維持)
# ──────────────────────────────────────────────────────────────────────


def _lookup_persona(persona_key: str) -> Optional[dict]:
    """ai_employee_store.get_persona_by_key の thin wrapper.

    既存 store symbol surface を維持 (G24). 不正 key は store layer の
    AIEmployeeError として伝播するため caller で catch.
    """
    from services.ai_employee_store import get_store, AIEmployeeError
    store = get_store()
    try:
        persona = store.get_persona_by_key(persona_key)
    except AIEmployeeError as e:
        raise HandoffError(f"persona lookup failed: {e}")
    if persona is None:
        return None
    return persona.to_dict()


def list_handoff_targets(workspace_id: Optional[int] = None) -> list[dict]:
    """利用可能な target persona (employee 経由) を返す read view.

    workspace_id=None で全 workspace の active employee + そのペルソナを返す.
    audit emit しない (read-only).
    """
    from services.ai_employee_store import get_store
    store = get_store()
    employees = store.list_employees(workspace_id=workspace_id, include_inactive=False)
    out: list[dict] = []
    for emp in employees:
        persona = (
            store.get_persona(emp.persona_id) if emp.persona_id else None
        )
        out.append({
            "employee_id": emp.id,
            "employee_key": emp.employee_key,
            "display_name": emp.display_name,
            "role_level": emp.role_level,
            "persona_key": persona.persona_key if persona else None,
            "specialty": persona.specialty if persona else None,
        })
    return out


# ──────────────────────────────────────────────────────────────────────
# G25: audit emit (必須 / 失敗時 raise)
# ──────────────────────────────────────────────────────────────────────


async def _emit_handoff_audit(
    *,
    event_type: str,
    user_id: Optional[str],
    session_id: Optional[str],
    detail: dict,
) -> None:
    """m27.handoff event を audit_logs に emit. 失敗時は raise."""
    from services.memory_service import emit_event
    await emit_event(
        event_type,
        session_id=session_id,
        user_id=user_id,
        detail=detail,
    )


# ──────────────────────────────────────────────────────────────────────
# 公開 API: request_handoff (entry point)
# ──────────────────────────────────────────────────────────────────────


async def request_handoff(
    *,
    source_persona: str,
    target_persona: str,
    message: str,
    session_id: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    context: Optional[dict] = None,
    use_backend: bool = True,
) -> dict:
    """source persona から target persona への handoff を要求する.

    Returns:
      {
        "status": "scheduled" | "dispatched",
        "source_persona": str,
        "target_persona": str,
        "target_persona_resolved": dict|None,  # ai_employee_store lookup result
        "session_id": str|None,
        "message_preview": str,
        "config": {backend_used: bool, had_context: bool, had_session: bool},
        "meta": {latency_ms: float, dispatched_at: float},
        "backend_result": dict|None,  # backend が返した詳細 (dispatched 時のみ)
      }

    AC-4: invalid input → raise HandoffError. persistent state は audit_logs
          のみ書き込み (handoff request 自体は SDK 任せ).
    G22: register 済 backend があれば優先 (use_backend=True 時).
    G23: backend 未登録 / 例外 / 不正出力時は scheduled status を返す Phase 1
         stub に fallback.
    G24: ai_employee_store からの persona lookup を必須化 (不明 persona は
         HandoffError).
    G25: audit emit を必ず実行. emit 失敗時は HandoffError (silent failure 防止).
    """
    source = _validate_persona_key(source_persona, field_name="source_persona")
    target = _validate_persona_key(target_persona, field_name="target_persona")
    msg = _validate_message(message)
    sid = _validate_session_id(session_id)
    actor = _validate_actor_user_id(actor_user_id)
    ctx = _validate_context(context)
    if not isinstance(use_backend, bool):
        raise HandoffError("use_backend must be bool")
    if source == target:
        raise HandoffError("source_persona and target_persona must differ")

    # G24: target persona lookup (source は手前で classify 済み想定なので check しない)
    target_resolved = _lookup_persona(target)
    if target_resolved is None:
        raise HandoffError(f"target_persona not found in ai_employee_store: {target}")

    t0 = time.time()
    backend_used = False
    backend_result: Optional[dict] = None
    status = "scheduled"

    # G22: backend 優先 (失敗時 G23 fallback)
    if use_backend and _HANDOFF_BACKEND is not None:
        try:
            raw = _HANDOFF_BACKEND(
                source=source,
                target=target,
                message=msg,
                session_id=sid,
                context=ctx,
            )
            if asyncio.iscoroutine(raw):
                raw = await raw
            backend_result = _validate_backend_output(raw)
            backend_used = True
            status = backend_result.get("status", "dispatched")
        except Exception as e:
            logger.warning(
                "handoff backend failed, falling back to Phase 1 stub: %s", e,
            )
            backend_result = None
            backend_used = False
            status = "scheduled"

    elapsed_ms = (time.time() - t0) * 1000.0
    dispatched_at = time.time()

    # G25: audit emit 必須
    audit_detail = {
        "source_persona": source,
        "target_persona": target,
        "target_persona_id": target_resolved["id"],
        "status": status,
        "backend_used": backend_used,
        "session_id": sid,
        "had_context": bool(ctx),
        "message_chars": len(msg),
        "latency_ms": round(elapsed_ms, 2),
    }
    await _emit_handoff_audit(
        event_type="m27.handoff",
        user_id=actor,
        session_id=sid,
        detail=audit_detail,
    )

    return {
        "status": status,
        "source_persona": source,
        "target_persona": target,
        "target_persona_resolved": target_resolved,
        "session_id": sid,
        "message_preview": msg[:80],
        "config": {
            "backend_used": backend_used,
            "had_context": bool(ctx),
            "had_session": sid is not None,
        },
        "meta": {
            "latency_ms": round(elapsed_ms, 2),
            "dispatched_at": dispatched_at,
        },
        "backend_result": backend_result,
    }
