"""T-V3-B-24 / F-018: Audit logs query service.

audit_logs テーブルからの read 専用 service.
trigger による INSERT は migration / services.audit_trigger 側の責務.

Public API:
  - MAX_RANGE_DAYS                 : filter window 上限 (90 日 / AC-F1, AC-F5, AC-F8)
  - AuditLogFilterError            : input validation error (422 にマップ)
  - validate_date_range(from_, to) : range > 90 日で raise
  - normalize_iso(value, field)    : ISO-8601 normalize / raise on invalid
  - list_audit_logs(filter)        : list rows (page = total no pagination cursor in P1)
  - rows_to_csv(rows)              : CSV serializer (RFC 4180 minimal)
  - count_audit_logs(filter)       : total count

設計境界:
  - 既存 db.async_db (psycopg/aiosqlite adapter) を使う.
  - cost_dashboard.py と同様 graceful empty fallback (table 不存在 / 接続失敗).
  - workspace_admin RLS は services.rls_context.set_request_user で session に注入される前提.
  - service 自身は role 判定しない (router 側で require_user / workspace admin check).
"""
from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


# T-V3-B-24 AC-F1 / AC-F5 / AC-F8: >90 日の range は 422 filter_too_broad
MAX_RANGE_DAYS = 90

# T-V3-B-24 default page size (no cursor pagination in Phase 1 — 全件返却 with
# implicit cap. window が 90 日に絞られるので row 数は実用範囲内に収まる).
MAX_ROWS = 10_000


class AuditLogFilterError(RuntimeError):
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
    workspace_id: Optional[int] = None
    from_iso: Optional[str] = None
    to_iso: Optional[str] = None
    user_id: Optional[str] = None
    action: Optional[str] = None


def normalize_iso(value: Optional[str], field: str) -> Optional[str]:
    """ISO-8601 date / datetime を normalize. naive datetime は UTC とみなす.

    Raises AuditLogFilterError on invalid format.
    """
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise AuditLogFilterError(
            "audit_logs.invalid_date",
            f"{field} must be a string, got {type(value).__name__}",
        )
    raw = value.strip()
    if not raw:
        return None
    try:
        # date-only (YYYY-MM-DD) → midnight UTC
        if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
            dt = datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError) as e:
        raise AuditLogFilterError(
            "audit_logs.invalid_date",
            f"{field} must be ISO-8601 (YYYY-MM-DD or full ISO), got {value!r}: {e}",
        )


def _parse_iso_to_dt(iso_value: Optional[str]) -> Optional[datetime]:
    if iso_value is None:
        return None
    return datetime.fromisoformat(iso_value)


def validate_date_range(from_iso: Optional[str], to_iso: Optional[str]) -> None:
    """range > MAX_RANGE_DAYS で AuditLogFilterError (422 filter_too_broad).

    AC-F1 / AC-F5 / AC-F8: >90 days → filter_too_broad.
    片側だけ指定された場合は dual-bound 必須として 422 (filter_too_broad).
    両端 None の場合は OK (default = 直近のみ).
    """
    fd = _parse_iso_to_dt(from_iso)
    td = _parse_iso_to_dt(to_iso)
    if fd is None and td is None:
        return
    if fd is None or td is None:
        raise AuditLogFilterError(
            "audit_logs.filter_too_broad",
            "from and to must both be provided when range is specified",
        )
    if fd > td:
        raise AuditLogFilterError(
            "audit_logs.invalid_date",
            "from must be <= to",
        )
    delta = td - fd
    if delta > timedelta(days=MAX_RANGE_DAYS):
        raise AuditLogFilterError(
            "audit_logs.filter_too_broad",
            f"date range must be <= {MAX_RANGE_DAYS} days (got {delta.days} days)",
        )


