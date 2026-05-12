"""T-023-02: API キー管理 UI — 5 AC.

Production artifact 完成済
(frontend/src/app/settings/profile/page.tsx ApiKeysTab +
OAuthConnectionsCard + OAuthRow +
frontend/src/lib/workspace-api.ts {fetchOAuthProviders, fetchOAuthStatus,
startOAuthAuthorize, disconnectOAuth} +
backend/routers/oauth.py /authorize + /status + /callback CSRF guard).
本 module は **spec contract layer**.

AC マッピング:
  AC-1 UBIQUITOUS    : ApiKeysTab + OAuthConnectionsCard + OAuthRow /
                       3 provider [slack, github, anthropic] /
                       PROVIDER_META + Lucide MessageSquare/FileCode2/
                       Bot/KeyRound/Link2/Unlink/Loader2 / fetchOAuthStatus
                       / bg-eb-500 / no emoji.
  AC-2 EVENT-DRIVEN  : startOAuthAuthorize → sessionStorage
                       oauth_state_${provider} → window.location.href ;
                       disconnectOAuth → invalidateQueries(['oauth-
                       status']).
  AC-3 STATE-DRIVEN  : statusQ.isLoading → Loader2 / fallback
                       Object.keys(PROVIDER_META) / one-way mirror.
  AC-4 OPTIONAL      : startOAuthAuthorize null → JA alert / disconnect
                       confirm() prompt.
  AC-5 UNWANTED      : oauth callback expected_state vs received_state
                       differ → HTTP 400 {code: csrf_mismatch} /
                       no langgraph / no XSS / no hardcoded secret.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PAGE_TSX = (
    REPO_ROOT / "frontend" / "src" / "app" / "settings"
    / "profile" / "page.tsx"
)
API_LIB = REPO_ROOT / "frontend" / "src" / "lib" / "workspace-api.ts"
OAUTH_ROUTER = REPO_ROOT / "backend" / "routers" / "oauth.py"
CREDS_SERVICE = REPO_ROOT / "backend" / "services" / "credentials_store.py"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — ApiKeysTab + 3 providers + Lucide + eb-500
# ══════════════════════════════════════════════════════════════════════


def test_ac1_page_and_api_lib_exist():
    assert PAGE_TSX.exists()
    assert API_LIB.exists()


def test_ac1_api_keys_tab_component_exists():
    src = PAGE_TSX.read_text(encoding="utf-8")
    assert re.search(r"function\s+ApiKeysTab\s*\(", src)


def test_ac1_oauth_connections_card_and_row():
    src = PAGE_TSX.read_text(encoding="utf-8")
    assert re.search(r"function\s+OAuthConnectionsCard\s*\(", src)
    assert re.search(r"function\s+OAuthRow\s*\(", src)


def test_ac1_provider_meta_three_providers():
    src = PAGE_TSX.read_text(encoding="utf-8")
    m = re.search(
        r"PROVIDER_META\s*:\s*Record<OAuthProvider[\s\S]+?\};",
        src,
    )
    assert m, "PROVIDER_META not found"
    body = m.group(0)
    for p in ("slack", "github", "anthropic"):
        assert p in body, f"PROVIDER_META missing {p}"


def test_ac1_lucide_icons_for_oauth():
    src = PAGE_TSX.read_text(encoding="utf-8")
    assert "lucide-react" in src
    for icon in (
        "MessageSquare", "FileCode2", "Bot",
        "KeyRound", "Link2", "Unlink", "Loader2",
    ):
        assert icon in src, f"lucide icon missing: {icon}"


def test_ac1_workspace_api_oauth_helpers():
    src = API_LIB.read_text(encoding="utf-8")
    for fn in (
        "fetchOAuthProviders",
        "fetchOAuthStatus",
        "startOAuthAuthorize",
        "disconnectOAuth",
    ):
        assert re.search(rf"export\s+async\s+function\s+{fn}\b", src), (
            f"workspace-api missing {fn}"
        )


def test_ac1_oauth_provider_type_three_values():
    src = API_LIB.read_text(encoding="utf-8")
    # export type OAuthProvider = "slack" | "github" | "anthropic";
    m = re.search(r"export\s+type\s+OAuthProvider\s*=\s*([^;]+);", src)
    assert m
    body = m.group(1)
    for p in ("slack", "github", "anthropic"):
        assert f'"{p}"' in body, f"OAuthProvider missing {p}"


def test_ac1_eb_500_primary():
    src = PAGE_TSX.read_text(encoding="utf-8")
    assert "bg-eb-500" in src


def test_ac1_no_emoji_in_page():
    src = PAGE_TSX.read_text(encoding="utf-8")
    emoji = re.compile(
        r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF]"
    )
    hits = emoji.findall(src)
    assert not hits, f"emoji: {hits}"


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — onConnect sessionStorage + location.href / onDisconnect
# ══════════════════════════════════════════════════════════════════════


def test_ac2_on_connect_calls_start_oauth_authorize():
    src = PAGE_TSX.read_text(encoding="utf-8")
    # const onConnect = async () => { ... startOAuthAuthorize(...) }
    m = re.search(
        r"const\s+onConnect\s*=\s*async\s*\(\)\s*=>\s*\{[\s\S]+?\};",
        src,
    )
    assert m
    body = m.group(0)
    assert "startOAuthAuthorize" in body


def test_ac2_on_connect_stores_state_in_session_storage():
    src = PAGE_TSX.read_text(encoding="utf-8")
    # sessionStorage.setItem(`oauth_state_${provider}`, r.state)
    assert re.search(
        r"sessionStorage\.setItem\(\s*`oauth_state_\$\{provider\}`",
        src,
    )


def test_ac2_on_connect_redirects_via_location_href():
    src = PAGE_TSX.read_text(encoding="utf-8")
    assert re.search(
        r"window\.location\.href\s*=\s*r\.authorize_url",
        src,
    )


def test_ac2_on_disconnect_calls_disconnect_oauth_and_invalidates():
    src = PAGE_TSX.read_text(encoding="utf-8")
    # const onDisconnect = async () => { ... disconnectOAuth(...) ... onChanged() }
    m = re.search(
        r"const\s+onDisconnect\s*=\s*async\s*\(\)\s*=>\s*\{[\s\S]+?\};",
        src,
    )
    assert m
    body = m.group(0)
    assert "disconnectOAuth" in body
    assert "onChanged" in body
    # OAuthConnectionsCard 側で invalidateQueries(['oauth-status', ...])
    assert re.search(
        r"invalidateQueries\(\s*\{\s*queryKey:\s*\[\s*[\"']oauth-status[\"']",
        src,
    )


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — Loader2 / fallback / one-way mirror
# ══════════════════════════════════════════════════════════════════════


def test_ac3_status_loading_renders_loader2():
    src = PAGE_TSX.read_text(encoding="utf-8")
    # statusQ.isLoading ? ( <Loader2 ... /> ) : ...
    assert re.search(
        r"statusQ\.isLoading\s*\?\s*\(?\s*<\s*Loader2",
        src,
    )


def test_ac3_fallback_to_object_keys_provider_meta():
    src = PAGE_TSX.read_text(encoding="utf-8")
    # providersQ.data ?? Object.keys(PROVIDER_META)
    assert re.search(
        r"providersQ\.data\s*\?\?\s*Object\.keys\(\s*PROVIDER_META",
        src,
    )


def test_ac3_connected_check_one_way_from_backend():
    src = PAGE_TSX.read_text(encoding="utf-8")
    # const connected = statusQ.data?.connected === true;
    assert re.search(
        r"connected\s*=\s*statusQ\.data\??\.connected\s*===\s*true",
        src,
    )


def test_ac3_no_langgraph_langchain_litellm():
    for path in (PAGE_TSX, API_LIB, OAUTH_ROUTER, CREDS_SERVICE):
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8").lower()
        for bad in ("langgraph", "langchain", "litellm"):
            assert bad not in src, f"{path.name} imports {bad}"


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — start null → alert / disconnect confirm()
# ══════════════════════════════════════════════════════════════════════


def test_ac4_start_authorize_null_triggers_alert():
    src = PAGE_TSX.read_text(encoding="utf-8")
    # if (!r) { alert(`... client_id 未設定 ... .env ...`); return; }
    assert re.search(
        r"if\s*\(\s*!r\s*\)\s*\{\s*alert\(",
        src,
    )
    assert ".env" in src


def test_ac4_disconnect_requires_confirm():
    src = PAGE_TSX.read_text(encoding="utf-8")
    # if (!confirm(`... 解除 ...`)) return;
    assert re.search(
        r"if\s*\(\s*!confirm\(",
        src,
    )
    assert "解除" in src


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — csrf_mismatch / no XSS / no hardcoded secret
# ══════════════════════════════════════════════════════════════════════


def test_ac5_oauth_callback_state_mismatch_400_csrf():
    src = OAUTH_ROUTER.read_text(encoding="utf-8")
    # body.expected_state and body.received_state and body.expected_state != body.received_state
    assert re.search(
        r"expected_state\s*!=\s*body\.received_state",
        src,
    )
    # raise HTTPException(status_code=400, detail={"code": "csrf_mismatch"})
    assert re.search(
        r"HTTPException\(\s*status_code\s*=\s*400[\s\S]+?csrf_mismatch",
        src,
    )


def test_ac5_no_dangerously_set_inner_html():
    src = PAGE_TSX.read_text(encoding="utf-8")
    assert "dangerouslySetInnerHTML" not in src


def test_ac5_no_hardcoded_credential():
    for path in (PAGE_TSX, API_LIB, OAUTH_ROUTER):
        src = path.read_text(encoding="utf-8")
        assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)
        assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


def test_ac5_oauth_router_audits_csrf_rejected():
    """CSRF rejection は監査ログに残す."""
    src = OAUTH_ROUTER.read_text(encoding="utf-8")
    assert "csrf_rejected" in src


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_023_02_canonical_ears():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-023-02"), None)
    assert t is not None
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == [
        "UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED",
    ]


def test_tickets_t_023_02_has_adr_link_and_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-023-02"), None)
    assert t.get("adr_link") is not None
    assert "ADR-010" in t["adr_link"]
    files = t.get("existing_files", [])
    assert "backend/routers/oauth.py" in files
    assert "backend/services/credentials_store.py" in files
    assert any("settings/profile/page.tsx" in f for f in files)
    assert any("workspace-api.ts" in f for f in files)


def test_tickets_t_023_02_ac_mentions_concrete_symbols():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-023-02"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "ApiKeysTab",
        "OAuthConnectionsCard",
        "OAuthRow",
        "PROVIDER_META",
        "startOAuthAuthorize",
        "fetchOAuthStatus",
        "disconnectOAuth",
        "oauth_state_${provider}",
        "csrf_mismatch",
        "ADR-010",
    ):
        assert sym in full, f"T-023-02 AC missing: {sym}"
