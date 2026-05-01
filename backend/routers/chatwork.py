"""
chatwork.py — Chatwork Webhook & 通知 API

POST /api/chatwork/webhook  Chatwork からの Webhook 受信
GET  /api/chatwork/status   接続状態確認
"""

import hashlib
import hmac
import os
import asyncio

from fastapi import APIRouter, HTTPException, Request, Header
from typing import Optional

from integrations.chatwork_client import (
    handle_webhook_message,
    is_configured,
)

router = APIRouter(prefix="/api/chatwork", tags=["chatwork"])

WEBHOOK_TOKEN = os.environ.get("CHATWORK_WEBHOOK_TOKEN", "")


def _verify_signature(body: bytes, signature: Optional[str]) -> bool:
    """Chatwork Webhook の HMAC-SHA256 署名を検証する。トークン未設定なら常に通す。"""
    if not WEBHOOK_TOKEN or not signature:
        return True
    mac = hmac.new(WEBHOOK_TOKEN.encode(), body, hashlib.sha256)
    return hmac.compare_digest(mac.hexdigest(), signature)


@router.post("/webhook")
async def chatwork_webhook(
    request: Request,
    x_chatworkwebhooksignature: Optional[str] = Header(default=None),
):
    """
    Chatwork Webhook エンドポイント。
    メッセージイベントを受け取り、承認コマンドを処理する。
    """
    body = await request.body()

    if WEBHOOK_TOKEN and not _verify_signature(body, x_chatworkwebhooksignature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    webhook_type = payload.get("webhook_event_type")
    if webhook_type not in ("mention_to_me", "message_created"):
        return {"status": "ignored", "type": webhook_type}

    event = payload.get("webhook_event", {})
    message_text = event.get("body", "").strip()
    room_id = str(event.get("room_id", ""))
    account_id = str(event.get("account_id", ""))
    account_name = str(account_id)

    print(f"[chatwork webhook] room={room_id} msg={message_text[:80]}")

    asyncio.create_task(
        handle_webhook_message(message_text, room_id, account_id, account_name)
    )

    return {"status": "accepted"}


@router.get("/status")
async def chatwork_status():
    """Chatwork の設定状態を返す。"""
    return {
        "configured": is_configured(),
        "room_id": os.environ.get("CHATWORK_ROOM_ID", ""),
        "webhook_token_set": bool(os.environ.get("CHATWORK_WEBHOOK_TOKEN")),
    }
