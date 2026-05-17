"""T-V3-D-10 (F-030, E-030 APIKey): personal API token service.

`/api/me/api-tokens` 系 endpoint のバックエンド. 公式に発行する **opaque token** の
発行 / list / revoke を担う.

設計:
    - 平文トークンは **発行レスポンス 1 回のみ** 返す (display-once contract,
      AC-F4 / risk_flag: security_critical)
    - DB には sha256 ハッシュ + key_hint (先頭 8 + 末尾 4 文字) のみを保存
    - rate-limit (per user / per hour) は token_count_per_hour で簡易実装
    - test/dev では SQLite (build.db) 上で `api_tokens` テーブルを遅延作成

DB schema (SQLite fallback, 本番 Postgres では migration 済 assume):
    api_tokens(
        id           TEXT PRIMARY KEY   -- uuid v4
        user_id      TEXT NOT NULL
        name         TEXT NOT NULL
        scopes_json  TEXT NOT NULL      -- JSON array string
        token_hash   TEXT NOT NULL      -- sha256(plaintext)
        token_hint   TEXT NOT NULL      -- 'bft_xxxxxxxx...yyyy'
        expires_at   TEXT NOT NULL      -- ISO8601 UTC
        created_at   TEXT NOT NULL
        revoked_at   TEXT
    )

このサービスは認可レイヤを持たない. caller (router) で auth user_id を確定させて渡す.
"""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

TOKEN_PREFIX = "bft_"          # Build-Factory token marker
TOKEN_BYTES = 32                # 256 bit
MAX_TOKENS_PER_HOUR_PER_USER = 5  # AC: 429 rate-limit


class ApiTokenError(Exception):
    """汎用 service-layer error."""


class ApiTokenValidationError(ApiTokenError):
    """入力検証失敗 (422)."""


class ApiTokenRateLimitError(ApiTokenError):
    """rate-limit 超過 (429)."""


class ApiTokenNotFoundError(ApiTokenError):
    """対象 token なし (404)."""


def _db():
    from db import async_db as aiosqlite
    return aiosqlite


def _db_path():
    from db.queries import DB_PATH
    return DB_PATH


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _hash(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def _hint(plaintext: str) -> str:
    """先頭 8 + 末尾 4 の hint を返す (display 用)."""
    if len(plaintext) < 16:
        return plaintext[:4] + "..."
    return f"{plaintext[:8]}...{plaintext[-4:]}"


async def _ensure_table() -> None:
    """test/dev (SQLite) で api_tokens を遅延作成."""
    try:
        async with _db().connect(_db_path()) as db:
            await db.execute(
                """CREATE TABLE IF NOT EXISTS api_tokens (
                       id          TEXT PRIMARY KEY,
                       user_id     TEXT NOT NULL,
                       name        TEXT NOT NULL,
                       scopes_json TEXT NOT NULL,
                       token_hash  TEXT NOT NULL,
                       token_hint  TEXT NOT NULL,
                       expires_at  TEXT NOT NULL,
                       created_at  TEXT NOT NULL,
                       revoked_at  TEXT
                   )"""
            )
            await db.commit()
    except Exception as e:  # pragma: no cover
        logger.warning("api_token_service._ensure_table failed: %s", e)


def _validate_input(name: str, scopes: list[str], expires_at: Optional[str]) -> None:
    errors: dict[str, str] = {}
    if not isinstance(name, str) or not name.strip():
        errors["name"] = "name must be a non-empty string"
    elif len(name) > 200:
        errors["name"] = "name must be <= 200 chars"
    if not isinstance(scopes, list) or not scopes:
        errors["scopes"] = "scopes must be a non-empty array of strings"
    else:
        for s in scopes:
            if not isinstance(s, str) or not s.strip():
                errors["scopes"] = "each scope must be a non-empty string"
                break
    if expires_at is not None:
        if not isinstance(expires_at, str):
            errors["expires_at"] = "expires_at must be an ISO8601 string"
        else:
            try:
                dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt <= _now():
                    errors["expires_at"] = "expires_at must be in the future"
            except ValueError:
                errors["expires_at"] = "expires_at must be a valid ISO8601 datetime"
    if errors:
        raise ApiTokenValidationError(errors)


async def _count_recent_for_user(user_id: str) -> int:
    """直近 1h で発行した token 数 (rate-limit 用)."""
    one_hour_ago = _iso(_now() - timedelta(hours=1))
    async with _db().connect(_db_path()) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM api_tokens WHERE user_id = ? AND created_at >= ?",
            (user_id, one_hour_ago),
        )
        row = await cur.fetchone()
    return int(row[0]) if row else 0


