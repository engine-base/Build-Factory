"""T-010d-03: swarm_session_detail UI — 4 AC 機械 invariant 検証.

NEW FE タスク. backend pytest として TSX を文字列で静的解析する
(frontend node_modules 未インストール環境でも CI が回る設計, T-009-02 /
T-S0-06 と同 pattern).

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : SwarmSessionDetail.tsx + sessions/[id]/page.tsx +
                       sessions.ts に fetch helper / props signature /
                       default + named export.
  AC-2 EVENT-DRIVEN  : useEffect で fetchAgentSession / onResume → POST
                       /resume / VALID_RESUME_CHOICES が T-S0-08 と一致.
  AC-3 STATE-DRIVEN  : 4 status palette (running=eb-500 / done=eb-700 /
                       crashed=rose-500 / paused=amber-500) / Lucide check /
                       絵文字なし / log 3 column.
  AC-4 UNWANTED      : 404 で empty state / logs 空で placeholder /
                       component が backend を直接呼ばない (layer
                       separation) / no reactflow / langgraph / langchain /
                       litellm.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPONENT = (
    REPO_ROOT / "frontend" / "src" / "components" / "sessions"
    / "SwarmSessionDetail.tsx"
)
PAGE = (
    REPO_ROOT / "frontend" / "src" / "app" / "sessions" / "[id]" / "page.tsx"
)
SESSIONS_API = REPO_ROOT / "frontend" / "src" / "lib" / "api" / "sessions.ts"

EMOJI_PATTERN = re.compile(
    r"[\U0001F300-\U0001FAFF"
    r"\U00002600-\U000027BF"
    r"\U0001F000-\U0001F2FF]"
)


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — files + types + exports
# ══════════════════════════════════════════════════════════════════════


def test_ac1_component_exists():
    assert COMPONENT.exists()


def test_ac1_page_exists():
    assert PAGE.exists()


def test_ac1_sessions_api_exists():
    assert SESSIONS_API.exists()


def test_ac1_component_default_and_named_exports():
    src = COMPONENT.read_text(encoding="utf-8")
    assert "export function SwarmSessionDetail" in src
    assert "export default SwarmSessionDetail" in src


def test_ac1_component_props_signature():
    src = COMPONENT.read_text(encoding="utf-8")
    # SwarmSessionDetailProps interface に session / logs / onResume / onCancel
    assert "interface SwarmSessionDetailProps" in src
    assert re.search(r"session\s*:\s*SwarmSessionData", src)
    assert re.search(r"logs\s*:\s*SwarmLogLine\[\]", src)
    assert "onResume" in src
    assert "onCancel" in src
    assert "className" in src


def test_ac1_sessions_api_exports_required_types():
    src = SESSIONS_API.read_text(encoding="utf-8")
    for sym in (
        "SwarmSessionData",
        "SwarmLogLine",
        "SwarmSessionStatus",
        "VALID_RESUME_CHOICES",
        "ResumeChoice",
        "fetchAgentSession",
        "resumeAgentSession",
    ):
        assert re.search(rf"\b{sym}\b", src), (
            f"sessions.ts missing export: {sym}"
        )


def test_ac1_component_imports_from_sessions_api():
    """REUSE: sessions.ts から types + VALID_RESUME_CHOICES を import."""
    src = COMPONENT.read_text(encoding="utf-8")
    assert "@/lib/api/sessions" in src
    assert "SwarmSessionData" in src
    assert "SwarmLogLine" in src
    assert "ResumeChoice" in src
    assert "VALID_RESUME_CHOICES" in src


def test_ac1_page_uses_app_router_dynamic_segment():
    """[id] segment + useParams from next/navigation."""
    src = PAGE.read_text(encoding="utf-8")
    assert "useParams" in src
    assert "next/navigation" in src
    # path 自体が /sessions/[id]
    assert "sessions" in str(PAGE.parts)
    assert "[id]" in str(PAGE.parts)


def test_ac1_page_renders_swarm_session_detail():
    src = PAGE.read_text(encoding="utf-8")
    assert "SwarmSessionDetail" in src
    assert "@/components/sessions/SwarmSessionDetail" in src


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — fetch on mount / resume choice / T-S0-08 invariant
# ══════════════════════════════════════════════════════════════════════


def test_ac2_page_calls_fetch_agent_session_in_use_effect():
    src = PAGE.read_text(encoding="utf-8")
    assert "useEffect" in src
    assert "fetchAgentSession" in src


def test_ac2_page_calls_resume_agent_session_on_resume():
    src = PAGE.read_text(encoding="utf-8")
    assert "resumeAgentSession" in src


def test_ac2_resume_endpoint_path_matches_t_s0_08():
    """POST /api/agent/sessions/{id}/resume と一致."""
    src = SESSIONS_API.read_text(encoding="utf-8")
    # /sessions/{id}/resume パターン
    assert re.search(
        r"\$\{AGENT_SESSIONS_ENDPOINT\}/\$\{sessionId\}/resume",
        src,
    ), "resumeAgentSession URL pattern drift"


def test_ac2_valid_resume_choices_match_t_s0_08():
    """VALID_RESUME_CHOICES = ('from_checkpoint','rerun_full','manual_fix','cancel').

    T-S0-08 backend `VALID_RESUME_CHOICES` と完全一致 (cross-module invariant).
    """
    src = SESSIONS_API.read_text(encoding="utf-8")
    # const VALID_RESUME_CHOICES = ["from_checkpoint", "rerun_full", "manual_fix", "cancel"]
    m = re.search(
        r"VALID_RESUME_CHOICES\s*=\s*\[([^\]]+)\]",
        src,
    )
    assert m, "VALID_RESUME_CHOICES literal not found"
    choices = re.findall(r'"([^"]+)"', m.group(1))
    assert choices == ["from_checkpoint", "rerun_full", "manual_fix", "cancel"]


def test_ac2_resume_helper_validates_choice():
    """resumeAgentSession が choice を VALID_RESUME_CHOICES で validate."""
    src = SESSIONS_API.read_text(encoding="utf-8")
    # if (!VALID_RESUME_CHOICES.includes(choice))
    assert "VALID_RESUME_CHOICES.includes(choice)" in src


def test_ac2_component_invokes_onresume_callback():
    """SwarmSessionDetail が onResume を呼ぶ."""
    src = COMPONENT.read_text(encoding="utf-8")
    assert re.search(r"onResume\??\.\(", src), (
        "SwarmSessionDetail must invoke onResume callback"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — 4 status palette + Lucide + no emoji
# ══════════════════════════════════════════════════════════════════════


def test_ac3_status_border_running_eb_500():
    src = COMPONENT.read_text(encoding="utf-8")
    assert re.search(r'running\s*:\s*"border-eb-500"', src)


def test_ac3_status_border_done_eb_700():
    src = COMPONENT.read_text(encoding="utf-8")
    assert re.search(r'done\s*:\s*"border-eb-700"', src)


def test_ac3_status_border_crashed_rose_500():
    src = COMPONENT.read_text(encoding="utf-8")
    assert re.search(r'crashed\s*:\s*"border-rose-500"', src)


def test_ac3_status_border_paused_amber_500():
    src = COMPONENT.read_text(encoding="utf-8")
    assert re.search(r'paused\s*:\s*"border-amber-500"', src)


def test_ac3_component_uses_lucide_check_icon():
    src = COMPONENT.read_text(encoding="utf-8")
    assert "lucide-react" in src
    assert re.search(r"\bCheck\b", src)


def test_ac3_no_emoji_in_component():
    src = COMPONENT.read_text(encoding="utf-8")
    hits = EMOJI_PATTERN.findall(src)
    assert not hits, f"emoji in SwarmSessionDetail.tsx: {hits}"


def test_ac3_no_emoji_in_page():
    src = PAGE.read_text(encoding="utf-8")
    hits = EMOJI_PATTERN.findall(src)
    assert not hits, f"emoji in sessions/[id]/page.tsx: {hits}"


def test_ac3_no_hex_color_hardcode():
    """Tailwind class 経由のみ. #1a6648 (ENGINE BASE green) を直接書かない."""
    for path in (COMPONENT, PAGE):
        src = path.read_text(encoding="utf-8")
        assert "#1a6648" not in src
        # 他の brand hex も典型的には無いはず — eb-50 / eb-500 / eb-700 のみ
        # (※ slate / rose / amber / sky / emerald は許可 / shadcn palette)


