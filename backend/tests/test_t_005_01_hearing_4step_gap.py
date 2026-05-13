"""T-005-01: hearing AI (Mary) 4STEP — gap closure (G1-G5).

主要実装 (services/hearing_service.py + routers/hearing.py + 16 既存 tests) は
完備. 本 PR で **audit emit + timing + 4STEP 全網羅 + 4xx form 統一**
の 5 件 gap を埋める.

## Gaps

  G1 (AC-STATE audit): hearing.step_started / .replied / .step_completed を
     audit_logs に emit (v2.1 適合チェック #7 audit_log).
  G2 (AC-2 timing): 各 endpoint が 2 秒以内に response を返す実測 test.
  G3 (AC-1 4STEP 全網羅): STEPS list の 4 step すべてが get_step_meta() で
     引け, _ensure_valid_step が 1-4 を受理する.
  G4 (AC-4 4xx form 統一): 全 endpoint の 4xx response が {detail:{code,message}}.
  G5 (AC-3 backward compat): 5 endpoint の prefix が無改変 (router path 不変).
"""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import pytest

from services import hearing_service as hs
from services.hearing_service import (
    EVENT_HEARING_REPLIED,
    EVENT_HEARING_STEP_COMPLETED,
    EVENT_HEARING_STEP_STARTED,
    STEPS,
    apply_center_patch,
    empty_center_state,
    get_step_meta,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app, raise_server_exceptions=False)


# ══════════════════════════════════════════════════════════════════════
# G1 (AC-STATE audit): audit event emit
# ══════════════════════════════════════════════════════════════════════


def test_g1_audit_event_constants_exported():
    assert EVENT_HEARING_STEP_STARTED == "hearing.step_started"
    assert EVENT_HEARING_REPLIED == "hearing.replied"
    assert EVENT_HEARING_STEP_COMPLETED == "hearing.step_completed"


def test_g1_emit_hearing_audit_calls_memory_service(monkeypatch):
    captured: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({"event_type": event_type, "detail": detail or {}})
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)

    asyncio.run(hs._emit_hearing_audit(
        EVENT_HEARING_STEP_STARTED,
        workspace_id=42, step=1,
        detail={"artifact_id": "art-x"},
    ))
    assert len(captured) == 1
    assert captured[0]["event_type"] == "hearing.step_started"
    d = captured[0]["detail"]
    assert d["workspace_id"] == 42
    assert d["step"] == 1
    assert d["artifact_id"] == "art-x"


def test_g1_emit_hearing_audit_swallows_db_failure(monkeypatch):
    """DB 不在環境 (memory_service emit 失敗) でも raise しない (best-effort)."""

    async def failing_emit(*a, **k):
        raise RuntimeError("DB not available (test)")

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", failing_emit)

    # raise しないことを確認
    asyncio.run(hs._emit_hearing_audit(
        EVENT_HEARING_REPLIED, workspace_id=1, step=2,
    ))


# ══════════════════════════════════════════════════════════════════════
# G3 (AC-1): 4STEP 全網羅
# ══════════════════════════════════════════════════════════════════════


def test_g3_steps_count_exactly_4():
    """spec 文 '4STEP' 通り step 1-4 のみ."""
    assert len(STEPS) == 4
    step_numbers = {s["step"] for s in STEPS}
    assert step_numbers == {1, 2, 3, 4}


@pytest.mark.parametrize("step", [1, 2, 3, 4])
def test_g3_get_step_meta_returns_for_each_step(step):
    meta = get_step_meta(step)
    assert meta is not None
    assert meta["step"] == step
    assert isinstance(meta["title"], str) and meta["title"]
    assert isinstance(meta["core_sections"], list)
    assert len(meta["core_sections"]) >= 1


def test_g3_get_step_meta_returns_none_for_invalid_step():
    for bad in (0, 5, -1, 100):
        assert get_step_meta(bad) is None


def test_g3_empty_center_state_uses_step_sections():
    """各 step の empty_center_state が STEPS の core_sections と整合."""
    for step in (1, 2, 3, 4):
        center = empty_center_state(step)
        assert "sections" in center
        meta = get_step_meta(step)
        section_keys = {s["key"] for s in center["sections"]}
        meta_keys = {s["key"] for s in meta["core_sections"]}
        assert section_keys == meta_keys


# ══════════════════════════════════════════════════════════════════════
# G2 (AC-2): timing 2 秒以内
# ══════════════════════════════════════════════════════════════════════