async def create_token(
    user_id: str,
    *,
    name: str,
    scopes: list[str],
    expires_at: Optional[str] = None,
) -> dict[str, Any]:
    """新 token を発行.

    Returns: { token_id, plaintext_token_shown_once, token_hint, expires_at,
               name, scopes, created_at }
    Raises : ApiTokenValidationError / ApiTokenRateLimitError
    """
    await _ensure_table()
    # default expiry = 90 days
    if expires_at is None:
        expires_dt = _now() + timedelta(days=90)
        expires_at_iso = _iso(expires_dt)
    else:
        expires_at_iso = expires_at
    _validate_input(name, scopes, expires_at_iso)

    recent = await _count_recent_for_user(user_id)
    if recent >= MAX_TOKENS_PER_HOUR_PER_USER:
        raise ApiTokenRateLimitError(
            f"user {user_id} exceeded {MAX_TOKENS_PER_HOUR_PER_USER} tokens/hour"
        )

    token_id = str(uuid.uuid4())
    plaintext = TOKEN_PREFIX + secrets.token_urlsafe(TOKEN_BYTES)
    token_hash = _hash(plaintext)
    token_hint = _hint(plaintext)
    created_at = _iso(_now())

    async with _db().connect(_db_path()) as db:
        await db.execute(
            """INSERT INTO api_tokens
                   (id, user_id, name, scopes_json, token_hash, token_hint,
                    expires_at, created_at, revoked_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)""",
            (
                token_id,
                user_id,
                name.strip(),
                json.dumps(list(scopes)),
                token_hash,
                token_hint,
                expires_at_iso,
                created_at,
            ),
        )
        await db.commit()

    return {
        "token_id": token_id,
        # AC-F1: plaintext は **発行レスポンスでのみ** 返す
        "plaintext_token_shown_once": plaintext,
        "token_hint": token_hint,
        "name": name.strip(),
        "scopes": list(scopes),
        "expires_at": expires_at_iso,
        "created_at": created_at,
    }


async def list_tokens(user_id: str) -> list[dict[str, Any]]:
    """user 所有の active token list (plaintext 一切返さない).

    AC-F4 enforcement: 返却 dict に plaintext_token_shown_once / token_hash は
    含めない (test_token_never_returned_a_second_time で検証).
    """
    await _ensure_table()
    async with _db().connect(_db_path()) as db:
        cur = await db.execute(
            """SELECT id, name, scopes_json, token_hint, expires_at, created_at,
                      revoked_at
                 FROM api_tokens
                WHERE user_id = ?
                ORDER BY created_at DESC""",
            (user_id,),
        )
        rows = await cur.fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append({
            "token_id": row[0],
            "name": row[1],
            "scopes": json.loads(row[2]) if row[2] else [],
            "token_hint": row[3],
            "expires_at": row[4],
            "created_at": row[5],
            "revoked_at": row[6],
        })
    return out


async def revoke_token(user_id: str, token_id: str) -> dict[str, Any]:
    """対象 token を revoke (soft-delete).

    Returns: { token_id, revoked_at }
    Raises : ApiTokenNotFoundError (404 等価)
    """
    await _ensure_table()
    revoked_at = _iso(_now())
    async with _db().connect(_db_path()) as db:
        cur = await db.execute(
            "SELECT id FROM api_tokens WHERE id = ? AND user_id = ? AND revoked_at IS NULL",
            (token_id, user_id),
        )
        row = await cur.fetchone()
        if not row:
            raise ApiTokenNotFoundError(f"token {token_id} not found for user {user_id}")
        await db.execute(
            "UPDATE api_tokens SET revoked_at = ? WHERE id = ?",
            (revoked_at, token_id),
        )
        await db.commit()
    return {"token_id": token_id, "revoked_at": revoked_at}
