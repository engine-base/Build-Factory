"""T-023-03: encrypted_store の smoke test.

local Fernet 経路 (Phase 1) で set / get / list / delete の round-trip を確認。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from services import encrypted_store


@pytest.fixture(autouse=True)
def _isolated_creds_dir(tmp_path: Path, monkeypatch):
    """各テストで credentials_store の保管先を tmp_path に隔離する。"""
    monkeypatch.setenv("BF_CREDENTIALS_DIR", str(tmp_path))
    # モジュールキャッシュをクリア (credentials_store がロード済みの場合)
    import importlib
    import services.credentials_store as cs
    importlib.reload(cs)
    yield


def test_set_get_roundtrip() -> None:
    encrypted_store.set_secret("anthropic", "api_key", "sk-test-123")
    assert encrypted_store.get_secret("anthropic", "api_key") == "sk-test-123"


def test_get_missing_returns_none() -> None:
    assert encrypted_store.get_secret("nope", "no_such_key") is None


def test_delete_secret_returns_true_on_success() -> None:
    encrypted_store.set_secret("slack", "bot_token", "xoxb-test")
    assert encrypted_store.delete_secret("slack", "bot_token") is True
    assert encrypted_store.get_secret("slack", "bot_token") is None


def test_delete_missing_returns_false() -> None:
    assert encrypted_store.delete_secret("nope", "nope") is False


def test_list_keys_within_scope() -> None:
    encrypted_store.set_secret("github", "pat", "ghp-1")
    encrypted_store.set_secret("github", "webhook", "secret-2")
    encrypted_store.set_secret("slack", "bot_token", "xoxb-3")
    keys = encrypted_store.list_keys("github")
    assert "pat" in keys
    assert "webhook" in keys
    assert "bot_token" not in keys  # slack scope は含めない


def test_owner_id_scopes_keys() -> None:
    """owner_id ありで保存したものは無し owner では取得できない (separation)。"""
    encrypted_store.set_secret("openai", "api_key", "u1-key", owner_id="user_1")
    encrypted_store.set_secret("openai", "api_key", "u2-key", owner_id="user_2")
    assert encrypted_store.get_secret("openai", "api_key", owner_id="user_1") == "u1-key"
    assert encrypted_store.get_secret("openai", "api_key", owner_id="user_2") == "u2-key"
    # 異なる owner_id では取れない
    assert encrypted_store.get_secret("openai", "api_key", owner_id="user_3") is None


def test_backend_dispatch_default_is_fernet(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert encrypted_store._backend() == "fernet_local"


def test_backend_dispatch_postgres_detected(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pw@host:5432/db")
    assert encrypted_store._backend() == "postgres"


# ──────────────────────────────────────────────────────────────────────────
# Postgres backend coverage (psycopg を mock)
# ──────────────────────────────────────────────────────────────────────────


import sys
import types


class _FakeCursor:
    def __init__(self, fetch_rows=None):
        self._rows = fetch_rows or []
        self.executed: list[tuple] = []
        self.rowcount = 0

    def execute(self, sql, params=()):
        self.executed.append((sql, params))
        if "delete from encrypted_secrets" in sql.lower():
            # delete は store の状態に応じて rowcount を変える (caller 側で設定)
            self.rowcount = 1
        return self

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    def __enter__(self): return self
    def __exit__(self, *a): return None


class _FakeConn:
    def __init__(self, *, fetch_rows=None, delete_rowcount=0):
        self.fetch_rows = fetch_rows or []
        self.delete_rowcount = delete_rowcount
        self.cursor_obj = _FakeCursor(fetch_rows=self.fetch_rows)
        self.cursor_obj.rowcount = delete_rowcount
        self.committed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def __enter__(self): return self
    def __exit__(self, *a): return None


def _patch_psycopg(monkeypatch, *, fetch_rows=None, delete_rowcount=0):
    fake_conn = _FakeConn(fetch_rows=fetch_rows, delete_rowcount=delete_rowcount)
    fake_mod = types.ModuleType("psycopg")
    fake_mod.connect = lambda url: fake_conn
    sys.modules["psycopg"] = fake_mod
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    return fake_conn


def _cleanup_psycopg():
    sys.modules.pop("psycopg", None)


def test_pg_conn_raises_when_no_database_url(monkeypatch) -> None:
    """psycopg は import できるが DATABASE_URL 無い → RuntimeError."""
    fake_mod = types.ModuleType("psycopg")
    fake_mod.connect = lambda url: None
    sys.modules["psycopg"] = fake_mod
    monkeypatch.delenv("DATABASE_URL", raising=False)
    try:
        with pytest.raises(RuntimeError, match="DATABASE_URL"):
            encrypted_store._pg_conn()
    finally:
        _cleanup_psycopg()


def test_pg_set_secret_executes_upsert(monkeypatch) -> None:
    fake = _patch_psycopg(monkeypatch)
    try:
        encrypted_store.set_secret("anthropic", "api_key", "sk-pg-test", owner_id="user_1")
        # INSERT ... ON CONFLICT が走った
        assert any("insert into encrypted_secrets" in s.lower()
                   for s, _ in fake.cursor_obj.executed)
        assert any("on conflict" in s.lower()
                   for s, _ in fake.cursor_obj.executed)
        # commit が呼ばれた
        assert fake.committed
    finally:
        _cleanup_psycopg()


def test_pg_get_secret_returns_decrypted(monkeypatch) -> None:
    # 1) 先に Fernet 暗号化された文字列を生成
    import services.credentials_store as cs
    import importlib
    importlib.reload(cs)
    encrypted = cs._cipher().encrypt(b"plain-value").decode("ascii")
    # 2) psycopg fetchone がそれを返すように
    _patch_psycopg(monkeypatch, fetch_rows=[(encrypted,)])
    try:
        out = encrypted_store.get_secret("anthropic", "api_key", owner_id="user_1")
        assert out == "plain-value"
    finally:
        _cleanup_psycopg()


def test_pg_get_secret_missing_returns_none(monkeypatch) -> None:
    _patch_psycopg(monkeypatch, fetch_rows=[])
    try:
        assert encrypted_store.get_secret("none", "none") is None
    finally:
        _cleanup_psycopg()


def test_pg_get_secret_decrypt_failure_returns_none(monkeypatch) -> None:
    """DB 内の暗号化文字列が壊れていたら None (silent corruption fallback)."""
    _patch_psycopg(monkeypatch, fetch_rows=[("not-a-valid-fernet-token",)])
    try:
        assert encrypted_store.get_secret("anthropic", "api_key") is None
    finally:
        _cleanup_psycopg()


def test_pg_delete_secret_returns_true_when_rowcount_positive(monkeypatch) -> None:
    fake = _patch_psycopg(monkeypatch, delete_rowcount=1)
    try:
        ok = encrypted_store.delete_secret("anthropic", "api_key", owner_id="user_1")
        assert ok is True
        assert fake.committed
        # DELETE SQL が実行された
        assert any("delete from encrypted_secrets" in s.lower()
                   for s, _ in fake.cursor_obj.executed)
    finally:
        _cleanup_psycopg()


def test_pg_delete_secret_returns_false_when_no_rows(monkeypatch) -> None:
    """rowcount = 0 でも cursor.execute "DELETE" が rowcount=1 を返すため、
    存在しない key の挙動を fake で 0 設定."""
    fake_conn = _FakeConn(delete_rowcount=0)
    # _FakeCursor.execute が rowcount=1 を強制セットするので override
    fake_conn.cursor_obj.rowcount = 0

    class _NoRowsCursor(_FakeCursor):
        def execute(self, sql, params=()):
            self.executed.append((sql, params))
            self.rowcount = 0  # 削除対象なし
            return self

    fake_conn.cursor_obj = _NoRowsCursor()
    fake_mod = types.ModuleType("psycopg")
    fake_mod.connect = lambda url: fake_conn
    sys.modules["psycopg"] = fake_mod
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    try:
        ok = encrypted_store.delete_secret("none", "none")
        assert ok is False
    finally:
        _cleanup_psycopg()


def test_pg_list_keys_with_owner_id(monkeypatch) -> None:
    _patch_psycopg(monkeypatch, fetch_rows=[("api_key",), ("webhook",)])
    try:
        keys = encrypted_store.list_keys("anthropic", owner_id="user_1")
        assert keys == ["api_key", "webhook"]
    finally:
        _cleanup_psycopg()


def test_pg_list_keys_without_owner_id(monkeypatch) -> None:
    """owner_id=None → WHERE owner_id IS NULL 経路."""
    fake = _patch_psycopg(monkeypatch, fetch_rows=[("k1",)])
    try:
        keys = encrypted_store.list_keys("scope")
        assert keys == ["k1"]
        # owner_id IS NULL を含む SQL が実行
        assert any("owner_id is null" in s.lower()
                   for s, _ in fake.cursor_obj.executed)
    finally:
        _cleanup_psycopg()


def test_pg_list_keys_empty(monkeypatch) -> None:
    _patch_psycopg(monkeypatch, fetch_rows=[])
    try:
        assert encrypted_store.list_keys("none") == []
    finally:
        _cleanup_psycopg()


def test_fernet_encrypt_decrypt_roundtrip() -> None:
    """_fernet_encrypt_for_db / _fernet_decrypt_from_db round trip."""
    plain = "round-trip-test-value"
    cipher_str = encrypted_store._fernet_encrypt_for_db(plain)
    assert cipher_str != plain
    assert isinstance(cipher_str, str)
    decrypted = encrypted_store._fernet_decrypt_from_db(cipher_str)
    assert decrypted == plain


def test_scoped_key_with_owner() -> None:
    assert encrypted_store._scoped_key("a", "b", "c") == "a:b:c"


def test_scoped_key_without_owner() -> None:
    assert encrypted_store._scoped_key("a", "b", None) == "a:b"
