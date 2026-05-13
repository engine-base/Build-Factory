"""T-010d-04: 自動 reconnect + 履歴 fetch — 4 AC 機械 invariant 検証.

NEW FE タスク. backend pytest として TS / TSX を文字列で静的解析
(frontend node_modules 未インストール 環境でも CI 回る / T-009-02 /
T-S0-06 / T-010d-03 と同 pattern).

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : sessions-ws.ts に SessionStreamClient class +
                       fetchSessionReplay / hooks/useSwarmSessionStream.ts /
                       backend WS contract (since_seq query) REUSE /
                       VALID_RESUME_CHOICES を再定義しない.
  AC-2 EVENT-DRIVEN  : exponential backoff (INITIAL=1000 → MAX=30000 cap) /
                       MAX_RECONNECT_ATTEMPTS=8 / since_seq=lastSeq+1 /
                       reconnect_exhausted event / CLEAN_CLOSE_CODES.
  AC-3 STATE-DRIVEN  : hook が replay 先 → WS subscribe / AbortController /
                       cleanup / no fetch in render phase / no langgraph /
                       langchain / litellm / reactflow.
  AC-4 UNWANTED      : invalid sessionId で WS 開かない / 404 で graceful
                       empty / clean close で reconnect しない /
                       close() idempotent.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WS_CLIENT = REPO_ROOT / "frontend" / "src" / "lib" / "api" / "sessions-ws.ts"
HOOK = REPO_ROOT / "frontend" / "src" / "hooks" / "useSwarmSessionStream.ts"
PAGE = (
    REPO_ROOT / "frontend" / "src" / "app" / "sessions" / "[id]" / "page.tsx"
)
SESSIONS_API = REPO_ROOT / "frontend" / "src" / "lib" / "api" / "sessions.ts"
WS_BACKEND = REPO_ROOT / "backend" / "routers" / "ws.py"

EMOJI_PATTERN = re.compile(
    r"[\U0001F300-\U0001FAFF"
    r"\U00002600-\U000027BF"
    r"\U0001F000-\U0001F2FF]"
)


def _strip_js_comments(src: str) -> str:
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    src = re.sub(r"//[^\n]*", "", src)
    return src


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — public API + REUSE invariant
# ══════════════════════════════════════════════════════════════════════


def test_ac1_ws_client_file_exists():
    assert WS_CLIENT.exists()


def test_ac1_hook_file_exists():
    assert HOOK.exists()


def test_ac1_ws_client_exports_session_stream_client_class():
    src = WS_CLIENT.read_text(encoding="utf-8")
    assert "export class SessionStreamClient" in src


def test_ac1_ws_client_exports_fetch_session_replay():
    src = WS_CLIENT.read_text(encoding="utf-8")
    assert re.search(
        r"export\s+async\s+function\s+fetchSessionReplay",
        src,
    )


def test_ac1_ws_client_exports_constants():
    src = WS_CLIENT.read_text(encoding="utf-8")
    for c in (
        "INITIAL_RECONNECT_MS",
        "MAX_RECONNECT_MS",
        "MAX_RECONNECT_ATTEMPTS",
        "CLEAN_CLOSE_CODES",
    ):
        assert re.search(rf"export\s+const\s+{c}\b", src), (
            f"sessions-ws.ts missing export const: {c}"
        )


def test_ac1_session_stream_client_has_start_close_on():
    src = WS_CLIENT.read_text(encoding="utf-8")
    # method patterns inside the class
    assert re.search(r"\bstart\s*\(\s*\)\s*:\s*void", src)
    assert re.search(r"\bclose\s*\(\s*\)\s*:\s*void", src)
    assert re.search(r"\bon\s*\(\s*event\s*:\s*StreamEventName", src)


def test_ac1_hook_exports_use_swarm_session_stream():
    src = HOOK.read_text(encoding="utf-8")
    assert "export function useSwarmSessionStream" in src


def test_ac1_hook_return_type_has_required_fields():
    src = HOOK.read_text(encoding="utf-8")
    # return shape: { logs, connected, lastSeq, reconnectAttempt, error, client }
    assert "logs:" in src
    assert "connected:" in src
    assert "lastSeq:" in src
    assert "reconnectAttempt:" in src
    assert "error:" in src
    assert "client:" in src


def test_ac1_backend_ws_endpoint_unchanged():
    """REUSE invariant: backend/routers/ws.py に T-010d-04 依存追加なし."""
    src = WS_BACKEND.read_text(encoding="utf-8")
    assert "T-010d-04" not in src
    # endpoint signature 変更なし (since_seq query を受け取る前提)
    assert "since_seq" in src
    assert "@router.websocket" in src


def test_ac1_hook_imports_from_sessions_ws():
    src = HOOK.read_text(encoding="utf-8")
    assert "@/lib/api/sessions-ws" in src
    assert "SessionStreamClient" in src
    assert "fetchSessionReplay" in src


def test_ac1_no_redefinition_of_valid_resume_choices():
    """T-S0-08 / T-010d-03 cross-module invariant: VALID_RESUME_CHOICES の
    再定義禁止. sessions-ws.ts と hook では宣言しない (sessions.ts のみ)."""
    for path in (WS_CLIENT, HOOK):
        src = path.read_text(encoding="utf-8")
        code = _strip_js_comments(src)
        # 'VALID_RESUME_CHOICES =' のような assignment が無いこと
        assert not re.search(r"VALID_RESUME_CHOICES\s*=", code), (
            f"VALID_RESUME_CHOICES redefined in {path.name}"
        )


def test_ac1_page_uses_hook():
    src = PAGE.read_text(encoding="utf-8")
    assert "useSwarmSessionStream" in src
    assert "@/hooks/useSwarmSessionStream" in src


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — exponential backoff + since_seq resume + exhaustion
# ══════════════════════════════════════════════════════════════════════


def test_ac2_initial_reconnect_ms_is_1000():
    src = WS_CLIENT.read_text(encoding="utf-8")
    assert re.search(r"INITIAL_RECONNECT_MS\s*=\s*1_?000", src)


def test_ac2_max_reconnect_ms_is_30000():
    src = WS_CLIENT.read_text(encoding="utf-8")
    assert re.search(r"MAX_RECONNECT_MS\s*=\s*30_?000", src)


def test_ac2_max_reconnect_attempts_is_8():
    src = WS_CLIENT.read_text(encoding="utf-8")
    assert re.search(r"MAX_RECONNECT_ATTEMPTS\s*=\s*8\b", src)


def test_ac2_clean_close_codes_1000_1001_1008():
    src = WS_CLIENT.read_text(encoding="utf-8")
    m = re.search(r"CLEAN_CLOSE_CODES[^=]*=\s*\[([^\]]+)\]", src)
    assert m
    codes = re.findall(r"\d+", m.group(1))
    assert set(codes) == {"1000", "1001", "1008"}


def test_ac2_exponential_backoff_formula():
    """delay = INITIAL * 2 ** (attempt - 1), capped at MAX."""
    src = WS_CLIENT.read_text(encoding="utf-8")
    # Math.min(INITIAL_RECONNECT_MS * 2 ** ..., MAX_RECONNECT_MS)
    assert re.search(
        r"INITIAL_RECONNECT_MS\s*\*\s*2\s*\*\*\s*\(",
        src,
    )
    assert "MAX_RECONNECT_MS" in src
    assert "Math.min" in src


def test_ac2_since_seq_is_last_plus_1_on_reconnect():
    """resume 時 since_seq = lastSeq + 1 (T-010d-01 backend contract)."""
    src = WS_CLIENT.read_text(encoding="utf-8")
    # this.lastSeq > 0 ? this.lastSeq + 1 : 0
    assert re.search(r"this\.lastSeq\s*>\s*0\s*\?\s*this\.lastSeq\s*\+\s*1", src)


def test_ac2_emits_reconnect_exhausted_event():
    src = WS_CLIENT.read_text(encoding="utf-8")
    assert re.search(
        r'this\.emit\(\s*["\']reconnect_exhausted["\']',
        src,
    )


def test_ac2_emits_reconnect_attempt_event_with_delay():
    src = WS_CLIENT.read_text(encoding="utf-8")
    assert re.search(
        r'this\.emit\(\s*["\']reconnect_attempt["\']\s*,\s*\{[^}]*delay_ms',
        src,
    )


def test_ac2_reconnect_attempt_increments_before_emit():
    """reconnect_attempt counter が emit より前にインクリメント (test 検証用)."""
    src = WS_CLIENT.read_text(encoding="utf-8")
    inc_pos = src.find("this.reconnectAttempt += 1")
    emit_pos = src.find('this.emit("reconnect_attempt"')
    assert inc_pos > 0 and emit_pos > 0
    assert inc_pos < emit_pos


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — replay-then-WS ordering + AbortController + cleanup
# ══════════════════════════════════════════════════════════════════════


def test_ac3_hook_uses_use_effect():
    src = HOOK.read_text(encoding="utf-8")
    assert "useEffect" in src


def test_ac3_hook_uses_abort_controller():
    src = HOOK.read_text(encoding="utf-8")
    assert "AbortController" in src
    assert "controller.abort()" in src


def test_ac3_hook_fetches_replay_first_then_subscribes_ws():
    """fetchSessionReplay → streamClient.start() の順序を source 上で確認.

    docstring に含まれる `.start()` 記述ではなく、 実コード上での
    `streamClient.start()` の位置を見る.
    """
    code = _strip_js_comments(HOOK.read_text(encoding="utf-8"))
    fetch_pos = code.find("fetchSessionReplay(")
    start_pos = code.find("streamClient.start()")
    assert fetch_pos > 0 and start_pos > 0
    assert fetch_pos < start_pos, (
        "replay must be fetched BEFORE WS subscribe (no flash-of-empty)"
    )


def test_ac3_hook_cleans_up_on_unmount():
    """useEffect cleanup で controller.abort + streamClient.close."""
    src = HOOK.read_text(encoding="utf-8")
    # return () => { ... controller.abort(); streamClient?.close(); }
    assert "return () =>" in src
    assert "controller.abort()" in src
    assert "streamClient?.close()" in src


def test_ac3_hook_does_not_fetch_in_render_phase():
    """top-level (= render 時) に fetch / new SessionStreamClient が無い."""
    src = HOOK.read_text(encoding="utf-8")
    code = _strip_js_comments(src)
    # 関数本体の中で React.useEffect の外で fetch / WebSocket 呼び出しが無い
    # useEffect の {...} 内に閉じ込められていること
    # 単純検査: useEffect の前に fetchSessionReplay / new SessionStreamClient が無い
    use_effect_pos = code.find("useEffect(")
    fetch_pos = code.find("fetchSessionReplay(")
    new_client_pos = code.find("new SessionStreamClient(")
    # fetchSessionReplay は useEffect の中で呼ぶ → fetch_pos > use_effect_pos
    if fetch_pos > 0 and use_effect_pos > 0:
        assert fetch_pos > use_effect_pos
    if new_client_pos > 0 and use_effect_pos > 0:
        assert new_client_pos > use_effect_pos


def test_ac3_no_emoji_in_files():
    for path in (WS_CLIENT, HOOK, PAGE):
        src = path.read_text(encoding="utf-8")
        hits = EMOJI_PATTERN.findall(src)
        assert not hits, f"emoji in {path.name}: {hits}"


def test_ac3_no_langgraph_langchain_litellm_reactflow():
    forbidden = ("langgraph", "langchain", "litellm")
    for path in (WS_CLIENT, HOOK):
        src = path.read_text(encoding="utf-8").lower()
        for bad in forbidden:
            assert bad not in src, f"forbidden {bad} in {path.name}"
        # legacy reactflow も禁止
        assert 'from "reactflow"' not in src
        assert "from 'reactflow'" not in src


def test_ac3_page_renders_connection_status():
    src = PAGE.read_text(encoding="utf-8")
    assert 'data-testid="connection-status"' in src
    assert "stream.connected" in src
    assert "stream.reconnectAttempt" in src


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED — invalid sessionId / 404 graceful / clean close /
#                  idempotent close
# ══════════════════════════════════════════════════════════════════════


def test_ac4_hook_handles_invalid_session_id():
    """sessionId が NaN / <= 0 で WS 開かない + error='invalid sessionId'."""
    src = HOOK.read_text(encoding="utf-8")
    assert "Number.isFinite(sessionId)" in src
    assert "sessionId <= 0" in src
    assert "invalid sessionId" in src


def test_ac4_hook_handles_404_gracefully():
    src = HOOK.read_text(encoding="utf-8")
    assert "e.status === 404" in src
    # 404 で setError(null) + 空 logs
    assert "setLogs([])" in src


def test_ac4_client_skips_reconnect_on_clean_close():
    src = WS_CLIENT.read_text(encoding="utf-8")
    # CLEAN_CLOSE_CODES.includes(ev.code) で return
    assert re.search(
        r"CLEAN_CLOSE_CODES\.includes\(ev\.code\)\s*\)\s*return",
        src,
    ), "clean close で reconnect しないロジックが見つからない"


def test_ac4_client_skips_reconnect_after_caller_close():
    src = WS_CLIENT.read_text(encoding="utf-8")
    assert "this.closedByCaller" in src
    # close() で closedByCaller = true / _scheduleReconnect で return
    assert "this.closedByCaller = true" in src


def test_ac4_close_is_idempotent():
    """close() 内で ws が null でも throw しない / try-catch."""
    src = WS_CLIENT.read_text(encoding="utf-8")
    # close() method の中
    m = re.search(
        r"close\s*\(\s*\)\s*:\s*void\s*\{([\s\S]+?)\n  \}",
        src,
    )
    assert m
    body = m.group(1)
    assert "try" in body or "if (this.ws)" in body
    # null clear で 2 回目以降 no-op
    assert "this.ws = null" in body


def test_ac4_constructor_validates_session_id():
    src = WS_CLIENT.read_text(encoding="utf-8")
    # constructor で Number.isFinite + sessionId <= 0 → throw AgentSessionError
    assert "Number.isFinite(sessionId)" in src
    assert "AgentSessionError" in src
    assert "agent.invalid_session_id" in src


def test_ac4_no_dangerously_set_inner_html():
    for path in (WS_CLIENT, HOOK, PAGE):
        src = path.read_text(encoding="utf-8")
        assert "dangerouslySetInnerHTML" not in src


def test_ac4_no_hardcoded_secret():
    for path in (WS_CLIENT, HOOK, PAGE):
        src = path.read_text(encoding="utf-8")
        assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_010d_04_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-010d-04"), None)
    assert t is not None
    generic = [
        "as specified by feature F-010d",
        "When the user interacts with the UI for T-010d-04",
        "While the new feature for T-010d-04 is enabled",
        "If invalid input or unauthorized actor is detected during T-010d-04",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], (
                f"T-010d-04 still generic: {phrase!r}"
            )
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "SessionStreamClient", "useSwarmSessionStream",
        "fetchSessionReplay", "INITIAL_RECONNECT_MS",
        "MAX_RECONNECT_MS", "MAX_RECONNECT_ATTEMPTS",
        "CLEAN_CLOSE_CODES", "since_seq", "reconnect_exhausted",
    ):
        assert sym in full, f"T-010d-04 AC missing concrete symbol: {sym}"


def test_tickets_t_010d_04_has_adr_link_and_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-010d-04"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert any("sessions.ts" in f for f in files)
    assert any("ws.py" in f for f in files)
    assert any("SwarmSessionDetail" in f for f in files)


def test_tickets_t_010d_04_canonical_ears_types():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-010d-04"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == ["UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "UNWANTED"]
