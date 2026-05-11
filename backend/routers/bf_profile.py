"""T-023-01: Build-Factory profile REST API.

別 router `routers/user_profile_bf.py` を避け、`/api/bf-profile/*` prefix で
company-dashboard の legacy profile router と衝突しないように分離する。

- GET   /api/bf-profile?user_id=...
- PATCH /api/bf-profile?user_id=...   body: display_name / role_text / bio / theme / avatar_url
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.bf_profile import get_profile, upsert_profile


router = APIRouter(prefix="/api/bf-profile", tags=["bf_profile"])


@router.get("")
async def get(user_id: str) -> dict:
    return await get_profile(user_id)


class ProfilePatch(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=120)
    role_text:    Optional[str] = Field(default=None, max_length=120)
    bio:          Optional[str] = Field(default=None, max_length=2000)
    theme:        Optional[str] = Field(default=None)
    avatar_url:   Optional[str] = Field(default=None, max_length=500)


@router.patch("")
async def patch(user_id: str, body: ProfilePatch) -> dict:
    """T-023-01 AC:
      - EVENT: PATCH /api/bf-profile が呼ばれたら dirty fields を upsert
      - UNWANTED: invalid theme → 422 (code=invalid_theme)
    """
    try:
        return await upsert_profile(
            user_id,
            display_name=body.display_name,
            role_text=body.role_text,
            bio=body.bio,
            theme=body.theme,
            avatar_url=body.avatar_url,
        )
    except ValueError as e:
        msg = str(e)
        if msg.startswith("invalid theme"):
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_theme", "message": msg},
            )
        raise HTTPException(400, msg)
