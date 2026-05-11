"""T-023-03: encrypted secret 統一 API (REFACTOR)

既存 credentials_store.py (local Fernet 暗号化) を「DB backend を選ばない」
adapter pattern で抽象化する。

Phase 1 (現状 SQLite):
  - credentials_store の Fernet 経路を REUSE (single-tenant local file)

Phase 2 (Supabase Postgres):
  - pgsodium で DB-level 暗号化 (`encrypted_secrets` テーブル + `pgsodium.crypto_aead_det_encrypt`)
  - DATABASE_URL が postgres スキームなら自動切替

## 公開 API

- `set_secret(scope, key, value, *, owner_id=None) -> None`
- `get_secret(scope, key) -> Optional[str]`
- `list_keys(scope) -> list[str]`
- `delete_secret(scope, key) -> bool`

scope はサービス名 (e.g. "anthropic_api_key", "slack_oauth_token") で、
owner_id は user ごとに分離したい場合に指定する (将来 multi-tenant 想定)。
"""
from __future__ import annotations

import os
from typing import Optional


def _backend() -> str:
    """DATABASE_URL のスキームから backend を判定する。"""
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith(("postgres://", "postgresql://", "postgresql+")):
        return "postgres"
    return "fernet_local"


def _scoped_key(scope: str, key: str, owner_id: Optional[str]) -> str:
    """scope / key / owner_id を 1 つの credential service name に折りたたむ。"""
    parts = [scope, key]
    if owner_id:
        parts.append(owner_id)
    return ":".join(parts)


# ──────────────────────────────────────────
# Public API (backend dispatcher)
# ──────────────────────────────────────────

def set_secret(scope: str, key: str, value: str, *, owner_id: Optional[str] = None) -> None:
    if _backend() == "postgres":
        return _pg_set_secret(scope, key, value, owner_id=owner_id)
    return _fernet_set_secret(scope, key, value, owner_id=owner_id)


def get_secret(scope: str, key: str, *, owner_id: Optional[str] = None) -> Optional[str]:
    if _backend() == "postgres":
        return _pg_get_secret(scope, key, owner_id=owner_id)
    return _fernet_get_secret(scope, key, owner_id=owner_id)


def delete_secret(scope: str, key: str, *, owner_id: Optional[str] = None) -> bool:
    if _backend() == "postgres":
        return _pg_delete_secret(scope, key, owner_id=owner_id)
    return _fernet_delete_secret(scope, key, owner_id=owner_id)


def list_keys(scope: str, *, owner_id: Optional[str] = None) -> list[str]:
    if _backend() == "postgres":
        return _pg_list_keys(scope, owner_id=owner_id)
    return _fernet_list_keys(scope, owner_id=owner_id)


# ──────────────────────────────────────────
# Phase 1: Fernet local backend (REUSE credentials_store.py)
# ──────────────────────────────────────────

def _fernet_set_secret(scope: str, key: str, value: str, *, owner_id: Optional[str]) -> None:
    from services.credentials_store import set_credential
    set_credential(
        service=_scoped_key(scope, key, owner_id),
        username=owner_id or "_",
        password=value,
    )


def _fernet_get_secret(scope: str, key: str, *, owner_id: Optional[str]) -> Optional[str]:
    from services.credentials_store import get_credential
    rec = get_credential(_scoped_key(scope, key, owner_id))
    if not rec:
        return None
    return rec.get("password")


def _fernet_delete_secret(scope: str, key: str, *, owner_id: Optional[str]) -> bool:
    from services.credentials_store import delete_credential
    return delete_credential(_scoped_key(scope, key, owner_id))


def _fernet_list_keys(scope: str, *, owner_id: Optional[str]) -> list[str]:
    from services.credentials_store import list_services
    prefix = f"{scope}:"
    suffix = f":{owner_id}" if owner_id else ""
    out = []
    for s in list_services():
        if s.startswith(prefix) and (not suffix or s.endswith(suffix)):
            # scope:key[:owner_id] → key を抜き出す
            mid = s[len(prefix):]
            if suffix and mid.endswith(suffix):
                mid = mid[: -len(suffix)]
            out.append(mid)
    return out


# ──────────────────────────────────────────
# Phase 2: Postgres pgsodium backend (stub for now)
#
# Supabase Postgres 移行時に pgsodium.crypto_aead_det_encrypt を使う実装を
# 入れる。Phase 1 では Fernet にフォールバックする。
# ──────────────────────────────────────────

def _pg_set_secret(scope: str, key: str, value: str, *, owner_id: Optional[str]) -> None:
    # Phase 2 で実装: INSERT INTO encrypted_secrets (scope, key, owner_id,
    # encrypted_value) VALUES (?, ?, ?, pgsodium.crypto_aead_det_encrypt(?, ...))
    # 暫定: Fernet にフォールバック
    _fernet_set_secret(scope, key, value, owner_id=owner_id)


def _pg_get_secret(scope: str, key: str, *, owner_id: Optional[str]) -> Optional[str]:
    return _fernet_get_secret(scope, key, owner_id=owner_id)


def _pg_delete_secret(scope: str, key: str, *, owner_id: Optional[str]) -> bool:
    return _fernet_delete_secret(scope, key, owner_id=owner_id)


def _pg_list_keys(scope: str, *, owner_id: Optional[str]) -> list[str]:
    return _fernet_list_keys(scope, owner_id=owner_id)
