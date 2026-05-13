"""T-M27-02: Intent 分類 (existing intent_preprocessor / mode_detector / skill_detector 統合).

AC マッピング (1:1 テスト):
  AC-1 UBIQUITOUS    : 3 detector REFACTOR 統合 + top_signal 優先度
  AC-2 EVENT-DRIVEN  : 全 endpoint 2 秒以内 + classify endpoint で audit emit
  AC-3 STATE-DRIVEN  : 既存 3 module API surface 不変 / health で audit emit しない /
                       persistent state mutate しない / coverage baseline 維持
  AC-4 UNWANTED      : invalid input / unauthorized actor → 4xx structured /
                       state mutate なし

Spec gap closure (PR #128 G1-G6 / PR #129 G7-G10 / PR #130 G11-G14 /
PR #131 機械的ガード と同じ精神 / G18-G21):
  G18 register_classifier_backend (SDK 差替点, 例外/不正 fallback)
  G19 rules_only flag (LLM fallback opt-out)
  G20 元 3 module 不変 (symbol surface cross-module check)
  G21 top_signal 優先度 (純関数として export, テスト可)
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from services import intent_classifier as ic
from services.intent_classifier import (
    MAX_ACTOR_USER_ID_LEN,
    MAX_HISTORY_ITEM_CHARS,
    MAX_HISTORY_ITEMS,
    MAX_MESSAGE_CHARS,
    MAX_PRIMARY_SKILL_LEN,
    SIGNAL_PRIORITY,
    VALID_MODES,
    IntentClassifierError,
    top_signal,
)


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_backend():
    """各テスト前後で backend hook を clear (テスト間状態漏れ防止)."""
    ic.register_classifier_backend(None)
    yield
    ic.register_classifier_backend(None)


@pytest.fixture(autouse=True)
def _capture_audit(monkeypatch):
    captured: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({
            "event_type": event_type,
            "session_id": session_id,
            "user_id": user_id,
            "detail": detail or {},
        })
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)
    yield captured


@pytest.fixture(autouse=True)
def _no_openai_key(monkeypatch):
    """LLM fallback を無効化 (テスト deterministic)."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


# ══════════════════════════════════════════════════════════════════════
# Service: constants & invariants
# ══════════════════════════════════════════════════════════════════════


def test_constants_sane():
    assert SIGNAL_PRIORITY == ("explicit", "skill", "mode")
    assert "chat" in VALID_MODES
    assert "task" in VALID_MODES
    assert MAX_MESSAGE_CHARS > 0
    assert MAX_HISTORY_ITEMS > 0
    assert MAX_PRIMARY_SKILL_LEN > 0


# ══════════════════════════════════════════════════════════════════════
# Service: validation (UNWANTED AC-4)
# ══════════════════════════════════════════════════════════════════════


def test_validate_message_rejects_empty():
    for bad in ("", "   ", None, 123, "x" * (MAX_MESSAGE_CHARS + 1)):
        with pytest.raises(IntentClassifierError):
            ic._validate_message(bad)
    assert ic._validate_message("  hello  ") == "hello"


def test_validate_history():
    assert ic._validate_history(None) is None
    assert ic._validate_history([]) == []
    out = ic._validate_history([{"role": "user", "content": "hi"}])
    assert out == [{"role": "user", "content": "hi"}]


def test_validate_history_rejects_non_list_and_oversized():
    for bad in ("not list", {"role": "user"}, 1):
        with pytest.raises(IntentClassifierError):
            ic._validate_history(bad)
    too_big = [{"role": "user", "content": "x"}] * (MAX_HISTORY_ITEMS + 1)
    with pytest.raises(IntentClassifierError):
        ic._validate_history(too_big)


def test_validate_history_rejects_non_dict_item():
    with pytest.raises(IntentClassifierError):
        ic._validate_history(["not dict"])


def test_validate_history_rejects_non_str_content():
    with pytest.raises(IntentClassifierError):
        ic._validate_history([{"role": "user", "content": 123}])


def test_validate_history_rejects_non_str_role():
    with pytest.raises(IntentClassifierError):
        ic._validate_history([{"role": 1, "content": "x"}])


def test_validate_history_rejects_oversized_content():
    big = [{"role": "user", "content": "x" * (MAX_HISTORY_ITEM_CHARS + 1)}]
    with pytest.raises(IntentClassifierError):
        ic._validate_history(big)


