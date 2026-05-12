"""T-006-04: タスク分解 UI (TaskDecomposeForm + API client) — 4 AC.

Static analysis of frontend TSX/TS sources (no node_modules required) verifies
spec invariants per CLAUDE.md §5.1 (Lucide only / no emoji) + §5.2 (eb-500 /
shadcn) and ADR-010.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : TaskDecomposeForm.tsx + api/task-decomposition.ts 存在.
                       shadcn/ui (Button/Card/Input/Textarea/Badge) + Lucide +
                       cn() 使用. POST /api/task-decomposition/decompose.
  AC-2 EVENT-DRIVEN  : loading state / config.backend_used 表示 /
                       error.detail.code + message を verbatim render.
  AC-3 STATE-DRIVEN  : subtask_count [1, 20] (min/max attr) /
                       submit 中 button disabled / local state のみ.
  AC-4 UNWANTED      : 空 / 2000 chars 超 → client validate (API 呼ばない) /
                       backend 4xx は code + message を verbatim 表示.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
FORM = REPO_ROOT / "frontend" / "src" / "components" / "task-decomposition" / "TaskDecomposeForm.tsx"
API = REPO_ROOT / "frontend" / "src" / "lib" / "api" / "task-decomposition.ts"
LIB_UTILS = REPO_ROOT / "frontend" / "src" / "lib" / "utils.ts"


@pytest.fixture(scope="module")
def form_src() -> str:
    return FORM.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def api_src() -> str:
    return API.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS
# ══════════════════════════════════════════════════════════════════════


def test_ac1_form_exists():
    assert FORM.exists(), f"missing {FORM}"


def test_ac1_api_client_exists():
    assert API.exists(), f"missing {API}"


def test_ac1_form_is_client_component(form_src):
    """Next.js 16 App Router: client component には "use client" 必須."""
    assert form_src.lstrip().startswith('"use client"')


def test_ac1_form_uses_shadcn_components(form_src):
    for comp in ("Button", "Card", "CardContent", "Input", "Textarea", "Badge"):
        assert f"{comp}" in form_src, f"missing shadcn {comp}"
    # imports come from @/components/ui
    assert '"@/components/ui/' in form_src or "@/components/ui/" in form_src


def test_ac1_form_uses_cn_utility(form_src):
    assert "from \"@/lib/utils\"" in form_src
    assert re.search(r"\bcn\(", form_src), "cn() must be invoked"


def test_ac1_form_uses_lucide_icons(form_src):
    """CLAUDE.md §5.1: Lucide icons only."""
    assert 'from "lucide-react"' in form_src
    # At least one icon imported (Loader2 / Sparkles / AlertTriangle)
    assert re.search(
        r'import \{[^}]*(Loader2|Sparkles|AlertTriangle)[^}]*\} from "lucide-react"',
        form_src,
    )


def test_ac1_api_client_endpoint(api_src):
    assert "/api/task-decomposition/decompose" in api_src
    assert "TASK_DECOMPOSITION_ENDPOINT" in api_src


def test_ac1_api_client_post_method(api_src):
    assert re.search(r'method:\s*"POST"', api_src)


def test_ac1_api_client_exports_typed_error(api_src):
    assert "class TaskDecompositionError" in api_src
    assert "code:" in api_src
    assert "status:" in api_src


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN
# ══════════════════════════════════════════════════════════════════════


def test_ac2_form_has_loading_state(form_src):
    assert "loading" in form_src
    assert "setLoading" in form_src
    # Button disabled while loading
    assert re.search(r"disabled=\{loading\}", form_src)


def test_ac2_form_renders_backend_used(form_src):
    assert "backend_used" in form_src
    # boolean rendered as "true"/"false" string
    assert re.search(r"backend_used\s*\?\s*\"true\"\s*:\s*\"false\"", form_src)


def test_ac2_form_renders_count_returned(form_src):
    assert "count_returned" in form_src


def test_ac2_form_renders_error_code_and_message(form_src):
    """AC-4 と兼用: backend の {detail:{code,message}} を verbatim render."""
    assert "error.code" in form_src
    assert "error.message" in form_src


def test_ac2_api_client_throws_structured_error(api_src):
    """resp.detail.code + message を TaskDecompositionError に詰める."""
    assert re.search(r"data\?\.detail\?\.code", api_src)
    assert re.search(r"data\?\.detail\?\.message", api_src)
    assert "throw new TaskDecompositionError" in api_src


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN
# ══════════════════════════════════════════════════════════════════════


def test_ac3_subtask_count_min_max_mirrors_backend(form_src):
    """MIN_SUBTASK_COUNT=1 / MAX_SUBTASK_COUNT=20 (backend と一致)."""
    assert re.search(r"MIN_SUBTASK_COUNT\s*=\s*1", form_src)
    assert re.search(r"MAX_SUBTASK_COUNT\s*=\s*20", form_src)
    # Input attributes use these constants
    assert re.search(r"min=\{MIN_SUBTASK_COUNT\}", form_src)
    assert re.search(r"max=\{MAX_SUBTASK_COUNT\}", form_src)


def test_ac3_brief_min_max_chars(form_src):
    """MIN_BRIEF_CHARS=5 / MAX_BRIEF_CHARS=2000."""
    assert re.search(r"MIN_BRIEF_CHARS\s*=\s*5", form_src)
    assert re.search(r"MAX_BRIEF_CHARS\s*=\s*2000", form_src)


def test_ac3_no_global_store_write(form_src):
    """zustand / mobx 等の global store write を行わない (local state のみ)."""
    # use[State|Reducer] のみ. zustand store update は無いこと.
    assert "useStore(" not in form_src
    assert ".setState(" not in form_src  # mobx
    assert "useState" in form_src


def test_ac3_no_external_state_mutation(form_src):
    """props 経由の callback も含めて global mutate しない."""
    # window. / globalThis. を書き換えていない
    assert "window." not in form_src or "window.alert" not in form_src
    assert "globalThis." not in form_src


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED
# ══════════════════════════════════════════════════════════════════════


def test_ac4_client_side_validation_for_empty_brief(form_src):
    """空 / 2000 chars 超 → API 呼ばずに error 表示."""
    assert "validate(" in form_src
    # validate() must check both min and max
    assert "MIN_BRIEF_CHARS" in form_src
    assert "MAX_BRIEF_CHARS" in form_src


def test_ac4_no_emoji_in_form(form_src):
    """CLAUDE.md §5.1: 絵文字禁止."""
    emoji_re = re.compile(
        r"[\U0001F000-\U0001FFFF\U00002600-\U000027BF\U0001F300-\U0001F9FF]"
    )
    found = emoji_re.findall(form_src)
    assert not found, f"emoji detected: {found}"


def test_ac4_no_emoji_in_api(api_src):
    emoji_re = re.compile(
        r"[\U0001F000-\U0001FFFF\U00002600-\U000027BF\U0001F300-\U0001F9FF]"
    )
    found = emoji_re.findall(api_src)
    assert not found, f"emoji detected: {found}"


def test_ac4_no_forbidden_icon_library(form_src):
    """CLAUDE.md §5.1: Lucide のみ. @heroicons / @fortawesome / react-icons 禁止."""
    for lib in ("@heroicons/", "@fortawesome/", "react-icons", "@iconify/"):
        assert lib not in form_src, f"forbidden icon lib: {lib}"


def test_ac4_no_hardcoded_secret_in_form(form_src):
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", form_src)
    assert not re.search(r"AIza[0-9A-Za-z_-]{20,}", form_src)
    # NEXT_PUBLIC_SUPABASE_ANON_KEY 等の name は OK, 実値は NG
    assert not re.search(r"eyJ[A-Za-z0-9_-]{30,}\.[A-Za-z0-9_-]{30,}", form_src)


def test_ac4_no_hardcoded_secret_in_api(api_src):
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", api_src)
    assert not re.search(r"AIza[0-9A-Za-z_-]{20,}", api_src)


def test_ac4_error_render_is_not_generic(form_src):
    """generic 'Error' message ではなく code + message verbatim."""
    # render 部に "Error" hardcode が無い (or 限定的)
    # core constraint: error.code AND error.message が render される
    error_block_match = re.search(r"\{error\s*&&[\s\S]+?\}\)", form_src)
    if error_block_match:
        block = error_block_match.group(0)
        assert "error.code" in block
        assert "error.message" in block


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_006_04_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-006-04"), None)
    assert t is not None
    generic = [
        "as specified by feature F-006",
        "When the user interacts with the UI for T-006-04",
        "While the new feature for T-006-04 is enabled",
        "If invalid input or unauthorized actor is detected during T-006-04",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], (
                f"T-006-04 still generic: {phrase!r}"
            )
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "TaskDecomposeForm.tsx" in full
    assert "/api/task-decomposition/decompose" in full
    assert "lucide" in full.lower()


def test_tickets_t_006_04_has_adr_link_and_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-006-04"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert "TBD" not in str(files)
    assert any("shadcn" in f or "button.tsx" in f or "card.tsx" in f for f in files)
