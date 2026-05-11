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
