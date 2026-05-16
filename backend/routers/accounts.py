"""
accounts.py — Account API

GET    /api/accounts                   user の所属 account 一覧
GET    /api/accounts/{id}              account 詳細
POST   /api/accounts                   新規作成（Owner として登録）
PATCH  /api/accounts/{id}              更新
DELETE /api/accounts/{id}              無効化
GET    /api/accounts/{id}/members      account メンバー一覧
GET    /api/accounts/{id}/dashboard    account ダッシュボード (T-V3-B-27 / F-024)
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from services import account_service as acc
from services import account_dashboard as acc_dash
from services.auth_middleware import require_user

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


class AccountCreate(BaseModel):
    name: str
    type: str = "individual"            # company / individual
    plan: str = "free"
    owner_user_id: str = "masato"
    billing_email: Optional[str] = None
    metadata: Optional[dict] = None


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    plan: Optional[str] = None
    billing_email: Optional[str] = None
    metadata: Optional[dict] = None


@router.get("")
async def list_my_accounts(user_id: str = Query("masato")):
    return {"accounts": await acc.list_accounts(user_id)}


@router.get("/{account_id}")
async def get_account(account_id: int):
    a = await acc.get_account(account_id)
    if not a:
        raise HTTPException(
            status_code=404,
            detail={"code": "account_not_found", "message": f"account not found: {account_id}"},
        )
    return a


@router.post("")
async def create_account(body: AccountCreate):
    """T-004-01: account 新規作成 (creator = owner として member 登録).

    Error contract (AC-4): {detail: {code, message}}
      400 invalid_account_type / invalid_plan / invalid_name / invalid_request
    """
    # AC-4 UNWANTED: 名前空 reject (Pydantic より明確なメッセージで)
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_name", "message": "account name must not be empty"},
        )
    if body.type not in ("individual", "company"):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_account_type",
                "message": f"type must be 'individual' or 'company', got {body.type!r}",
            },
        )
    if body.plan not in ("free", "pro", "enterprise"):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_plan",
                "message": f"plan must be 'free' / 'pro' / 'enterprise', got {body.plan!r}",
            },
        )
    try:
        return await acc.create_account(
            name=name, type=body.type, plan=body.plan,
            owner_user_id=body.owner_user_id,
            billing_email=body.billing_email,
            metadata=body.metadata,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_request", "message": str(e)},
        )


@router.patch("/{account_id}")
async def update_account(account_id: int, body: AccountUpdate):
    fields = body.model_dump(exclude_unset=True)
    if "type" in fields and fields["type"] not in ("individual", "company"):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_account_type",
                "message": f"type must be 'individual' or 'company', got {fields['type']!r}",
            },
        )
    if "plan" in fields and fields["plan"] not in ("free", "pro", "enterprise"):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "invalid_plan",
                "message": f"plan must be 'free' / 'pro' / 'enterprise', got {fields['plan']!r}",
            },
        )
    try:
        return await acc.update_account(account_id, **fields)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_request", "message": str(e)},
        )


@router.delete("/{account_id}")
async def deactivate_account(account_id: int):
    return await acc.deactivate_account(account_id)


@router.get("/{account_id}/members")
async def list_members(account_id: int):
    return {"members": await acc.list_members(account_id)}


# ─────────────────────────────────────────────────────────────────────
# T-V3-B-27 / F-024: GET /api/accounts/{id}/dashboard
# ─────────────────────────────────────────────────────────────────────
#
# EARS AC mapping (T-V3-B-27):
#   AC-F4  EVENT-DRIVEN : aggregate KPI across all workspaces the caller
#                         belongs to within the account.
#   AC-F8  EVENT-DRIVEN : 2xx response matches openapi.yaml#/api/accounts/
#                         {id}/dashboard (workspaces + kpi).
#   AC-F9  UNWANTED     : missing / invalid auth -> 401 (require_user).
#   AC-F10 UNWANTED     : path/body validation failure -> 422 (field map).
#
# Error responses follow the same {detail: {code, message, errors?}} shape used
# by the rest of accounts.py.

def _resolve_user_key(user: dict) -> str:
    return (
        user.get("sub")
        or (user.get("user_metadata") or {}).get("slug")
        or user.get("email")
        or "anonymous"
    )


@router.get("/{account_id}/dashboard")
async def get_accounts_by_id_dashboard(
    account_id: int,
    user: dict = Depends(require_user),
):
    """T-V3-B-27 / F-024: Per-account dashboard.

    Status codes:
      200 — {account_id, workspaces, kpi, computed_at, duration_ms}
      401 — handled by require_user.
      403 — caller is not a member of the account.
      404 — account does not exist.
      422 — account_id invariant violation.
    """
    if not isinstance(account_id, int) or account_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "validation_error",
                "message": "account_id must be a positive integer",
                "errors": {"id": "must be a positive integer"},
            },
        )
    user_key = _resolve_user_key(user)
    try:
        return await acc_dash.get_account_dashboard(account_id, user_id=user_key)
    except acc_dash.AccountNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "account_not_found", "message": str(e)},
        )
    except acc_dash.AccountForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "forbidden", "message": str(e)},
        )
    except acc_dash.AccountDashboardError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "validation_error",
                "message": str(e),
                "errors": {"id": str(e)},
            },
        )
