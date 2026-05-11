"""T-010c-04 / F-010c: circuit breaker REST endpoint.

Endpoint:
  POST /api/circuit-breaker/{target_key}/success    record success
  POST /api/circuit-breaker/{target_key}/failure    record failure (auto-block if N 連続)
  GET  /api/circuit-breaker/{target_key}            status
  GET  /api/circuit-breaker/{target_key}/allow      call 可否
  POST /api/circuit-breaker/{target_key}/reset      手動 reset
  GET  /api/circuit-breaker                         list all
  POST /api/circuit-breaker/configure               threshold / recover 変更

AC マッピング:
  AC-1 UBIQUITOUS    : F-010c circuit breaker endpoint + service
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit emit (open/recover/reset) + 状態遷移ルール強制
  AC-4 UNWANTED      : invalid input は 4xx + structured / persistent state mutate しない
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import circuit_breaker as cb

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/circuit-breaker", tags=["circuit-breaker"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("circuit-breaker audit emit failed: %s -- %s", event_type, e)


def _validate_key(target_key: str) -> str:
    if not target_key or not target_key.strip():
        raise _error("circuit.invalid_target_key", "target_key must not be empty")
    if len(target_key) > 200:
        raise _error("circuit.invalid_target_key", "target_key must be <= 200 chars")
    return target_key.strip()


class EventRequest(BaseModel):
    actor_user_id: Optional[str] = None


class ConfigureRequest(BaseModel):
    failure_threshold: int = Field(..., ge=1, le=1000)
    recover_seconds: float = Field(..., gt=0, le=cb.MAX_RECOVER_SECONDS)
    actor_user_id: Optional[str] = None


@router.get("")
async def list_breakers() -> dict[str, Any]:
    items = cb.get_registry().list_breakers()
    return {"count": len(items), "breakers": items}


@router.get("/{target_key}")
async def status(target_key: str) -> dict[str, Any]:
    k = _validate_key(target_key)
    return cb.get_registry().status(k)


@router.get("/{target_key}/allow")
async def allow(target_key: str) -> dict[str, Any]:
    k = _validate_key(target_key)
    return {"target_key": k, "allowed": cb.get_registry().allow(k)}


@router.post("/{target_key}/success")
async def record_success(target_key: str, body: EventRequest) -> dict[str, Any]:
    k = _validate_key(target_key)
    if body.actor_user_id is not None and not body.actor_user_id.strip():
        raise _error("circuit.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    try:
        state = cb.get_registry().record_success(k)
    except cb.CircuitBreakerError as e:
        raise _error("circuit.invalid", str(e))
    await _audit(
        "circuit.success",
        user_id=body.actor_user_id,
        detail={"target_key": k, "state": state.state},
    )
    return state.to_dict()


@router.post("/{target_key}/failure")
async def record_failure(target_key: str, body: EventRequest) -> dict[str, Any]:
    k = _validate_key(target_key)
    if body.actor_user_id is not None and not body.actor_user_id.strip():
        raise _error("circuit.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    try:
        state = cb.get_registry().record_failure(k)
    except cb.CircuitBreakerError as e:
        raise _error("circuit.invalid", str(e))
    event = "circuit.opened" if state.state == "open" else "circuit.failure"
    await _audit(
        event,
        user_id=body.actor_user_id,
        detail={
            "target_key": k,
            "state": state.state,
            "consecutive_failures": state.consecutive_failures,
        },
    )
    return state.to_dict()


@router.post("/{target_key}/reset")
async def reset(target_key: str, body: EventRequest) -> dict[str, Any]:
    k = _validate_key(target_key)
    if body.actor_user_id is not None and not body.actor_user_id.strip():
        raise _error("circuit.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    ok = cb.get_registry().reset(k)
    if not ok:
        raise _error("circuit.not_found",
                     f"breaker not found: {k}", status_code=404)
    await _audit(
        "circuit.reset",
        user_id=body.actor_user_id,
        detail={"target_key": k},
    )
    return {"reset": True, "target_key": k}


@router.post("/configure")
async def configure(req: ConfigureRequest) -> dict[str, Any]:
    if req.actor_user_id is not None and not req.actor_user_id.strip():
        raise _error("circuit.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    try:
        cb.reset_registry(
            failure_threshold=req.failure_threshold,
            recover_seconds=req.recover_seconds,
        )
    except cb.CircuitBreakerError as e:
        raise _error("circuit.invalid_config", str(e))
    await _audit(
        "circuit.configured",
        user_id=req.actor_user_id,
        detail={
            "failure_threshold": req.failure_threshold,
            "recover_seconds": req.recover_seconds,
        },
    )
    return {
        "failure_threshold": req.failure_threshold,
        "recover_seconds": req.recover_seconds,
    }
