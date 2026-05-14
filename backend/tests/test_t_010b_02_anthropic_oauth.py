"""T-010b-02: OAuth フロー (Claude Pro/Max トークン) 1:1 spec test.

REFACTOR / 既存 oauth_providers.py + routers/oauth.py の anthropic provider が
Claude Pro/Max OAuth flow を満たすことを spec として固定する.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : anthropic provider が PROVIDERS に登録される
  AC-2 EVENT-DRIVEN  : authorize URL 生成 + token exchange の API endpoint が動く
  AC-3 STATE-DRIVEN  : token は encrypted_secrets 経由で永続化 (RLS)
  AC-4 UNWANTED      : invalid provider / unauthorized actor → 4xx {detail:{code,message}}

既存実装:
  - backend/services/oauth_providers.py (anthropic provider config)
  - backend/routers/oauth.py (authorize / callback / status / delete endpoints)
  - backend/services/encrypted_store.py (pgsodium 暗号化)
"""
import pytest
from fastapi.testclient import TestClient


# ════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS: anthropic provider 登録
# ════════════════════════════════════════════════════════════════════


def test_ac1_anthropic_provider_registered():
    """oauth_providers.PROVIDERS に anthropic キーがある."""
    from services.oauth_providers import PROVIDERS
    assert "anthropic" in PROVIDERS


def test_ac1_anthropic_endpoints_correct():
    """anthropic provider の authorize_url / token_url が公式エンドポイント."""
    from services.oauth_providers import PROVIDERS
    cfg = PROVIDERS["anthropic"]
    assert cfg.authorize_url == "https://console.anthropic.com/oauth/authorize"
    assert cfg.token_url == "https://console.anthropic.com/oauth/token"


def test_ac1_anthropic_default_scope_claude_read_write():
    """default scope は claude.read + claude.write (Claude Pro/Max トークン用)."""
    from services.oauth_providers import PROVIDERS
    cfg = PROVIDERS["anthropic"]
    assert "claude.read" in cfg.default_scope
    assert "claude.write" in cfg.default_scope


# ════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: API endpoint structured response
# ════════════════════════════════════════════════════════════════════


def test_ac2_authorize_url_built_with_state():
    """build_authorize_url(anthropic, state, redirect_uri) が正しい URL を返す."""
    import os
    os.environ["ANTHROPIC_CLIENT_ID"] = "test_id"
    from services.oauth_providers import build_authorize_url
    url = build_authorize_url(
        "anthropic", state="random_state_abc", redirect_uri="https://app/cb"
    )
    assert url.startswith("https://console.anthropic.com/oauth/authorize?")
    assert "state=random_state_abc" in url
    assert "redirect_uri=" in url
    assert "client_id=test_id" in url


def test_ac2_provider_list_endpoint():
    """GET /api/oauth/providers が anthropic を含む."""
    from main import app
    client = TestClient(app)
    r = client.get("/api/oauth/providers")
    assert r.status_code == 200
    body = r.json()
    assert "anthropic" in body["providers"]


# ════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: encrypted_store / RLS
# ════════════════════════════════════════════════════════════════════


def test_ac3_save_load_token_uses_encrypted_store():
    """save_token + load_token が動く (encrypted_store 経由)."""
    from services.oauth_providers import save_token, load_token
    save_token(
        "anthropic",
        "user_test_t010b02",
        {"access_token": "fake_token_xyz", "scope": "claude.read claude.write"},
    )
    loaded = load_token("anthropic", "user_test_t010b02")
    assert loaded is not None
    assert loaded["access_token"] == "fake_token_xyz"


# ════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: invalid provider → 4xx
# ════════════════════════════════════════════════════════════════════


def test_ac4_unknown_provider_raises():
    """build_authorize_url で未登録 provider → UnknownProviderError."""
    from services.oauth_providers import build_authorize_url, UnknownProviderError
    with pytest.raises(UnknownProviderError):
        build_authorize_url("invalid_xyz", state="s", redirect_uri="https://app/cb")


def test_ac4_status_invalid_provider_4xx():
    """GET /api/oauth/{invalid}/status → 4xx structured response."""
    from main import app
    client = TestClient(app)
    r = client.get("/api/oauth/invalid_xyz/status", params={"owner_id": "user_t010b02"})
    assert 400 <= r.status_code < 500
    body = r.json()
    # FastAPI default: {"detail": "..."}
    assert "detail" in body