def test_validate_history_accepts_message_alias():
    """既存 detector は h.get('content') or h.get('message') を見る."""
    out = ic._validate_history([{"role": "user", "message": "via alias"}])
    # 正規化後は content フィールド
    assert out is not None
    assert out[0]["content"] == "via alias"


def test_validate_primary_skill():
    assert ic._validate_primary_skill(None) is None
    assert ic._validate_primary_skill(" skill-x ") == "skill-x"
    for bad in ("", "   ", 1, "x" * (MAX_PRIMARY_SKILL_LEN + 1)):
        with pytest.raises(IntentClassifierError):
            ic._validate_primary_skill(bad)


def test_validate_actor_user_id():
    assert ic._validate_actor_user_id(None) is None
    assert ic._validate_actor_user_id(" alice ") == "alice"
    for bad in ("", "   ", 1, "x" * (MAX_ACTOR_USER_ID_LEN + 1)):
        with pytest.raises(IntentClassifierError):
            ic._validate_actor_user_id(bad)


def test_validate_rules_only():
    assert ic._validate_rules_only(True) is True
    assert ic._validate_rules_only(False) is False
    for bad in (1, 0, "true", None):
        with pytest.raises(IntentClassifierError):
            ic._validate_rules_only(bad)


# ══════════════════════════════════════════════════════════════════════
# G21: top_signal (pure function priority)
# ══════════════════════════════════════════════════════════════════════


def test_top_signal_explicit_wins_over_skill_and_mode():
    out = top_signal(
        {"type": "remember", "content": "x"},
        "01_sales",
        "task",
    )
    assert out["kind"] == "explicit"
    assert out["value"] == "remember"
    assert out["detail"] == {"type": "remember", "content": "x"}
    assert out["priority_rank"] == 0


def test_top_signal_skill_wins_over_mode():
    out = top_signal(None, "invoice-create", "chat")
    assert out["kind"] == "skill"
    assert out["value"] == "invoice-create"
    assert out["priority_rank"] == 1


def test_top_signal_mode_fallback():
    out = top_signal(None, None, "task")
    assert out["kind"] == "mode"
    assert out["value"] == "task"
    assert out["priority_rank"] == 2


def test_top_signal_all_none_falls_back_to_chat():
    out = top_signal(None, None, "unknown_mode")
    assert out["kind"] == "mode"
    assert out["value"] == "chat"


def test_top_signal_empty_explicit_dict_ignored():
    """type が無い explicit_intent は無視される."""
    out = top_signal({}, "skill-x", "chat")
    assert out["kind"] == "skill"


def test_top_signal_non_dict_explicit_ignored():
    out = top_signal("not dict", "skill-x", "chat")
    assert out["kind"] == "skill"


def test_top_signal_empty_skill_falls_to_mode():
    out = top_signal(None, "", "task")
    assert out["kind"] == "mode"


def test_top_signal_non_str_skill_falls_to_mode():
    out = top_signal(None, 123, "task")
    assert out["kind"] == "mode"


# ══════════════════════════════════════════════════════════════════════
# G18: backend hook
# ══════════════════════════════════════════════════════════════════════


def test_g18_register_backend_callable_only():
    with pytest.raises(IntentClassifierError):
        ic.register_classifier_backend("not callable")
    with pytest.raises(IntentClassifierError):
        ic.register_classifier_backend(123)
    ic.register_classifier_backend(lambda m, h, p: {
        "explicit_intent": None, "mode": "chat", "skill": None,
        "top_signal": {"kind": "mode", "value": "chat", "detail": None, "priority_rank": 2},
    })
    assert ic.get_classifier_backend() is not None
    ic.register_classifier_backend(None)
    assert ic.get_classifier_backend() is None


def test_g18_backend_used_when_registered():
    sentinel = {
        "explicit_intent": {"type": "FROM_BACKEND", "content": "x"},
        "mode": "task",
        "skill": "backend-skill",
        "top_signal": {"kind": "explicit", "value": "FROM_BACKEND",
                       "detail": None, "priority_rank": 0},
    }
    ic.register_classifier_backend(lambda m, h, p: sentinel)
    out = asyncio.run(ic.classify("hello"))
    assert out["config"]["backend_used"] is True
    assert out["explicit_intent"]["type"] == "FROM_BACKEND"
    assert out["skill"] == "backend-skill"


