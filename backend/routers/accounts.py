"""
accounts.py — Account API

GET    /api/accounts                   user の所属 account 一覧
GET    /api/accounts/{id}              account 詳細
POST   /api/accounts                   新規作成（Owner として登録）
PATCH  /api/accounts/{id}              更新
DELETE /api/accounts/{id}              無効化
GET    /api/accounts/{id}/members      account メンバー一覧
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services import account_service as acc

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
        raise HTTPException(404, f"account not found: {account_id}")
    return a


@router.post("")
async def create_account(body: AccountCreate):
    try:
        return await acc.create_account(
            name=body.name, type=body.type, plan=body.plan,
            owner_user_id=body.owner_user_id,
            billing_email=body.billing_email,
            metadata=body.metadata,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.patch("/{account_id}")
async def update_account(account_id: int, body: AccountUpdate):
    fields = body.model_dump(exclude_unset=True)
    return await acc.update_account(account_id, **fields)


@router.delete("/{account_id}")
async def deactivate_account(account_id: int):
    return await acc.deactivate_account(account_id)


@router.get("/{account_id}/members")
async def list_members(account_id: int):
    return {"members": await acc.list_members(account_id)}
