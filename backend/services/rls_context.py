"""T-S0-09b: RLS context helper.

auth_middleware から得た user_id を per-request basis で PostgreSQL session
変数 `request.jwt.claim.sub` / `request.jwt.claims` に設定し、 RLS policy
(auth.uid() / auth.jwt() -> ...) が機能するようにする helper.

設計境界:
  - auth_middleware.py は読み取りのみ (REUSE / 無改変).
  - DB connection は呼び出し側が用意 (依存注入 / asyncpg / aiosqlite どちらでも).
  - prod では BUILD_FACTORY_DEV_BYPASS_AUTH を無視 (bf_env_guard 経由 enforce).
  - ADR-010: LangGraph / LangChain / LiteLLM なし.

公開 API:
  - set_request_user(conn, user_id, custom_permissions=None) -> None
  - reset_request_user(conn) -> None
  - with_request_user(conn, user_id, custom_permissions=None) -> async CM
  - DEV_BYPASS_USER_ID
  - MAX_USER_ID_LEN = 200
  - RLSContextError

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : 6 公開 symbol + SET LOCAL request.jwt.claim.sub.
  AC-2 EVENT-DRIVEN  : with_request_user 出口 (success / exception) で
                       reset_request_user 呼出 / RESET 使用.
  AC-3 STATE-DRIVEN  : DEV_BYPASS_USER_ID = auth_middleware と一致 /
                       prod で bypass 不可 / no AI stack import.
  AC-4 OPTIONAL      : custom_permissions JSONB を SET LOCAL request.jwt.
                       claims に safe escape で渡す.
  AC-5 UNWANTED      : invalid user_id (empty / non-string / over 200 /
                       single-quote / null-byte) で RLSContextError /
                       reset 失敗で re-raise / no force_bypass.
"""
from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

# T-001-10 REUSE: bf_env_guard で prod 判定
from services.bf_env_guard import is_prod

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────

# auth_middleware.DEV_USER.sub と完全一致 (cross-module invariant).
DEV_BYPASS_USER_ID = "00000000-0000-0000-0000-000000000001"

MAX_USER_ID_LEN = 200
MAX_CLAIMS_JSON_LEN = 8192  # JWT claims 全体の合理的上限

# SQL injection 防止: user_id に許容しない文字
_FORBIDDEN_USER_ID_CHARS = ("'", "\x00", "\\", ";", "\n", "\r")


class RLSContextError(ValueError):
    """RLS context helper 入力 / 不変条件違反 (router で 4xx 化)."""


# ──────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────


def _validate_user_id(user_id: Any) -> str:
    if not isinstance(user_id, str):
        raise RLSContextError("user_id must be string")
    s = user_id.strip()
    if not s:
        raise RLSContextError("user_id must not be empty")
    if len(s) > MAX_USER_ID_LEN:
        raise RLSContextError(
            f"user_id must be <= {MAX_USER_ID_LEN} chars (got {len(s)})"
        )
    for ch in _FORBIDDEN_USER_ID_CHARS:
        if ch in s:
            raise RLSContextError(
                f"user_id contains forbidden character (SQL injection vector)"
            )
    return s


def _validate_custom_permissions(perms: Any) -> Optional[dict]:
    if perms is None:
        return None
    if not isinstance(perms, dict):
        raise RLSContextError(
            f"custom_permissions must be dict or None, got {type(perms).__name__}"
        )
    # JSON serializable / 大きさ制限
    try:
        s = json.dumps(perms, ensure_ascii=True)
    except (TypeError, ValueError) as e:
        raise RLSContextError(f"custom_permissions not JSON-serializable: {e}")
    if len(s) > MAX_CLAIMS_JSON_LEN:
        raise RLSContextError(
            f"custom_permissions JSON exceeds {MAX_CLAIMS_JSON_LEN} chars"
        )
    return perms


def _build_claims_json(user_id: str, custom_permissions: Optional[dict]) -> str:
    """SET LOCAL request.jwt.claims に渡す JSON 文字列を構築."""
    claims: dict[str, Any] = {"sub": user_id}
    if custom_permissions:
        claims["custom_permissions"] = custom_permissions
    return json.dumps(claims, ensure_ascii=True)


