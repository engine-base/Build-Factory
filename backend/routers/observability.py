"""T-017-02 / F-017: Langfuse SDK 統合 REST endpoint (observability 拡張).

既存 services.observability.py を REUSE する薄い REST ラッパー.
外部クライアント (claude-runner / worker / FE) から trace / span / generation を
HTTP 経由で記録できる.

Endpoint:
  GET  /api/observability/status           Langfuse 接続状態
  POST /api/observability/trace            trace + span + generation を 1 リクエストで記録
  POST /api/observability/shutdown         flush して未送信ログを送る (admin)

T-017-02 AC:
  AC-1 UBIQUITOUS    : F-017 observability endpoint + service が公開
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 observability.py (trace/span/log_generation/observe/shutdown)
                       contract 不変 (backwards compat) + audit emit
  AC-4 UNWANTED      : invalid input / 巨大 payload は 4xx + structured /
                       persistent state mutate しない (Langfuse 未接続は no-op)
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import observability as obs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/observability", tags=["observability"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("observability audit emit failed: %s -- %s", event_type, e)


# size 上限 (Langfuse の payload とのバランス)
MAX_NAME_LEN = 200
MAX_USER_ID_LEN = 200
MAX_SESSION_ID_LEN = 200
MAX_METADATA_KEYS = 50
MAX_PROMPT_LEN = 50_000
MAX_COMPLETION_LEN = 50_000
MAX_MODEL_LEN = 200


class GenerationEntry(BaseModel):
    name: str
    model: str
    prompt: Any
    completion: str
    usage: Optional[dict] = None
    metadata: Optional[dict] = None


class TraceRequest(BaseModel):
    name: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Optional[dict] = None
    spans: list[GenerationEntry] = Field(default_factory=list)
    actor_user_id: Optional[str] = None


class ShutdownRequest(BaseModel):
    actor_user_id: Optional[str] = None


def _validate_name(name: str, field: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise _error(
            f"obs.invalid_{field}",
            f"{field} must not be empty",
        )
    if len(name) > MAX_NAME_LEN:
        raise _error(
            f"obs.invalid_{field}",
            f"{field} must be <= {MAX_NAME_LEN} chars",
        )
    return name.strip()


def _validate_optional_id(value: Optional[str], field: str, max_len: int) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise _error(
            f"obs.invalid_{field}",
            f"{field} must not be empty when provided",
        )
    if len(value) > max_len:
        raise _error(
            f"obs.invalid_{field}",
            f"{field} must be <= {max_len} chars",
        )
    return value.strip()


def _validate_metadata(meta: Optional[dict], field: str = "metadata") -> Optional[dict]:
    if meta is None:
        return None
    if not isinstance(meta, dict):
        raise _error(f"obs.invalid_{field}", f"{field} must be a dict")
    if len(meta) > MAX_METADATA_KEYS:
        raise _error(
            f"obs.invalid_{field}",
            f"{field} must have <= {MAX_METADATA_KEYS} keys",
        )
    return meta


@router.get("/status")
async def status() -> dict[str, Any]:
    return {
        "enabled": obs.is_enabled(),
        "langfuse_host": _safe_getenv("LANGFUSE_HOST", "http://localhost:3000"),
        "public_key_configured": bool(_safe_getenv("LANGFUSE_PUBLIC_KEY")),
        "secret_key_configured": bool(_safe_getenv("LANGFUSE_SECRET_KEY")),
    }


def _safe_getenv(key: str, default: Optional[str] = None) -> Optional[str]:
    import os as _os
    return _os.environ.get(key) or default


@router.post("/trace")
async def record_trace(req: TraceRequest) -> dict[str, Any]:
    """trace + 0..N の generation を 1 リクエストで記録. Langfuse 未接続でも 200 を返す (no-op)."""
    if req.actor_user_id is not None and not req.actor_user_id.strip():
        raise _error("obs.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    trace_name = _validate_name(req.name, "name")
    user_id = _validate_optional_id(req.user_id, "user_id", MAX_USER_ID_LEN)
    session_id = _validate_optional_id(
        req.session_id, "session_id", MAX_SESSION_ID_LEN,
    )
    metadata = _validate_metadata(req.metadata)
    if not isinstance(req.spans, list):
        raise _error("obs.invalid_spans", "spans must be a list")
    if len(req.spans) > 100:
        raise _error("obs.spans_too_many", "spans must be <= 100")
    for i, gen in enumerate(req.spans):
        _validate_name(gen.name, f"spans[{i}].name")
        if not isinstance(gen.model, str) or not gen.model.strip():
            raise _error("obs.invalid_model", f"spans[{i}].model must not be empty")
        if len(gen.model) > MAX_MODEL_LEN:
            raise _error("obs.invalid_model",
                         f"spans[{i}].model must be <= {MAX_MODEL_LEN} chars")
        # prompt は dict / str / list を許容
        if isinstance(gen.prompt, str) and len(gen.prompt) > MAX_PROMPT_LEN:
            raise _error("obs.prompt_too_long",
                         f"spans[{i}].prompt must be <= {MAX_PROMPT_LEN} chars")
        if not isinstance(gen.completion, str):
            raise _error("obs.invalid_completion",
                         f"spans[{i}].completion must be a string")
        if len(gen.completion) > MAX_COMPLETION_LEN:
            raise _error("obs.completion_too_long",
                         f"spans[{i}].completion must be <= {MAX_COMPLETION_LEN} chars")
        _validate_metadata(gen.metadata, f"spans[{i}].metadata")

    # 実 langfuse 呼び出し (未接続なら no-op)
    span_count = 0
    enabled = obs.is_enabled()
    if enabled:
        try:
            with obs.trace(
                trace_name, user_id=user_id, session_id=session_id,
                metadata=metadata or {},
            ) as t:
                for gen in req.spans:
                    obs.log_generation(
                        t, name=gen.name, model=gen.model,
                        prompt=gen.prompt, completion=gen.completion,
                        usage=gen.usage, metadata=gen.metadata or {},
                    )
                    span_count += 1
        except Exception as e:
            # SDK エラーは silent + audit 残す
            logger.warning("observability.trace SDK failure: %s", e)
            enabled = False

    await _audit(
        "observability.trace.recorded",
        user_id=req.actor_user_id,
        detail={
            "name": trace_name,
            "spans": len(req.spans),
            "recorded": enabled,
        },
    )
    return {
        "name": trace_name,
        "user_id": user_id,
        "session_id": session_id,
        "spans": len(req.spans),
        "recorded": enabled,
    }


@router.post("/shutdown")
async def shutdown(req: ShutdownRequest) -> dict[str, Any]:
    if req.actor_user_id is not None and not req.actor_user_id.strip():
        raise _error("obs.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    enabled = obs.is_enabled()
    try:
        obs.shutdown()
    except Exception as e:
        raise _error("obs.shutdown_failed",
                     f"shutdown failed: {e}", status_code=500)
    await _audit(
        "observability.shutdown",
        user_id=req.actor_user_id,
        detail={"was_enabled": enabled},
    )
    return {"flushed": True, "was_enabled": enabled}
