"""T-010c-06: resume 機能 (4 択) round-trip — 4 AC 機械 invariant 検証.

WK + FE NEW task. backend (handle_resume + resume_session) は既存 (T-S0-08 +
T-010b-01) を REUSE. 新規 frontend hook useSessionResume.ts を追加して
UI button → POST → audit → re-fetch の round-trip を完成させる.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : useSessionResume.ts hook 公開 / sessions.ts の
                       VALID_RESUME_CHOICES 再 import / backend
                       handle_resume + resume_session 無改変 (REUSE).
  AC-2 EVENT-DRIVEN  : 4 choice の status mapping / audit emit
                       (agent.session.resumed) / SDK session preservation.
  AC-3 STATE-DRIVEN  : isResuming は POST + re-fetch window のみ /
                       render phase に backend call なし / lastChoice persist /
                       ADR-010 invariant.
  AC-4 UNWANTED      : invalid sessionId / invalid choice / 404 / 並行
                       resume() 呼出 serialize.
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

from integrations import claude_agent_runner as car


REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK = REPO_ROOT / "frontend" / "src" / "hooks" / "useSessionResume.ts"
SESSIONS_API = REPO_ROOT / "frontend" / "src" / "lib" / "api" / "sessions.ts"
PAGE = (
    REPO_ROOT / "frontend" / "src" / "app" / "sessions" / "[id]" / "page.tsx"
)
BACKEND_RUNNER = REPO_ROOT / "backend" / "integrations" / "claude_agent_runner.py"
BACKEND_ROUTER = REPO_ROOT / "backend" / "routers" / "agent_runner.py"


def _strip_js_comments(src: str) -> str:
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    src = re.sub(r"//[^\n]*", "", src)
    return src


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — hook public surface + REUSE invariant
# ══════════════════════════════════════════════════════════════════════


def test_ac1_hook_file_exists():
    assert HOOK.exists()


def test_ac1_hook_exports_use_session_resume():
    src = HOOK.read_text(encoding="utf-8")
    assert "export function useSessionResume" in src


def test_ac1_hook_exports_resume_choice_to_expected_status():
    src = HOOK.read_text(encoding="utf-8")
    assert "export const RESUME_CHOICE_TO_EXPECTED_STATUS" in src


def test_ac1_hook_return_shape_5_fields():
    src = HOOK.read_text(encoding="utf-8")
    for field in ("resume:", "isResuming:", "lastChoice:", "lastStatus:", "error:"):
        assert field in src, f"hook return shape missing: {field}"


def test_ac1_hook_imports_valid_resume_choices_from_sessions():
    """sessions.ts から VALID_RESUME_CHOICES を re-import (再定義禁止)."""
    src = HOOK.read_text(encoding="utf-8")
    assert "@/lib/api/sessions" in src
    assert "VALID_RESUME_CHOICES" in src
    code = _strip_js_comments(src)
    # `VALID_RESUME_CHOICES =` のような assignment が無いこと
    assert not re.search(r"VALID_RESUME_CHOICES\s*=", code), (
        "VALID_RESUME_CHOICES must NOT be redefined in useSessionResume.ts"
    )


def test_ac1_hook_uses_resume_agent_session_and_fetch_agent_session():
    src = HOOK.read_text(encoding="utf-8")
    assert "resumeAgentSession" in src
    assert "fetchAgentSession" in src


def test_ac1_backend_handle_resume_unchanged_no_t_010c_06_dep():
    """REUSE invariant: handle_resume に T-010c-06 依存追加なし."""
    src = BACKEND_RUNNER.read_text(encoding="utf-8")
    assert "T-010c-06" not in src


def test_ac1_backend_resume_session_unchanged_no_t_010c_06_dep():
    src = BACKEND_ROUTER.read_text(encoding="utf-8")
    assert "T-010c-06" not in src


def test_ac1_page_uses_use_session_resume():
    src = PAGE.read_text(encoding="utf-8")
    assert "useSessionResume" in src
    assert "@/hooks/useSessionResume" in src


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — 4 status mapping + audit + SDK preservation
# ══════════════════════════════════════════════════════════════════════


def test_ac2_status_mapping_cancel_to_cancelled():
    src = HOOK.read_text(encoding="utf-8")
    assert re.search(r'cancel\s*:\s*"cancelled"', src)


def test_ac2_status_mapping_manual_fix_to_paused():
    src = HOOK.read_text(encoding="utf-8")
    assert re.search(r'manual_fix\s*:\s*"paused"', src)


def test_ac2_status_mapping_from_checkpoint_to_running():
    src = HOOK.read_text(encoding="utf-8")
    assert re.search(r'from_checkpoint\s*:\s*"running"', src)


def test_ac2_status_mapping_rerun_full_to_running():
    src = HOOK.read_text(encoding="utf-8")
    assert re.search(r'rerun_full\s*:\s*"running"', src)


def test_ac2_backend_handle_resume_implements_4_branches():
    """handle_resume が 4 choice 全てを分岐実装."""
    src = inspect.getsource(car.ClaudeAgentRunner.handle_resume)
    assert 'choice == "cancel"' in src
    assert 'choice == "manual_fix"' in src
    assert 'choice == "from_checkpoint"' in src
    # rerun_full は fallthrough だが prompt + sdk_session_id=None で run_task
    assert "sdk_session_id=None" in src


def test_ac2_cancel_sets_status_cancelled_in_handle_resume():
    src = inspect.getsource(car.ClaudeAgentRunner.handle_resume)
    assert 'prev.status = "cancelled"' in src


def test_ac2_manual_fix_sets_status_paused_in_handle_resume():
    src = inspect.getsource(car.ClaudeAgentRunner.handle_resume)
    assert 'prev.status = "paused"' in src


def test_ac2_from_checkpoint_preserves_sdk_session_id():
    """SDK session continuity: sdk_session_id=prev.sdk_session_id or None."""
    src = inspect.getsource(car.ClaudeAgentRunner.handle_resume)
    assert "sdk_session_id=prev.sdk_session_id or None" in src


def test_ac2_resume_session_endpoint_emits_audit():
    """backend resume_session が agent.session.resumed event を emit."""
    src = BACKEND_ROUTER.read_text(encoding="utf-8")
    assert '"agent.session.resumed"' in src or "'agent.session.resumed'" in src


def test_ac2_audit_detail_has_choice_and_new_status():
    src = BACKEND_ROUTER.read_text(encoding="utf-8")
    # detail={"session_id": ..., "choice": ..., "new_status": ...}
    assert '"choice":' in src or "'choice':" in src
    assert "new_status" in src


def test_ac2_hook_round_trip_resume_then_fetch():
    """hook ソース上で resumeAgentSession → fetchAgentSession の順序."""
    code = _strip_js_comments(HOOK.read_text(encoding="utf-8"))
    resume_pos = code.find("await resumeAgentSession(")
    fetch_pos = code.find("await fetchAgentSession(")
    assert resume_pos > 0 and fetch_pos > 0
    assert resume_pos < fetch_pos, (
        "resume must complete BEFORE re-fetch (round-trip order)"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — isResuming window / no render-phase fetch / ADR-010
# ══════════════════════════════════════════════════════════════════════


def test_ac3_is_resuming_set_true_before_resume():
    src = HOOK.read_text(encoding="utf-8")
    # setIsResuming(true) が resumeAgentSession の前に置かれる
    pos_true = src.find("setIsResuming(true)")
    pos_post = src.find("resumeAgentSession(")
    assert pos_true > 0 and pos_post > 0
    assert pos_true < pos_post


def test_ac3_is_resuming_set_false_in_finally():
    src = HOOK.read_text(encoding="utf-8")
    # finally block で setIsResuming(false)
    assert "finally" in src
    assert "setIsResuming(false)" in src


def test_ac3_no_fetch_in_render_phase():
    """hook 関数本体に直接 fetch/resume call が無い (useCallback の中だけ)."""
    src = HOOK.read_text(encoding="utf-8")
    code = _strip_js_comments(src)
    use_callback_pos = code.find("useCallback(")
    resume_call_pos = code.find("await resumeAgentSession(")
    assert use_callback_pos > 0 and resume_call_pos > 0
    assert resume_call_pos > use_callback_pos


def test_ac3_no_langgraph_langchain_litellm_reactflow():
    src = HOOK.read_text(encoding="utf-8").lower()
    for forbidden in ("langgraph", "langchain", "litellm"):
        assert forbidden not in src
    assert 'from "reactflow"' not in src


def test_ac3_status_mapping_aligns_with_handle_resume():
    """frontend RESUME_CHOICE_TO_EXPECTED_STATUS と backend handle_resume が
    一致する.

    cancel → cancelled / manual_fix → paused.
    from_checkpoint / rerun_full は run_task に行くので 'running' が
    expected.
    """
    src_fe = HOOK.read_text(encoding="utf-8")
    fe_mapping = {}
    m = re.search(
        r"RESUME_CHOICE_TO_EXPECTED_STATUS[^=]*=\s*\{([^}]+)\}",
        src_fe,
        re.DOTALL,
    )
    assert m
    for key, value in re.findall(r'(\w+)\s*:\s*"([^"]+)"', m.group(1)):
        fe_mapping[key] = value

    # backend handle_resume の status 設定
    be_src = inspect.getsource(car.ClaudeAgentRunner.handle_resume)
    assert ('prev.status = "cancelled"' in be_src
            and fe_mapping["cancel"] == "cancelled")
    assert ('prev.status = "paused"' in be_src
            and fe_mapping["manual_fix"] == "paused")
    # from_checkpoint / rerun_full は run_task → default status='running'
    assert fe_mapping["from_checkpoint"] == "running"
    assert fe_mapping["rerun_full"] == "running"


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED — invalid input / serialization / 404
# ══════════════════════════════════════════════════════════════════════


def test_ac4_hook_rejects_invalid_session_id():
    src = HOOK.read_text(encoding="utf-8")
    assert "Number.isFinite(sessionId)" in src
    assert "sessionId <= 0" in src
    assert '"invalid sessionId"' in src or "'invalid sessionId'" in src


def test_ac4_hook_rejects_invalid_choice_before_backend():
    """choice が VALID_RESUME_CHOICES に無い時、 backend 呼ばずに reject."""
    src = HOOK.read_text(encoding="utf-8")
    assert "VALID_RESUME_CHOICES.includes(choice)" in src
    # invalid choice のチェックが resumeAgentSession より前
    code = _strip_js_comments(src)
    check_pos = code.find("VALID_RESUME_CHOICES.includes(choice)")
    call_pos = code.find("await resumeAgentSession(")
    assert check_pos > 0 and call_pos > 0
    assert check_pos < call_pos


def test_ac4_hook_serializes_concurrent_resume_calls():
    """inflightRef で並行 resume() 呼出を dedupe."""
    src = HOOK.read_text(encoding="utf-8")
    assert "inflightRef" in src
    # inflightRef.current で並行ガード
    assert re.search(r"inflightRef\.current", src)


def test_ac4_inflight_ref_reset_in_finally():
    """finally で inflightRef.current = false / 連続呼び出しを許容."""
    src = HOOK.read_text(encoding="utf-8")
    # finally の中で inflightRef.current = false
    finally_idx = src.find("finally")
    reset_idx = src.find("inflightRef.current = false")
    assert finally_idx > 0 and reset_idx > 0
    assert reset_idx > finally_idx


def test_ac4_backend_resume_404_on_unknown_session():
    """backend handle_resume が LookupError → router で 404."""
    src = BACKEND_ROUTER.read_text(encoding="utf-8")
    # except LookupError as e: → status_code=404
    assert "LookupError" in src
    assert "status_code=404" in src
    assert "agent.session_not_found" in src


def test_ac4_backend_resume_invalid_choice_returns_400():
    src = BACKEND_ROUTER.read_text(encoding="utf-8")
    assert "agent.invalid_resume_choice" in src
    # VALID_RESUME_CHOICES でガード
    assert "VALID_RESUME_CHOICES" in src


def test_ac4_no_hardcoded_secret():
    src = HOOK.read_text(encoding="utf-8")
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# Cross-module invariant (T-S0-08 / T-010d-03 / T-010c-06 整合性)
# ══════════════════════════════════════════════════════════════════════


def test_cross_module_resume_choices_python_ts_aligned():
    """VALID_RESUME_CHOICES が Python (T-S0-08) と TS (sessions.ts) で一致."""
    py = (REPO_ROOT / "backend" / "integrations" / "claude_agent_runner.py").read_text()
    m_py = re.search(r"VALID_RESUME_CHOICES\s*=\s*\(([^)]+)\)", py)
    py_choices = tuple(re.findall(r'"([^"]+)"', m_py.group(1)))

    ts = SESSIONS_API.read_text(encoding="utf-8")
    m_ts = re.search(r"VALID_RESUME_CHOICES\s*=\s*\[([^\]]+)\]", ts)
    ts_choices = tuple(re.findall(r'"([^"]+)"', m_ts.group(1)))

    assert py_choices == ts_choices == (
        "from_checkpoint", "rerun_full", "manual_fix", "cancel",
    )


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_010c_06_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-010c-06"), None)
    assert t is not None
    generic = [
        "as specified by feature F-010c",
        "When the user interacts with the UI for T-010c-06",
        "While the new feature for T-010c-06 is enabled",
        "If invalid input or unauthorized actor is detected during T-010c-06",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], (
                f"T-010c-06 still generic: {phrase!r}"
            )
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "useSessionResume.ts", "useSessionResume",
        "resumeAgentSession", "fetchAgentSession",
        "VALID_RESUME_CHOICES",
        "agent.session.resumed",
        "from_checkpoint", "rerun_full", "manual_fix", "cancel",
    ):
        assert sym in full, f"T-010c-06 AC missing concrete symbol: {sym}"


def test_tickets_t_010c_06_has_adr_link_and_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-010c-06"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert any("claude_agent_runner.py" in f for f in files)
    assert any("agent_runner.py" in f for f in files)
    assert any("sessions.ts" in f for f in files)


def test_tickets_t_010c_06_canonical_ears_types():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-010c-06"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == ["UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "UNWANTED"]
