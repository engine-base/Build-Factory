"""T-023-03: encrypted secret 統一 API (REFACTOR + DB 化)

`credentials_store.py` (Fernet ファイルベース) と Supabase Postgres
(`encrypted_secrets` テーブル + RLS) を adapter pattern で抽象化する。

backend 判定:
  - DATABASE_URL が `postgres*` スキーム → Postgres backend
  - それ以外 → Fernet local backend (Phase 1 / single-tenant)

Postgres backend (本 PR で実装):
  - Fernet で app-side 暗号化した文字列を `encrypted_secrets.encrypted_value`
    に保存する (Phase 1 互換の暗号方式)
  - Phase 2 で pgsodium.crypto_aead_det_encrypt に切替予定

RLS (supabase/migrations/20260511000001_encrypted_secrets.sql):
  - service_role: 全件 R/W
  - authenticated: owner_id = auth.uid()::text のみ R/W

## 公開 API (sync)

- `set_secret(scope, key, value, *, owner_id=None) -> None`
- `get_secret(scope, key, *, owner_id=None) -> Optional[str]`
- `list_keys(scope, *, owner_id=None) -> list[str]`
- `delete_secret(scope, key, *, owner_id=None) -> bool`
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
# Postgres backend (encrypted_secrets テーブル)
#
# DATABASE_URL = postgres スキームの時に使用。 app-side で Fernet 暗号化済み
# 文字列を encrypted_value 列に保存する (Phase 1 暗号方式互換)。
# Phase 2 で pgsodium.crypto_aead_det_encrypt に切替予定。
# ──────────────────────────────────────────
def _pg_conn():
    """sync psycopg connection を返す。 import エラー時は RuntimeError。"""
    import psycopg  # type: ignore
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL is not set; cannot use postgres backend")
    return psycopg.connect(url)


def _fernet_encrypt_for_db(value: str) -> str:
    """app-side で Fernet 暗号化した base64 文字列を返す (encrypted_value 列用)。"""
    import services.credentials_store as cs
    cipher = cs._cipher()
    return cipher.encrypt(value.encode("utf-8")).decode("ascii")


def _fernet_decrypt_from_db(encrypted: str) -> str:
    import services.credentials_store as cs
    cipher = cs._cipher()
    return cipher.decrypt(encrypted.encode("ascii")).decode("utf-8")


def _pg_set_secret(scope: str, key: str, value: str, *, owner_id: Optional[str]) -> None:
    encrypted = _fernet_encrypt_for_db(value)
    with _pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO encrypted_secrets (scope, key, owner_id, encrypted_value)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (scope, key, owner_id)
                   DO UPDATE SET encrypted_value = EXCLUDED.encrypted_value,
                                 updated_at = NOW()""",
                (scope, key, owner_id, encrypted),
            )
        conn.commit()


def _pg_get_secret(scope: str, key: str, *, owner_id: Optional[str]) -> Optional[str]:
    with _pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT encrypted_value FROM encrypted_secrets
                   WHERE scope = %s AND key = %s AND owner_id IS NOT DISTINCT FROM %s
                   LIMIT 1""",
                (scope, key, owner_id),
            )
            row = cur.fetchone()
    if not row:
        return None
    try:
        return _fernet_decrypt_from_db(row[0])
    except Exception:
        return None


def _pg_delete_secret(scope: str, key: str, *, owner_id: Optional[str]) -> bool:
    with _pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """DELETE FROM encrypted_secrets
                   WHERE scope = %s AND key = %s AND owner_id IS NOT DISTINCT FROM %s""",
                (scope, key, owner_id),
            )
            deleted = cur.rowcount > 0
        conn.commit()
    return deleted


def _pg_list_keys(scope: str, *, owner_id: Optional[str]) -> list[str]:
    with _pg_conn() as conn:
        with conn.cursor() as cur:
            if owner_id is None:
                cur.execute(
                    "SELECT key FROM encrypted_secrets WHERE scope = %s AND owner_id IS NULL ORDER BY key",
                    (scope,),
                )
            else:
                cur.execute(
                    "SELECT key FROM encrypted_secrets WHERE scope = %s AND owner_id = %s ORDER BY key",
                    (scope, owner_id),
                )
            rows = cur.fetchall()
    return [r[0] for r in rows]
