"""T-V3-B-23 / F-017: Workspace token-limit service.

`token_limits` テーブル (supabase/migrations/20260512000000) に対応する upsert /
fetch / enforcement check を提供. workspaces.budget_jpy_monthly とは独立した
USD ベース月次 LLM コスト上限.

## 公開 API

  - set_token_limit(workspace_id, limit_usd_per_month, *, actor_user_id)
        upsert + updated_at 返却
  - get_token_limit(workspace_id) -> dict | None
  - check_workspace_within_limit(workspace_id) -> dict
        {workspace_id, monthly_usd, limit_usd, exceeded, warning_at_80pct}

## AC (T-V3-B-23 / F-017)

  AC-F7 EVENT-DRIVEN  : POST /api/workspaces/{id}/token-limit で limit upsert.
  AC-F8 UNWANTED      : auth 無しは Depends(require_user) で 401.
  AC-F9 UNWANTED      : limit_usd_per_month が number でない / negative なら 422.
  AC-F2 STATE-DRIVEN  : monthly_usd >= limit_usd * 0.8 で cost_limit_warning.
  AC-F3 UNWANTED      : monthly_usd > limit_usd で budget_exceeded (429 / block).

## 設計境界

  - cost_service.monthly_cost() を REUSE (重複実装しない).
  - 失敗時は graceful (raise しない、 None / 0 を返す) — Build-Factory 流.
  - audit event 'cost_limit_updated' を upsert 時に emit (features.json#F-017).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from services import cost_service

logger = logging.getLogger(__name__)


# AC-F2: warning threshold (80% of limit)
WARNING_RATIO = 0.8

# audit events (features.json#F-017 audit_logs)
EVENT_COST_LIMIT_UPDATED = "cost_limit_updated"
EVENT_COST_LIMIT_WARNING = "cost_limit_warning"
EVENT_COST_LIMIT_BREACHED = "cost_limit_breached"

DEFAULT_PROVIDER_KEY = "anthropic"


class InvalidLimitError(ValueError):
    """limit_usd_per_month validation failure (422)."""


class WorkspaceNotFoundError(LookupError):
    """workspace not found (404)."""


@dataclass
class TokenLimit:
    workspace_id: int
    limit_usd_per_month: float
    provider_key: str
    soft_threshold_ratio: float
    is_enforced: bool
    updated_at: str


def _db():
    from db import async_db as aiosqlite
    return aiosqlite


def _db_path():
    from db.queries import DB_PATH
    return DB_PATH


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_limit(value: object) -> float:
    """AC-F9 UNWANTED: limit_usd_per_month must be a non-negative number.

    bool は number として拒否 (Python の True/False は int subclass のため
    明示的に弾く).
    """
    if isinstance(value, bool):
        raise InvalidLimitError(
            "limit_usd_per_month must be a number, got bool"
        )
    if not isinstance(value, (int, float)):
        raise InvalidLimitError(
            f"limit_usd_per_month must be a number, got {type(value).__name__}"
        )
    f = float(value)
    if f < 0:
        raise InvalidLimitError(
            "limit_usd_per_month must be >= 0"
        )
    if f > 1_000_000_000:  # sanity ceiling
        raise InvalidLimitError(
            "limit_usd_per_month must be <= 1,000,000,000"
        )
    return round(f, 4)


async def _workspace_exists(workspace_id: int) -> bool:
    """workspace_id が workspaces テーブルに存在するか.

    failure 時は False (graceful).
    """
    try:
        async with _db().connect(_db_path()) as db:
            cur = await db.execute(
                "SELECT 1 FROM workspaces WHERE id = ? LIMIT 1",
                (workspace_id,),
            )
            rows = await cur.fetchall()
            return bool(rows)
    except Exception as e:
        logger.warning("_workspace_exists failed for %s: %s", workspace_id, e)
        return False


async def set_token_limit(
    workspace_id: int,
    limit_usd_per_month: float,
    *,
    actor_user_id: Optional[str] = None,
    provider_key: str = DEFAULT_PROVIDER_KEY,
) -> dict:
    """AC-F7: upsert workspace token_limit.

    Raises:
        WorkspaceNotFoundError: workspace が存在しない.
        InvalidLimitError: value 検証失敗 (caller で 422 化).

    Returns:
        {limit_usd_per_month, updated_at, workspace_id, provider_key}
    """
    if workspace_id is None or not isinstance(workspace_id, int) or workspace_id <= 0:
        raise InvalidLimitError("workspace_id must be positive int")
    limit = validate_limit(limit_usd_per_month)

    if not await _workspace_exists(workspace_id):
        raise WorkspaceNotFoundError(
            f"workspace not found: {workspace_id}"
        )

    updated_at = _now_iso()
    try:
        async with _db().connect(_db_path()) as db:
            # SQLite 用 upsert. token_limits は impl_integration_ops migration で作成.
            await db.execute(
                """CREATE TABLE IF NOT EXISTS token_limits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workspace_id INTEGER NOT NULL,
                    provider_key TEXT NOT NULL DEFAULT 'anthropic',
                    daily_token_limit INTEGER,
                    monthly_token_limit INTEGER,
                    daily_cost_usd_limit REAL,
                    monthly_cost_usd_limit REAL,
                    soft_threshold_ratio REAL DEFAULT 0.8,
                    is_enforced INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT,
                    UNIQUE(workspace_id, provider_key)
                )"""
            )
            await db.execute(
                """INSERT INTO token_limits
                    (workspace_id, provider_key, monthly_cost_usd_limit,
                     soft_threshold_ratio, is_enforced, updated_at)
                   VALUES (?, ?, ?, ?, 1, ?)
                   ON CONFLICT(workspace_id, provider_key) DO UPDATE SET
                       monthly_cost_usd_limit = excluded.monthly_cost_usd_limit,
                       soft_threshold_ratio = excluded.soft_threshold_ratio,
                       updated_at = excluded.updated_at""",
                (workspace_id, provider_key, limit, WARNING_RATIO, updated_at),
            )
            await db.commit()
    except WorkspaceNotFoundError:
        raise
    except Exception as e:
        logger.warning("set_token_limit failed: %s", e)
        # graceful: 既存挙動と同じく失敗時は raise (caller で 500)
        raise

    await _emit_audit(
        EVENT_COST_LIMIT_UPDATED,
        user_id=actor_user_id,
        detail={
            "workspace_id": workspace_id,
            "limit_usd_per_month": limit,
            "provider_key": provider_key,
        },
    )

    return {
        "workspace_id": workspace_id,
        "provider_key": provider_key,
        "limit_usd_per_month": limit,
        "updated_at": updated_at,
    }


async def get_token_limit(
    workspace_id: int,
    *,
    provider_key: str = DEFAULT_PROVIDER_KEY,
) -> Optional[dict]:
    """workspace の現在の token_limit を返す. 未設定 / failure なら None."""
    try:
        async with _db().connect(_db_path()) as db:
            db.row_factory = _db().Row  # type: ignore[attr-defined]
            cur = await db.execute(
                """SELECT workspace_id, provider_key,
                          monthly_cost_usd_limit AS limit_usd_per_month,
                          soft_threshold_ratio, is_enforced, updated_at
                     FROM token_limits
                    WHERE workspace_id = ? AND provider_key = ?
                    LIMIT 1""",
                (workspace_id, provider_key),
            )
            rows = await cur.fetchall()
    except Exception as e:
        logger.warning("get_token_limit failed: %s", e)
        return None
    if not rows:
        return None
    row = dict(rows[0])
    if row.get("limit_usd_per_month") is None:
        return None
    return {
        "workspace_id": int(row["workspace_id"]),
        "provider_key": row["provider_key"],
        "limit_usd_per_month": float(row["limit_usd_per_month"]),
        "soft_threshold_ratio": float(
            row.get("soft_threshold_ratio") or WARNING_RATIO
        ),
        "is_enforced": bool(row.get("is_enforced", 1)),
        "updated_at": row.get("updated_at"),
    }


async def check_workspace_within_limit(workspace_id: int) -> dict:
    """AC-F2 STATE-DRIVEN + AC-F3 UNWANTED: 月次合計と limit を比較.

    Returns:
        {
            workspace_id,
            monthly_usd,
            limit_usd,
            exceeded: bool,        # AC-F3 (block + 429)
            warning_at_80pct: bool # AC-F2 (notify only)
        }

    limit 未設定なら exceeded=False / warning_at_80pct=False.
    """
    out: dict = {
        "workspace_id": workspace_id,
        "monthly_usd": 0.0,
        "limit_usd": None,
        "exceeded": False,
        "warning_at_80pct": False,
    }
    limit_row = await get_token_limit(workspace_id)
    monthly = await cost_service.monthly_cost(workspace_id)
    out["monthly_usd"] = round(float(monthly), 6)
    if not limit_row:
        return out
    limit_usd = float(limit_row.get("limit_usd_per_month") or 0)
    out["limit_usd"] = limit_usd
    if limit_usd <= 0:
        return out
    if monthly > limit_usd:
        out["exceeded"] = True
        await _emit_audit(
            EVENT_COST_LIMIT_BREACHED,
            user_id=None,
            detail={
                "workspace_id": workspace_id,
                "monthly_usd": out["monthly_usd"],
                "limit_usd": limit_usd,
            },
        )
    elif monthly >= limit_usd * WARNING_RATIO:
        out["warning_at_80pct"] = True
        await _emit_audit(
            EVENT_COST_LIMIT_WARNING,
            user_id=None,
            detail={
                "workspace_id": workspace_id,
                "monthly_usd": out["monthly_usd"],
                "limit_usd": limit_usd,
                "ratio": round(monthly / limit_usd, 4),
            },
        )
    return out


# ──────────────────────────────────────────────────────────────────────
# audit helper
# ──────────────────────────────────────────────────────────────────────


async def _emit_audit(
    event_type: str, *,
    user_id: Optional[str] = None,
    detail: Optional[dict] = None,
) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail or {})
    except Exception as e:
        logger.warning("token_limit audit emit failed: %s -- %s", event_type, e)


def serialize_detail(detail: dict) -> str:
    """JSON encode helper (mainly for tests)."""
    return json.dumps(detail, ensure_ascii=False, default=str)
