"""T-023-03: pgsodium 暗号化保管 (encrypted_store adapter) — 5 AC.

Production artifact 完成済
(backend/services/encrypted_store.py adapter +
backend/services/credentials_store.py Fernet local +
supabase/migrations/20260511000001_encrypted_secrets.sql).
本 module は **spec contract layer**.

AC マッピング:
  AC-1 UBIQUITOUS    : set/get/delete/list signature + _backend()
                       dispatch / no plain text persist.
  AC-2 EVENT-DRIVEN  : _pg_get_secret SQL + _fernet_decrypt_from_db /
                       fernet local routes to credentials_store.
  AC-3 STATE-DRIVEN  : encrypted_secrets table + UNIQUE +
                       2 indexes + RLS 2 policies.
  AC-4 OPTIONAL      : Phase 2 pgsodium 切替 / BF_CREDENTIALS_DIR +
                       0600 perm.
  AC-5 UNWANTED      : DATABASE_URL unset on pg path → RuntimeError /
                       no langgraph / no plain log / no hardcoded
                       secret.
"""
from __future__ import annotations

import inspect
import json
import re
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
ENCRYPTED_STORE_PY = REPO_ROOT / "backend" / "services" / "encrypted_store.py"
CREDS_STORE_PY = REPO_ROOT / "backend" / "services" / "credentials_store.py"
MIGRATION_SQL = (
    REPO_ROOT / "supabase" / "migrations"
    / "20260511000001_encrypted_secrets.sql"
)
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"


def _strip_sql_comments(src: str) -> str:
    """Remove SQL -- and /* */ comments."""
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    src = re.sub(r"--[^\n]*", "", src)
    return src


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — public API + _backend() dispatch + no plain text
# ══════════════════════════════════════════════════════════════════════


def test_ac1_encrypted_store_module_exists():
    assert ENCRYPTED_STORE_PY.exists()


def test_ac1_public_api_callable():
    from services import encrypted_store
    for name in ("set_secret", "get_secret", "delete_secret", "list_keys"):
        fn = getattr(encrypted_store, name, None)
        assert callable(fn), f"encrypted_store missing {name}"


def test_ac1_signatures_have_keyword_only_owner_id():
    from services import encrypted_store
    for name in ("set_secret", "get_secret", "delete_secret", "list_keys"):
        sig = inspect.signature(getattr(encrypted_store, name))
        params = sig.parameters
        assert "owner_id" in params, f"{name} missing owner_id"
        assert params["owner_id"].kind == inspect.Parameter.KEYWORD_ONLY
        assert params["owner_id"].default is None


def test_ac1_backend_dispatch_postgres_vs_fernet(monkeypatch):
    from services import encrypted_store
    monkeypatch.setenv("DATABASE_URL", "postgresql://user@host/db")
    assert encrypted_store._backend() == "postgres"
    monkeypatch.setenv("DATABASE_URL", "postgres://u@h/d")
    assert encrypted_store._backend() == "postgres"
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u@h/d")
    assert encrypted_store._backend() == "postgres"
    monkeypatch.setenv("DATABASE_URL", "")
    assert encrypted_store._backend() == "fernet_local"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert encrypted_store._backend() == "fernet_local"