def test_g18_backend_async_callable_also_works():
    async def async_backend(m, h, p):
        return {
            "explicit_intent": None, "mode": "task", "skill": "async-skill",
            "top_signal": {"kind": "skill", "value": "async-skill",
                           "detail": None, "priority_rank": 1},
        }
    ic.register_classifier_backend(async_backend)
    out = asyncio.run(ic.classify("hello"))
    assert out["config"]["backend_used"] is True
    assert out["skill"] == "async-skill"


def test_g18_backend_exception_falls_back():
    def boom(m, h, p):
        raise RuntimeError("backend down")
    ic.register_classifier_backend(boom)
    out = asyncio.run(ic.classify("こんにちは"))
    assert out["config"]["backend_used"] is False
    # heuristic で chat 判定 (CHAT_GREETINGS)
    assert out["mode"] == "chat"


def test_g18_backend_invalid_output_falls_back():
    cases = [
        (lambda m, h, p: "not a dict"),
        (lambda m, h, p: {"mode": "chat"}),  # missing keys
        (lambda m, h, p: {"explicit_intent": None, "mode": "bogus",
                           "skill": None, "top_signal": {}}),  # invalid mode
        (lambda m, h, p: {"explicit_intent": "not dict", "mode": "chat",
                           "skill": None, "top_signal": {}}),
        (lambda m, h, p: {"explicit_intent": None, "mode": "chat",
                           "skill": 123, "top_signal": {}}),  # skill must be str
        (lambda m, h, p: {"explicit_intent": None, "mode": "chat",
                           "skill": None, "top_signal": "not dict"}),
    ]
    for bad in cases:
        ic.register_classifier_backend(bad)
        out = asyncio.run(ic.classify("test"))
        assert out["config"]["backend_used"] is False, f"backend {bad} should fall back"


def test_g18_use_backend_false_skips_backend():
    ic.register_classifier_backend(lambda m, h, p: {
        "explicit_intent": {"type": "BACKEND", "content": "x"},
        "mode": "task", "skill": "x",
        "top_signal": {"kind": "explicit", "value": "BACKEND",
                       "detail": None, "priority_rank": 0},
    })
    out = asyncio.run(ic.classify("hello", use_backend=False))
    assert out["config"]["backend_used"] is False
    # heuristic で実際の検出結果を返す (BACKEND は含まれない)
    if out["explicit_intent"]:
        assert out["explicit_intent"].get("type") != "BACKEND"


# ══════════════════════════════════════════════════════════════════════
# G19: rules_only flag (LLM fallback opt-out)
# ══════════════════════════════════════════════════════════════════════


def test_g19_rules_only_skips_llm_detect(monkeypatch):
    """rules_only=True なら mode_detector.detect_mode (LLM) を呼ばない."""
    import services.mode_detector as md
    llm_called = []

    async def fake_llm(message):
        llm_called.append(message)
        return "task"

    monkeypatch.setattr(md, "llm_detect", fake_llm)
    # rules_only=True かつ rule_detect が None を返す曖昧入力
    out = asyncio.run(ic.classify(
        "I have a question about marketing performance metrics analysis",
        rules_only=True,
    ))
    assert out["config"]["rules_only"] is True
    assert llm_called == [], "LLM should not be called when rules_only=True"


def test_g19_rules_only_false_allows_llm():
    """rules_only=False がデフォルト動作 (LLM fallback あり、ただし OPENAI_API_KEY なしで chat)."""
    out = asyncio.run(ic.classify("hello", rules_only=False))
    assert out["config"]["rules_only"] is False


# ══════════════════════════════════════════════════════════════════════
# G20: 既存 3 detector module 不変保証
# ══════════════════════════════════════════════════════════════════════


def test_g20_intent_preprocessor_unchanged():
    from services import intent_preprocessor as ip
    assert hasattr(ip, "detect_explicit_intent")
    assert hasattr(ip, "REMEMBER_PATTERNS")
    # 既存挙動: 「覚えて」系
    result = ip.detect_explicit_intent("覚えておいて: 私の名前は太郎")
    assert result is not None
    assert result["type"] == "remember"


