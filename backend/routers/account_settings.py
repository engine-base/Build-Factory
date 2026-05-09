"""
account_settings.py — アカウント設定 API

GET    /api/accounts/{id}/settings     設定取得
PATCH  /api/accounts/{id}/settings     部分更新
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Any

from services import account_settings_service as svc

router = APIRouter(prefix="/api/accounts", tags=["account-settings"])


class SettingsPatchBody(BaseModel):
    # すべて Optional で部分更新を許容
    company_name:           Optional[str] = None
    company_name_kana:      Optional[str] = None
    representative_name:    Optional[str] = None
    representative_title:   Optional[str] = None
    postal_code:            Optional[str] = None
    address:                Optional[str] = None
    phone:                  Optional[str] = None
    email:                  Optional[str] = None
    website:                Optional[str] = None

    bank_name:              Optional[str] = None
    bank_branch:            Optional[str] = None
    bank_account_type:      Optional[str] = None
    bank_account_number:    Optional[str] = None
    bank_account_holder:    Optional[str] = None

    logo_url:               Optional[str] = None
    stamp_url:              Optional[str] = None
    stamp_text:             Optional[str] = None
    primary_color:          Optional[str] = None
    secondary_color:        Optional[str] = None
    font_family:            Optional[str] = None

    achievement_stats:      Optional[list] = None
    case_studies:           Optional[list] = None

    payment_terms_default:  Optional[str] = None
    warranty_days:          Optional[int] = None
    monthly_maintenance_yen: Optional[int] = None
    estimate_validity_days: Optional[int] = None
    tax_rate:               Optional[float] = None

    estimate_prefix:        Optional[str] = None
    proposal_prefix:        Optional[str] = None

    default_notes:          Optional[list] = None
    template_config:        Optional[dict] = None


@router.get("/{account_id}/settings")
async def get_account_settings(account_id: int):
    return await svc.get_or_create_default(account_id)


@router.patch("/{account_id}/settings")
async def patch_account_settings(account_id: int, body: SettingsPatchBody):
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if not patch:
        raise HTTPException(400, "no fields to update")
    return await svc.upsert_settings(account_id, patch)


@router.get("/{account_id}/settings/issuer")
async def get_issuer_block(account_id: int):
    """発行者情報のサブセット (HTML テンプレ置換用) を返す。"""
    return await svc.render_issuer_block(account_id)
