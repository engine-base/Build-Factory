"""T-023-04: OAuth 連携 (Slack/GitHub/Anthropic) — 5 AC.

Production artifact 完成済
(backend/routers/oauth.py + backend/services/oauth_providers.py +
encrypted_store.set_secret('oauth', ...)).
本 module は **spec contract layer**.

AC マッピング:
  AC-1 UBIQUITOUS    : APIRouter prefix /api/oauth + 5 endpoints /
                       PROVIDERS = slack/github/anthropic with
                       ProviderConfig frozen dataclass + 5 fields.
  AC-2 EVENT-DRIVEN  : exchange_code httpx.AsyncClient POST
                       grant_type=authorization_code / save_token →
                       encrypted_store.set_secret('oauth', provider,
                       JSON, owner_id) / secrets.token_urlsafe(24).
  AC-3 STATE-DRIVEN  : OAuthConfigError → HTTPException 503 /
                       status returns connected bool only (no token
                       value in response).
  AC-4 OPTIONAL      : exchange_code parse_qs fallback / disconnect
                       audit event.
  AC-5 UNWANTED      : csrf_mismatch 400 + audit / token exchange
                       failure 502 + audit / no langgraph / no plain
                       token in logs / no hardcoded secret.
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTER_PY = REPO_ROOT / "backend" / "routers" / "oauth.py"
PROVIDERS_PY = REPO_ROOT / "backend" / "services" / "oauth_providers.py"
ENCRYPTED_STORE_PY = REPO_ROOT / "backend" / "services" / "encrypted_store.py"
CREDS_STORE_PY = REPO_ROOT / "backend" / "services" / "credentials_store.py"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — 5 endpoints + 3 providers + ProviderConfig 5 fields
# ══════════════════════════════════════════════════════════════════════


def test_ac1_router_module_exists():
    assert ROUTER_PY.exists()


def test_ac1_providers_module_exists():
    assert PROVIDERS_PY.exists()


def test_ac1_router_prefix_api_oauth():
    src = ROUTER_PY.read_text(encoding="utf-8")
    assert re.search(
        r"APIRouter\(\s*prefix\s*=\s*[\"']/api/oauth[\"']",
        src,
    )


def test_ac1_five_endpoints():
    src = ROUTER_PY.read_text(encoding="utf-8")
    # GET /providers
    assert re.search(r"@router\.get\(\s*[\"']/providers[\"']", src)
    # GET /{provider}/authorize
    assert re.search(r"@router\.get\(\s*[\"']/\{provider\}/authorize[\"']", src)
    # POST /{provider}/callback
    assert re.search(r"@router\.post\(\s*[\"']/\{provider\}/callback[\"']", src)
    # GET /{provider}/status
    assert re.search(r"@router\.get\(\s*[\"']/\{provider\}/status[\"']", src)
    # DELETE /{provider}
    assert re.search(r"@router\.delete\(\s*[\"']/\{provider\}[\"']", src)


def test_ac1_three_providers_with_required_fields():
    from services.oauth_providers import PROVIDERS, ProviderConfig
    for p in ("slack", "github", "anthropic"):
        assert p in PROVIDERS, f"PROVIDERS missing {p}"
        cfg = PROVIDERS[p]
        assert isinstance(cfg, ProviderConfig)
        for fld in (
            "authorize_url", "token_url", "default_scope",
            "client_id_env", "client_secret_env",
        ):
            v = getattr(cfg, fld, None)
            assert v, f"{p}.{fld} empty"


def test_ac1_provider_config_is_frozen_dataclass():
    from services.oauth_providers import ProviderConfig, PROVIDERS
    cfg = PROVIDERS["slack"]
    # frozen=True なら set 不能
    with pytest.raises(Exception):
        cfg.authorize_url = "hacked"  # type: ignore


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — exchange_code httpx POST / save_token / token_urlsafe
# ══════════════════════════════════════════════════════════════════════


def test_ac2_exchange_code_uses_httpx_async_client():
    src = PROVIDERS_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def exchange_code[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "httpx.AsyncClient" in body
    assert re.search(r"grant_type[\"']?\s*:\s*[\"']authorization_code", body)


def test_ac2_save_token_uses_encrypted_store_set_secret():
    src = PROVIDERS_PY.read_text(encoding="utf-8")
    m = re.search(
        r"def save_token[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "encrypted_store.set_secret" in body
    assert '"oauth"' in body or "'oauth'" in body
    assert "owner_id" in body
    # token を JSON encode
    assert "json.dumps" in body


def test_ac2_authorize_uses_secrets_token_urlsafe_24():
    src = ROUTER_PY.read_text(encoding="utf-8")
    assert re.search(
        r"secrets\.token_urlsafe\(\s*24\s*\)",
        src,
    )


def test_ac2_callback_emits_oauth_connected_audit():
    src = ROUTER_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def callback[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "oauth.connected" in body
    assert "save_token" in body


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — OAuthConfigError → 503 / status returns bool only
# ══════════════════════════════════════════════════════════════════════


def test_ac3_authorize_maps_config_error_to_503():
    src = ROUTER_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def authorize[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "OAuthConfigError" in body
    assert re.search(r"status_code\s*=\s*503", body)


def test_ac3_build_authorize_raises_on_missing_client_id():
    src = PROVIDERS_PY.read_text(encoding="utf-8")
    m = re.search(
        r"def build_authorize_url[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "OAuthConfigError" in body
    assert "client_id" in body


def test_ac3_status_returns_connected_bool_only():
    src = ROUTER_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def status[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    # connected: token is not None
    assert "load_token" in body
    assert re.search(r"\"connected\"\s*:\s*token\s+is\s+not\s+None", body)
    # raw token を返さない
    assert "access_token" not in body


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — parse_qs fallback / disconnect audit
# ══════════════════════════════════════════════════════════════════════


def test_ac4_exchange_code_parse_qs_fallback():
    src = PROVIDERS_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def exchange_code[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "parse_qs" in body
    assert "JSONDecodeError" in body


def test_ac4_disconnect_audit():
    src = ROUTER_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def disconnect[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "oauth.disconnected" in body
    assert "delete_token" in body


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — csrf_mismatch / 502 audit / no langgraph / no plain log
# ══════════════════════════════════════════════════════════════════════


def test_ac5_callback_csrf_mismatch_400():
    src = ROUTER_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def callback[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    # raises 400 BEFORE exchange_code
    csrf_idx = body.find("csrf_mismatch")
    exchange_idx = body.find("exchange_code")
    assert csrf_idx >= 0
    assert exchange_idx >= 0
    assert csrf_idx < exchange_idx, "csrf check must precede exchange_code"
    assert "oauth.csrf_rejected" in body


def test_ac5_callback_token_exchange_failure_502_audit():
    src = ROUTER_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def callback[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert re.search(r"status_code\s*=\s*502", body)
    assert "oauth.callback_failed" in body


def test_ac5_no_langgraph_langchain_litellm():
    for path in (ROUTER_PY, PROVIDERS_PY):
        src = path.read_text(encoding="utf-8").lower()
        for bad in ("langgraph", "langchain", "litellm"):
            assert bad not in src, f"{path.name} imports {bad}"


def test_ac5_no_plain_token_in_print_logger():
    """token / access_token を print/logger に直接出力していない."""
    for path in (ROUTER_PY, PROVIDERS_PY):
        src = path.read_text(encoding="utf-8")
        leaks = re.findall(
            r"(?:print|logger\.\w+)\([^)]*\baccess_token\b[^)]*\)",
            src,
        )
        assert not leaks, f"{path.name} prints access_token: {leaks}"


def test_ac5_no_hardcoded_supabase_or_anthropic_key():
    for path in (ROUTER_PY, PROVIDERS_PY, ENCRYPTED_STORE_PY, CREDS_STORE_PY):
        src = path.read_text(encoding="utf-8")
        assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)
        assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_023_04_canonical_ears():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-023-04"), None)
    assert t is not None
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == [
        "UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED",
    ]


def test_tickets_t_023_04_has_adr_link_and_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-023-04"), None)
    assert t.get("adr_link") is not None
    assert "ADR-010" in t["adr_link"]
    files = t.get("existing_files", [])
    assert "backend/routers/oauth.py" in files
    assert "backend/services/oauth_providers.py" in files
    assert "backend/services/encrypted_store.py" in files


def test_tickets_t_023_04_ac_mentions_concrete_symbols():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-023-04"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "/api/oauth",
        "PROVIDERS",
        "ProviderConfig",
        "build_authorize_url",
        "exchange_code",
        "save_token",
        "secrets.token_urlsafe(24)",
        "csrf_mismatch",
        "oauth.connected",
        "oauth.disconnected",
        "OAuthConfigError",
        "ADR-010",
    ):
        assert sym in full, f"T-023-04 AC missing: {sym}"
