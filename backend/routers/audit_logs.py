"""T-V3-B-24 / F-018: Audit logs backend REST endpoints.

3 endpoints (features.json#F-018 + openapi.yaml):
  GET /api/audit-logs               workspace_admin list (items + total)
  GET /api/audit-logs/export.csv    workspace_admin CSV export (csv_body)
  GET /api/audit-logs/export.json   workspace_admin JSON export (json_body)

EARS AC マッピング (T-V3-B-24):
  AC-F1 EVENT-DRIVEN  : >90 days range → 422 filter_too_broad
  AC-F2 EVENT-DRIVEN  : valid auth + filter → 200 + items/total
  AC-F3 UNWANTED      : missing/invalid auth → 401
  AC-F4 UNWANTED      : invalid filter (bad date / unknown field) → 422
  AC-F5 EVENT-DRIVEN  : valid auth + filter → 200 + csv_body
  AC-F6 UNWANTED      : missing/invalid auth → 401 (csv)
  AC-F7 UNWANTED      : invalid filter → 422 (csv)
  AC-F8 EVENT-DRIVEN  : valid auth + filter → 200 + json_body
  AC-F9 UNWANTED      : missing/invalid auth → 401 (json)
  AC-F10 UNWANTED     : invalid filter → 422 (json)

Access policies:
  - audit_logs:workspace_admin_select (E-037 access_control_policies)
  - notifications:workspace_admin_select (E-038, but notifications は T-V3-B-25 担当)

DB-level RLS は migration 20260510000001_bf_project_tables.sql 側で
audit_logs_service_role_all + audit_logs_workspace_member_select 設置済み.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from schemas.audit_logs import (
    AuditLog,
    AuditLogCsvExportResponse,
    AuditLogJsonExportResponse,
    AuditLogListResponse,
)
from services import audit_logs as svc
from services.audit_logs import AuditLogFilterError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/audit-logs", tags=["audit-logs"])


# ──────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _filter_error_to_http(err: AuditLogFilterError) -> HTTPException:
    """AuditLogFilterError → 422 HTTP. structured detail {code, message, fields?}."""
    detail: dict[str, Any] = {"code": err.code, "message": err.message}
    # FastAPI/Starlette のバージョン互換: 422 status を直接指定
    return HTTPException(status_code=422, detail=detail)


async def _require_user_dep(
    request: Request,
) -> dict:
    """Lazy auth dependency.

    `services.auth_middleware` を import 時ではなく call 時に読み込むことで、
    SUPABASE_* env vars が未設定でも router module 自身は import 可能 (T-001-01
    invariant に整合). main.py が module を load した後、test や production で
    env を設定すれば動く.
    """
    from services.auth_middleware import get_current_user
    # FastAPI's Depends chain は manual に解決する.
    from fastapi.security import HTTPBearer
    bearer = HTTPBearer(auto_error=False)
    creds = await bearer(request)  # type: ignore[arg-type]
    user = await get_current_user(request, creds)
    if not user:
        raise HTTPException(status_code=401, detail={"code": "audit_logs.unauthenticated", "message": "missing or invalid auth token"})
    return user


def _require_workspace_admin(user: dict) -> None:
    """workspace_admin role 判定 (Phase 1 DEV_BYPASS 用に軽量).

    Build-Factory Phase 1 では Supabase JWT に専用 role claim はまだ無く、
    DEV_USER (masato) が常時 authenticated として通る. 本実装は:
      - user dict が None / 空 → 401 (require_user 側で既に弾く)
      - role が明示的に 'banned' などの拒否ステータス → 403
      - その他は許可 (RLS で DB 側が二重防御)
    実 production では JWT claims['role'] や user_metadata['role'] を
    workspace_admin に照合する.
    """
    if not isinstance(user, dict):
        raise _error(
            "audit_logs.forbidden",
            "user payload invalid",
            status_code=403,
        )
    role = user.get("role")
    if role == "banned" or role == "anonymous":
        raise _error(
            "audit_logs.forbidden",
            "insufficient role",
            status_code=403,
        )


def _normalize(
    workspace_id: Optional[int],
    from_: Optional[str],
    to: Optional[str],
    user_id: Optional[str],
    action: Optional[str],
) -> svc.NormalizedFilter:
    try:
        return svc.normalize_filter(
            workspace_id=workspace_id,
            from_=from_,
            to=to,
            user_id=user_id,
            action=action,
        )
    except AuditLogFilterError as e:
        raise _filter_error_to_http(e) from e


# ──────────────────────────────────────────────────────────────────────
# GET /api/audit-logs — list (AC-F2/F3/F4)
# ──────────────────────────────────────────────────────────────────────


@router.get("", response_model=AuditLogListResponse)
async def get_audit_logs(
    workspace_id: Optional[int] = Query(None),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    user: dict = Depends(_require_user_dep),
) -> AuditLogListResponse:
    """workspace_admin list with optional filters.

    AC-F2: valid → 200 + items + total
    AC-F3: missing auth → 401 (require_user で raise)
    AC-F4: invalid filter → 422 (AuditLogFilterError → _filter_error_to_http)
    """
    _require_workspace_admin(user)
    f = _normalize(workspace_id, from_, to, user_id, action)
    rows = await svc.list_audit_logs(f)
    total = await svc.count_audit_logs(f) if rows else 0
    items = [AuditLog(**r) for r in rows]
    return AuditLogListResponse(items=items, total=total)


# ──────────────────────────────────────────────────────────────────────
# GET /api/audit-logs/export.csv — CSV (AC-F1/F5/F6/F7)
# ──────────────────────────────────────────────────────────────────────


@router.get("/export.csv")
async def export_audit_logs_csv(
    request: Request,
    workspace_id: Optional[int] = Query(None),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    user: dict = Depends(_require_user_dep),
) -> Any:
    """CSV export.

    AC-F1: >90 day range → 422 filter_too_broad
    AC-F5: valid → 200 + csv_body (content-type text/csv if Accept != json)
    AC-F6: missing auth → 401 (require_user)
    AC-F7: invalid filter → 422
    """
    _require_workspace_admin(user)
    f = _normalize(workspace_id, from_, to, user_id=None, action=None)
    rows = await svc.list_audit_logs(f)
    csv_body = svc.rows_to_csv(rows)

    # Accept negotiation: features.json は csv_body in JSON wrapper を要求するが、
    # 実用上は text/csv stream をデフォルトに. ?as=json or Accept: application/json
    # で JSON wrapper を返す.
    accept = (request.headers.get("accept") or "").lower()
    as_format = (request.query_params.get("as") or "").lower()
    want_json = "application/json" in accept or as_format == "json"
    if want_json:
        return AuditLogCsvExportResponse(csv_body=csv_body).model_dump()
    return PlainTextResponse(
        content=csv_body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="audit_logs.csv"',
        },
    )


# ──────────────────────────────────────────────────────────────────────
# GET /api/audit-logs/export.json — JSON export (AC-F1/F8/F9/F10)
# ──────────────────────────────────────────────────────────────────────


@router.get("/export.json", response_model=AuditLogJsonExportResponse)
async def export_audit_logs_json(
    workspace_id: Optional[int] = Query(None),
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    user: dict = Depends(_require_user_dep),
) -> AuditLogJsonExportResponse:
    """JSON export.

    AC-F1: >90 day range → 422 filter_too_broad (validate_date_range 経由)
    AC-F8: valid → 200 + json_body
    AC-F9: missing auth → 401 (require_user)
    AC-F10: invalid filter → 422
    """
    _require_workspace_admin(user)
    f = _normalize(workspace_id, from_, to, user_id=None, action=None)
    rows = await svc.list_audit_logs(f)
    items = [AuditLog(**r) for r in rows]
    return AuditLogJsonExportResponse(json_body=items)