def test_ac1_no_plain_text_storage_in_module():
    """Postgres set 経路で plain value を encrypted_value に直接 INSERT しない."""
    src = ENCRYPTED_STORE_PY.read_text(encoding="utf-8")
    # value を encrypted_value 列に渡す前に _fernet_encrypt_for_db を経る
    m = re.search(
        r"def\s+_pg_set_secret[\s\S]+?(?=\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "_fernet_encrypt_for_db" in body, (
        "Postgres set path must encrypt value before INSERT"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — _pg_get_secret SQL + decrypt / fernet routes
# ══════════════════════════════════════════════════════════════════════


def test_ac2_pg_get_secret_query_shape():
    src = ENCRYPTED_STORE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"def\s+_pg_get_secret[\s\S]+?(?=\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "encrypted_value" in body
    assert "encrypted_secrets" in body
    assert re.search(
        r"scope\s*=\s*%s\s*AND\s*key\s*=\s*%s\s*AND\s*owner_id\s+IS\s+NOT\s+DISTINCT\s+FROM\s*%s",
        body,
        re.IGNORECASE,
    )
    assert "LIMIT 1" in body
    assert "_fernet_decrypt_from_db" in body


def test_ac2_fernet_get_routes_to_credentials_store():
    src = ENCRYPTED_STORE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"def\s+_fernet_get_secret[\s\S]+?(?=\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "credentials_store" in body
    assert "get_credential" in body


def test_ac2_scoped_key_format():
    from services.encrypted_store import _scoped_key
    assert _scoped_key("oauth", "github", None) == "oauth:github"
    assert _scoped_key("oauth", "github", "user1") == "oauth:github:user1"


def test_ac2_fernet_set_uses_set_credential():
    src = ENCRYPTED_STORE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"def\s+_fernet_set_secret[\s\S]+?(?=\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "set_credential" in body


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — encrypted_secrets schema + UNIQUE + indexes + RLS
# ══════════════════════════════════════════════════════════════════════


def test_ac3_migration_exists():
    assert MIGRATION_SQL.exists()


def test_ac3_table_create_with_unique():
    src = _strip_sql_comments(MIGRATION_SQL.read_text(encoding="utf-8"))
    assert "CREATE TABLE IF NOT EXISTS encrypted_secrets" in src
    # UNIQUE (scope, key, owner_id)
    assert re.search(
        r"UNIQUE\s*\(\s*scope\s*,\s*key\s*,\s*owner_id\s*\)",
        src,
    )


def test_ac3_two_indexes():
    src = _strip_sql_comments(MIGRATION_SQL.read_text(encoding="utf-8"))
    assert "idx_encrypted_secrets_scope_key" in src
    assert "idx_encrypted_secrets_owner" in src


def test_ac3_rls_enabled():
    src = _strip_sql_comments(MIGRATION_SQL.read_text(encoding="utf-8"))
    assert re.search(
        r"ALTER\s+TABLE\s+encrypted_secrets\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY",
        src,
        re.IGNORECASE,
    )


def test_ac3_two_policies_service_role_and_self():
    src = _strip_sql_comments(MIGRATION_SQL.read_text(encoding="utf-8"))
    assert "encrypted_secrets_service_role" in src
    assert "encrypted_secrets_self" in src
    # owner_id = auth.uid()::text
    assert re.search(
        r"owner_id\s*=\s*auth\.uid\(\)::text",
        src,
    )


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — Phase 2 pgsodium hint + BF_CREDENTIALS_DIR + 0600
# ══════════════════════════════════════════════════════════════════════


def test_ac4_phase2_pgsodium_documented():
    """ docstring に Phase 2 で pgsodium に切替予定 と明記."""
    src = ENCRYPTED_STORE_PY.read_text(encoding="utf-8").lower()
    assert "pgsodium" in src


def test_ac4_credentials_store_uses_env_dir():
    """BF_CREDENTIALS_DIR で override 可能."""
    src = CREDS_STORE_PY.read_text(encoding="utf-8")
    assert "BF_CREDENTIALS_DIR" in src


def test_ac4_credentials_store_0600_perm():
    """key file は chmod 0o600."""
    src = CREDS_STORE_PY.read_text(encoding="utf-8")
    assert "0o600" in src
    assert "0o700" in src


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — DATABASE_URL unset → RuntimeError / no langgraph / no
#                  plain log / no hardcoded secret
# ══════════════════════════════════════════════════════════════════════


def test_ac5_database_url_unset_raises_runtime_error(monkeypatch):
    """_pg_conn 経由で DATABASE_URL が未設定なら RuntimeError."""
    monkeypatch.setenv("DATABASE_URL", "")
    from services import encrypted_store
    # _pg_conn() を直接呼ぶ
    with pytest.raises(RuntimeError) as excinfo:
        encrypted_store._pg_conn()
    msg = str(excinfo.value)
    assert "DATABASE_URL" in msg


def test_ac5_no_langgraph_langchain_litellm():
    for path in (ENCRYPTED_STORE_PY, CREDS_STORE_PY):
        src = path.read_text(encoding="utf-8").lower()
        for bad in ("langgraph", "langchain", "litellm"):
            assert bad not in src, f"{path.name} imports {bad}"


def test_ac5_no_plain_text_secret_in_logs():
    """encrypted_store の logger / print に value を露出していない."""
    src = ENCRYPTED_STORE_PY.read_text(encoding="utf-8")
    # print/logger に value を直接渡す行が無い (encrypted のみ)
    leaks = re.findall(
        r"(?:print|logger\.\w+)\([^)]*\bvalue\b[^)]*\)",
        src,
    )
    assert not leaks, f"plain value in print/log: {leaks}"


def test_ac5_no_hardcoded_supabase_or_anthropic_key():
    for path in (ENCRYPTED_STORE_PY, CREDS_STORE_PY, MIGRATION_SQL):
        src = path.read_text(encoding="utf-8")
        assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)
        assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_023_03_canonical_ears():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-023-03"), None)
    assert t is not None
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == [
        "UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED",
    ]


def test_tickets_t_023_03_has_adr_link_and_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-023-03"), None)
    assert t.get("adr_link") is not None
    assert "ADR-010" in t["adr_link"]
    files = t.get("existing_files", [])
    assert "backend/services/credentials_store.py" in files
    assert "backend/services/encrypted_store.py" in files
    assert any("encrypted_secrets.sql" in f for f in files)


def test_tickets_t_023_03_ac_mentions_concrete_symbols():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-023-03"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "encrypted_store",
        "set_secret",
        "get_secret",
        "_backend()",
        "encrypted_secrets",
        "DATABASE_URL",
        "RuntimeError",
        "auth.uid()",
        "pgsodium",
        "BF_CREDENTIALS_DIR",
        "ADR-010",
    ):
        assert sym in full, f"T-023-03 AC missing: {sym}"
