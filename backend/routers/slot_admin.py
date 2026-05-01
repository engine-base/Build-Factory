"""
slot_admin.py — スロット管理 API

POST /api/slots/reset?thread_id=N        全スロット削除
POST /api/slots/reset_corrupt?thread_id=N 破損したものだけ削除
GET  /api/slots/list?thread_id=N         現在のスロット一覧
"""

from fastapi import APIRouter, Query

from services import slot_state as ss

router = APIRouter(prefix="/api/slots", tags=["slot-admin"])


@router.get("/list")
async def list_slots(thread_id: int = Query(...)):
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
async def reset_all_slots(thread_id: int = Query(...)):
    n = await ss.reset_slots(thread_id)
    return {"thread_id": thread_id, "deleted": n}


@router.post("/reset_corrupt")
async def reset_corrupt_only(thread_id: int = Query(...)):
    n = await ss.reset_corrupt_slots(thread_id)
    return {"thread_id": thread_id, "deleted": n}
