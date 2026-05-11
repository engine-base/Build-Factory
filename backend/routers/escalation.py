"""T-011-03 / F-011: エスカレ通知 REST endpoint.

Endpoint:
  POST   /api/escalation/notify                      新規エスカレ (Slack DM + バッジ)
  GET    /api/escalation/badges/{user_id}            バッジ一覧 (default: 未読のみ)
  POST   /api/escalation/badges/{badge_id}/read      既読化
  DELETE /api/escalation/badges/{user_id}            user の全バッジ clear

AC マッピング:
  AC-1 UBIQUITOUS    : F-011 エスカレ通知 endpoint + service (Slack DM + UI バッジ)
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit emit + Slack 未接続でもバッジは記録 (state 保証)
  AC-4 UNWANTED      : invalid input / 他人 badge の既読化 は 4xx + structured
                       かつ persistent state mutate しない
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services import escalation_notifier as en

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/escalation", tags=["escalation"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("escalation audit emit failed: %s -- %s", event_type, e)


class NotifyRequest(BaseModel):
    target_user_id: str
    message: str
    severity: str = Field("warning", description="info / warning / critical / redline")
    badge_label: str = "Escalation"
    slack_dm: bool = True
    slack_channel: Optional[str] = None
    actor_user_id: Optional[str] = None
    detail: dict = Field(default_factory=dict)


class ReadRequest(BaseModel):
    user_id: str
    actor_user_id: Optional[str] = None


@router.post("/notify")
async def notify(req: NotifyRequest) -> dict[str, Any]:
    if req.actor_user_id is not None and not req.actor_user_id.strip():
        raise _error("escalation.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    if not req.target_user_id or not req.target_user_id.strip():
        raise _error("escalation.invalid_target_user",
                     "target_user_id must not be empty")
    if len(req.target_user_id) > 200:
        raise _error("escalation.invalid_target_user",
                     "target_user_id must be <= 200 chars")
    if not req.message or not req.message.strip():
        raise _error("escalation.invalid_message", "message must not be empty")
    if len(req.message) > 4000:
        raise _error("escalation.message_too_long", "message must be <= 4000 chars")
    if req.severity not in en.VALID_SEVERITIES:
        raise _error(
            "escalation.invalid_severity",
            f"severity must be one of {en.VALID_SEVERITIES}",
        )
    if not req.badge_label or not req.badge_label.strip():
        raise _error("escalation.invalid_badge_label",
                     "badge_label must not be empty")
    if len(req.badge_label) > 200:
        raise _error("escalation.invalid_badge_label",
                     "badge_label must be <= 200 chars")
    if req.slack_channel is not None and not req.slack_channel.strip():
        raise _error("escalation.invalid_slack_channel",
                     "slack_channel must not be empty when provided")

    try:
        result = await en.escalate(
            req.target_user_id,
            req.message,
            severity=req.severity,
            badge_label=req.badge_label,
            slack_dm=req.slack_dm,
            slack_channel=req.slack_channel,
            detail=req.detail or {},
        )
    except en.EscalationError as e:
        raise _error("escalation.invalid", str(e))

    await _audit(
        "escalation.notified",
        user_id=req.actor_user_id,
        detail={
            "badge_id": result["badge_id"],
            "target_user_id": req.target_user_id,
            "severity": req.severity,
            "slack_delivered": result["slack_delivered"],
        },
    )
    return result


@router.get("/badges/{user_id}")
async def list_badges(
    user_id: str,
    include_read: bool = Query(False),
) -> dict[str, Any]:
    if not user_id or not user_id.strip():
        raise _error("escalation.invalid_user_id", "user_id must not be empty")
    if len(user_id) > 200:
        raise _error("escalation.invalid_user_id", "user_id must be <= 200 chars")
    try:
        badges = en.get_store().list_for_user(user_id, include_read=include_read)
    except en.EscalationError as e:
        raise _error("escalation.invalid", str(e))
    return {
        "user_id": user_id,
        "count": len(badges),
        "badges": [b.to_dict() for b in badges],
    }


@router.post("/badges/{badge_id}/read")
async def mark_read(badge_id: int, body: ReadRequest) -> dict[str, Any]:
    if badge_id <= 0:
        raise _error("escalation.invalid_badge_id", "badge_id must be > 0")
    if body.actor_user_id is not None and not body.actor_user_id.strip():
        raise _error("escalation.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    if not body.user_id or not body.user_id.strip():
        raise _error("escalation.invalid_user_id", "user_id must not be empty")
    try:
        ok = en.get_store().mark_read(badge_id, user_id=body.user_id)
    except en.EscalationError as e:
        # other-user violation
        if "does not belong" in str(e):
            raise _error("escalation.forbidden", str(e), status_code=403)
        raise _error("escalation.invalid", str(e))
    if not ok:
        # 存在しないか already read
        b = en.get_store().get_badge(badge_id)
        if b is None:
            raise _error("escalation.not_found",
                         f"badge not found: {badge_id}", status_code=404)
        raise _error("escalation.already_read",
                     f"badge already read: {badge_id}", status_code=409)
    await _audit(
        "escalation.badge.read",
        user_id=body.actor_user_id or body.user_id,
        detail={"badge_id": badge_id, "user_id": body.user_id},
    )
    return {"read": True, "badge_id": badge_id}


@router.delete("/badges/{user_id}")
async def clear_badges(
    user_id: str,
    actor_user_id: Optional[str] = Query(None),
) -> dict[str, Any]:
    if not user_id or not user_id.strip():
        raise _error("escalation.invalid_user_id", "user_id must not be empty")
    if actor_user_id is not None and not actor_user_id.strip():
        raise _error("escalation.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    try:
        n = en.get_store().clear_user(user_id)
    except en.EscalationError as e:
        raise _error("escalation.invalid", str(e))
    await _audit(
        "escalation.badges.cleared",
        user_id=actor_user_id,
        detail={"user_id": user_id, "cleared": n},
    )
    return {"cleared": n, "user_id": user_id}
