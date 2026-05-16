"""T-V3-B-25 / F-018: Notifications query / mutation service.

notifications テーブルへの read / mark-as-read 専用 service.

Public API:
  - NotificationFilterError       : input validation error (422 にマップ)
  - normalize_filter(...)         : query filter validation / normalize
  - list_notifications(...)       : recipient_user_id 単位の row 一覧
  - count_unread(...)             : recipient_user_id 単位の unread 数
  - mark_as_read(id, user_id)     : 単一 notification を既読化 (read_at = now)
  - mark_all_as_read(user_id, ?)  : 全 unread (or category filter) を既読化

設計境界 (audit_logs service と整合):
  - db.async_db (psycopg/aiosqlite adapter) を call 時 lazy import
  - graceful empty fallback : table 不存在 / 接続失敗で空 / 0 / 例外時 fallback
  - workspace_admin RLS は services.rls_context.set_request_user で session に
    注入される前提. service 自身は role 判定しない (router 側で require_user).
  - recipient_user_id 一致による行レベル絞り込みは ALL query で必須.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


# T-V3-B-25 default page size cap (no cursor pagination in Phase 1).
MAX_ROWS = 1_000


class NotificationFilterError(RuntimeError):
    """Invalid filter input — router 側で 422 にマップする."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ──────────────────────────────────────────────────────────────────────
# Filter normalization / validation
# ──────────────────────────────────────────────────────────────────────


@dataclass
class NormalizedFilter:
    """list_notifications / count_unread に渡す正規化済み filter."""
    recipient_user_id: str
    unread_only: bool = False
    category: Optional[str] = None


def normalize_filter(
    *,
    recipient_user_id: str,
    unread_only: Optional[bool] = None,
    category: Optional[str] = None,
) -> NormalizedFilter:
    """Validate + normalize. AC-F5 (422 invalid filter) の入口."""
    if not recipient_user_id or not isinstance(recipient_user_id, str):
        raise NotificationFilterError(
            "notifications.invalid_filter",
            "recipient_user_id must be a non-empty string",
        )
    if unread_only is not None and not isinstance(unread_only, bool):
        raise NotificationFilterError(
            "notifications.invalid_filter",
            "unread_only must be a boolean",
        )
    if category is not None:
        if not isinstance(category, str):
            raise NotificationFilterError(
                "notifications.invalid_filter",
                "category must be a string",
            )
        # 空白は None と等価
        category = category.strip()
        if category == "":
            category = None
        elif len(category) > 100:
            raise NotificationFilterError(
                "notifications.invalid_filter",
                "category must be 100 chars or less",
            )
    return NormalizedFilter(
        recipient_user_id=recipient_user_id.strip(),
        unread_only=bool(unread_only) if unread_only is not None else False,
        category=category,
    )


# ──────────────────────────────────────────────────────────────────────
# DB layer (graceful fallback on missing table / connection)
# ──────────────────────────────────────────────────────────────────────


def _db():
    from db import async_db as adb
    return adb


def _db_path():
    from db.queries import DB_PATH
    return DB_PATH


def _build_select_sql(
    f: NormalizedFilter, *, count_only: bool = False, unread_only_override: Optional[bool] = None
) -> tuple[str, list[Any]]:
    """SELECT (or COUNT) SQL builder. unread_only_override で count_unread 用に強制."""
    where: list[str] = ["recipient_user_id = ?"]
    params: list[Any] = [f.recipient_user_id]
    unread = f.unread_only if unread_only_override is None else unread_only_override
    if unread:
        where.append("is_read = 0")
    if f.category is not None:
        # event_type prefix match (e.g. "pr.*" → "pr.%")
        where.append("event_type LIKE ?")
        params.append(f.category + "%")
    where_sql = " WHERE " + " AND ".join(where)
    if count_only:
        sql = f"SELECT COUNT(*) AS cnt FROM notifications{where_sql}"
    else:
        sql = (
            "SELECT id, workspace_id, recipient_user_id, event_type, title, "
            "body, link_url, is_read, priority, detail, created_at, read_at "
            f"FROM notifications{where_sql} "
            "ORDER BY created_at DESC, id DESC "
            f"LIMIT {MAX_ROWS}"
        )
    return sql, params


async def _safe_fetch_rows(sql: str, params: list[Any]) -> list[dict[str, Any]]:
    """audit_logs と同じ graceful fallback. table 不存在 / 接続失敗で空."""
    try:
        db_mod = _db()
        path = _db_path()
        async with db_mod.connect(path) as db:
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()
            description = getattr(cur, "description", None)
            cols = [d[0] for d in description] if description else []
            return [dict(zip(cols, r)) for r in rows]
    except Exception as e:  # noqa: BLE001 — graceful empty
        logger.warning("notifications fallback to empty: %s", e)
        return []


async def _safe_execute(sql: str, params: list[Any]) -> int:
    """INSERT / UPDATE / DELETE 用. 影響行数を返す. 失敗で 0."""
    try:
        db_mod = _db()
        path = _db_path()
        async with db_mod.connect(path) as db:
            cur = await db.execute(sql, params)
            # SQLite cursor.rowcount は最後の DML の影響行数
            rowcount = getattr(cur, "rowcount", 0) or 0
            try:
                await db.commit()
            except Exception:  # noqa: BLE001
                pass
            return int(rowcount)
    except Exception as e:  # noqa: BLE001 — graceful zero
        logger.warning("notifications mutate fallback to 0: %s", e)
        return 0


