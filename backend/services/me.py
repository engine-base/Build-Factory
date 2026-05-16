"""T-V3-B-26: Account profile backend service (F-023).

`/api/me` 系 endpoint のビジネスロジックを集約する.

責務:
    1. profile (name / avatar_url) と user_settings (theme / locale / notifications) を
       1 つのレスポンスにまとめて取得 / 更新する
    2. API key (provider × user_id) の暗号化保管 (BYOK store 経由)。
       per-user/provider 1 key 制約 (重複時 409)。
    3. OAuth トークンの provider 側 revoke + ローカル unlink

設計:
    - profile/settings の永続化は SQLite (build.db) で行う。`bf_profile`
      テーブル (display_name 等) と `user_settings` テーブル (theme 等) を別 row として持つ
    - API key は services.byok_store (Fernet 暗号化) を利用 (pgsodium レイヤ等価)
    - OAuth unlink は services.oauth_providers.delete_token + httpx revoke
    - すべての副作用には audit_logs を emit (失敗してもアプリは止めない)

このサービスは認可レイヤを持たない. caller (router) で auth user_id を確定させて渡す.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

VALID_THEMES = {"light", "dark", "system"}
VALID_OAUTH_PROVIDERS = {"anthropic", "github", "slack", "google"}


def _db():
    from db import async_db as aiosqlite
    return aiosqlite


def _db_path():
    from db.queries import DB_PATH
    return DB_PATH


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ──────────────────────────────────────────────────────────────────────────────
# Profile + Settings (GET /api/me, PUT /api/me)
# ──────────────────────────────────────────────────────────────────────────────


async def _ensure_me_tables() -> None:
    """test/dev 環境 (SQLite) で `me_profile` / `me_settings` を遅延作成する.

    実 Postgres 環境では migration (20260512000000_impl_integration_ops_tables.sql)
    で `user_settings` 等が作成済み. 本関数は SQLite 上での test fallback のみ.
    """
    try:
        async with _db().connect(_db_path()) as db:
            await db.execute(
                """CREATE TABLE IF NOT EXISTS me_profile (
                       user_id    TEXT PRIMARY KEY,
                       name       TEXT,
                       avatar_url TEXT,
                       updated_at TEXT
                   )"""
            )
            await db.execute(
                """CREATE TABLE IF NOT EXISTS me_settings (
                       user_id               TEXT PRIMARY KEY,
                       theme                 TEXT NOT NULL DEFAULT 'system',
                       locale                TEXT NOT NULL DEFAULT 'ja',
                       notifications_enabled INTEGER NOT NULL DEFAULT 1,
                       updated_at            TEXT
                   )"""
            )
            await db.commit()
    except Exception as e:  # pragma: no cover
        logger.warning("me._ensure_me_tables failed: %s", e)


async def get_me(user_id: str) -> dict[str, Any]:
    """`{ "user": {...}, "settings": {...} }` を返す.

    DB 非接続 / row なしの場合は default を返す (404 にはしない).
    """
    await _ensure_me_tables()
    user = {"id": user_id, "name": None, "avatar_url": None, "updated_at": None}
    settings = {
        "user_id": user_id,
        "theme": "system",
        "locale": "ja",
        "notifications_enabled": True,
        "updated_at": None,
    }
    try:
        async with _db().connect(_db_path()) as db:
            try:
                db.row_factory = _db().Row  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover
                pass
            cur = await db.execute(
                "SELECT name, avatar_url, updated_at FROM me_profile WHERE user_id = ?",
                (user_id,),
            )
            row = await cur.fetchone()
            if row:
                d = dict(row)
                user.update({
                    "name": d.get("name"),
                    "avatar_url": d.get("avatar_url"),
                    "updated_at": d.get("updated_at"),
                })
            cur = await db.execute(
                "SELECT theme, locale, notifications_enabled, updated_at "
                "FROM me_settings WHERE user_id = ?",
                (user_id,),
            )
            srow = await cur.fetchone()
            if srow:
                sd = dict(srow)
                settings.update({
                    "theme": sd.get("theme") or "system",
                    "locale": sd.get("locale") or "ja",
                    "notifications_enabled": bool(sd.get("notifications_enabled")),
                    "updated_at": sd.get("updated_at"),
                })
    except Exception as e:  # pragma: no cover
        logger.warning("me.get_me read failed: %s", e)
    return {"user": user, "settings": settings}


class InvalidSettingsError(ValueError):
    """422 validation error to be raised from put_me / register_api_key."""


def _validate_put_me(
    name: Optional[str],
    avatar_url: Optional[str],
    settings: Optional[dict[str, Any]],
) -> dict[str, str]:
    """name / avatar_url / settings を validate. field-level error map を返す."""
    errors: dict[str, str] = {}
    if name is not None:
        if not isinstance(name, str):
            errors["name"] = "must be string"
        elif len(name) > 200:
            errors["name"] = "must be <= 200 chars"
    if avatar_url is not None:
        if not isinstance(avatar_url, str):
            errors["avatar_url"] = "must be string"
        elif len(avatar_url) > 1000:
            errors["avatar_url"] = "must be <= 1000 chars"
        elif avatar_url and not (
            avatar_url.startswith("http://")
            or avatar_url.startswith("https://")
            or avatar_url.startswith("/")
        ):
            errors["avatar_url"] = "must start with http(s):// or /"
    if settings is not None:
        if not isinstance(settings, dict):
            errors["settings"] = "must be object"
        else:
            theme = settings.get("theme")
            if theme is not None and theme not in VALID_THEMES:
                errors["settings.theme"] = (
                    f"must be one of {sorted(VALID_THEMES)}"
                )
            locale = settings.get("locale")
            if locale is not None:
                if not isinstance(locale, str) or len(locale) > 16 or not locale:
                    errors["settings.locale"] = "must be 1..16 chars"
            ne = settings.get("notifications_enabled")
            if ne is not None and not isinstance(ne, bool):
                errors["settings.notifications_enabled"] = "must be boolean"
    return errors


async def put_me(
    user_id: str,
    *,
    name: Optional[str] = None,
    avatar_url: Optional[str] = None,
    settings: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """profile / settings を UPSERT. 指定された field のみ更新する.

    Raises:
        InvalidSettingsError: validation error (router 層で 422 に変換)
    """
    errors = _validate_put_me(name, avatar_url, settings)
    if errors:
        raise InvalidSettingsError(errors)

    await _ensure_me_tables()
    now = _now_iso()
    changed_fields: list[str] = []
    if name is not None:
        changed_fields.append("name")
    if avatar_url is not None:
        changed_fields.append("avatar_url")
    if settings:
        for k in ("theme", "locale", "notifications_enabled"):
            if settings.get(k) is not None:
                changed_fields.append(f"settings.{k}")

    try:
        async with _db().connect(_db_path()) as db:
            if name is not None or avatar_url is not None:
                await db.execute(
                    """INSERT INTO me_profile (user_id, name, avatar_url, updated_at)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(user_id) DO UPDATE SET
                         name       = COALESCE(excluded.name,       me_profile.name),
                         avatar_url = COALESCE(excluded.avatar_url, me_profile.avatar_url),
                         updated_at = excluded.updated_at""",
                    (user_id, name, avatar_url, now),
                )
            if settings:
                theme = settings.get("theme")
                locale = settings.get("locale")
                ne = settings.get("notifications_enabled")
                await db.execute(
                    """INSERT INTO me_settings (user_id, theme, locale, notifications_enabled, updated_at)
                       VALUES (?, COALESCE(?, 'system'), COALESCE(?, 'ja'), COALESCE(?, 1), ?)
                       ON CONFLICT(user_id) DO UPDATE SET
                         theme                 = COALESCE(excluded.theme, me_settings.theme),
                         locale                = COALESCE(excluded.locale, me_settings.locale),
                         notifications_enabled = COALESCE(excluded.notifications_enabled, me_settings.notifications_enabled),
                         updated_at            = excluded.updated_at""",
                    (
                        user_id,
                        theme,
                        locale,
                        (1 if ne else 0) if ne is not None else None,
                        now,
                    ),
                )
            await db.commit()
    except Exception as e:  # pragma: no cover
        logger.warning("me.put_me write failed: %s", e)

    await _audit(
        "profile.updated",
        user_id=user_id,
        detail={"changed_fields": changed_fields},
    )
    return {"updated_at": now, "changed_fields": changed_fields}


# ──────────────────────────────────────────────────────────────────────────────
# API keys (POST /api/me/api-keys) — pgsodium 等価の Fernet 暗号化
# ──────────────────────────────────────────────────────────────────────────────


class ApiKeyConflictError(RuntimeError):
    """provider 重複時 (409)."""


class ApiKeyValidationError(ValueError):
    """request body validation (422)."""


async def register_api_key(
    user_id: str,
    *,
    provider: str,
    key_plaintext: str,
) -> dict[str, Any]:
    """provider × user_id で 1 つの API key を暗号化保管する.

    Raises:
        ApiKeyValidationError: 422 (provider unknown / key prefix mismatch / 空文字)
        ApiKeyConflictError:   409 (既に同 provider の key が登録済)

    Returns:
        { key_id: uuid, masked_key: "sk-ant-...abcd" }

    Note:
        - key plaintext は決して return / log しない.
        - 既存実装 services.byok_store の Fernet 暗号化に delegate.
        - audit_logs に api_key.added を emit (silent fail).
    """
    from services import byok_store as bs
    if not isinstance(provider, str) or not provider.strip():
        raise ApiKeyValidationError({"provider": "must not be empty"})
    if not isinstance(key_plaintext, str) or not key_plaintext.strip():
        raise ApiKeyValidationError({"key_plaintext": "must not be empty"})

    store = bs.get_store()
    try:
        existing = store.get_record(user_id, provider)
    except bs.BYOKError as e:
        # SUPPORTED_PROVIDERS 外 / user_id 不正 etc. は 422 validation error
        raise ApiKeyValidationError({"provider": str(e)})
    if existing is not None:
        raise ApiKeyConflictError(
            f"key already exists for provider={provider}"
        )
    try:
        rec = store.set_key(user_id, provider, key_plaintext, detail={"source": "me.api_keys"})
    except bs.BYOKError as e:
        msg = str(e)
        # 全て 422 validation error として扱う
        raise ApiKeyValidationError({"key_plaintext": msg})

    # uuid 風の key_id (BYOKRecord は composite key だが API レスポンス互換のため生成)
    import uuid
    key_id = str(uuid.uuid5(
        uuid.NAMESPACE_OID, f"{user_id}|{provider}|{rec.created_at}"
    ))
    await _audit(
        "api_key.added",
        user_id=user_id,
        detail={"provider": provider, "key_id": key_id},
    )
    return {
        "key_id": key_id,
        "masked_key": rec.masked_preview,
        "provider": provider,
    }


# ──────────────────────────────────────────────────────────────────────────────
# OAuth unlink (DELETE /api/me/oauth/{provider})
# ──────────────────────────────────────────────────────────────────────────────


class OAuthUnknownProviderError(ValueError):
    """unknown / unsupported provider (404)."""


class OAuthNotLinkedError(LookupError):
    """provider not linked (404)."""


async def unlink_oauth(user_id: str, provider: str) -> dict[str, Any]:
    """provider 側で token を revoke + local store を消す.

    Raises:
        OAuthUnknownProviderError: 404 (unknown provider)
        OAuthNotLinkedError: 404 (token なし)

    Returns:
        { unlinked_at: ISO timestamp, provider: ... }
    """
    if provider not in VALID_OAUTH_PROVIDERS:
        raise OAuthUnknownProviderError(f"unknown provider: {provider}")

    # provider side revoke (best-effort) + local delete
    from services import oauth_providers as op
    try:
        token = op.load_token(provider, user_id) if provider in op.PROVIDERS else None
    except op.UnknownProviderError:
        token = None

    if token is None:
        # google は PROVIDERS にないか load 失敗 — local も無いので Not Linked
        raise OAuthNotLinkedError(f"provider not linked: {provider}")

    # best-effort: call provider revoke endpoint (Slack / GitHub / Anthropic)
    await _try_revoke_remote(provider, token)
    op.delete_token(provider, user_id)
    now = _now_iso()
    await _audit(
        "oauth.unlinked",
        user_id=user_id,
        detail={"provider": provider},
    )
    return {"unlinked_at": now, "provider": provider}


async def _try_revoke_remote(provider: str, token: dict[str, Any]) -> None:
    """provider 側に revoke を投げる. 失敗してもローカル削除は続行する."""
    access = token.get("access_token") or token.get("token")
    if not access:
        return
    # 各プロバイダの revoke endpoint (なければ skip).
    revoke_urls = {
        "slack": "https://slack.com/api/auth.revoke",
        "github": None,  # GitHub は App-level revoke が必要 (skip)
        "anthropic": None,  # Anthropic は console.anthropic.com 側 (skip)
    }
    url = revoke_urls.get(provider)
    if not url:
        return
    try:
        import httpx  # noqa: WPS433
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(url, headers={"Authorization": f"Bearer {access}"})
    except Exception as e:  # pragma: no cover
        logger.warning("oauth.revoke remote failed: provider=%s err=%s", provider, e)


# ──────────────────────────────────────────────────────────────────────────────
# audit helper
# ──────────────────────────────────────────────────────────────────────────────


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict[str, Any]) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("me.audit emit failed: %s -- %s", event_type, e)
