"""
accounts.py — Account API

GET    /api/accounts                              user の所属 account 一覧
GET    /api/accounts/{id}                         account 詳細
POST   /api/accounts                              新規作成（Owner として登録）
PATCH  /api/accounts/{id}                         更新
DELETE /api/accounts/{id}                         無効化
GET    /api/accounts/{id}/members                 account メンバー一覧

T-V3-B-05 (F-004):
POST   /api/accounts/{id}/transfer-owner          owner を別 member に atomic 移譲
POST   /api/accounts/{id}/invitations             account レベル招待発行 (rate-limit 20/h)
DELETE /api/accounts/{id}/members/{user_id}       account member 削除 (owner は不可)
"""

import re as _re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from services import account_service as acc
from services import invitation_service as inv_svc
from services.auth_middleware import require_user

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


# T-V3-B-05: shared error helper (workspaces.py と同じ contract)
def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message}
    )


# T-V3-B-05: shared validators
_EMAIL_RE = _re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ACCOUNT_INVITE_ROLES = ("owner", "admin", "member", "viewer", "guest")


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


# ──────────────────────────────────────────────────────────────────────
# T-V3-B-05 (F-004 / AC-F4 / AC-F1 / AC-F5 / AC-F6): POST .../transfer-owner
# ──────────────────────────────────────────────────────────────────────


class TransferOwnerRequest(BaseModel):
    new_owner_user_id: str = Field(..., min_length=1)


@router.post("/{account_id}/transfer-owner", status_code=201)
async def transfer_owner_route(
    account_id: int,
    body: TransferOwnerRequest,
    user: dict = Depends(require_user),
) -> dict:
    """T-V3-B-05 AC-F4 / AC-F1 / AC-F5 / AC-F6.

    - EVENT-DRIVEN: valid auth + valid input → 201 {old_owner_id, new_owner_id, transferred_at}
    - UNWANTED 409: new_owner_user_id が account member でない
    - UNWANTED 401: 認証ヘッダ無し → require_user dependency が 401 を投げる
    - UNWANTED 422: request body invalid (Pydantic validation)
    """
    # AC-F6 422 fallback (Pydantic constraint で既に弾かれるが明示)
    target = (body.new_owner_user_id or "").strip()
    if not target:
        raise _error(
            "accounts.invalid_new_owner",
            "new_owner_user_id must not be empty",
            status_code=422,
        )
    actor = (user.get("user_metadata") or {}).get("slug") or user.get("sub")

    try:
        result = await acc.transfer_owner(
            account_id, new_owner_user_id=target, actor_user_id=actor
        )
    except acc.AccountNotFoundError as e:
        raise _error("accounts.not_found", str(e), status_code=404)
    except acc.TargetNotAccountMemberError as e:
        # AC-F1: new owner が member でない → 409
        raise _error("accounts.target_not_member", str(e), status_code=409)
    except ValueError as e:
        raise _error("accounts.invalid_request", str(e), status_code=409)
    return result


# ──────────────────────────────────────────────────────────────────────
# T-V3-B-05 (F-004 / AC-F7 / AC-F8 / AC-F9 / AC-F10 / AC-F2): POST .../invitations
# ──────────────────────────────────────────────────────────────────────


class AccountInvitationCreate(BaseModel):
    email: str = Field(..., min_length=1, max_length=254)
    role: str = Field("member", min_length=1)
    expires_in_days: int = Field(7, ge=1, le=90)


@router.post("/{account_id}/invitations", status_code=201)
async def create_account_invitation_route(
    account_id: int,
    body: AccountInvitationCreate,
    user: dict = Depends(require_user),
) -> dict:
    """T-V3-B-05 AC-F7 / AC-F8 / AC-F9 / AC-F10 / AC-F2.

    - EVENT-DRIVEN: valid → 201 {invitation_token, expires_at}
    - UNWANTED 401: 認証ヘッダ無し
    - UNWANTED 422: email format invalid / role invalid / expires_in_days out of range
    - EVENT-DRIVEN 429: 20/hour/account を超えると rate-limit
    """
    # AC-F9: email validation (422)
    email = (body.email or "").strip().lower()
    if not email or not _EMAIL_RE.match(email):
        raise _error(
            "invitations.invalid_email",
            f"email format invalid: {body.email!r}",
            status_code=422,
        )
    # AC-F9: role validation (422)
    role = (body.role or "").strip().lower()
    if role not in _ACCOUNT_INVITE_ROLES:
        raise _error(
            "invitations.invalid_role",
            f"role must be one of {_ACCOUNT_INVITE_ROLES}, got {body.role!r}",
            status_code=422,
        )

    # AC-F2 / AC-F10: rate limit (20 / hour / account)
    allowed, _remaining = inv_svc.check_invitation_rate_limit(account_id)
    if not allowed:
        raise _error(
            "invitations.rate_limited",
            "invitation rate limit exceeded (20/hour/account)",
            status_code=429,
        )

    invited_by = (user.get("user_metadata") or {}).get("slug") or user.get("sub") or ""
    try:
        result = await acc.create_account_invitation(
            account_id,
            email=email,
            role=role,
            invited_by=str(invited_by),
            expires_in_days=body.expires_in_days,
        )
    except acc.AccountNotFoundError as e:
        raise _error("accounts.not_found", str(e), status_code=404)
    except ValueError as e:
        raise _error("invitations.create_failed", str(e), status_code=422)

    await acc._emit_audit(  # type: ignore[attr-defined]
        "accounts.invitation_created",
        user_id=str(invited_by),
        detail={
            "account_id": account_id,
            "email_hash": str(hash(email)),
            "role": role,
        },
    )
    return result


# ──────────────────────────────────────────────────────────────────────
# T-V3-B-05 (F-004 / AC-F11 / AC-F12): DELETE .../members/{user_id}
# ──────────────────────────────────────────────────────────────────────


@router.delete("/{account_id}/members/{user_id}")
async def remove_account_member_route(
    account_id: int,
    user_id: str,
    user: dict = Depends(require_user),
) -> dict:
    """T-V3-B-05 AC-F11 / AC-F12.

    - EVENT-DRIVEN: valid → 200 {removed_at}
    - UNWANTED 401: 認証ヘッダ無し
    - UNWANTED 404: 対象 member が居ない
    - UNWANTED 409: 対象が owner (まず transfer-owner)
    """
    target = (user_id or "").strip()
    if not target:
        raise _error(
            "accounts.invalid_user_id",
            "user_id must not be empty",
            status_code=422,
        )
    actor = (user.get("user_metadata") or {}).get("slug") or user.get("sub")
    try:
        return await acc.remove_account_member(
            account_id, target, actor_user_id=actor
        )
    except acc.CannotRemoveAccountOwnerError as e:
        raise _error("accounts.cannot_remove_owner", str(e), status_code=409)
    except acc.AccountNotFoundError as e:
        raise _error("accounts.not_found", str(e), status_code=404)
