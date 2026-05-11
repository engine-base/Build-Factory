"""T-023-01: Build-Factory user_profiles 読み書き service.

別ファイル services/user_profile.py は company-dashboard 由来の legacy で
スキーマも別 (user_profile)。本 service は Build-Factory の T-023-01 用に
新規導入した `user_profiles` テーブル (migration c7d8e9f0a1b2) を扱う。

Phase 1 scope: 1 user = 1 profile row (display_name / role_text / bio / theme / avatar_url)。
Phase 2 で workspace 単位の visible profile を追加予定。
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _db():
    from db import async_db as aiosqlite
    return aiosqlite


def _db_path():
    from db.queries import DB_PATH
    return DB_PATH


VALID_THEMES = {"light", "dark", "system"}


async def get_profile(user_id: str) -> dict:
    """profile を返す。存在しない場合は default を返す (404 にしない)。"""
    try:
        async with _db().connect(_db_path()) as db:
            db.row_factory = _db().Row
            cur = await db.execute(
                "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,),
            )
            row = await cur.fetchone()
    except Exception as e:
        logger.warning("bf_profile.get failed: %s", e)
        return _default(user_id)
    if not row:
        return _default(user_id)
    return dict(row)


def _default(user_id: str) -> dict:
    return {
        "user_id": user_id,
        "display_name": user_id,
        "role_text": None,
        "bio": None,
        "theme": "light",
        "avatar_url": None,
        "updated_at": None,
    }


async def upsert_profile(
    user_id: str,
    *,
    display_name: Optional[str] = None,
    role_text: Optional[str] = None,
    bio: Optional[str] = None,
    theme: Optional[str] = None,
    avatar_url: Optional[str] = None,
) -> dict:
    """UPSERT。指定された field のみ更新する。

    AC (T-023-01):
      - UNWANTED: invalid theme は ValueError (router 層で 422 に変換)
      - audit_logs に profile.updated event を emit (silent fail で本処理は止めない)
    """
    if theme is not None and theme not in VALID_THEMES:
        raise ValueError(f"invalid theme: {theme}")

    changed_fields = [
        k for k, v in {
            "display_name": display_name, "role_text": role_text,
            "bio": bio, "theme": theme, "avatar_url": avatar_url,
        }.items() if v is not None
    ]

    try:
        async with _db().connect(_db_path()) as db:
            await db.execute(
                """INSERT INTO user_profiles (user_id, display_name, role_text, bio, theme, avatar_url)
                   VALUES (?, ?, ?, ?, COALESCE(?, 'light'), ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                     display_name = COALESCE(excluded.display_name, user_profiles.display_name),
                     role_text    = COALESCE(excluded.role_text, user_profiles.role_text),
                     bio          = COALESCE(excluded.bio, user_profiles.bio),
                     theme        = COALESCE(excluded.theme, user_profiles.theme),
                     avatar_url   = COALESCE(excluded.avatar_url, user_profiles.avatar_url),
                     updated_at   = datetime('now','localtime')""",
                (user_id, display_name, role_text, bio, theme, avatar_url),
            )
            await db.commit()
    except Exception as e:
        logger.warning("bf_profile.upsert failed: %s", e)
        return {
            **_default(user_id),
            "display_name": display_name or user_id,
            "role_text": role_text,
            "bio": bio,
            "theme": theme or "light",
            "avatar_url": avatar_url,
        }

    # audit_logs に profile.updated event を emit (失敗してもアプリは止めない)
    try:
        from services.memory_service import emit_event
        await emit_event(
            "profile.updated",
            user_id=user_id,
            detail={"changed_fields": changed_fields},
        )
    except Exception as e:
        logger.warning("bf_profile.audit emit failed: %s", e)

    return await get_profile(user_id)