def normalize_filter(
    *,
    workspace_id: Optional[int] = None,
    from_: Optional[str] = None,
    to: Optional[str] = None,
    user_id: Optional[str] = None,
    action: Optional[str] = None,
) -> NormalizedFilter:
    """全フィールド検証 + ISO normalize. 422 候補は AuditLogFilterError を raise."""
    if workspace_id is not None and not isinstance(workspace_id, int):
        raise AuditLogFilterError(
            "audit_logs.invalid_filter",
            "workspace_id must be int",
        )
    if user_id is not None and not isinstance(user_id, str):
        raise AuditLogFilterError(
            "audit_logs.invalid_filter",
            "user_id must be str",
        )
    if action is not None and not isinstance(action, str):
        raise AuditLogFilterError(
            "audit_logs.invalid_filter",
            "action must be str",
        )
    from_iso = normalize_iso(from_, "from")
    to_iso = normalize_iso(to, "to")
    validate_date_range(from_iso, to_iso)
    return NormalizedFilter(
        workspace_id=workspace_id,
        from_iso=from_iso,
        to_iso=to_iso,
        user_id=(user_id.strip() if user_id else None),
        action=(action.strip() if action else None),
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


def _build_select_sql(f: NormalizedFilter, *, count_only: bool = False) -> tuple[str, list[Any]]:
    where: list[str] = []
    params: list[Any] = []
    if f.workspace_id is not None:
        where.append("workspace_id = ?")
        params.append(f.workspace_id)
    if f.from_iso is not None:
        where.append("created_at >= ?")
        params.append(f.from_iso)
    if f.to_iso is not None:
        where.append("created_at <= ?")
        params.append(f.to_iso)
    if f.user_id is not None:
        where.append("actor_user_id = ?")
        params.append(f.user_id)
    if f.action is not None:
        where.append("action = ?")
        params.append(f.action)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    if count_only:
        sql = f"SELECT COUNT(*) AS cnt FROM audit_logs{where_sql}"
    else:
        sql = (
            "SELECT id, workspace_id, actor_user_id, actor_persona, "
            "action, resource_type, resource_id, payload, success, created_at "
            f"FROM audit_logs{where_sql} "
            "ORDER BY created_at DESC, id DESC "
            f"LIMIT {MAX_ROWS}"
        )
    return sql, params


async def _safe_fetch_rows(sql: str, params: list[Any]) -> list[dict[str, Any]]:
    """cost_dashboard pattern と同じ graceful fallback. table 不存在 / 接続失敗で空."""
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
        logger.warning("audit_logs fallback to empty: %s", e)
        return []


def _row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    """DB row → API representation (AuditLog schema). created_at は ISO-8601 str."""
    created_at = row.get("created_at")
    if isinstance(created_at, datetime):
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        created_iso: Optional[str] = created_at.astimezone(timezone.utc).isoformat()
    elif created_at is None:
        created_iso = None
    else:
        created_iso = str(created_at)
    payload = row.get("payload") or {}
    if isinstance(payload, str):
        import json
        try:
            payload = json.loads(payload)
        except (ValueError, TypeError):
            payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return {
        "id": int(row.get("id") or 0),
        "workspace_id": (
            int(row["workspace_id"]) if row.get("workspace_id") is not None else None
        ),
        "actor_user_id": row.get("actor_user_id"),
        "actor_persona": row.get("actor_persona"),
        "action": str(row.get("action") or ""),
        "resource_type": row.get("resource_type"),
        "resource_id": (
            int(row["resource_id"]) if row.get("resource_id") is not None else None
        ),
        "payload": payload,
        "success": bool(row.get("success", True)),
        "created_at": created_iso,
    }


async def list_audit_logs(f: NormalizedFilter) -> list[dict[str, Any]]:
    """audit_logs を filter 条件で SELECT. graceful empty fallback.

    AC-F2 / AC-F5 / AC-F8: valid input → items 配列 (空でも 200).
    """
    sql, params = _build_select_sql(f, count_only=False)
    rows = await _safe_fetch_rows(sql, params)
    return [_row_to_dict(r) for r in rows]


async def count_audit_logs(f: NormalizedFilter) -> int:
    sql, params = _build_select_sql(f, count_only=True)
    rows = await _safe_fetch_rows(sql, params)
    if not rows:
        return 0
    return int(rows[0].get("cnt") or 0)


# ──────────────────────────────────────────────────────────────────────
# CSV serializer (RFC 4180 minimal)
# ──────────────────────────────────────────────────────────────────────


CSV_COLUMNS = (
    "id",
    "created_at",
    "workspace_id",
    "actor_user_id",
    "actor_persona",
    "action",
    "resource_type",
    "resource_id",
    "success",
    "payload",
)


def rows_to_csv(rows: list[dict[str, Any]]) -> str:
    """rows を CSV (RFC 4180) に serialize. payload は JSON string で 1 cell に押し込む.

    AC-F5: csv_body string を返す.
    """
    import json
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        payload_str = json.dumps(row.get("payload") or {}, ensure_ascii=False, sort_keys=True)
        writer.writerow(
            [
                row.get("id", ""),
                row.get("created_at", ""),
                row.get("workspace_id", "") if row.get("workspace_id") is not None else "",
                row.get("actor_user_id", "") or "",
                row.get("actor_persona", "") or "",
                row.get("action", "") or "",
                row.get("resource_type", "") or "",
                row.get("resource_id", "") if row.get("resource_id") is not None else "",
                "true" if row.get("success") else "false",
                payload_str,
            ]
        )
    return buf.getvalue()
