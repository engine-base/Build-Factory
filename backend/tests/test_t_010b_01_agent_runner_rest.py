"""T-010b-01: claude-agent-sdk REST integration (REFACTOR) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-010b claude-agent-sdk endpoint 公開 (sessions / get / resume)
  AC-2 EVENT-DRIVEN  : 2 秒以内に success or {detail:{code,message}} (背景実行)
  AC-3 STATE-DRIVEN  : 既存 ClaudeAgentRunner / SessionRecord contract 不変
  AC-4 UNWANTED      : invalid input / unknown session / 不正 resume choice は 4xx +
                       {detail:{code,message}} かつ persistent state mutate しない
"""
from __future__ import annotations

import asyncio
import os
import time

import pytest
from fastapi.testclient import TestClient

from integrations.claude_agent_runner import (
    ClaudeAgentRunner,
    InMemorySessionStore,
    SessionRecord,
    NoopCostHook,
    NoopSummaryHook,
    NoopAuditHook,
)


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
            "event_type": event_type, "user_id": user_id, "detail": detail or {},
        })
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)
    yield captured


@pytest.fixture(autouse=True)
def _fake_runner(monkeypatch):
    """InMemorySessionStore を持つ runner を注入 (SDK 呼び出しは fake)."""
    import routers.agent_runner as ar

    store = InMemorySessionStore()
    runner = ClaudeAgentRunner(
        store=store,
        cost_hook=NoopCostHook(),
        summary_hook=NoopSummaryHook(),
        audit_hook=NoopAuditHook(),
    )

    completed: list[dict] = []

    async def fake_run_task(prompt, *, sdk_session_id=None, workspace_id=None, project_id=None,
                            bf_task_id=None, agent_persona=None, skill_name=None,
                            model="claude-sonnet-4-6", agents=None, cwd=None):
        rec = SessionRecord(
            sdk_session_id=sdk_session_id or "sdk-fake-1",
            workspace_id=workspace_id,
            project_id=project_id,
            bf_task_id=bf_task_id,
            agent_persona=agent_persona,
            skill_name=skill_name,
            prompt=prompt,
            status="done",
            started_at=time.time(),
            completed_at=time.time(),
        )
        rec = await store.create_session(rec)
        completed.append({"rec_id": rec.id, "prompt": prompt})
        return rec

    monkeypatch.setattr(runner, "run_task", fake_run_task)
    monkeypatch.setattr(ar, "_runner", runner)
    yield {"store": store, "runner": runner, "completed": completed}
    monkeypatch.setattr(ar, "_runner", None)


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint 公開
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_create_session_endpoint_exists(client):
    """AC-1: POST /api/agent/sessions が定義."""
    r = client.post("/api/agent/sessions", json={"prompt": "hello"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "queued"
    assert "session" in body
    assert body["session"]["status"] == "queued"


def test_ac1_get_session_endpoint_exists(client, _fake_runner):
    """AC-1: GET /api/agent/sessions/{id} が定義."""
    # 既存 session を store に直接追加
    store = _fake_runner["store"]
    asyncio.run(store.create_session(SessionRecord(prompt="x", status="done")))
    r = client.get("/api/agent/sessions/1")
    assert r.status_code == 200
    assert r.json()["session"]["id"] == 1


def test_ac1_resume_session_endpoint_exists(client, _fake_runner):
    """AC-1: POST /api/agent/sessions/{id}/resume が定義."""
    store = _fake_runner["store"]
    asyncio.run(store.create_session(SessionRecord(prompt="x", status="crashed")))
    r = client.post("/api/agent/sessions/1/resume", json={"choice": "cancel"})
    assert r.status_code == 200
    assert r.json()["choice"] == "cancel"
    assert r.json()["session"]["status"] == "cancelled"


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured response
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_create_session_returns_within_2s(client):
    """AC-2: 背景実行モードで 2 秒以内に id 返却."""
    t0 = time.perf_counter()
    r = client.post(
        "/api/agent/sessions",
        json={"prompt": "long task", "run_in_background": True, "user_id": "alice"},
    )
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0
    body = r.json()
    assert body["session"]["id"] is not None


def test_ac2_get_session_returns_within_2s(client, _fake_runner):
    """AC-2: get session も 2 秒以内."""
    store = _fake_runner["store"]
    asyncio.run(store.create_session(SessionRecord(prompt="x", status="done")))
    t0 = time.perf_counter()
    r = client.get("/api/agent/sessions/1")
    assert r.status_code == 200
    assert time.perf_counter() - t0 < 2.0


def test_ac2_error_uses_detail_code_message(client):
    """AC-2: error response は {detail:{code,message}}."""
    r = client.post("/api/agent/sessions", json={"prompt": ""})
    assert r.status_code == 400
    body = r.json()
    assert body["detail"]["code"] == "agent.invalid_prompt"
    assert "message" in body["detail"]


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: 既存 ClaudeAgentRunner / SessionRecord contract 不変
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_session_response_shape_matches_record():
    """AC-3: _serialize の field が SessionRecord の主要 field を網羅."""
    from routers.agent_runner import _serialize

    rec = SessionRecord(
        id=1, sdk_session_id="sdk-1", prompt="hi", status="running",
        workspace_id=10, project_id=20, bf_task_id=30, agent_persona="mary",
        skill_name="brief", started_at=100.0,
    )
    out = _serialize(rec)
    expected_keys = {"id", "sdk_session_id", "workspace_id", "project_id", "bf_task_id",
                     "agent_persona", "skill_name", "prompt", "status", "resume_choice",
                     "crash_reason", "started_at", "completed_at"}
    assert expected_keys == set(out.keys())
    assert out["agent_persona"] == "mary"


def test_ac3_synchronous_mode_delegates_to_run_task(client, _fake_runner):
    """AC-3: run_in_background=False で既存 runner.run_task を呼ぶ."""
    r = client.post(
        "/api/agent/sessions",
        json={"prompt": "sync hi", "run_in_background": False, "user_id": "alice"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "done"  # fake_run_task は 'done' を返す
    # contract: SessionRecord field が response.session に含まれる
    assert body["session"]["sdk_session_id"] == "sdk-fake-1"
    assert len(_fake_runner["completed"]) >= 1


def test_ac3_resume_choices_match_existing_constant():
    """AC-3: 4 つの resume choice は既存 VALID_RESUME_CHOICES と一致."""
    from integrations.claude_agent_runner import VALID_RESUME_CHOICES
    assert set(VALID_RESUME_CHOICES) == {"from_checkpoint", "rerun_full", "manual_fix", "cancel"}


def test_ac3_audit_emitted_on_queued(client, _capture_audit):
    """AC-3 + 監査: queued 時に agent.session.queued emit."""
    client.post("/api/agent/sessions", json={"prompt": "hi", "user_id": "carol"})
    events = [e for e in _capture_audit if e["event_type"] == "agent.session.queued"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "carol"


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_empty_prompt_rejected(client, _capture_audit, _fake_runner):
    """AC-4: empty prompt は 400 + invalid_prompt + audit emit なし."""
    r = client.post("/api/agent/sessions", json={"prompt": "   "})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "agent.invalid_prompt"
    # AC-4: store にも何も入っていない
    assert len(_fake_runner["store"]._sessions) == 0
    events = [e for e in _capture_audit if e["event_type"] == "agent.session.queued"]
    assert len(events) == 0


def test_ac4_empty_user_id_rejected(client):
    """AC-4: 空 user_id は 401 + unauthorized."""
    r = client.post("/api/agent/sessions", json={"prompt": "hi", "user_id": "   "})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "agent.unauthorized"


def test_ac4_empty_agent_persona_rejected(client):
    """AC-4: 空 agent_persona は 400."""
    r = client.post("/api/agent/sessions", json={"prompt": "hi", "agent_persona": "   "})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "agent.invalid_agent_persona"


def test_ac4_empty_model_rejected(client):
    """AC-4: 空 model は 400."""
    r = client.post("/api/agent/sessions", json={"prompt": "hi", "model": "   "})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "agent.invalid_model"


def test_ac4_get_session_invalid_id_rejected(client):
    """AC-4: get session_id<=0 は 400."""
    r = client.get("/api/agent/sessions/0")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "agent.invalid_session_id"


def test_ac4_get_session_not_found(client):
    """AC-4: 存在しない session は 404."""
    r = client.get("/api/agent/sessions/99999")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "agent.session_not_found"


def test_ac4_resume_invalid_choice_rejected(client, _fake_runner):
    """AC-4: 不正 resume choice は 400."""
    store = _fake_runner["store"]
    asyncio.run(store.create_session(SessionRecord(prompt="x", status="crashed")))
    r = client.post("/api/agent/sessions/1/resume", json={"choice": "bogus"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "agent.invalid_resume_choice"


def test_ac4_resume_session_not_found(client):
    """AC-4: 存在しない session の resume は 404."""
    r = client.post("/api/agent/sessions/99999/resume", json={"choice": "cancel"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "agent.session_not_found"


def test_ac4_resume_invalid_session_id(client):
    """AC-4: session_id<=0 の resume は 400."""
    r = client.post("/api/agent/sessions/0/resume", json={"choice": "cancel"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "agent.invalid_session_id"


def test_ac4_no_state_mutation_on_rejected(client, _capture_audit, _fake_runner):
    """AC-4 UNWANTED: rejected request は store に書き込まない."""
    # 各種 reject 経由で store 不変を確認
    before = len(_fake_runner["store"]._sessions)
    client.post("/api/agent/sessions", json={"prompt": ""})
    client.post("/api/agent/sessions", json={"prompt": "hi", "user_id": "   "})
    after = len(_fake_runner["store"]._sessions)
    assert before == after == 0


# ──────────────────────────────────────────────────────────────────────────
# 補助: error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client, _fake_runner):
    """全 error response が {detail:{code:str, message:str}} の shape."""
    cases = [
        ("POST", "/api/agent/sessions", {"prompt": ""}),
        ("POST", "/api/agent/sessions", {"prompt": "x", "user_id": "   "}),
        ("POST", "/api/agent/sessions", {"prompt": "x", "agent_persona": "   "}),
        ("POST", "/api/agent/sessions", {"prompt": "x", "model": "   "}),
        ("GET", "/api/agent/sessions/0", None),
        ("GET", "/api/agent/sessions/99999", None),
        ("POST", "/api/agent/sessions/99999/resume", {"choice": "cancel"}),
        ("POST", "/api/agent/sessions/1/resume", {"choice": "bogus"}),
    ]
    for method, path, payload in cases:
        if method == "GET":
            r = client.get(path)
        else:
            r = client.post(path, json=payload)
        assert 400 <= r.status_code < 500, f"{method} {path}: {r.status_code}"
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