def test_ac3_log_line_three_columns():
    """log line が time / tool / status の 3 column 構造."""
    src = COMPONENT.read_text(encoding="utf-8")
    assert 'data-testid="log-line"' in src
    assert "formatTime" in src
    # tool span (オプション) + status span
    assert re.search(r"line\.tool", src)
    assert re.search(r"line\.status", src)


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED — 404 / empty / layer separation / no forbidden imports
# ══════════════════════════════════════════════════════════════════════


def test_ac4_page_handles_404_empty_state():
    """status === 404 で 'session not found' を表示."""
    src = PAGE.read_text(encoding="utf-8")
    assert "404" in src
    assert "session not found" in src


def test_ac4_component_handles_empty_logs():
    """logs 空で 'No logs yet' placeholder."""
    src = COMPONENT.read_text(encoding="utf-8")
    assert "logs.length === 0" in src
    assert "No logs yet" in src
    assert 'data-testid="empty-log-state"' in src


def test_ac4_component_does_not_fetch_backend_directly():
    """layer separation: component から fetch / api client を呼ばない.

    docstring / コメントブロック (/** ... */) は除外して検査.
    """
    src = COMPONENT.read_text(encoding="utf-8")
    code = _strip_js_block_comments(src)
    # types は import OK / fetch 関数自体は呼ばない
    assert "fetchAgentSession(" not in code, (
        "SwarmSessionDetail must not call fetchAgentSession — page responsibility"
    )
    assert "resumeAgentSession(" not in code, (
        "SwarmSessionDetail must not call resumeAgentSession directly"
    )
    assert not re.search(r"\bfetch\s*\(", code), (
        "SwarmSessionDetail must not call fetch() directly"
    )
    assert "axios" not in code
    assert "useQuery" not in code
    assert "useSWR" not in code


