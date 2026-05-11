"""T-006-01 / F-006: feature-decomposition AI (Devon) REST endpoint.

Endpoint:
  POST /api/features/decompose   feature dict を独立 task に分解

T-006-01 AC:
  AC-1 UBIQUITOUS    : F-006 の feature 分解 endpoint
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit_logs emit + RLS は migration 側で担保
  AC-4 UNWANTED      : invalid feature / 空 actor は 4xx + structured +
                       persistent state mutate しない
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.feature_decomposer import (
    FeatureDecomposerError,
    decompose_feature,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/features", tags=["features"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("feature-decomposer audit emit failed: %s -- %s", event_type, e)


class DecomposeRequest(BaseModel):
    feature: dict
    actor_user_id: Optional[str] = None


@router.post("/decompose")
async def decompose(body: DecomposeRequest) -> dict[str, Any]:
    if body.actor_user_id is not None and not body.actor_user_id.strip():
        raise _error("features.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    if not isinstance(body.feature, dict):
        raise _error("features.invalid_feature", "feature must be a dict")

    try:
        result = decompose_feature(body.feature)
    except FeatureDecomposerError as e:
        raise _error("features.invalid_feature", str(e))

    await _audit(
        "features.decomposed",
        user_id=body.actor_user_id,
        detail={
            "feature_id": result.feature_id,
            "total_tasks": result.total,
            "layers": [t.layer for t in result.tasks],
        },
    )
    return result.to_dict()
