"""T-010b-04: Play ボタン UI + session 起動 API — 4 AC.

Static analysis verifies CLAUDE.md §5.1 Lucide-only + REFACTOR invariant on
existing backend/routers/agent_runner.py.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : PlaySessionButton.tsx + lib/api/sessions.ts 存在.
                       shadcn Button + Lucide Play icon (絵文字禁止).
                       POST /api/agent/sessions REUSE (backend 無改変).
  AC-2 EVENT-DRIVEN  : クリックで POST / run_in_background=true /
                       Loader2 spinner / error.code+message verbatim.
  AC-3 STATE-DRIVEN  : agent_runner.CreateSessionRequest field 不変 /
                       button disabled while loading / global state mutate なし.
  AC-4 UNWANTED      : 空 prompt で disabled / 4xx code verbatim /
                       絵文字 ▶︎ 禁止 / @heroicons/@fortawesome/react-icons 禁止.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
BUTTON = REPO_ROOT / "frontend" / "src" / "components" / "sessions" / "PlaySessionButton.tsx"
API = REPO_ROOT / "frontend" / "src" / "lib" / "api" / "sessions.ts"
EXISTING_BACKEND_ROUTER = REPO_ROOT / "backend" / "routers" / "agent_runner.py"


@pytest.fixture(scope="module")
def btn_src() -> str:
    return BUTTON.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def api_src() -> str:
    return API.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def backend_src() -> str:
    return EXISTING_BACKEND_ROUTER.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS
# ══════════════════════════════════════════════════════════════════════


def test_ac1_button_exists():
    assert BUTTON.exists()


def test_ac1_api_client_exists():
    assert API.exists()


def test_ac1_button_is_client_component(btn_src):
    assert btn_src.lstrip().startswith('"use client"')


def test_ac1_button_uses_shadcn_button(btn_src):
    assert 'from "@/components/ui/button"' in btn_src
    assert "<Button" in btn_src


def test_ac1_button_uses_lucide_play_icon(btn_src):
    """CLAUDE.md §5.1: Lucide Play icon."""
    assert 'from "lucide-react"' in btn_src
    assert re.search(
        r'import\s*\{[^}]*\bPlay\b[^}]*\}\s*from\s*"lucide-react"',
        btn_src,
    )


def test_ac1_button_uses_cn_utility(btn_src):
    assert 'from "@/lib/utils"' in btn_src
    assert re.search(r"\bcn\(", btn_src)


def test_ac1_api_client_endpoint(api_src):
    assert "/api/agent/sessions" in api_src
    assert "AGENT_SESSIONS_ENDPOINT" in api_src


def test_ac1_api_client_post_method(api_src):
    assert re.search(r'method:\s*"POST"', api_src)


def test_ac1_api_client_exports_typed_error(api_src):
    assert "class AgentSessionError" in api_src
    assert "code:" in api_src


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN
# ══════════════════════════════════════════════════════════════════════


def test_ac2_button_has_loading_state(btn_src):
    assert "loading" in btn_src
    assert "setLoading" in btn_src
    # Loader2 used when loading
    assert re.search(
        r'import\s*\{[^}]*Loader2[^}]*\}\s*from\s*"lucide-react"',
        btn_src,
    )


def test_ac2_button_calls_api_with_run_in_background_true(btn_src):
    """run_in_background=true で T-010b-01 AC-2 (即時 id 返却) 動作."""
    assert "run_in_background: true" in btn_src or '"run_in_background": true' in btn_src


def test_ac2_api_client_defaults_run_in_background_true(api_src):
    """client default も run_in_background=true."""
    # ...body のスプレッド前に default を置く pattern
    assert re.search(
        r"run_in_background:\s*true",
        api_src,
    )


def test_ac2_button_renders_error_code_and_message(btn_src):
    """AC-4 と兼用: backend の {detail:{code,message}} を verbatim render."""
    assert "error.code" in btn_src
    assert "error.message" in btn_src


def test_ac2_api_client_throws_structured_error(api_src):
    assert "data?.detail?.code" in api_src
    assert "data?.detail?.message" in api_src
    assert "throw new AgentSessionError" in api_src


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN
# ══════════════════════════════════════════════════════════════════════


def test_ac3_existing_backend_router_unchanged(backend_src):
    """REFACTOR invariant: agent_runner.py に PlaySessionButton 依存追加なし."""
    assert "PlaySessionButton" not in backend_src
    assert "frontend/" not in backend_src


def test_ac3_backend_create_session_fields_preserved(backend_src):
    """CreateSessionRequest の field 名が renaming されていない."""
    for field in (
        "prompt", "workspace_id", "project_id", "bf_task_id",
        "agent_persona", "model", "run_in_background",
    ):
        assert re.search(rf"\b{field}:", backend_src), (
            f"existing CreateSessionRequest field '{field}' missing"
        )


def test_ac3_button_disabled_while_loading(btn_src):
    """submit 中 button が disabled."""
    assert "disabled={disabled}" in btn_src or "disabled={loading" in btn_src


def test_ac3_button_no_global_store_write(btn_src):
    """zustand / mobx / direct window.* mutation を行わない."""
    assert "useStore(" not in btn_src
    assert ".setState(" not in btn_src
    # window.X = ... の代入はない (subscribeのみは OK)
    assert not re.search(r"window\.\w+\s*=", btn_src)


def test_ac3_api_client_request_shape_matches_backend(api_src, backend_src):
    """typed client の field 名が backend と一致."""
    for field in (
        "prompt", "workspace_id", "project_id", "bf_task_id",
        "agent_persona", "model", "run_in_background",
    ):
        assert field in api_src, f"client missing field '{field}'"
        assert field in backend_src


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED
# ══════════════════════════════════════════════════════════════════════


def test_ac4_empty_prompt_disables_button(btn_src):
    """trimmed prompt が空なら disabled."""
    assert "trim()" in btn_src
    assert re.search(r"trimmedPrompt\.length\s*===\s*0", btn_src)


def test_ac4_no_emoji_play_symbol(btn_src):
    """▶︎ / ▶ 等の絵文字を使わない (CLAUDE.md §5.1)."""
    # U+25B6 (BLACK RIGHT-POINTING TRIANGLE) / U+FE0E variation selector
    forbidden = ("▶", "▶︎", "⏵", "⏵︎")
    for ch in forbidden:
        assert ch not in btn_src, (
            f"forbidden play emoji U+{ord(ch[0]):04X} detected"
        )


def test_ac4_no_emoji_in_button(btn_src):
    """CLAUDE.md §5.1: 全絵文字禁止."""
    emoji_re = re.compile(
        r"[\U0001F000-\U0001FFFF\U00002600-\U000027BF\U0001F300-\U0001F9FF]"
    )
    found = emoji_re.findall(btn_src)
    assert not found, f"emoji detected: {found}"


def test_ac4_no_emoji_in_api(api_src):
    emoji_re = re.compile(
        r"[\U0001F000-\U0001FFFF\U00002600-\U000027BF\U0001F300-\U0001F9FF]"
    )
    found = emoji_re.findall(api_src)
    assert not found, f"emoji detected: {found}"


def test_ac4_no_forbidden_icon_library(btn_src):
    """forbidden icon lib を import していない (comment 記述は許容)."""
    code = _strip_ts_comments(btn_src)
    for lib in ("@heroicons/", "@fortawesome/", "react-icons", "@iconify/"):
        assert lib not in code, f"forbidden icon lib imported: {lib}"


def _strip_ts_comments(src: str) -> str:
    """Remove // line comments and /* */ block comments from TS/TSX source.

    docstring / comment-only mentions of forbidden tokens は除外したい場合に使う.
    """
    # block comments
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    # line comments (only those starting at column 0 or after whitespace)
    out_lines = []
    for line in src.splitlines():
        idx = line.find("//")
        if idx >= 0:
            # ensure it's not inside a string (very rough heuristic: count "/' before //)
            before = line[:idx]
            if before.count('"') % 2 == 0 and before.count("'") % 2 == 0:
                line = before
        out_lines.append(line)
    return "\n".join(out_lines)


def test_ac4_no_hardcoded_secret(btn_src, api_src):
    for src in (btn_src, api_src):
        assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)
        assert not re.search(r"AIza[0-9A-Za-z_-]{20,}", src)
        assert not re.search(r"eyJ[A-Za-z0-9_-]{30,}\.[A-Za-z0-9_-]{30,}", src)


def test_ac4_error_render_uses_code_verbatim(btn_src):
    """generic 'Error' ではなく code を verbatim render."""
    m = re.search(r"\{error\s*&&[\s\S]+?\}\)", btn_src)
    if m:
        block = m.group(0)
        assert "error.code" in block
        assert "error.message" in block


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_010b_04_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-010b-04"), None)
    assert t is not None
    generic = [
        "as specified by feature F-010b",
        "When the relevant API endpoint or service function is invoked for T-010b-04",
        "While refactoring for T-010b-04 is in progress",
        "If invalid input or unauthorized actor is detected during T-010b-04",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], (
                f"T-010b-04 still generic: {phrase!r}"
            )
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "PlaySessionButton.tsx" in full
    assert "/api/agent/sessions" in full
    assert "Lucide" in full or "lucide" in full


def test_tickets_t_010b_04_has_adr_link_and_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-010b-04"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert "TBD" not in str(files)
    assert "backend/routers/agent_runner.py" in files
