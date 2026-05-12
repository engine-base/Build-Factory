"""T-025-02: EARS classifier REST endpoint.

POST /api/ears/classify : free-form text を 5 EARS 形式に分類 + 書き直し suggest
POST /api/ears/suggest  : target_type 指定で rewrite のみ
GET  /api/ears/health   : backend 登録状況 (read-only)
GET  /api/ears/forms    : 5 EARS forms の説明一覧 (read-only)
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import ears_classifier as ec

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ears", tags=["ears-classifier"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message},
    )


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("ears audit emit failed: %s -- %s", event_type, e)


def _check_actor(actor: Optional[str]) -> Optional[str]:
    if actor is not None and not actor.strip():
        raise _error(
            "ears.unauthorized",
            "actor_user_id must not be empty when provided",
            status_code=401,
        )
    return actor.strip() if actor else None


def _map_error(e: Exception) -> HTTPException:
    return _error("ears.invalid", str(e), status_code=400)


# ──────────────────────────────────────────────────────────────────────
# POST /api/ears/classify
# ──────────────────────────────────────────────────────────────────────


class ClassifyRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=ec.MAX_TEXT_CHARS)
    hint_type: Optional[str] = None
    actor_user_id: Optional[str] = None
    use_backend: bool = True


@router.post("/classify")
async def classify(req: ClassifyRequest) -> dict[str, Any]:
    actor = _check_actor(req.actor_user_id)
    try:
        result = ec.classify(
            req.text,
            hint_type=req.hint_type,
            use_backend=req.use_backend,
        )
    except ValueError as e:
        raise _map_error(e)
    await _audit(
        "ears.classified",
        user_id=actor,
        detail={
            "classified_type": result["classified_type"],
            "confidence": result["confidence"],
            "backend_used": result["backend_used"],
            "input_chars": len(req.text),
        },
    )
    return result


# ──────────────────────────────────────────────────────────────────────
# POST /api/ears/suggest
# ──────────────────────────────────────────────────────────────────────


class SuggestRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=ec.MAX_TEXT_CHARS)
    target_type: str
    actor_user_id: Optional[str] = None


@router.post("/suggest")
async def suggest(req: SuggestRequest) -> dict[str, Any]:
    actor = _check_actor(req.actor_user_id)
    try:
        rewritten = ec.suggest_rewrite(req.text, req.target_type)
        valid = ec.validate_against_schema(rewritten, req.target_type)
    except ValueError as e:
        raise _map_error(e)
    await _audit(
        "ears.suggested",
        user_id=actor,
        detail={
            "target_type": req.target_type.upper(),
            "schema_valid": valid,
            "input_chars": len(req.text),
        },
    )
    return {
        "target_type": req.target_type.upper(),
        "rewritten_text": rewritten,
        "schema_valid": valid,
    }


# ──────────────────────────────────────────────────────────────────────
# GET /api/ears/health
# ──────────────────────────────────────────────────────────────────────


@router.get("/health")
async def health() -> dict[str, Any]:
    return {
        "backend_registered": ec.get_classifier_backend() is not None,
        "phase": "ai" if ec.get_classifier_backend() is not None else "rule-based",
        "prompt_file_exists": ec.get_prompt_path().exists(),
        "valid_types": list(ec.VALID_TYPES),
    }


# ──────────────────────────────────────────────────────────────────────
# GET /api/ears/forms
# ──────────────────────────────────────────────────────────────────────


_FORM_DESCRIPTIONS = {
    "UBIQUITOUS": {
        "form": "The system shall {action}.",
        "use_when": "Always-true property with no precondition.",
    },
    "EVENT-DRIVEN": {
        "form": "When [event], the system shall {action}.",
        "use_when": "Behavior triggered by a discrete event.",
    },
    "STATE-DRIVEN": {
        "form": "While [state], the system shall {action}.",
        "use_when": "Behavior active while a state holds.",
    },
    "OPTIONAL": {
        "form": "Where [feature is enabled], the system shall {action}.",
        "use_when": "Feature-gated functionality.",
    },
    "UNWANTED": {
        "form": "If [unwanted condition], the system shall not {bad action}.",
        "use_when": "Prevents a bad outcome / handles errors.",
    },
}


@router.get("/forms")
async def forms() -> dict[str, Any]:
    return {
        "valid_types": list(ec.VALID_TYPES),
        "forms": _FORM_DESCRIPTIONS,
    }
