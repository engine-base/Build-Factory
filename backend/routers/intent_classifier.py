"""T-M27-02 / M-27: Intent 分類 REST endpoint.

3 detector (intent_preprocessor / mode_detector / skill_detector) を統一
インターフェースで提供する.

Endpoint:
  POST /api/intent/classify    3 detector 並列実行 + 統一 dict + audit emit
  GET  /api/intent/health      detector 利用可能性 (read-only diagnostic)

AC マッピング:
  AC-1 UBIQUITOUS    : T-M27-02 を M-27 (Intent Router) 仕様通り実装
                       (3 detector REFACTOR + top_signal 優先度統一)
  AC-2 EVENT-DRIVEN  : classify endpoint で audit emit (action + timestamp) /
                       全 endpoint 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 3 detector module 不変 / read endpoint は audit
                       emit しない / persistent state mutate しない /
                       coverage >= baseline 維持
  AC-4 UNWANTED      : invalid input / unauthorized actor → 4xx structured /
                       state mutate なし
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import intent_classifier as ic

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/intent", tags=["intent-classifier"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message},
    )


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover (sqlite 未配備環境向け)
        logger.warning("intent audit emit failed: %s -- %s", event_type, e)


def _check_actor(actor: Optional[str]) -> Optional[str]:
    if actor is not None and not actor.strip():
        raise _error(
            "intent.unauthorized",
            "actor_user_id must not be empty when provided",
            status_code=401,
        )
    return actor.strip() if actor else None


def _map_service_error(e: ic.IntentClassifierError) -> HTTPException:
    return _error("intent.invalid", str(e), status_code=400)


# ──────────────────────────────────────────────────────────────────────
# POST /api/intent/classify
# ──────────────────────────────────────────────────────────────────────


class HistoryItem(BaseModel):
    role: Optional[str] = None
    content: str = ""


class ClassifyRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=ic.MAX_MESSAGE_CHARS)
    history: Optional[list[dict]] = None
    employee_primary_skill: Optional[str] = None
    actor_user_id: Optional[str] = None
    rules_only: bool = False
    use_backend: bool = True


@router.post("/classify")
async def classify(req: ClassifyRequest) -> dict[str, Any]:
    actor = _check_actor(req.actor_user_id)
    try:
        result = await ic.classify(
            req.message,
            history=req.history,
            employee_primary_skill=req.employee_primary_skill,
            actor_user_id=actor,
            rules_only=req.rules_only,
            use_backend=req.use_backend,
        )
    except ic.IntentClassifierError as e:
        raise _map_service_error(e)
    await _audit(
        "intent.classified",
        user_id=actor,
        detail={
            "top_signal_kind": result["top_signal"]["kind"],
            "top_signal_value": result["top_signal"]["value"],
            "mode": result["mode"],
            "skill": result["skill"],
            "has_explicit": result["explicit_intent"] is not None,
            "rules_only": result["config"]["rules_only"],
            "backend_used": result["config"]["backend_used"],
            "latency_ms": result["meta"]["latency_ms"],
            "input_chars": result["meta"]["input_chars"],
        },
    )
    return result


# ──────────────────────────────────────────────────────────────────────
# GET /api/intent/health
# ──────────────────────────────────────────────────────────────────────


@router.get("/health")
async def health() -> dict[str, Any]:
    """3 detector の利用可能性を確認 (read-only, 副作用なし, audit emit なし)."""
    out: dict[str, Any] = {}
    for name, module_name in (
        ("intent_preprocessor", "services.intent_preprocessor"),
        ("mode_detector", "services.mode_detector"),
        ("skill_detector", "services.skill_detector"),
    ):
        try:
            __import__(module_name)
            out[name] = {"available": True, "module": module_name.split(".")[-1]}
        except Exception as e:
            out[name] = {
                "available": False,
                "module": module_name.split(".")[-1],
                "error": f"{type(e).__name__}: {str(e)[:200]}",
            }
    out["all_available"] = all(
        v["available"] for v in out.values() if isinstance(v, dict)
    )
    return out
