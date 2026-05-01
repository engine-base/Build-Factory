"""
chatwork_client.py — Chatwork API 連携

- メッセージ送信（通知）
- Webhook ペイロード解析
- 承認コマンドの受付（承認 N / 却下 N / 修正 N: text）
"""

import os
import re
from typing import Optional

import aiosqlite
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"

# Chatwork の通知先デフォルトルーム
_DEFAULT_ROOM_ID = os.environ.get("CHATWORK_ROOM_ID", "")


def is_configured() -> bool:
    return bool(os.environ.get("CHATWORK_API_TOKEN"))


async def send_message(room_id: str, message: str) -> bool:
    """指定ルームにメッセージを送信する。未設定なら False を返す。"""
    token = os.environ.get("CHATWORK_API_TOKEN")
    if not token or not room_id:
        return False

    try:
        import aiohttp
        url = f"https://api.chatwork.com/v2/rooms/{room_id}/messages"
        headers = {"X-ChatWorkToken": token}
        data = {"body": message, "self_unread": 0}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=data) as resp:
                ok = resp.status in (200, 201)
                if not ok:
                    body = await resp.text()
                    print(f"[chatwork] 送信失敗 status={resp.status}: {body[:200]}")
                return ok
    except Exception as e:
        print(f"[chatwork] send_message エラー: {e}")
        return False


async def send_approval_notification(
    approval_id: int,
    title: str,
    skill_name: str,
    action_type: str,
    room_id: Optional[str] = None,
) -> None:
    """承認リクエストを Chatwork に通知する。"""
    room = room_id or _DEFAULT_ROOM_ID
    if not room:
        return
    msg = (
        f"[info][title]⏳ 承認リクエスト #{approval_id}[/title]\n"
        f"スキル: {skill_name}\n"
        f"内容: {title}\n"
        f"アクション: {action_type}\n\n"
        f"返信コマンド:\n"
        f"  承認 {approval_id}\n"
        f"  却下 {approval_id}\n"
        f"  修正 {approval_id}: 修正内容[/info]"
    )
    await send_message(room, msg)


async def send_completion_notification(
    title: str,
    detail: str,
    room_id: Optional[str] = None,
) -> None:
    """完了通知を Chatwork に送信する。"""
    room = room_id or _DEFAULT_ROOM_ID
    if not room:
        return
    msg = f"[info][title]✅ {title}[/title]\n{detail}[/info]"
    await send_message(room, msg)


def parse_command(text: str) -> Optional[dict]:
    """
    Chatwork メッセージからコマンドを解析する。

    対応コマンド:
      承認 N       → { "action": "approve",  "id": N }
      却下 N       → { "action": "reject",   "id": N }
      修正 N: text → { "action": "revise",   "id": N, "notes": text }
      承認一覧      → { "action": "list" }

    Returns:
        コマンド辞書 or None（コマンドでない場合）
    """
    text = text.strip()

    if text == "承認一覧":
        return {"action": "list"}

    m = re.match(r"^承認\s+(\d+)$", text)
    if m:
        return {"action": "approve", "id": int(m.group(1))}

    m = re.match(r"^却下\s+(\d+)$", text)
    if m:
        return {"action": "reject", "id": int(m.group(1))}

    m = re.match(r"^修正\s+(\d+)\s*[:：]\s*(.+)$", text, re.DOTALL)
    if m:
        return {"action": "revise", "id": int(m.group(1)), "notes": m.group(2).strip()}

    return None


async def handle_webhook_message(
    message_text: str,
    room_id: str,
    account_id: str,
    account_name: str,
) -> None:
    """
    Chatwork Webhook で受け取ったメッセージを処理する。
    承認コマンドなら approval_queue を更新し、結果を返信する。
    """
    cmd = parse_command(message_text)
    if not cmd:
        return

    action = cmd["action"]

    if action == "list":
        reply = await _handle_list()
        await send_message(room_id, reply)
        return

    approval_id = cmd["id"]
    notes = cmd.get("notes", "")

    if action == "approve":
        ok, title = await _update_approval(approval_id, "approved", notes)
        reply = f"✅ 承認しました: [{approval_id}] {title}" if ok else f"❌ ID {approval_id} が見つかりません"
    elif action == "reject":
        ok, title = await _update_approval(approval_id, "rejected", notes)
        reply = f"🚫 却下しました: [{approval_id}] {title}" if ok else f"❌ ID {approval_id} が見つかりません"
    elif action == "revise":
        ok, title = await _update_approval(approval_id, "revision_requested", notes)
        reply = f"✏️ 修正依頼を送りました: [{approval_id}] {title}\n→ {notes}" if ok else f"❌ ID {approval_id} が見つかりません"
    else:
        return

    print(f"[chatwork] {account_name} → {action} #{approval_id}")
    await send_message(room_id, reply)


async def _update_approval(approval_id: int, status: str, notes: str) -> tuple[bool, str]:
    """approval_queue を更新する。成功なら (True, title) を返す。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        row = await db.execute_fetchall(
            "SELECT title FROM approval_queue WHERE id=? AND status='pending'",
            (approval_id,)
        )
        if not row:
            return False, ""
        title = row[0]["title"]
        await db.execute(
            """UPDATE approval_queue
               SET status=?, notes=?, resolved_at=datetime('now','localtime')
               WHERE id=?""",
            (status, notes, approval_id)
        )
        await db.commit()
    return True, title


async def _handle_list() -> str:
    """承認待ち一覧を返す。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT id, title, skill_name, requested_at FROM approval_queue WHERE status='pending' ORDER BY id"
        )
    if not rows:
        return "承認待ちの項目はありません ✅"
    lines = ["[承認待ち一覧]"]
    for r in rows:
        lines.append(f"  #{r['id']} {r['title']} ({r['skill_name']}) - {r['requested_at'][:16]}")
    return "\n".join(lines)
