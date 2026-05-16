"""T-V3-B-29 / F-027: Onboarding flow REST API.

OpenAPI spec: docs/api-design/2026-05-16_v3/openapi.yaml
  - GET   /api/me/onboarding         → 現在の onboarding 状態 (state, current_step, completed)
  - POST  /api/me/onboarding/advance → step を進めて next_step を返す
  - POST  /api/me/onboarding/skip    → optional step を skip / skipped_at を返す

AC マッピング (audit: docs/audit/2026-05-16_v3/T-V3-B-29.md):
  AC-F1 EVENT-DRIVEN  : POST /advance with valid step → persist + return next_step
  AC-F2 UNWANTED      : POST /skip for required step  → 409
  AC-F3 EVENT-DRIVEN  : GET  /onboarding              → 2xx with state
  AC-F4 UNWANTED      : GET  unauthorized             → 401
  AC-F5 UNWANTED      : GET  invalid body             → 422
  AC-F6 EVENT-DRIVEN  : POST /advance with valid auth → 2xx with next_step
  AC-F7 UNWANTED      : POST /advance unauthorized    → 401
  AC-F8 UNWANTED      : POST /advance invalid body    → 422
  AC-F9 EVENT-DRIVEN  : POST /skip with valid auth    → 2xx with skipped_at
  AC-F10 UNWANTED     : POST /skip unauthorized       → 401
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services import onboarding as svc
from services.auth_middleware import require_user

router = APIRouter(prefix="/api/me/onboarding", tags=["onboarding"])


# ── Pydantic schemas ────────────────────────────────────

class AdvanceRequest(BaseModel):
    step: str = Field(..., min_length=1, max_length=100, description="完了マークする step ID")
    payload: dict[str, Any] = Field(default_factory=dict, description="その step の入力データ")


class SkipRequest(BaseModel):
    step: Optional[str] = Field(default=None, max_length=100, description="skip 対象 step (未指定なら current_step)")
    reason: Optional[str] = Field(default=None, max_length=500)


class OnboardingStateResponse(BaseModel):
    state: dict[str, Any]
    current_step: str
    completed: bool
    completed_steps: list[str]
    skipped_steps: list[str]
    completed_at: Optional[str] = None
    skipped_at: Optional[str] = None


class AdvanceResponse(BaseModel):
    next_step: Optional[str]
    completed: bool
    current_step: str


class SkipResponse(BaseModel):
    skipped_at: str
    next_step: Optional[str]
    completed: bool


# ── error helper ─────────────────────────────────────────

def _err(code: str, message: str, *, status_code: int) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _map_service_error(e: svc.OnboardingError) -> HTTPException:
    if isinstance(e, svc.RequiredStepSkipError):
        return _err("required_step_skip", str(e), status_code=409)
    if isinstance(e, svc.StepOutOfOrderError):
        return _err("step_out_of_order", str(e), status_code=409)
    if isinstance(e, svc.UnknownStepError):
        return _err("unknown_step", str(e), status_code=422)
    return _err("onboarding_error", str(e), status_code=400)


def _user_id(user: dict) -> str:
    return str(user.get("sub") or user.get("id") or "")


# ── endpoints ─────────────────────────────────────────────

@router.get("", response_model=OnboardingStateResponse)
async def get_me_onboarding(user: dict = Depends(require_user)) -> dict:
    """AC-F3: GET /api/me/onboarding — 現在の onboarding 状態を返す.
    AC-F4: require_user が unauthorized → 401 を投げる.
    """
    uid = _user_id(user)
    state = await svc.get_state(uid)
    return {
        "state":           state["state"],
        "current_step":    state["current_step"],
        "completed":       state["completed"],
        "completed_steps": state["completed_steps"],
        "skipped_steps":   state["skipped_steps"],
        "completed_at":    state["completed_at"],
        "skipped_at":      state["skipped_at"],
    }


@router.post("/advance", response_model=AdvanceResponse, status_code=201)
async def post_me_onboarding_advance(
    body: AdvanceRequest,
    user: dict = Depends(require_user),
) -> dict:
    """AC-F1 / AC-F6: POST /advance — step を進めて next_step を返す.
    AC-F7: unauthorized → 401 (require_user).
    AC-F8: invalid body → 422 (Pydantic).
    """
    uid = _user_id(user)
    try:
        return await svc.advance(uid, body.step, body.payload)
    except svc.OnboardingError as e:
        raise _map_service_error(e)


@router.post("/skip", response_model=SkipResponse, status_code=201)
async def post_me_onboarding_skip(
    body: SkipRequest,
    user: dict = Depends(require_user),
) -> dict:
    """AC-F2 / AC-F9: POST /skip — optional step を skip / skipped_at 返す.
    AC-F2: required step → 409 (RequiredStepSkipError).
    AC-F10: unauthorized → 401 (require_user).
    """
    uid = _user_id(user)
    try:
        return await svc.skip(uid, body.step, body.reason)
    except svc.OnboardingError as e:
        raise _map_service_error(e)