def test_g2_invalid_step_endpoint_within_2sec(client):
    """validation 経路 (LLM call なし) は ms オーダーで返る."""
    t0 = time.time()
    r = client.post(
        "/api/workspaces/1/hearing/start-step", json={"step": 99},
    )
    elapsed_ms = (time.time() - t0) * 1000
    assert r.status_code == 400
    assert elapsed_ms < 2000, f"validation path {elapsed_ms:.1f}ms exceeded 2s"


def test_g2_empty_message_endpoint_within_2sec(client):
    t0 = time.time()
    r = client.post(
        "/api/workspaces/1/hearing/reply",
        json={"step": 1, "message": "   "},
    )
    elapsed_ms = (time.time() - t0) * 1000
    assert r.status_code == 400
    assert elapsed_ms < 2000


# ══════════════════════════════════════════════════════════════════════
# G4 (AC-4): 全 4xx response が {detail:{code,message}}
# ══════════════════════════════════════════════════════════════════════


def test_g4_invalid_step_4xx_form(client):
    r = client.post(
        "/api/workspaces/1/hearing/start-step", json={"step": 99},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == "invalid_step"
    assert "message" in detail


def test_g4_empty_message_4xx_form(client):
    r = client.post(
        "/api/workspaces/1/hearing/reply",
        json={"step": 1, "message": ""},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == "empty_message"


def test_g4_complete_invalid_step_4xx_form(client):
    r = client.post(
        "/api/workspaces/1/hearing/complete-step", json={"step": 0},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "invalid_step"


def test_g4_all_4xx_responses_have_uniform_shape(client):
    """全 endpoint の 4xx を一括検証."""
    cases = [
        ("POST", "/api/workspaces/1/hearing/start-step",
         {"step": 99}, 400, "invalid_step"),
        ("POST", "/api/workspaces/1/hearing/reply",
         {"step": 0, "message": "hi"}, 400, "invalid_step"),
        ("POST", "/api/workspaces/1/hearing/reply",
         {"step": 1, "message": ""}, 400, "empty_message"),
        ("POST", "/api/workspaces/1/hearing/complete-step",
         {"step": 5}, 400, "invalid_step"),
    ]
    for _, path, body, expected_status, expected_code in cases:
        r = client.post(path, json=body)
        assert r.status_code == expected_status, f"{path}: {r.status_code}"
        detail = r.json()["detail"]
        assert isinstance(detail, dict), f"{path}: detail must be dict"
        assert detail.get("code") == expected_code, f"{path}: bad code"
        assert isinstance(detail.get("message", ""), str) and detail["message"]


# ══════════════════════════════════════════════════════════════════════
# G5 (AC-3): 5 endpoint routing backward compat
# ══════════════════════════════════════════════════════════════════════


def test_g5_5_endpoints_routing_preserved(client):
    """既存 5 endpoint の path が router に登録されている."""
    paths = [getattr(r, "path", "") for r in client.app.routes]
    # 4 endpoint at minimum (start-step / reply / complete-step / state / center)
    expected_substrings = [
        "/hearing/start-step",
        "/hearing/reply",
        "/hearing/complete-step",
        "/hearing/state",
        "/hearing/center",
    ]
    for sub in expected_substrings:
        assert any(sub in p for p in paths), f"path missing: {sub}"


# ══════════════════════════════════════════════════════════════════════
# Pure function (apply_center_patch)
# ══════════════════════════════════════════════════════════════════════


def test_apply_center_patch_basic_add():
    """patch op 'add' が item を section に追加する.

    apply_center_patch の正規 patch 形式: {section_key, operation, items}.
    """
    center = empty_center_state(1)
    patch = [
        {
            "section_key": "overview",
            "operation": "add",
            "items": ["Build-Factory ver 1.0"],
        },
    ]
    new_center = apply_center_patch(center, patch)
    overview = next(s for s in new_center["sections"] if s["key"] == "overview")
    assert any("Build-Factory" in str(item) for item in overview["items"])


# ══════════════════════════════════════════════════════════════════════
# Cross-reference: tickets + module docstring
# ══════════════════════════════════════════════════════════════════════


def test_ticket_t_005_01_has_4_ac():
    import json
    tj = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.loads(tj.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-005-01"), None)
    assert t is not None
    assert len(t["acceptance_criteria"]) == 4


def test_module_docstring_documents_event_constants():
    doc = hs.__doc__ or ""
    for ev in ("hearing.step_started", "hearing.replied", "hearing.step_completed"):
        assert ev in doc
    assert "T-005-01" in doc
