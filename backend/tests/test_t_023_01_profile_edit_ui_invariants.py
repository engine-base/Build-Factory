"""T-023-01: プロフィール編集 UI — 5 AC.

Production artifact 完成済
(frontend/src/app/settings/profile/page.tsx ProfileTab + AppearanceTab +
backend/routers/bf_profile.py /api/bf-profile GET/PATCH +
frontend/src/lib/workspace-api.ts fetchProfile / patchProfile).
本 module は **spec contract layer** (静的 source 解析).

AC マッピング:
  AC-1 UBIQUITOUS    : 5 TabKey / Lucide User/Bell/Palette/ShieldCheck/
                       KeyRound / fetchProfile / patchProfile / theme
                       enum / bg-eb-500 / no emoji.
  AC-2 EVENT-DRIVEN  : saveMut.mutate → patchProfile / qc.setQueryData /
                       savedAt + setTimeout 2200ms / themeMut.
  AC-3 STATE-DRIVEN  : profileQ.isLoading || !draft → Loader2 /
                       saveMut.isPending → disabled / draft useState
                       detached from cache.
  AC-4 OPTIONAL      : draft.display_name 1 文字目 initial / リセット
                       button rolls back to profileQ.data.
  AC-5 UNWANTED      : patchProfile null → throw (input preserved) /
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
BF_ROUTER = REPO_ROOT / "backend" / "routers" / "bf_profile.py"
BF_SERVICE = REPO_ROOT / "backend" / "services" / "bf_profile.py"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — 5 TabKey + Lucide + fetch/patchProfile + theme enum
# ══════════════════════════════════════════════════════════════════════


def test_ac1_page_exists():
    assert PAGE_TSX.exists()


def test_ac1_workspace_api_lib_exists():
    assert API_LIB.exists()


def test_ac1_five_tab_keys_declared():
    src = PAGE_TSX.read_text(encoding="utf-8")
    # type TabKey = "profile" | "notifications" | "appearance" | "security" | "api_keys";
    m = re.search(r"type\s+TabKey\s*=\s*([^;]+);", src)
    assert m, "TabKey type not found"
    body = m.group(1)
    for key in ("profile", "notifications", "appearance", "security", "api_keys"):
        assert f'"{key}"' in body, f"TabKey missing {key}"


def test_ac1_uses_lucide_react_icons():
    src = PAGE_TSX.read_text(encoding="utf-8")
    assert "lucide-react" in src
    for icon in (
        "User", "Bell", "Palette", "ShieldCheck", "KeyRound",
        "Save", "Loader2", "Check",
        "Sun", "Moon", "Monitor",
    ):
        assert icon in src, f"lucide icon missing: {icon}"


def test_ac1_calls_fetch_and_patch_profile():
    src = PAGE_TSX.read_text(encoding="utf-8")
    assert "fetchProfile" in src
    assert "patchProfile" in src


def test_ac1_workspace_api_uses_bf_profile_endpoint():
    src = API_LIB.read_text(encoding="utf-8")
    assert "/api/bf-profile" in src
    assert re.search(r"export\s+async\s+function\s+fetchProfile", src)
    assert re.search(r"export\s+async\s+function\s+patchProfile", src)


def test_ac1_theme_enum_three_values():
    src = PAGE_TSX.read_text(encoding="utf-8")
    # 'light' | 'dark' | 'system'
    assert re.search(r"['\"]light['\"]\s*\|\s*['\"]dark['\"]\s*\|\s*['\"]system['\"]", src)


def test_ac1_uses_eb_500_primary():
    src = PAGE_TSX.read_text(encoding="utf-8")
    assert "bg-eb-500" in src


def test_ac1_no_emoji_in_page():
    src = PAGE_TSX.read_text(encoding="utf-8")
    emoji = re.compile(
        r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF]"
    )
    hits = emoji.findall(src)
    assert not hits, f"emoji in profile page: {hits}"


def test_ac1_backend_bf_profile_router_get_patch():
    src = BF_ROUTER.read_text(encoding="utf-8")
    assert "/api/bf-profile" in src
    # GET / PATCH endpoints
    assert re.search(r'@router\.get\(["\']/["\']', src) or re.search(r'@router\.get\(', src)
    assert re.search(r'@router\.patch\(', src)


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — saveMut + qc.setQueryData + savedAt setTimeout 2200ms
# ══════════════════════════════════════════════════════════════════════


def test_ac2_save_mut_calls_patch_profile():
    src = PAGE_TSX.read_text(encoding="utf-8")
    # saveMut の mutationFn body 内で patchProfile を呼ぶ
    m = re.search(
        r"const\s+saveMut\s*=\s*useMutation[\s\S]+?\}\);",
        src,
    )
    assert m
    body = m.group(0)
    assert "patchProfile" in body
    assert "display_name" in body
    assert "role_text" in body
    assert "bio" in body


def test_ac2_save_mut_writes_cache_via_set_query_data():
    src = PAGE_TSX.read_text(encoding="utf-8")
    # qc.setQueryData(["bf-profile", USER_ID], res)
    assert re.search(
        r"qc\.setQueryData\(\s*\[\s*[\"']bf-profile[\"']",
        src,
    )


def test_ac2_saved_at_uses_set_timeout_with_2200ms():
    src = PAGE_TSX.read_text(encoding="utf-8")
    # setTimeout(() => setSavedAt(null), 2200)
    assert re.search(
        r"setTimeout\([^,]+setSavedAt\(null\)[^,]*,\s*2200\s*\)",
        src,
    )


def test_ac2_theme_mut_calls_patch_profile_with_theme():
    src = PAGE_TSX.read_text(encoding="utf-8")
    m = re.search(
        r"const\s+themeMut\s*=\s*useMutation[\s\S]+?\}\);",
        src,
    )
    assert m
    body = m.group(0)
    assert "patchProfile" in body
    assert "theme" in body


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — loader + saveMut.isPending disable + detached draft
# ══════════════════════════════════════════════════════════════════════


def test_ac3_loader_when_loading_or_no_draft():
    src = PAGE_TSX.read_text(encoding="utf-8")
    # if (profileQ.isLoading || !draft) return <Loader2 ...>
    assert re.search(r"profileQ\.isLoading\s*\|\|\s*!draft", src)
    assert "Loader2" in src
    assert "読み込み中" in src


def test_ac3_save_button_disabled_when_pending():
    src = PAGE_TSX.read_text(encoding="utf-8")
    # disabled={saveMut.isPending}
    assert re.search(r"disabled=\{saveMut\.isPending\}", src)


def test_ac3_draft_uses_separate_state():
    src = PAGE_TSX.read_text(encoding="utf-8")
    # const [draft, setDraft] = useState<BfProfile | null>(null);
    assert re.search(
        r"const\s*\[\s*draft\s*,\s*setDraft\s*\]\s*=\s*useState",
        src,
    )


def test_ac3_no_langgraph_langchain_litellm():
    src = PAGE_TSX.read_text(encoding="utf-8").lower()
    for bad in ("langgraph", "langchain", "litellm"):
        assert bad not in src


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — avatar initial + reset button
# ══════════════════════════════════════════════════════════════════════


def test_ac4_avatar_initial_first_char():
    src = PAGE_TSX.read_text(encoding="utf-8")
    # const initial = (draft.display_name?.[0] ?? "?").toUpperCase();
    assert re.search(
        r"draft\.display_name\??\.\[0\][\s\S]+?toUpperCase",
        src,
    )


def test_ac4_reset_button_restores_profileq_data():
    src = PAGE_TSX.read_text(encoding="utf-8")
    # onClick={() => profileQ.data && setDraft(profileQ.data)} or similar
    assert re.search(
        r"profileQ\.data\s*&&\s*setDraft\(\s*profileQ\.data\s*\)",
        src,
    )
    assert "リセット" in src


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — patchProfile null → throw / no XSS / no hardcoded secret
# ══════════════════════════════════════════════════════════════════════


def test_ac5_save_throws_on_null_response():
    src = PAGE_TSX.read_text(encoding="utf-8")
    # if (!res) throw new Error("save failed");
    assert re.search(
        r"if\s*\(\s*!res\s*\)\s*throw\s+new\s+Error\(\s*[\"']save failed",
        src,
    )


def test_ac5_no_dangerously_set_inner_html():
    src = PAGE_TSX.read_text(encoding="utf-8")
    assert "dangerouslySetInnerHTML" not in src


def test_ac5_no_hardcoded_supabase_or_anthropic_key():
    for path in (PAGE_TSX, API_LIB, BF_ROUTER, BF_SERVICE):
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8")
        assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)
        assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


def test_ac5_no_inline_token_password():
    src = PAGE_TSX.read_text(encoding="utf-8")
    hardcoded = re.findall(
        r'(?:token|password|api_key)\s*[:=]\s*["\'][A-Za-z0-9_-]{20,}["\']',
        src,
        re.IGNORECASE,
    )
    assert not hardcoded, f"hardcoded credential: {hardcoded}"


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_023_01_canonical_ears():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-023-01"), None)
    assert t is not None
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == [
        "UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED",
    ]


def test_tickets_t_023_01_has_adr_link_and_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-023-01"), None)
    assert t.get("adr_link") is not None
    assert "ADR-010" in t["adr_link"]
    files = t.get("existing_files", [])
    assert any("settings/profile/page.tsx" in f for f in files)
    assert "backend/routers/bf_profile.py" in files
    assert "backend/services/bf_profile.py" in files


def test_tickets_t_023_01_ac_mentions_concrete_symbols():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-023-01"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "TabKey",
        "fetchProfile",
        "patchProfile",
        "/api/bf-profile",
        "saveMut",
        "themeMut",
        "Loader2",
        "savedAt",
        "draft",
        "ADR-010",
    ):
        assert sym in full, f"T-023-01 AC missing: {sym}"