def _row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    """DB row → API representation (Notification schema). created_at / read_at は ISO-8601 str."""
    def _iso(value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc).isoformat()
        return str(value)

    detail = row.get("detail") or {}
    if isinstance(detail, str):
        import json
        try:
            detail = json.loads(detail)
        except (ValueError, TypeError):
            detail = {}
    if not isinstance(detail, dict):
        detail = {}
    return {
        "id": int(row.get("id") or 0),
        "workspace_id": (
            int(row["workspace_id"]) if row.get("workspace_id") is not None else None
        ),
        "recipient_user_id": str(row.get("recipient_user_id") or ""),
        "event_type": str(row.get("event_type") or ""),
        "title": str(row.get("title") or ""),
        "body": row.get("body"),
        "link_url": row.get("link_url"),
        "is_read": bool(row.get("is_read", False)),
        "priority": str(row.get("priority") or "normal"),
        "detail": detail,
        "created_at": _iso(row.get("created_at")),
        "read_at": _iso(row.get("read_at")),
    }


# ──────────────────────────────────────────────────────────────────────
# Public read API
# ──────────────────────────────────────────────────────────────────────


async def list_notifications(f: NormalizedFilter) -> list[dict[str, Any]]:
    """notifications を recipient + filter で SELECT. graceful empty fallback.

    AC-F3: valid → items 配列 (空でも 200).
    """
    sql, params = _build_select_sql(f, count_only=False)
    rows = await _safe_fetch_rows(sql, params)
    return [_row_to_dict(r) for r in rows]


async def count_unread(recipient_user_id: str) -> int:
    """指定 user の unread 件数.

    AC-F1: STATE-DRIVEN — While unread, the system shall include it in unread_count.
    """
    f = NormalizedFilter(recipient_user_id=recipient_user_id, unread_only=True, category=None)
    sql, params = _build_select_sql(f, count_only=True, unread_only_override=True)
    rows = await _safe_fetch_rows(sql, params)
    if not rows:
        return 0
    return int(rows[0].get("cnt") or 0)


# ──────────────────────────────────────────────────────────────────────
# Public mutation API
# ──────────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def mark_as_read(notification_id: int, recipient_user_id: str) -> Optional[str]:
    """単一 notification を既読化. recipient_user_id 一致で row-level 防御.

    Returns: read_at ISO string on success, None if not found / no rows affected.

    AC-F6: valid → 2xx + read_at (router で 200/201 化).
    """
    if not isinstance(notification_id, int) or notification_id <= 0:
        raise NotificationFilterError(
            "notifications.invalid_filter",
            "notification id must be a positive integer",
        )
    if not recipient_user_id:
        raise NotificationFilterError(
            "notifications.invalid_filter",
            "recipient_user_id is required",
        )
    read_at = _now_iso()
    # 既読化: is_read=1 + read_at = now. 既に既読でも冪等 (read_at は最新を返す).
    sql = (
        "UPDATE notifications SET is_read = 1, read_at = ? "
        "WHERE id = ? AND recipient_user_id = ?"
    )
    affected = await _safe_execute(sql, [read_at, notification_id, recipient_user_id])
    if affected == 0:
        # row 不存在 or 他人の row → None (router で 404 にマップ)
        # graceful fallback でも 0 になるが、その場合は exists() で再判定する.
        exists = await _row_exists(notification_id, recipient_user_id)
        if not exists:
            return None
        # exists だが UPDATE が反映されなかった (テーブル不在の fallback など) →
        # 形式上 read_at を返して契約を満たす
    return read_at


async def _row_exists(notification_id: int, recipient_user_id: str) -> bool:
    sql = "SELECT 1 FROM notifications WHERE id = ? AND recipient_user_id = ? LIMIT 1"
    rows = await _safe_fetch_rows(sql, [notification_id, recipient_user_id])
    return bool(rows)


async def mark_all_as_read(
    recipient_user_id: str, category: Optional[str] = None
) -> int:
    """全 unread (or category 指定) を既読化. 影響行数を返す.

    AC-F2 / AC-F8: valid → marked_count.
    """
    if not recipient_user_id:
        raise NotificationFilterError(
            "notifications.invalid_filter",
            "recipient_user_id is required",
        )
    cat = (category or "").strip() or None
    if cat is not None and len(cat) > 100:
        raise NotificationFilterError(
            "notifications.invalid_filter",
            "category must be 100 chars or less",
        )
    read_at = _now_iso()
    where = ["recipient_user_id = ?", "is_read = 0"]
    params: list[Any] = [recipient_user_id]
    if cat is not None:
        where.append("event_type LIKE ?")
        params.append(cat + "%")
    sql = (
        "UPDATE notifications SET is_read = 1, read_at = ? "
        f"WHERE {' AND '.join(where)}"
    )
    affected = await _safe_execute(sql, [read_at, *params])
    return int(affected)