# ──────────────────────────────────────────────────────────────────────
# Public API: SET LOCAL / RESET
# ──────────────────────────────────────────────────────────────────────


async def set_request_user(
    conn: Any,
    user_id: str,
    custom_permissions: Optional[dict] = None,
) -> None:
    """current request の user_id を PG session 変数に設定.

    SET LOCAL なので transaction 内のみ有効 / commit で auto reset.

    Args:
      conn: async DB connection (asyncpg / psycopg / aiosqlite で execute() を持つ).
      user_id: auth.uid() に伝播する user UUID 文字列.
      custom_permissions: 任意の dict (auth.jwt() -> 'custom_permissions' に伝播).
    """
    uid = _validate_user_id(user_id)
    perms = _validate_custom_permissions(custom_permissions)
    claims_json = _build_claims_json(uid, perms)

    # parameterized SET LOCAL (driver が $1 をサポートする場合)
    # fallback: 検証済 safe string を直接 inline (validate でメタ文字弾き済み)
    try:
        await conn.execute(
            "SELECT set_config('request.jwt.claim.sub', $1, true)",
            uid,
        )
        await conn.execute(
            "SELECT set_config('request.jwt.claims', $1, true)",
            claims_json,
        )
    except TypeError:
        # aiosqlite 等 positional args 未対応の driver: literal escape
        await conn.execute(
            f"SET LOCAL request.jwt.claim.sub = '{uid}'"
        )
        await conn.execute(
            f"SET LOCAL request.jwt.claims = '{_escape_sql_literal(claims_json)}'"
        )


async def reset_request_user(conn: Any) -> None:
    """SET LOCAL は transaction 終了で自動 reset だが、 接続 reuse 前に
    明示的に RESET して stale state を防ぐ."""
    try:
        await conn.execute("RESET request.jwt.claim.sub")
    except Exception as e:  # noqa: BLE001
        # 接続 pool に返す前に raise (stale state 防止)
        raise RLSContextError(
            f"failed to RESET request.jwt.claim.sub: {e}"
        )
    try:
        await conn.execute("RESET request.jwt.claims")
    except Exception as e:  # noqa: BLE001
        raise RLSContextError(
            f"failed to RESET request.jwt.claims: {e}"
        )


@asynccontextmanager
async def with_request_user(
    conn: Any,
    user_id: str,
    custom_permissions: Optional[dict] = None,
) -> AsyncIterator[None]:
    """set_request_user + reset_request_user を context manager でラップ.

    success / exception どちらの出口でも reset を実行する.
    """
    await set_request_user(conn, user_id, custom_permissions)
    try:
        yield
    finally:
        await reset_request_user(conn)


# ──────────────────────────────────────────────────────────────────────
# Production safety
# ──────────────────────────────────────────────────────────────────────


def is_bypass_allowed() -> bool:
    """BUILD_FACTORY_DEV_BYPASS_AUTH を考慮するかどうか.

    prod 環境では BUILD_FACTORY_DEV_BYPASS_AUTH を一切無視 (bypass しない).
    """
    if is_prod():
        return False
    return os.environ.get("BUILD_FACTORY_DEV_BYPASS_AUTH", "0") == "1"


def effective_user_id_for_request(authenticated_user_id: Optional[str]) -> str:
    """auth_middleware が authenticated user を返さなかった時の fallback.

    - prod では authenticated_user_id が空でも DEV_BYPASS_USER_ID を返さず
      RLSContextError を raise (PROD で bypass 禁止 / AC-3 / AC-5).
    - dev / test / local では BUILD_FACTORY_DEV_BYPASS_AUTH=1 のとき
      DEV_BYPASS_USER_ID を返す.
    """
    if authenticated_user_id:
        return _validate_user_id(authenticated_user_id)
    if is_bypass_allowed():
        return DEV_BYPASS_USER_ID
    raise RLSContextError(
        "no authenticated user_id and bypass not allowed in current BF_ENV"
    )


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


def _escape_sql_literal(s: str) -> str:
    """SQL string literal escape (single-quote の doubling).

    set_request_user で parameterized が失敗した fallback 経路.
    user_id は事前に _validate_user_id で single-quote 弾き済みなので
    安全だが、 claims JSON は値に '...' を含み得るので escape 必須.
    """
    return s.replace("'", "''")
