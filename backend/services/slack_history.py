"""
slack_history.py — Slack DM の会話履歴を conversation_log にロード/セーブする薄いラッパ。
"""

from db import async_db as aiosqlite

from db.queries import DB_PATH


async def load_recent_history(channel: str, limit: int = 10) -> list[dict]:
    """指定 Slack channel の直近メッセージを古い順で返す（agent向け）。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT role, message FROM conversation_log "
            "WHERE channel = ? ORDER BY created_at DESC LIMIT ?",
            (f"slack_{channel}", limit),
        )
    items = []
    for r in reversed(list(rows)):
        if r["role"] in ("user", "assistant"):
            items.append({"role": r["role"], "content": r["message"]})
    return items


async def save_message(channel: str, who: str, role: str, message: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO conversation_log (channel, role, message, with_employee) "
            "VALUES (?, ?, ?, NULL)",
            (f"slack_{channel}", role, message[:5000]),
        )
        await db.commit()