def test_g20_mode_detector_unchanged():
    from services import mode_detector as md
    for sym in ("rule_detect", "llm_detect", "detect_mode",
                "TASK_KEYWORDS", "CHAT_GREETINGS", "CLASSIFY_PROMPT"):
        assert hasattr(md, sym), f"mode_detector.{sym} missing"
    # 既存挙動: chat keyword
    assert md.rule_detect("こんにちは") == "chat"
    # task keyword
    assert md.rule_detect("請求書を作成して") == "task"


def test_g20_skill_detector_unchanged():
    from services import skill_detector as sd
    for sym in ("detect_skill", "load_skill_md",
                "SKILL_TRIGGERS", "SKILL_CONTINUATION_HINTS"):
        assert hasattr(sd, sym), f"skill_detector.{sym} missing"
    # 既存挙動: SKILL_TRIGGERS
    assert sd.detect_skill("請求書を作って") == "invoice-create"


# ══════════════════════════════════════════════════════════════════════
# Service: classify (AC-1 UBIQUITOUS)
# ══════════════════════════════════════════════════════════════════════


def test_classify_explicit_intent_wins():
    out = asyncio.run(ic.classify("覚えておいて: 私の名前は太郎"))
    assert out["explicit_intent"] is not None
    assert out["explicit_intent"]["type"] == "remember"
    assert out["top_signal"]["kind"] == "explicit"
    assert out["top_signal"]["priority_rank"] == 0


def test_classify_skill_when_no_explicit():
    out = asyncio.run(ic.classify("請求書を作って"))
    assert out["explicit_intent"] is None
    assert out["skill"] == "invoice-create"
    assert out["top_signal"]["kind"] == "skill"
    assert out["top_signal"]["value"] == "invoice-create"


def test_classify_mode_chat_for_greeting():
    out = asyncio.run(ic.classify("こんにちは", rules_only=True))
    assert out["mode"] == "chat"
    assert out["top_signal"]["kind"] in ("mode", "skill")  # skill 該当なら skill だが挨拶は skill 0


def test_classify_mode_task_for_task_keyword():
    out = asyncio.run(ic.classify("市場調査を実行", rules_only=True))
    # 市場調査 = TASK_KEYWORDS
    assert out["mode"] == "task"


def test_classify_returns_full_dict_structure():
    out = asyncio.run(ic.classify("hello"))
    for key in ("message_preview", "explicit_intent", "mode", "skill",
                "top_signal", "config", "meta"):
        assert key in out, f"classify return missing key: {key}"
    assert "latency_ms" in out["meta"]
    assert "input_chars" in out["meta"]
    assert out["meta"]["input_chars"] == 5


def test_classify_message_preview_truncates():
    long_msg = "x" * 200
    out = asyncio.run(ic.classify(long_msg))
    assert len(out["message_preview"]) == 80


def test_classify_with_history_and_primary_skill():
    out = asyncio.run(ic.classify(
        "次のメンバー",
        history=[{"role": "assistant", "content": "リーダーと特化分野について"}],
        employee_primary_skill="staff-management",
    ))
    assert out["config"]["had_history"] is True
    assert out["config"]["had_primary_skill"] is True


def test_classify_latency_ms_recorded():
    out = asyncio.run(ic.classify("hello"))
    assert isinstance(out["meta"]["latency_ms"], (int, float))
    assert out["meta"]["latency_ms"] >= 0


# ══════════════════════════════════════════════════════════════════════
# Service: AC-4 invalid input → raise, state mutate なし
# ══════════════════════════════════════════════════════════════════════


def test_classify_rejects_empty_message():
    with pytest.raises(IntentClassifierError):
        asyncio.run(ic.classify(""))


def test_classify_rejects_oversized_message():
    with pytest.raises(IntentClassifierError):
        asyncio.run(ic.classify("x" * (MAX_MESSAGE_CHARS + 1)))


def test_classify_rejects_empty_actor():
    with pytest.raises(IntentClassifierError):
        asyncio.run(ic.classify("hello", actor_user_id="  "))


def test_classify_rejects_non_bool_rules_only():
    with pytest.raises(IntentClassifierError):
        asyncio.run(ic.classify("hello", rules_only="yes"))


