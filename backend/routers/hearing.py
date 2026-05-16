"""
hearing.py — Phase 1 ヒアリング 対話駆動 API

POST /api/workspaces/{id}/hearing/start-step    body: { step: int }
POST /api/workspaces/{id}/hearing/reply          body: { step: int, message: str }
POST /api/workspaces/{id}/hearing/complete-step  body: { step: int }
GET  /api/workspaces/{id}/hearing/state          全 STEP の状態取得

v3 Phase 1 (T-V3-B-07 / F-005) で追加:
  POST /api/workspaces/{id}/hearing/save          body: { slot_state, transcript, ... }
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field

from services import hearing_service as hs
from services import specs_store as ss
from services.auth_middleware import require_user
from services.specs_store import (
    MAX_TRANSCRIPT_CHARS,
    SpecsStoreError,
)

router = APIRouter(prefix="/api/workspaces", tags=["hearing"])


class StartStepBody(BaseModel):
    step: int


class ReplyBody(BaseModel):
    step: int
    message: str


class CompleteStepBody(BaseModel):
    step: int


class CenterUpdateBody(BaseModel):
    center: dict
    edited_by_pm: bool = True


VALID_STEPS = (1, 2, 3, 4)  # T-005-01 / F-005: hearing AI Mary 4STEP


def _ensure_valid_step(step: int) -> None:
    """T-005-01 AC-4: step は 4STEP のいずれか."""
    if step not in VALID_STEPS:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_step",
                "message": f"step must be one of {list(VALID_STEPS)}, got {step}",
            },
        )


@router.post("/{workspace_id}/hearing/start-step")
async def start_step(workspace_id: int, body: StartStepBody):
    _ensure_valid_step(body.step)
    res = await hs.start_step(workspace_id, body.step)
    if "error" in res:
        raise HTTPException(
            status_code=400,
            detail={"code": "hearing_start_failed", "message": str(res["error"])},
        )
    return res


@router.post("/{workspace_id}/hearing/reply")
async def reply(workspace_id: int, body: ReplyBody):
    _ensure_valid_step(body.step)
    if not body.message.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": "empty_message", "message": "message must not be empty"},
        )
    return await hs.reply(workspace_id, body.step, body.message.strip())


@router.post("/{workspace_id}/hearing/complete-step")
async def complete_step(workspace_id: int, body: CompleteStepBody):
    _ensure_valid_step(body.step)
    return await hs.complete_step(workspace_id, body.step)


@router.get("/{workspace_id}/hearing/state")
async def get_state(workspace_id: int):
    return await hs.get_state(workspace_id)


@router.patch("/{workspace_id}/hearing/center")
async def update_center(workspace_id: int, body: CenterUpdateBody, step: int):
    """PM の直接編集 (BlockNote 経由) を反映."""
    _ensure_valid_step(step)
    art = await hs.get_or_create_center_artifact(workspace_id, step)
    center = body.center
    center["edited_by_pm"] = True
    updated = await hs.update_center_artifact(art["id"], center)
    return {"artifact": updated, "center": center}


# ──────────────────────────────────────────────────────────────────────────
# T-V3-B-07 / F-005: POST /hearing/save
# ──────────────────────────────────────────────────────────────────────────


class HearingSaveBody(BaseModel):
    """F-005 POST /api/workspaces/{id}/hearing/save body.

    AC-F1 EVENT-DRIVEN: persist slot_state with monotonic version.
    AC-F2 STATE-DRIVEN: accept while status='paused' to resume.
    AC-F6 UNWANTED   : validation failure → 422.
    """

    slot_state: dict = Field(default_factory=dict)
    transcript: str = Field("", max_length=MAX_TRANSCRIPT_CHARS)
    hearing_id: Optional[str] = Field(None, min_length=1, max_length=200)
    target_status: Optional[str] = Field(
        None, pattern=r"^(active|paused|completed)$",
    )


def _hs_error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message},
    )


async def _audit_save(
    event_type: str, *, user_id: Optional[str], detail: dict,
) -> None:
    """best-effort audit emit."""
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception:  # pragma: no cover
        pass


def _user_id_of(user: dict) -> Optional[str]:
    sub = user.get("sub") if isinstance(user, dict) else None
    if isinstance(sub, str) and sub.strip():
        return sub
    return None


@router.post("/{workspace_id}/hearing/save")
async def save_hearing(
    body: HearingSaveBody,
    workspace_id: str = Path(..., min_length=1, max_length=200),
    user: dict = Depends(require_user),
) -> dict:
    """F-005 POST /api/workspaces/{id}/hearing/save.

    AC-F1 (EVENT-DRIVEN): When called, persist slot_state with monotonic version.
    AC-F2 (STATE-DRIVEN): While status='paused', accept the call (resume).
    AC-F4 (EVENT-DRIVEN): Return 200 with {hearing_id, saved_at, version, ...}.
    AC-F5 (UNWANTED): If no valid token → 401 (handled by require_user).
    AC-F6 (UNWANTED): If body fails validation → 422 (pydantic).
    """
    store = ss.get_store()
    try:
        hearing = store.save_hearing(
            workspace_id,
            slot_state=body.slot_state,
            transcript=body.transcript,
            hearing_id=body.hearing_id,
            target_status=body.target_status,
        )
    except SpecsStoreError as e:
        msg = str(e)
        if "not found" in msg:
            raise _hs_error("hearing.not_found", msg, status_code=404) from e
        if "does not belong" in msg:
            raise _hs_error("hearing.forbidden", msg, status_code=403) from e
        raise _hs_error("hearing.invalid", msg, status_code=422) from e

    await _audit_save(
        "hearing_saved",
        user_id=_user_id_of(user),
        detail={
            "workspace_id": workspace_id,
            "hearing_id": hearing.id,
            "version": hearing.version,
            "status": hearing.status,
        },
    )

    return {
        "hearing_id": hearing.id,
        "saved_at": hearing.updated_at,
        "version": hearing.version,
        "status": hearing.status,
        "workspace_id": hearing.workspace_id,
    }
