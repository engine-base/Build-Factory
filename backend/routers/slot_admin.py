"""slot_admin.py — スロット管理 API (T-005-02 REFACTOR).

Endpoint:
  GET  /api/slots/list?thread_id=N          現在のスロット一覧
  POST /api/slots/reset?thread_id=N         全スロット削除
  POST /api/slots/reset_corrupt?thread_id=N 破損したものだけ削除
  POST /api/slots/upsert                    1 件 upsert (対話 UI 用, T-005-02 新規)

T-005-02 AC:
  AC-1 UBIQUITOUS    : F-005 の slot 管理 endpoint (list/reset/reset_corrupt/upsert) 公開
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 contract (route prefix / response shape) 不変 + audit emit
  AC-4 UNWANTED      : invalid thread_id / 空 slot_name / 空 actor は 4xx + structured
                       かつ persistent state mutate しない
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services import slot_state as ss

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/slots", tags=["slot-admin"])


# ──────────────────────────────────────────────────────────────────────────
# T-005-02: helpers
# ──────────────────────────────────────────────────────────────────────────


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("slot_admin audit emit failed: %s -- %s", event_type, e)


def _validate_thread_id(thread_id: int) -> None:
    if thread_id is None or thread_id <= 0:
        raise _error("slots.invalid_thread_id", f"thread_id must be > 0, got {thread_id}")


def _validate_actor(actor: Optional[str]) -> None:
    if actor is not None and not actor.strip():
        raise _error("slots.unauthorized", "actor_user_id must not be empty when provided",
                     status_code=401)


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: 既存 3 endpoint (backwards compat)
# ──────────────────────────────────────────────────────────────────────────


@router.get("/list")
async def list_slots(thread_id: int = Query(...)):
    _validate_thread_id(thread_id)
    slots = await ss.get_slots(thread_id)
    return {
        "thread_id": thread_id,
        "count": len(slots),
        "slots": [
            {
                "slot_name": s.slot_name,
                "confirmed_value": s.confirmed_value,
                "rejected": s.rejected,
                "hints": s.hints,
                "history": s.history,
                "is_resolved": s.is_resolved,
                "is_corrupt": ss.is_corrupt(s),
                "goal": s.goal,
            }
            for s in slots
        ],
    }


@router.post("/reset")
async def reset_all_slots(
    thread_id: int = Query(...),
    actor_user_id: Optional[str] = Query(None),
):
    _validate_thread_id(thread_id)
    _validate_actor(actor_user_id)
    n = await ss.reset_slots(thread_id)
    await _audit(
        "slots.reset",
        user_id=actor_user_id,
        detail={"thread_id": thread_id, "deleted": n},
    )
    return {"thread_id": thread_id, "deleted": n}


@router.post("/reset_corrupt")
async def reset_corrupt_only(
    thread_id: int = Query(...),
    actor_user_id: Optional[str] = Query(None),
):
    _validate_thread_id(thread_id)
    _validate_actor(actor_user_id)
    n = await ss.reset_corrupt_slots(thread_id)
    await _audit(
        "slots.reset_corrupt",
        user_id=actor_user_id,
        detail={"thread_id": thread_id, "deleted": n},
    )
    return {"thread_id": thread_id, "deleted": n}


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: T-005-02 新規 — 対話 UI 用 upsert
# ──────────────────────────────────────────────────────────────────────────


class SlotUpsertRequest(BaseModel):
    thread_id: int
    slot_name: str
    confirmed_value: Optional[str] = None
    goal: Optional[str] = None
    add_hint: Optional[str] = None
    add_rejected: Optional[str] = None
    add_history: Optional[str] = None
    position: Optional[int] = None
    is_resolved: Optional[bool] = None
    actor_user_id: Optional[str] = None


@router.post("/upsert")
async def upsert_slot(body: SlotUpsertRequest) -> dict[str, Any]:
    """対話 UI からスロットを永続化する (T-005-02)."""
    _validate_thread_id(body.thread_id)
    _validate_actor(body.actor_user_id)
    name = (body.slot_name or "").strip()
    if not name:
        raise _error("slots.invalid_slot_name", "slot_name must not be empty")
    if len(name) > 200:
        raise _error("slots.slot_name_too_long", "slot_name must be <= 200 chars")
    if body.confirmed_value is not None and len(body.confirmed_value) > 5000:
        raise _error("slots.value_too_long", "confirmed_value must be <= 5000 chars")
    if body.goal is not None and len(body.goal) > 1000:
        raise _error("slots.goal_too_long", "goal must be <= 1000 chars")

    try:
        await ss.upsert_slot(
            body.thread_id,
            name,
            goal=body.goal,
            confirmed_value=body.confirmed_value,
            add_rejected=body.add_rejected,
            add_hint=body.add_hint,
            add_history=body.add_history,
            position=body.position,
            is_resolved=body.is_resolved,
        )
    except Exception as e:
        raise _error("slots.upsert_failed", f"upsert failed: {e}", status_code=500)

    await _audit(
        "slots.upserted",
        user_id=body.actor_user_id,
        detail={
            "thread_id": body.thread_id,
            "slot_name": name,
            "has_value": body.confirmed_value is not None,
            "is_resolved": body.is_resolved,
        },
    )
    return {
        "thread_id": body.thread_id,
        "slot_name": name,
        "status": "upserted",
    }