def _strip_js_block_comments(src: str) -> str:
    """JS/TS の /* ... */ block comment + // line comment を削る."""
    # block comments
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    # line comments
    src = re.sub(r"//[^\n]*", "", src)
    return src


def test_ac4_no_dangerously_set_inner_html():
    for path in (COMPONENT, PAGE):
        src = path.read_text(encoding="utf-8")
        assert "dangerouslySetInnerHTML" not in src


def test_ac4_no_reactflow_legacy():
    """T-009-02 invariant: legacy reactflow 禁止."""
    for path in (COMPONENT, PAGE, SESSIONS_API):
        src = path.read_text(encoding="utf-8")
        assert 'from "reactflow"' not in src
        assert "from 'reactflow'" not in src


def test_ac4_no_langgraph_langchain_litellm():
    for path in (COMPONENT, PAGE, SESSIONS_API):
        src = path.read_text(encoding="utf-8").lower()
        for forbidden in ("langgraph", "langchain", "litellm"):
            assert forbidden not in src, (
                f"forbidden {forbidden} in {path.name}"
            )


def test_ac4_no_hardcoded_secret():
    for path in (COMPONENT, PAGE, SESSIONS_API):
        src = path.read_text(encoding="utf-8")
        assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_010d_03_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-010d-03"), None)
    assert t is not None
    generic = [
        "as specified by feature F-010d",
        "When the user interacts with the UI for T-010d-03",
        "While the new feature for T-010d-03 is enabled",
        "If invalid input or unauthorized actor is detected during T-010d-03",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], (
                f"T-010d-03 still generic: {phrase!r}"
            )
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "SwarmSessionDetail.tsx", "SwarmSessionData", "SwarmLogLine",
        "fetchAgentSession", "VALID_RESUME_CHOICES",
        "border-eb-500", "border-eb-700",
        "border-rose-500", "border-amber-500",
        "sessions/[id]/page.tsx",
    ):
        assert sym in full, f"T-010d-03 AC missing concrete symbol: {sym}"


def test_tickets_t_010d_03_has_adr_link_and_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-010d-03"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert any("sessions.ts" in f for f in files)
    assert any("PlaySessionButton.tsx" in f for f in files)


def test_tickets_t_010d_03_canonical_ears_types():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-010d-03"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == ["UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "UNWANTED"]
