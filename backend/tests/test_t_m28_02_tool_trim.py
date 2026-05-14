"""T-M28-02: Tier 1 tool result trimming (SDK auto activation + audit wrapper) — 4 AC 全網羅.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : SDK 内蔵 trim を有効化 / app code で trimming logic を
                       実装しない (scripts/lint-mock.sh で機械検知).
  AC-2 EVENT-DRIVEN  : SDK trim 完了時に tier1.tool_result_trimmed audit emit.
                       detail = {session_id, original_size, trimmed_size,
                                 reduction_ratio, timestamp, ...}.
  AC-3 STATE-DRIVEN  : chat_messages 不変 (SDK 側保持) / audit のみ書込.
  AC-4 UNWANTED      : 自前 trimming logic → lint fail / invalid input /
                       unauthorized → Tier1ToolTrimError → 4xx + state mutate なし.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import tier1_tool_trim as t1
from services.tier1_tool_trim import (
    MAX_ACTOR_USER_ID_LEN,
    MAX_ORIGINAL_SIZE,
    MAX_REASON_LEN,
    MAX_SESSION_ID_LEN,
    MAX_TOOL_NAME_LEN,
    TRIM_AUDIT_EVENT,
    Tier1ToolTrimError,
    VALID_TRIM_REASONS,
    record_trim_event,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


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


# ══════════════════════════════════════════════════════════════════════
# Constants & invariants
# ══════════════════════════════════════════════════════════════════════


def test_constants_sane():
    assert TRIM_AUDIT_EVENT == "tier1.tool_result_trimmed"
    assert MAX_SESSION_ID_LEN > 0
    assert MAX_ORIGINAL_SIZE > 0
    assert "policy" in VALID_TRIM_REASONS
    assert "size_cap" in VALID_TRIM_REASONS


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: validation
# ══════════════════════════════════════════════════════════════════════


def test_validate_session_id_rejects_blank():
    for bad in ("", "  ", None, 1, []):
        with pytest.raises(Tier1ToolTrimError):
            t1._validate_session_id(bad)


def test_validate_session_id_rejects_too_long():
    with pytest.raises(Tier1ToolTrimError):
        t1._validate_session_id("s" * (MAX_SESSION_ID_LEN + 1))


def test_validate_size_rejects_bad():
    for bad in (-1, True, "1", 1.5, None):
        with pytest.raises(Tier1ToolTrimError):
            t1._validate_size(bad, field_name="x")


def test_validate_size_rejects_too_large():
    with pytest.raises(Tier1ToolTrimError):
        t1._validate_size(MAX_ORIGINAL_SIZE + 1, field_name="x")


def test_validate_size_accepts_zero_and_max():
    assert t1._validate_size(0, field_name="x") == 0
    assert t1._validate_size(MAX_ORIGINAL_SIZE, field_name="x") == MAX_ORIGINAL_SIZE


def test_validate_actor_user_id_rejects_blank():
    with pytest.raises(Tier1ToolTrimError):
        t1._validate_actor_user_id("   ")


def test_validate_actor_user_id_rejects_too_long():
    with pytest.raises(Tier1ToolTrimError):
        t1._validate_actor_user_id("x" * (MAX_ACTOR_USER_ID_LEN + 1))


def test_validate_actor_user_id_accepts_none():
    assert t1._validate_actor_user_id(None) is None


def test_validate_tool_name_rejects_blank_when_provided():
    with pytest.raises(Tier1ToolTrimError):
        t1._validate_tool_name("  ")
    assert t1._validate_tool_name(None) is None
    assert t1._validate_tool_name("Bash") == "Bash"


def test_validate_reason_unknown_rejected():
    with pytest.raises(Tier1ToolTrimError):
        t1._validate_reason("magic_reason_xyz")


def test_validate_reason_none_or_blank_defaults_to_policy():
    assert t1._validate_reason(None) == "policy"
    assert t1._validate_reason("   ") == "policy"


@pytest.mark.parametrize("reason", list(VALID_TRIM_REASONS))
def test_validate_reason_accepts_each_valid(reason):
    assert t1._validate_reason(reason) == reason


# ══════════════════════════════════════════════════════════════════════
# record_trim_event: 成功経路 (AC-1 / AC-2)
# ══════════════════════════════════════════════════════════════════════


def test_record_trim_event_returns_full_payload(_capture_audit):
    result = asyncio.run(record_trim_event(
        "sess-A", 1000, 250, actor_user_id="alice", reason="size_cap",
    ))
    assert result["session_id"] == "sess-A"
    assert result["original_size"] == 1000
    assert result["trimmed_size"] == 250
    assert result["delta_bytes"] == 750
    assert result["reduction_ratio"] == pytest.approx(0.75)
    assert result["reason"] == "size_cap"
    assert isinstance(result["timestamp"], float)
    assert result["audit_event_id"] is not None


def test_record_trim_event_zero_original_yields_zero_ratio(_capture_audit):
    """original=0, trimmed=0 で 0 除算回避."""
    result = asyncio.run(record_trim_event("s", 0, 0))
    assert result["reduction_ratio"] == 0.0


def test_record_trim_event_no_trim_yields_zero_delta(_capture_audit):
    """trim 不要 (orig == trimmed) でも event は記録."""
    result = asyncio.run(record_trim_event("s", 500, 500))
    assert result["delta_bytes"] == 0
    assert result["reduction_ratio"] == 0.0


def test_record_trim_event_reason_defaults_to_policy(_capture_audit):
    result = asyncio.run(record_trim_event("s", 100, 50))
    assert result["reason"] == "policy"


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: trimmed > original は不変条件違反, state mutate なし
# ══════════════════════════════════════════════════════════════════════


def test_ac3_trimmed_larger_than_original_raises(_capture_audit):
    """SDK 不変条件違反 (trim で大きくなるのは異常). state mutate なし."""
    with pytest.raises(Tier1ToolTrimError, match="trimmed_size"):
        asyncio.run(record_trim_event("s", 100, 200))
    assert all(e["event_type"] != TRIM_AUDIT_EVENT for e in _capture_audit)


def test_ac3_invalid_input_does_not_emit_audit(_capture_audit):
    with pytest.raises(Tier1ToolTrimError):
        asyncio.run(record_trim_event("", 100, 50))
    assert all(e["event_type"] != TRIM_AUDIT_EVENT for e in _capture_audit)


def test_ac3_blank_actor_does_not_emit_audit(_capture_audit):
    with pytest.raises(Tier1ToolTrimError):
        asyncio.run(record_trim_event(
            "s", 100, 50, actor_user_id="   ",
        ))
    assert all(e["event_type"] != TRIM_AUDIT_EVENT for e in _capture_audit)


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: audit emit
# ══════════════════════════════════════════════════════════════════════


def test_ac2_audit_emits_trim_event(_capture_audit):
    asyncio.run(record_trim_event(
        "sess-B", 10000, 2500, actor_user_id="alice",
        tool_name="Bash", reason="window_eviction",
    ))
    events = [e for e in _capture_audit if e["event_type"] == TRIM_AUDIT_EVENT]
    assert len(events) == 1
    detail = events[0]["detail"]
    # 仕様要求 4 attrs
    assert detail["session_id"] == "sess-B"
    assert detail["original_size"] == 10000
    assert detail["trimmed_size"] == 2500
    # 追加 attrs
    assert detail["delta_bytes"] == 7500
    assert detail["reduction_ratio"] == pytest.approx(0.75)
    assert detail["tool_name"] == "Bash"
    assert detail["reason"] == "window_eviction"
    assert "timestamp" in detail
    assert detail["actor_user_id"] == "alice"


def test_ac2_audit_omits_actor_when_anonymous(_capture_audit):
    """anonymous (actor_user_id=None) 時は detail に actor_user_id を含めない."""
    asyncio.run(record_trim_event("s", 100, 50))
    detail = _capture_audit[0]["detail"]
    assert "actor_user_id" not in detail


def test_ac2_record_within_2sec(_capture_audit):
    t0 = time.time()
    asyncio.run(record_trim_event("s", 100, 50))
    assert (time.time() - t0) < 2.0


# ══════════════════════════════════════════════════════════════════════
# Endpoint smoke (AC-1 / AC-2 / AC-4)
# ══════════════════════════════════════════════════════════════════════


def test_endpoint_trim_success(client, _capture_audit):
    r = client.post("/api/tier1/tool-result-trim", json={
        "session_id": "s-1", "original_size": 1000, "trimmed_size": 250,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "s-1"
    assert body["delta_bytes"] == 750


def test_endpoint_trim_within_2sec(client, _capture_audit):
    t0 = time.time()
    r = client.post("/api/tier1/tool-result-trim", json={
        "session_id": "s-1", "original_size": 100, "trimmed_size": 50,
    })
    assert r.status_code == 200
    assert (time.time() - t0) < 2.0


def test_endpoint_trim_inverted_sizes_400(client, _capture_audit):
    """trimmed > original は service の不変条件違反 (400)."""
    r = client.post("/api/tier1/tool-result-trim", json={
        "session_id": "s-1", "original_size": 100, "trimmed_size": 200,
    })
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "tier1.invalid"


def test_endpoint_trim_unauthorized_401(client, _capture_audit):
    r = client.post("/api/tier1/tool-result-trim", json={
        "session_id": "s", "original_size": 100, "trimmed_size": 50,
        "actor_user_id": "   ",
    })
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "tier1.unauthorized"


def test_endpoint_trim_invalid_reason_400(client, _capture_audit):
    r = client.post("/api/tier1/tool-result-trim", json={
        "session_id": "s", "original_size": 100, "trimmed_size": 50,
        "reason": "magic_xyz",
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "tier1.invalid"


def test_endpoint_trim_session_id_blank_400_not_422(client):
    """AC-4: 全 4xx は {detail:{code,message}} に統一. 422 は返さない."""
    r = client.post("/api/tier1/tool-result-trim", json={
        "session_id": "", "original_size": 100, "trimmed_size": 50,
    })
    assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == "tier1.invalid"
    assert "message" in detail


def test_endpoint_trim_missing_required_400(client):
    r = client.post("/api/tier1/tool-result-trim", json={
        "original_size": 100, "trimmed_size": 50,
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "tier1.invalid"
    assert "session_id" in r.json()["detail"]["message"]


def test_endpoint_trim_oversize_400_not_422(client):
    """range 違反 (>= 0 / <= MAX_ORIGINAL_SIZE) も 422 でなく 400."""
    r = client.post("/api/tier1/tool-result-trim", json={
        "session_id": "s", "original_size": -1, "trimmed_size": 0,
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "tier1.invalid"


def test_endpoint_trim_non_dict_body_400(client):
    r = client.post("/api/tier1/tool-result-trim", json=["not", "a", "dict"])
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "tier1.invalid"


def test_endpoint_4xx_detail_shape_all_paths(client):
    """AC-4: 全 4xx response が {detail:{code,message}} 形式 (再帰検証)."""
    cases = [
        # (json, expected_status)
        ({}, 400),
        ({"session_id": "s"}, 400),
        ({"session_id": "", "original_size": 1, "trimmed_size": 0}, 400),
        ({"session_id": "s", "original_size": -1, "trimmed_size": 0}, 400),
        ({"session_id": "s", "original_size": 1, "trimmed_size": 2}, 400),
        ({"session_id": "s", "original_size": 1, "trimmed_size": 0,
          "reason": "magic"}, 400),
        ({"session_id": "s", "original_size": 1, "trimmed_size": 0,
          "actor_user_id": "   "}, 401),
    ]
    for body, expected in cases:
        r = client.post("/api/tier1/tool-result-trim", json=body)
        assert r.status_code == expected, f"{body} -> {r.status_code}: {r.text}"
        detail = r.json()["detail"]
        assert isinstance(detail, dict), f"{body}: detail must be dict"
        assert detail.get("code", "").startswith("tier1."), f"{body}: bad code"
        assert isinstance(detail.get("message", ""), str) and detail["message"]


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: session_id kwarg (audit_logs.session_id column)
# ══════════════════════════════════════════════════════════════════════


def test_ac2_audit_session_id_kwarg_passed(_capture_audit):
    """audit_logs.session_id column へマップされる kwarg として渡されること."""
    asyncio.run(record_trim_event("sess-C", 100, 25))
    ev = next(e for e in _capture_audit if e["event_type"] == TRIM_AUDIT_EVENT)
    # detail にも session_id (記録要件) / kwarg にも session_id (column マップ)
    assert ev["session_id"] == "sess-C"
    assert ev["detail"]["session_id"] == "sess-C"


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: chat_messages の destructive mutation なし
# ══════════════════════════════════════════════════════════════════════


def test_ac3_module_does_not_import_chat_messages_writer():
    """tier1_tool_trim module は chat_messages を書換しない.

    chat_thread_store / chat_messages writer の import が無いことを保証.
    """
    import inspect
    src = inspect.getsource(t1)
    forbidden_imports = [
        "from services.chat_thread_store",
        "import services.chat_thread_store",
        "from domains.chat",
        "delete_message",
        "update_message",
        "DELETE FROM chat_messages",
        "UPDATE chat_messages",
    ]
    for token in forbidden_imports:
        assert token not in src, (
            f"tier1_tool_trim must not touch chat_messages: {token!r} "
            "(T-M28-02 AC-3)"
        )


def test_ac3_router_does_not_mutate_chat_messages():
    """router も chat_messages を書換しない."""
    from routers import tier1_tool_trim as r
    import inspect
    src = inspect.getsource(r)
    for token in (
        "delete_message", "update_message", "DELETE FROM chat_messages",
        "UPDATE chat_messages",
    ):
        assert token not in src, (
            f"router must not mutate chat_messages: {token!r}"
        )


def test_ac3_audit_emit_uses_memory_service():
    """AC-3 RLS: 直接 audit_logs SQL でなく memory_service.emit_event 経由."""
    import inspect
    src = inspect.getsource(t1)
    assert "from services.memory_service import emit_event" in src
    for token in ("INSERT INTO audit_logs", "audit_logs (", "audit_logs("):
        assert token not in src, (
            f"audit_logs への直接 SQL は禁止 (RLS bypass 危険): {token!r}"
        )


def test_endpoint_reasons_list(client):
    r = client.get("/api/tier1/trim/reasons")
    assert r.status_code == 200
    body = r.json()
    assert set(body["valid_reasons"]) == set(VALID_TRIM_REASONS)


# ══════════════════════════════════════════════════════════════════════
# AC-1 / AC-4: 自前 trimming logic 不在 (lint)
# ══════════════════════════════════════════════════════════════════════


def test_ac1_module_has_no_self_trim_logic():
    """tier1_tool_trim service source に自前 trim ロジックの禁止語が無い."""
    import inspect
    src = inspect.getsource(t1)
    forbidden = (
        "trim_tool_result", "_apply_size_cap", "_apply_age_cap",
        "_dedup_tool_results", "truncate_tool_result",
        "_compute_trimmed_payload", "_run_trim_policy",
        "_apply_window_eviction",
    )
    for token in forbidden:
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert token not in line, (
                f"tier1_tool_trim must not define/use {token!r} "
                "(T-M28-02 AC-4 / ADR-010)"
            )


def test_ac4_lint_script_has_no_self_tool_trim_check():
    text = (_repo_root() / "scripts" / "lint-mock.sh").read_text(encoding="utf-8")
    assert "check_no_self_tool_trim()" in text
    assert "--no-self-tool-trim" in text


def test_ac4_lint_check_pass_when_module_clean():
    r = subprocess.run(
        ["bash", "scripts/lint-mock.sh", "--no-self-tool-trim"],
        capture_output=True, text=True, timeout=30, cwd=str(_repo_root()),
    )
    assert r.returncode == 0, (
        f"lint --no-self-tool-trim failed: stdout={r.stdout[:500]} "
        f"stderr={r.stderr[:500]}"
    )
    assert "OK" in r.stdout


def test_ac4_module_docstring_documents_reuse_constraint():
    """docstring に SDK 委譲 + 再実装禁止が明記されている."""
    doc = t1.__doc__ or ""
    assert "claude-agent-sdk" in doc
    assert ("再実装" in doc or "self-implement" in doc.lower()
            or "audit wrapper" in doc)
    assert "ADR-010" in doc
