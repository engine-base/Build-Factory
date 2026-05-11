"""T-023-05: クローン opt-in + GDPR 削除権 (30 日 grace)

ADR-005 / CLAUDE.md §3 で GDPR 削除権を確保する義務がある。
本サービスは:
  1. clone opt-in: ユーザーが「自分の persona / 会話を AI 社員のクローン作成に
     使ってよいか」を toggle で管理 (default OFF)
  2. deletion request: 削除リクエストを記録し 30 日 grace 後に確定実行

実物のデータ消去 (Mem0 / Obsidian / chat_messages / staff / sessions) は
別バッチで execute_after を過ぎた pending を拾って削除する想定。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional


def _db():
    from db import async_db as aiosqlite
    return aiosqlite


def _db_path():
    from db.queries import DB_PATH
    return DB_PATH


# ──────────────────────────────────────────
# Clone opt-in toggle
# ──────────────────────────────────────────

async def set_clone_optin(user_id: str, opted_in: bool) -> dict:
    """opt-in toggle を切り替える。default OFF。"""
    try:
        async with _db().connect(_db_path()) as db:
            now_col = "opted_in_at" if opted_in else "opted_out_at"
            await db.execute(
                f"""INSERT INTO user_clone_optin (user_id, opted_in, {now_col})
                    VALUES (?, ?, datetime('now','localtime'))
                    ON CONFLICT(user_id) DO UPDATE SET
                      opted_in = excluded.opted_in,
                      {now_col} = excluded.{now_col},
                      updated_at = datetime('now','localtime')""",
                (user_id, 1 if opted_in else 0),
            )
            await db.commit()
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
    return {"ok": True, "user_id": user_id, "opted_in": opted_in}


async def get_clone_optin(user_id: str) -> bool:
    """opt-in 状態を取得。未登録時は default OFF (False)。"""
    try:
        async with _db().connect(_db_path()) as db:
            db.row_factory = _db().Row
            cur = await db.execute(
                "SELECT opted_in FROM user_clone_optin WHERE user_id = ?",
                (user_id,),
            )
            row = await cur.fetchone()
    except Exception:
        return False
    if not row:
        return False
    return bool(dict(row).get("opted_in"))


# ──────────────────────────────────────────
# GDPR deletion request (30 日 grace)
# ──────────────────────────────────────────

GRACE_DAYS = 30


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _execute_after(days: int = GRACE_DAYS) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


async def request_deletion(user_id: str, *, reason: Optional[str] = None,
                           grace_days: int = GRACE_DAYS) -> dict:
    """削除リクエストを記録し execute_after を返す (30 日 grace)。"""
    execute_after = _execute_after(grace_days)
    try:
        async with _db().connect(_db_path()) as db:
            cur = await db.execute(
                """INSERT INTO user_deletion_requests (user_id, status, execute_after, reason)
                   VALUES (?, 'pending', ?, ?)""",
                (user_id, execute_after, reason),
            )
            await db.commit()
            req_id = cur.lastrowid or 0
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
    return {
        "ok": True,
        "request_id": req_id,
        "user_id": user_id,
        "execute_after": execute_after,
        "grace_days": grace_days,
    }


async def cancel_deletion(request_id: int) -> bool:
    """削除リクエストをキャンセル (grace 期間内のみ)。"""
    try:
        async with _db().connect(_db_path()) as db:
            cur = await db.execute(
                """UPDATE user_deletion_requests
                      SET status = 'cancelled',
                          cancelled_at = datetime('now','localtime')
                    WHERE id = ? AND status = 'pending'""",
                (request_id,),
            )
            await db.commit()
            return (cur.rowcount or 0) > 0
    except Exception:
        return False


async def list_pending_deletions(*, due_only: bool = False) -> list[dict]:
    """pending な削除リクエスト一覧 (due_only=True なら execute_after を過ぎたもの)。"""
    try:
        async with _db().connect(_db_path()) as db:
            db.row_factory = _db().Row
            if due_only:
                sql = ("SELECT * FROM user_deletion_requests "
                       "WHERE status = 'pending' AND execute_after <= datetime('now','localtime') "
                       "ORDER BY execute_after ASC")
            else:
                sql = ("SELECT * FROM user_deletion_requests "
                       "WHERE status = 'pending' ORDER BY execute_after ASC")
            cur = await db.execute(sql)
            rows = await cur.fetchall()
    except Exception:
        return []
    return [dict(r) for r in rows]


async def execute_due_deletions(*, dry_run: bool = False) -> dict:
    """execute_after を過ぎた pending を確定実行 (実 data 消去は別 worker、
    本関数は status を 'executed' に遷移するだけ)。"""
    due = await list_pending_deletions(due_only=True)
    if dry_run:
        return {"would_execute": len(due), "ids": [d["id"] for d in due]}
    if not due:
        return {"executed": 0}
    try:
        async with _db().connect(_db_path()) as db:
            for d in due:
                await db.execute(
                    """UPDATE user_deletion_requests
                          SET status = 'executed',
                              executed_at = datetime('now','localtime')
                        WHERE id = ?""",
                    (d["id"],),
                )
            await db.commit()
    except Exception as e:
        return {"executed": 0, "error": str(e)[:200]}
    return {"executed": len(due), "ids": [d["id"] for d in due]}
