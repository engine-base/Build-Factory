"""T-016-03 / F-016: export trigger REST endpoint.

Endpoint:
  POST   /api/export-triggers                    register
  GET    /api/export-triggers                    list (?artifact_id, ?trigger_type)
  GET    /api/export-triggers/{id}               single
  POST   /api/export-triggers/{id}/fire          手動 fire (manual/realtime/on_completion)
  POST   /api/export-triggers/{id}/disable       disable (soft)
  DELETE /api/export-triggers/{id}               削除
  POST   /api/export-triggers/scan-due           hourly due な trigger を fire

AC マッピング:
  AC-1 UBIQUITOUS    : F-016 4 trigger type (manual/realtime/hourly/on_completion)
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit emit + last_fired_at / fire_count を更新
  AC-4 UNWANTED      : invalid input / disabled trigger fire / not_found は 4xx +
                       structured / persistent state mutate しない
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services import export_trigger as et

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/export-triggers", tags=["export-triggers"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("export-trigger audit emit failed: %s -- %s", event_type, e)


async def _default_export(artifact_id: str) -> dict:
    """artifact_md.save_artifact_md を呼ぶ default exporter."""
    try:
        from services.artifact_md_renderer import save_artifact_md
        # 完全な artifact 情報は持っていないので id だけで minimal save
        result = save_artifact_md({"id": artifact_id, "title": artifact_id})
        return {"path": result["path"], "size": result["size"]}
    except Exception as e:
        logger.warning("default export failed for %s: %s", artifact_id, e)
        return {"error": str(e)}


class RegisterRequest(BaseModel):
    artifact_id: str
    trigger_type: str = Field(..., description="manual/realtime/hourly/on_completion")
    scheduled_at: Optional[float] = None
    enabled: bool = True
    actor_user_id: Optional[str] = None


class FireRequest(BaseModel):
    actor_user_id: Optional[str] = None


class DisableRequest(BaseModel):
    actor_user_id: Optional[str] = None


class ScanDueRequest(BaseModel):
    actor_user_id: Optional[str] = None


@router.post("")
async def register(req: RegisterRequest) -> dict[str, Any]:
    if req.actor_user_id is not None and not req.actor_user_id.strip():
        raise _error("export.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    if not req.artifact_id or not req.artifact_id.strip():
        raise _error("export.invalid_artifact_id",
                     "artifact_id must not be empty")
    if req.trigger_type not in et.VALID_TRIGGER_TYPES:
        raise _error(
            "export.invalid_trigger_type",
            f"trigger_type must be one of {et.VALID_TRIGGER_TYPES}",
        )
    try:
        trig = et.get_store().register(
            req.artifact_id, req.trigger_type,
            scheduled_at=req.scheduled_at, enabled=req.enabled,
        )
    except et.ExportTriggerError as e:
        msg = str(e)
        if "already exists" in msg:
            raise _error("export.duplicate", msg, status_code=409)
        if "triggers full" in msg:
            raise _error("export.store_full", msg, status_code=409)
        raise _error("export.invalid", msg)
    await _audit(
        "export.trigger.registered",
        user_id=req.actor_user_id,
        detail={
            "trigger_id": trig.id,
            "artifact_id": req.artifact_id,
            "trigger_type": req.trigger_type,
        },
    )
    return trig.to_dict()


@router.get("")
async def list_triggers(
    artifact_id: Optional[str] = Query(None),
    trigger_type: Optional[str] = Query(None),
    enabled: Optional[bool] = Query(None),
) -> dict[str, Any]:
    if trigger_type is not None and trigger_type not in et.VALID_TRIGGER_TYPES:
        raise _error(
            "export.invalid_trigger_type",
            f"trigger_type must be one of {et.VALID_TRIGGER_TYPES}",
        )
    items = et.get_store().list(
        artifact_id=artifact_id,
        trigger_type=trigger_type,
        enabled=enabled,
    )
    return {
        "count": len(items),
        "triggers": [t.to_dict() for t in items],
    }


@router.get("/{trigger_id}")
async def get_trigger(trigger_id: int) -> dict[str, Any]:
    if trigger_id <= 0:
        raise _error("export.invalid_id", "trigger_id must be > 0")
    t = et.get_store().get(trigger_id)
    if t is None:
        raise _error("export.not_found",
                     f"trigger not found: {trigger_id}", status_code=404)
    return t.to_dict()


@router.post("/{trigger_id}/fire")
async def fire(trigger_id: int, body: FireRequest) -> dict[str, Any]:
    if trigger_id <= 0:
        raise _error("export.invalid_id", "trigger_id must be > 0")
    if body.actor_user_id is not None and not body.actor_user_id.strip():
        raise _error("export.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    try:
        result = await et.fire_trigger(trigger_id, export_fn=_default_export)
    except et.ExportTriggerError as e:
        msg = str(e)
        if "not found" in msg:
            raise _error("export.not_found", msg, status_code=404)
        if "disabled" in msg:
            raise _error("export.disabled", msg, status_code=409)
        raise _error("export.invalid", msg)
    await _audit(
        "export.trigger.fired",
        user_id=body.actor_user_id,
        detail={
            "trigger_id": trigger_id,
            "trigger_type": result.trigger_type,
            "artifact_id": result.artifact_id,
            "success": result.success,
        },
    )
    return result.to_dict()


@router.post("/{trigger_id}/disable")
async def disable(trigger_id: int, body: DisableRequest) -> dict[str, Any]:
    if trigger_id <= 0:
        raise _error("export.invalid_id", "trigger_id must be > 0")
    if body.actor_user_id is not None and not body.actor_user_id.strip():
        raise _error("export.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    ok = et.get_store().disable(trigger_id)
    if not ok:
        raise _error("export.not_found",
                     f"trigger not found: {trigger_id}", status_code=404)
    await _audit(
        "export.trigger.disabled",
        user_id=body.actor_user_id,
        detail={"trigger_id": trigger_id},
    )
    return {"disabled": True, "trigger_id": trigger_id}


@router.delete("/{trigger_id}")
async def remove(
    trigger_id: int,
    actor_user_id: Optional[str] = Query(None),
) -> dict[str, Any]:
    if trigger_id <= 0:
        raise _error("export.invalid_id", "trigger_id must be > 0")
    if actor_user_id is not None and not actor_user_id.strip():
        raise _error("export.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    ok = et.get_store().delete(trigger_id)
    if not ok:
        raise _error("export.not_found",
                     f"trigger not found: {trigger_id}", status_code=404)
    await _audit(
        "export.trigger.deleted",
        user_id=actor_user_id,
        detail={"trigger_id": trigger_id},
    )
    return {"deleted": True, "trigger_id": trigger_id}


@router.post("/scan-due")
async def scan_due(body: ScanDueRequest) -> dict[str, Any]:
    if body.actor_user_id is not None and not body.actor_user_id.strip():
        raise _error("export.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    due = et.get_store().due_triggers()
    results = []
    for t in due:
        try:
            r = await et.fire_trigger(t.id, export_fn=_default_export)
            results.append(r.to_dict())
        except et.ExportTriggerError as e:
            results.append({
                "trigger_id": t.id,
                "success": False,
                "error": str(e),
            })
    await _audit(
        "export.trigger.scan_due",
        user_id=body.actor_user_id,
        detail={"count": len(due)},
    )
    return {"count": len(due), "fired": results}