def test_classify_rejects_non_bool_use_backend():
    with pytest.raises(IntentClassifierError):
        asyncio.run(ic.classify("hello", use_backend="yes"))


# ══════════════════════════════════════════════════════════════════════
# AC-1 endpoint smoke
# ══════════════════════════════════════════════════════════════════════


def test_ac1_endpoint_classify(client):
    r = client.post("/api/intent/classify", json={"message": "請求書を作って"})
    assert r.status_code == 200
    body = r.json()
    assert body["skill"] == "invoice-create"
    assert body["top_signal"]["kind"] == "skill"


def test_ac1_endpoint_health(client):
    r = client.get("/api/intent/health")
    assert r.status_code == 200
    body = r.json()
    assert body["all_available"] is True
    assert body["intent_preprocessor"]["available"] is True
    assert body["mode_detector"]["available"] is True
    assert body["skill_detector"]["available"] is True


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: 2 秒以内 + audit emit
# ══════════════════════════════════════════════════════════════════════


def test_ac2_classify_within_2sec(client):
    t0 = time.time()
    r = client.post("/api/intent/classify", json={
        "message": "hello", "rules_only": True,
    })
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_health_within_2sec(client):
    t0 = time.time()
    r = client.get("/api/intent/health")
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_classify_emits_audit(client, _capture_audit):
    r = client.post("/api/intent/classify", json={
        "message": "請求書を作って",
        "actor_user_id": "alice",
    })
    assert r.status_code == 200
    events = [e for e in _capture_audit if e["event_type"] == "intent.classified"]
    assert len(events) == 1
    detail = events[0]["detail"]
    assert detail["top_signal_kind"] == "skill"
    assert detail["top_signal_value"] == "invoice-create"
    assert detail["skill"] == "invoice-create"
    assert "latency_ms" in detail
    assert "input_chars" in detail
    assert events[0]["user_id"] == "alice"


def test_ac2_error_shape_consistency(client):
    """全 error path で {detail:{code,message}} + 'intent.' prefix."""
    cases = [
        # actor 空 → 401 (router _check_actor)
        ("POST", "/api/intent/classify",
         {"message": "x", "actor_user_id": "  "}, 401),
        # rules_only 不正型 (list は pydantic でも coerce 不可) → 422
        ("POST", "/api/intent/classify",
         {"message": "x", "rules_only": ["not", "bool"]}, 422),
        # message 欠落 → 422 pydantic
        ("POST", "/api/intent/classify", {}, 422),
    ]
    for method, path, body, expected_status in cases:
        r = client.post(path, json=body)
        assert r.status_code == expected_status, (
            f"{path}/{body}: got {r.status_code} expected {expected_status}"
        )
        if r.status_code != 422:  # 422 は pydantic で structured detail
            detail = r.json()["detail"]
            assert isinstance(detail, dict)
            assert "code" in detail and "message" in detail
            assert detail["code"].startswith("intent."), f"{path}: {detail['code']}"


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: 既存 module 不変 + read endpoint で audit emit しない
# ══════════════════════════════════════════════════════════════════════


def test_ac3_health_no_audit(client, _capture_audit):
    client.get("/api/intent/health")
    assert not [e for e in _capture_audit if e["event_type"].startswith("intent.")]


def test_ac3_audit_includes_full_signal_detail(client, _capture_audit):
    """audit detail に top_signal + mode + skill + has_explicit が含まれる."""
    r = client.post("/api/intent/classify", json={
        "message": "覚えておいて: 名前は太郎",
    })
    assert r.status_code == 200
    events = [e for e in _capture_audit if e["event_type"] == "intent.classified"]
    assert len(events) == 1
    detail = events[0]["detail"]
    assert detail["top_signal_kind"] == "explicit"
    assert detail["top_signal_value"] == "remember"
    assert detail["has_explicit"] is True


def test_ac3_existing_modules_routes_unchanged(client):
    """T-M27-02 追加で他 endpoint が消えていない."""
    paths = [getattr(r, "path", "") for r in client.app.routes]
    # 主要 endpoint が残っている
    assert "/health" in paths
    assert any(p.startswith("/api/long-term") for p in paths)
    assert "/api/intent/classify" in paths


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED endpoint level
# ══════════════════════════════════════════════════════════════════════


