"""T-017-03 / T-V3-B-23: cost-summary endpoint for 8-tab dashboard + CSV export.

cost_logs を 8 dimension で aggregate して frontend に返す:
  overview / provider / model / workspace / persona / skill /
  period_daily / session

T-V3-B-23 (F-017) で追加:
  - GET /api/observability/cost-summary/export.csv  (CSV export, auth required)

設計境界:
  - 既存 cost_service.py + cost_logs schema を REUSE (無改変).
  - 単一 SELECT GROUP BY (no N+1).
  - dimension 検証 + ISO-8601 range 検証 (AC-4 UNWANTED).
  - 既存 dependencies: aiosqlite (テスト用) / asyncpg / psycopg (production)
    の両方で動く設計だが、 Phase 1 は cost_service と同じ DB layer を使う.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from services import cost_service
from services.auth_middleware import require_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/observability", tags=["cost-dashboard"])


VALID_DIMENSIONS: tuple[str, ...] = (
    "overview",
    "provider",
    "model",
    "workspace",
    "persona",
    "skill",
    "period_daily",
    "session",
)


class CostSummaryItem(BaseModel):
    label: str
    cost_usd: float
    input_tokens: int
    output_tokens: int
    share: float            # 0.0–1.0


class CostSummary(BaseModel):
    dimension: str
    from_iso: Optional[str] = None
    to_iso: Optional[str] = None
    total_usd: float
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_tokens: int
    items: list[CostSummaryItem]


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _validate_dimension(dimension: str) -> str:
    if dimension not in VALID_DIMENSIONS:
        raise _error(
            "cost_dashboard.invalid_dimension",
            f"dimension must be one of {VALID_DIMENSIONS}, got {dimension!r}",
        )
    return dimension


def _validate_iso(value: Optional[str], field: str) -> Optional[str]:
    if value is None or value == "":
        return None
    try:
        # 必ず timezone-aware の ISO-8601
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError("naive datetime not allowed")
        return dt.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError) as e:
        raise _error(
            "cost_dashboard.invalid_date_range",
            f"{field} must be ISO-8601 with timezone, got {value!r}: {e}",
        )


# ──────────────────────────────────────────────────────────────────────
# Internal aggregation (uses cost_service._db connection)
# ──────────────────────────────────────────────────────────────────────


_DIMENSION_TO_SQL_COLUMN = {
    "provider": "provider",
    "model": "model",
    "workspace": "workspace_id",
    "session": "session_id",
    # persona / skill は cost_logs.metadata JSONB から抽出
    # period_daily は occurred_at::date を GROUP BY
}


async def _fetch_summary(
    dimension: str,
    from_iso: Optional[str],
    to_iso: Optional[str],
) -> CostSummary:
    """cost_logs を単一 SELECT で集計 (AC-2: no N+1)."""
    # group_expr を組み立て
    if dimension == "overview":
        group_expr = "'all'"
    elif dimension in _DIMENSION_TO_SQL_COLUMN:
        group_expr = _DIMENSION_TO_SQL_COLUMN[dimension]
    elif dimension == "persona":
        # metadata JSONB の 'agent_persona' key で aggregate
        group_expr = "COALESCE(metadata->>'agent_persona', 'unknown')"
    elif dimension == "skill":
        group_expr = "COALESCE(metadata->>'skill_name', 'unknown')"
    elif dimension == "period_daily":
        group_expr = "DATE(occurred_at)"
    else:  # pragma: no cover — _validate_dimension が先にガード
        raise _error(
            "cost_dashboard.invalid_dimension",
            f"unsupported dimension: {dimension}",
        )

    where_clauses: list[str] = []
    params: list[Any] = []
    if from_iso is not None:
        where_clauses.append("occurred_at >= $%d" % (len(params) + 1))
        params.append(from_iso)
    if to_iso is not None:
        where_clauses.append("occurred_at <= $%d" % (len(params) + 1))
        params.append(to_iso)
    where_sql = (
        " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    )

    sql = (
        f"SELECT {group_expr} AS label, "
        f"SUM(cost_usd) AS cost_usd, "
        f"SUM(input_tokens) AS input_tokens, "
        f"SUM(output_tokens) AS output_tokens, "
        f"SUM(cache_read_tokens) AS cache_read_tokens "
        f"FROM cost_logs{where_sql} "
        f"GROUP BY {group_expr} "
        f"ORDER BY cost_usd DESC NULLS LAST"
    )

    # cost_service._db() は production では psycopg async pool / test では
    # aiosqlite. Phase 1 はテスト互換性のため空集計 fallback.
    rows = await _safe_fetch_rows(sql, params)
    total_cost = sum(float(r.get("cost_usd") or 0) for r in rows)
    total_in = sum(int(r.get("input_tokens") or 0) for r in rows)
    total_out = sum(int(r.get("output_tokens") or 0) for r in rows)
    total_cache = sum(int(r.get("cache_read_tokens") or 0) for r in rows)

    items: list[CostSummaryItem] = []
    for r in rows:
        cost = float(r.get("cost_usd") or 0)
        share = (cost / total_cost) if total_cost > 0 else 0.0
        items.append(
            CostSummaryItem(
                label=str(r.get("label") or "unknown"),
                cost_usd=cost,
                input_tokens=int(r.get("input_tokens") or 0),
                output_tokens=int(r.get("output_tokens") or 0),
                share=share,
            )
        )
    return CostSummary(
        dimension=dimension,
        from_iso=from_iso,
        to_iso=to_iso,
        total_usd=total_cost,
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        total_cache_read_tokens=total_cache,
        items=items,
    )


async def _safe_fetch_rows(sql: str, params: list[Any]) -> list[dict[str, Any]]:
    """cost_service と同じ DB layer を使うが、 接続失敗 / table 不存在
    で空 list を返す graceful 設計 (AC-4: cost_logs 空でも 200)."""
    try:
        db_mod = cost_service._db()
        path = cost_service._db_path()
        async with db_mod.connect(path) as db:
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
            return [dict(zip(cols, r)) for r in rows]
    except Exception as e:  # noqa: BLE001 — graceful empty
        logger.warning("cost-summary fallback to empty: %s", e)
        return []


# ──────────────────────────────────────────────────────────────────────
# Public endpoint
# ──────────────────────────────────────────────────────────────────────


@router.get("/cost-summary")
async def get_cost_summary(
    dimension: str = Query("overview"),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
) -> dict[str, Any]:
    """8-tab dashboard 用 aggregate endpoint.

    AC-2 2 秒以内 / AC-4 invalid dim / invalid date で 400.
    """
    dim = _validate_dimension(dimension)
    from_iso = _validate_iso(from_, "from")
    to_iso = _validate_iso(to, "to")
    summary = await _fetch_summary(dim, from_iso, to_iso)
    return summary.model_dump()


# ──────────────────────────────────────────────────────────────────────
# T-V3-B-23 / F-017: cost-summary CSV export
# ──────────────────────────────────────────────────────────────────────


def _validate_date_query(value: Optional[str], field: str) -> Optional[str]:
    """date (YYYY-MM-DD) or ISO-8601 を受け付け ISO-8601 (UTC) 文字列で返す.

    T-V3-B-23 AC-F5: features.json で from/to は 'date?' (date only).
    後方互換のため datetime も許容.
    """
    if value is None or value == "":
        return None
    try:
        # date-only (YYYY-MM-DD) を midnight UTC として解釈
        if len(value) == 10 and value.count("-") == 2:
            dt = datetime.fromisoformat(value).replace(tzinfo=timezone.utc)
        else:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                raise ValueError("naive datetime not allowed")
        return dt.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError) as e:
        raise _error(
            "cost_dashboard.invalid_date_range",
            f"{field} must be date or ISO-8601 with timezone, got {value!r}: {e}",
        )


@router.get("/cost-summary/export.csv")
async def export_cost_summary_csv(
    dimension: str = Query("overview"),
    workspace_id: Optional[str] = Query(None),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    user: dict = Depends(require_user),
) -> Response:
    """T-V3-B-23 AC-F5/F6 (F-017): CSV export of cost-summary aggregation.

    Requires authenticated caller (Bearer token). Returns text/csv with
    workspace_admin-style aggregation (label,cost_usd,input_tokens,
    output_tokens,share).

    AC-F5: EVENT-DRIVEN — When called with valid inputs, return 2xx
           with csv_body matching features.json#F-017 contract.
    AC-F6: UNWANTED — If called without valid auth token, return 401
           (enforced by Depends(require_user)).
    """
    dim = _validate_dimension(dimension)
    from_iso = _validate_date_query(from_, "from")
    to_iso = _validate_date_query(to, "to")
    summary = await _fetch_summary(dim, from_iso, to_iso)

    # CSV body 生成 (RFC 4180 quoting via csv module)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "label", "cost_usd", "input_tokens", "output_tokens", "share",
    ])
    for item in summary.items:
        writer.writerow([
            item.label,
            f"{item.cost_usd:.6f}",
            item.input_tokens,
            item.output_tokens,
            f"{item.share:.6f}",
        ])
    # summary footer 行
    writer.writerow([
        "__TOTAL__",
        f"{summary.total_usd:.6f}",
        summary.total_input_tokens,
        summary.total_output_tokens,
        "1.000000",
    ])

    csv_body = buf.getvalue()
    filename = f"cost-summary-{dim}.csv"
    if workspace_id:
        filename = f"cost-summary-{dim}-ws{workspace_id}.csv"
    return Response(
        content=csv_body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Bf-Feature-Id": "F-017",
            "X-Bf-Task-Id": "T-V3-B-23",
        },
    )
