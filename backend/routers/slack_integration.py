"""T-014-01: Slack Bolt 統合 REST endpoint (existing slack_client + slack_block_kit REUSE).

既存 `integrations/slack_client.py` が公開する Bolt Socket Mode を REST 経由で利用可能にする
ためのラッパー router. AC は F-014 の REUSE 規約に従う:

  AC-1 UBIQUITOUS   : Slack Bolt 統合を F-014 の仕様通り提供 (status / notify endpoint)
  AC-2 EVENT-DRIVEN : 2 秒以内に success or {detail:{code,message}} を返す
  AC-3 STATE-DRIVEN : 既存実装 (slack_client / slack_block_kit) を import し regression を起こさない
  AC-4 UNWANTED     : invalid input / unauthorized actor は 4xx + {detail:{code,message}} かつ
                      persistent state mutate しない

Endpoint:
  GET  /api/slack/status                — 接続状態 (enabled / connected / bot info)
  POST /api/slack/notify                — 任意 channel に rich/plain メッセージ送信
  POST /api/slack/approval-notify       — approval_queue 通知送信 (id, title, preview)
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/slack", tags=["slack"])


# ──────────────────────────────────────────────────────────────────────────
# Helpers (AC-2 / AC-4 error contract + AC-3 audit emit)
# ──────────────────────────────────────────────────────────────────────────


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    """{detail:{code,message}} 形式の error."""
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    """audit_logs に Slack 関連 event を emit. 失敗してもアプリは止めない."""
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover — best-effort emit
        logger.warning("slack audit emit failed: %s -- %s", event_type, e)


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: status endpoint
# ──────────────────────────────────────────────────────────────────────────


@router.get("/status")
async def slack_status() -> dict[str, Any]:
    """AC-1: Slack Bolt 接続状態 (bot_token / app_token / live connection)."""
    bot_token_present = bool(os.environ.get("SLACK_BOT_TOKEN"))
    app_token_present = bool(os.environ.get("SLACK_APP_TOKEN"))

    # 既存 module から live state を読む (regression なしで REUSE)
    enabled = False
    bot_id = None
    try:
        from integrations import slack_client as sc
        enabled = bool(sc._slack_enabled)
        if enabled and sc._app:
            try:
                result = await sc._app.client.auth_test()
                bot_id = result.get("bot_id")
            except Exception:
                bot_id = None
    except Exception:
        enabled = False

    return {
        "enabled": enabled,
        "bot_token_configured": bot_token_present,
        "app_token_configured": app_token_present,
        "bot_id": bot_id,
        "channel": os.environ.get("SLACK_CHANNEL_ID", "#build-factory-ai"),
    }


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT: notify endpoint
# ──────────────────────────────────────────────────────────────────────────


class NotifyRequest(BaseModel):
    text: str = Field(..., description="本文 (空文字 NG)")
    channel: Optional[str] = Field(None, description="送信先 channel id (省略時 default)")
    rich: bool = Field(False, description="True なら Block Kit へ render (slack_block_kit 経由)")
    user_id: Optional[str] = Field(None, description="actor user_id (audit log 用)")


@router.post("/notify")
async def slack_notify(req: NotifyRequest) -> dict[str, Any]:
    """AC-2: 任意 channel に通知送信. invalid input は AC-4 で reject."""
    # AC-4 UNWANTED: empty body は reject (state mutate なし)
    if not req.text or not req.text.strip():
        raise _error("slack.invalid_text", "text must not be empty")
    if req.channel is not None and not req.channel.strip():
        raise _error("slack.invalid_channel", "channel must not be empty when provided")
    if req.user_id is not None and not req.user_id.strip():
        raise _error("slack.unauthorized", "user_id must not be empty when provided", status_code=401)

    # AC-3 STATE: 既存 module を REUSE (regression なし)
    try:
        from integrations import slack_client as sc
    except Exception as e:
        raise _error("slack.module_unavailable", f"slack_client unavailable: {e}", status_code=503)

    if not sc._slack_enabled:
        # 機械検証: Slack 未接続でも 503 を返し audit に skipped を残す (mutate なし)
        await _audit(
            "slack.notify.skipped",
            user_id=req.user_id,
            detail={"reason": "not_enabled", "text_len": len(req.text)},
        )
        raise _error("slack.not_enabled", "Slack integration is not enabled", status_code=503)

    try:
        if req.rich:
            await sc.send_rich_message(req.text, channel=req.channel)
        else:
            channel = req.channel or sc.CHANNEL
            if sc._app:
                await sc._app.client.chat_postMessage(channel=channel, text=req.text[:2900])
    except Exception as e:
        raise _error("slack.send_failed", f"Slack send failed: {e}", status_code=502)

    await _audit(
        "slack.notify.sent",
        user_id=req.user_id,
        detail={"channel": req.channel, "rich": req.rich, "text_len": len(req.text)},
    )
    return {
        "status": "sent",
        "channel": req.channel,
        "rich": req.rich,
    }


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT: approval notify (既存 send_approval_notification REUSE)
# ──────────────────────────────────────────────────────────────────────────


class ApprovalNotifyRequest(BaseModel):
    approval_id: int = Field(..., gt=0, description="approval_queue.id (1 以上)")
    title: str = Field(..., description="タイトル (空文字 NG)")
    preview: str = Field("", description="プレビュー (200 chars trim)")
    user_id: Optional[str] = Field(None, description="actor user_id (audit log 用)")


@router.post("/approval-notify")
async def slack_approval_notify(req: ApprovalNotifyRequest) -> dict[str, Any]:
    """approval_queue 通知の REST 形式 (既存 send_approval_notification REUSE)."""
    if req.approval_id <= 0:
        raise _error("slack.invalid_approval_id", "approval_id must be > 0")
    if not req.title or not req.title.strip():
        raise _error("slack.invalid_title", "title must not be empty")
    if req.user_id is not None and not req.user_id.strip():
        raise _error("slack.unauthorized", "user_id must not be empty when provided", status_code=401)

    try:
        from integrations import slack_client as sc
    except Exception as e:
        raise _error("slack.module_unavailable", f"slack_client unavailable: {e}", status_code=503)

    if not sc._slack_enabled:
        await _audit(
            "slack.approval_notify.skipped",
            user_id=req.user_id,
            detail={"approval_id": req.approval_id, "reason": "not_enabled"},
        )
        raise _error("slack.not_enabled", "Slack integration is not enabled", status_code=503)

    try:
        slack_ts = await sc.send_approval_notification(req.approval_id, req.title, req.preview)
    except Exception as e:
        raise _error("slack.send_failed", f"approval notify failed: {e}", status_code=502)

    await _audit(
        "slack.approval_notify.sent",
        user_id=req.user_id,
        detail={"approval_id": req.approval_id, "slack_ts": slack_ts},
    )
    return {
        "status": "sent",
        "approval_id": req.approval_id,
        "slack_ts": slack_ts,
    }