def test_ac4_classify_empty_message_pydantic_422(client):
    r = client.post("/api/intent/classify", json={"message": ""})
    assert r.status_code == 422


def test_ac4_classify_oversized_message_pydantic_422(client):
    r = client.post("/api/intent/classify", json={
        "message": "x" * (MAX_MESSAGE_CHARS + 1),
    })
    assert r.status_code == 422


def test_ac4_classify_missing_message_pydantic_422(client):
    r = client.post("/api/intent/classify", json={})
    assert r.status_code == 422


def test_ac4_classify_unauthorized_actor_401(client):
    r = client.post("/api/intent/classify", json={
        "message": "hello", "actor_user_id": "  ",
    })
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "intent.unauthorized"


def test_ac4_classify_invalid_history_returns_422(client):
    """history が list[dict] 不適合は pydantic 段で 422."""
    r = client.post("/api/intent/classify", json={
        "message": "x",
        "history": ["not a dict"],
    })
    assert r.status_code == 422


def test_ac4_unauthorized_no_audit_emitted(client, _capture_audit):
    r = client.post("/api/intent/classify", json={
        "message": "x", "actor_user_id": "  ",
    })
    assert r.status_code == 401
    assert not [e for e in _capture_audit if e["event_type"] == "intent.classified"]


def test_ac4_invalid_input_no_audit_emitted(client, _capture_audit):
    r = client.post("/api/intent/classify", json={
        "message": "x", "history": ["not dict"],
    })
    assert r.status_code == 422
    assert not [e for e in _capture_audit if e["event_type"] == "intent.classified"]


def test_ac4_service_invalid_history_inside_dict_returns_400(client, _capture_audit):
    """history の各 dict 内が不正な型なら service 段で 400 (pydantic 通過後)."""
    r = client.post("/api/intent/classify", json={
        "message": "x",
        "history": [{"role": 1, "content": "x"}],  # role が int
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "intent.invalid"
    assert not [e for e in _capture_audit if e["event_type"] == "intent.classified"]


# ══════════════════════════════════════════════════════════════════════
# ADR-010 整合性: LangGraph 不使用
# ══════════════════════════════════════════════════════════════════════


def _strip_comments_and_docstrings(src: str) -> str:
    """Python source から comment + module/function docstring を除く (簡易)."""
    import re
    out_lines = []
    in_triple = False
    triple_char = None
    for raw in src.splitlines():
        line = raw
        # triple-quoted strings 中
        if in_triple:
            if triple_char in line:
                line = line.split(triple_char, 1)[1]
                in_triple = False
            else:
                continue
        # 行内の triple-quoted 開始
        for ch in ('"""', "'''"):
            if ch in line:
                before, _, after = line.partition(ch)
                if ch in after:  # 同一行で閉じる
                    line = before + after.split(ch, 1)[1]
                else:
                    line = before
                    in_triple = True
                    triple_char = ch
                break
        # コメント削除
        if "#" in line:
            line = line.split("#", 1)[0]
        if line.strip():
            out_lines.append(line)
    return "\n".join(out_lines)


def test_no_langgraph_import_in_service():
    """ADR-010 §UNWANTED: LangGraph/LangChain import なし (コード本体のみ検査)."""
    import inspect
    src = _strip_comments_and_docstrings(inspect.getsource(ic))
    assert "langgraph" not in src.lower()
    assert "langchain" not in src.lower()


def test_no_langgraph_import_in_router():
    from routers import intent_classifier as router_mod
    import inspect
    src = _strip_comments_and_docstrings(inspect.getsource(router_mod))
    assert "langgraph" not in src.lower()
    assert "langchain" not in src.lower()


# ══════════════════════════════════════════════════════════════════════
# Module docstring (G18-G21 + 設計境界 明示) — 発見性
# ══════════════════════════════════════════════════════════════════════


def test_module_docstring_documents_g18_g21():
    doc = ic.__doc__ or ""
    for tag in ("G18", "G19", "G20", "G21"):
        assert tag in doc, f"module docstring must mention {tag}"


def test_module_docstring_documents_3_detectors():
    doc = ic.__doc__ or ""
    assert "intent_preprocessor" in doc
    assert "mode_detector" in doc
    assert "skill_detector" in doc


def test_module_docstring_references_adr_010():
    doc = ic.__doc__ or ""
    assert "ADR-010" in doc
