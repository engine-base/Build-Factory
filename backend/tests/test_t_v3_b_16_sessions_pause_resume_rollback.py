"""T-V3-B-16 / F-010: Sessions backend (pause / resume / rollback).

AC マッピング (9 functional + 11 regression):
  AC-F1  EVENT  : pause → checkpoint 保存 + status='paused' (within 5 s)
  AC-F2  UNWANT : resume not in paused/crashed → 409
  AC-F3  EVENT  : rollback (workspace_admin) → restore + audit emit
  AC-F4  EVENT  : pause 2xx + paused_at (+ checkpoint_id)
  AC-F5  UNWANT : pause 401 if no auth
  AC-F6  EVENT  : resume 2xx + resumed_at
  AC-F7  UNWANT : resume 401 if no auth
  AC-F8  EVENT  : rollback 2xx + rolled_back_at
  AC-F9  UNWANT : rollback 401 if no auth
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
)


AUTH_HEADER = {"Authorization": "Bearer test-token-T-V3-B-16"}


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client() -> TestClient:
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _capture_audit(monkeypatch):
    """audit emit を fake (T-V3-B-16 では rollback で audit を必須化)."""
    captured: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({
            "event_type": event_type,
            "user_id": user_id,
            "detail": detail or {},
        })
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)
    yield captured


@pytest.fixture
def fake_runner(monkeypatch):
    """agent_runner singleton を InMemorySessionStore に差し替え."""
    import routers.agent_runner as ar
    runner = ClaudeAgentRunner(store=InMemorySessionStore())
    monkeypatch.setattr(ar, "_runner", runner)
    yield {"runner": runner, "store": runner.store}
    monkeypatch.setattr(ar, "_runner", None)


def _seed_session(
    store: InMemorySessionStore,
    *,
    workspace_id: int = 100,
    status: str = "running",
    prompt: str = "test",
) -> int:
    rec = SessionRecord(
        prompt=prompt, status=status, workspace_id=workspace_id,
    )
    return asyncio.run(store.create_session(rec)).id  # type: ignore[return-value]


# ══════════════════════════════════════════════════════════════════════════
# AC-F1 / AC-F4 / AC-F5: POST /api/sessions/{id}/pause
# ══════════════════════════════════════════════════════════════════════════


def test_ac_f1_pause_running_session_saves_checkpoint_and_transitions(
    client, fake_runner,
):
    """AC-F1 EVENT: pause で checkpoint 保存 + status='paused' (5s 以内)."""
    store = fake_runner["store"]
    sid = _seed_session(store, workspace_id=100, status="running")

    t0 = time.monotonic()
    resp = client.post(f"/api/sessions/{sid}/pause", headers=AUTH_HEADER)
    elapsed = time.monotonic() - t0

    assert resp.status_code == 200, resp.text
    # 5 seconds 以内 (in-memory なので余裕で達成)
    assert elapsed < 5.0
    body = resp.json()
    assert "paused_at" in body
    assert "checkpoint_id" in body
    # status='paused' に遷移
    rec = asyncio.run(store.get_session(sid))
    assert rec is not None
    assert rec.status == "paused"
    # checkpoint が metadata に格納
    cps = rec.metadata.get("checkpoints", {})
    assert isinstance(cps, dict)
    assert body["checkpoint_id"] in cps
    assert rec.metadata.get("active_checkpoint_id") == body["checkpoint_id"]


def test_ac_f4_pause_contract_includes_paused_at(client, fake_runner):
    """AC-F4 EVENT: 2xx + paused_at (ISO-8601-ish string)."""
    store = fake_runner["store"]
    sid = _seed_session(store, workspace_id=100, status="running")

    resp = client.post(f"/api/sessions/{sid}/pause", headers=AUTH_HEADER)
    assert resp.status_code == 200
    body = resp.json()
    # ISO-8601 contains "T" between date and time
    assert "T" in body["paused_at"]


def test_ac_f5_pause_returns_401_without_auth(client, fake_runner):
    """AC-F5 UNWANTED: auth なし → 401."""
    resp = client.post("/api/sessions/1/pause")
    assert resp.status_code == 401
    body = resp.json()
    assert body["detail"]["code"] == "sessions.unauthorized"


def test_ac_f5_pause_returns_401_with_malformed_auth(client, fake_runner):
    """AC-F5: bearer scheme でないトークンは 401."""
    resp = client.post(
        "/api/sessions/1/pause",
        headers={"Authorization": "Token xyz"},
    )
    assert resp.status_code == 401


def test_pause_returns_404_for_unknown_session(client, fake_runner):
    """404: 不存在 session を pause しようとすると 404."""
    resp = client.post("/api/sessions/999999/pause", headers=AUTH_HEADER)
    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"]["code"] == "sessions.not_found"


def test_pause_returns_409_when_already_paused(client, fake_runner):
    """409: 既に paused の session を pause すると 409 (state conflict)."""
    store = fake_runner["store"]
    sid = _seed_session(store, workspace_id=100, status="paused")
    resp = client.post(f"/api/sessions/{sid}/pause", headers=AUTH_HEADER)
    assert resp.status_code == 409
    body = resp.json()
    assert body["detail"]["code"] == "sessions.not_pausable"


def test_pause_returns_409_when_already_terminated(client, fake_runner):
    """409: terminal (done / cancelled) は pause 不可."""
    store = fake_runner["store"]
    sid_done = _seed_session(store, workspace_id=100, status="done")
    resp = client.post(f"/api/sessions/{sid_done}/pause", headers=AUTH_HEADER)
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "sessions.already_terminated"


def test_pause_returns_422_for_invalid_session_id(client, fake_runner):
    """422: session_id <= 0 は 422."""
    resp = client.post("/api/sessions/0/pause", headers=AUTH_HEADER)
    assert resp.status_code == 422


# ══════════════════════════════════════════════════════════════════════════
# AC-F2 / AC-F6 / AC-F7: POST /api/sessions/{id}/resume
# ══════════════════════════════════════════════════════════════════════════


def test_ac_f6_resume_paused_session_returns_resumed_at(client, fake_runner):
    """AC-F6 EVENT: paused → running に遷移し resumed_at を返す."""
    store = fake_runner["store"]
    sid = _seed_session(store, workspace_id=100, status="paused")

    resp = client.post(f"/api/sessions/{sid}/resume", headers=AUTH_HEADER)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "resumed_at" in body
    assert "T" in body["resumed_at"]
    rec = asyncio.run(store.get_session(sid))
    assert rec is not None
    assert rec.status == "running"


def test_ac_f6_resume_crashed_session_also_works(client, fake_runner):
    """AC-F6 EVENT: crashed → resume 可能 (crashed も resumable)."""
    store = fake_runner["store"]
    sid = _seed_session(store, workspace_id=100, status="crashed")

    resp = client.post(f"/api/sessions/{sid}/resume", headers=AUTH_HEADER)
    assert resp.status_code == 200
    rec = asyncio.run(store.get_session(sid))
    assert rec is not None
    assert rec.status == "running"
    assert rec.crash_reason is None  # cleared


def test_ac_f6_resume_with_checkpoint_id_uses_checkpoint(client, fake_runner):
    """AC-F6: checkpoint_id 指定 → resume_choice=from_checkpoint."""
    store = fake_runner["store"]
    sid = _seed_session(store, workspace_id=100, status="running")

    # pause して checkpoint を作る
    pause_resp = client.post(
        f"/api/sessions/{sid}/pause", headers=AUTH_HEADER,
    )
    cp_id = pause_resp.json()["checkpoint_id"]

    resp = client.post(
        f"/api/sessions/{sid}/resume",
        headers=AUTH_HEADER,
        json={"checkpoint_id": cp_id},
    )
    assert resp.status_code == 200
    rec = asyncio.run(store.get_session(sid))
    assert rec is not None
    assert rec.resume_choice == "from_checkpoint"


def test_ac_f2_resume_returns_409_when_not_paused_or_crashed(
    client, fake_runner,
):
    """AC-F2 UNWANTED: paused/crashed 以外 (running) を resume すると 409."""
    store = fake_runner["store"]
    sid = _seed_session(store, workspace_id=100, status="running")
    resp = client.post(f"/api/sessions/{sid}/resume", headers=AUTH_HEADER)
    assert resp.status_code == 409
    body = resp.json()
    assert body["detail"]["code"] == "sessions.not_resumable"


def test_ac_f2_resume_returns_409_when_done(client, fake_runner):
    """AC-F2 UNWANTED: done を resume すると 409."""
    store = fake_runner["store"]
    sid = _seed_session(store, workspace_id=100, status="done")
    resp = client.post(f"/api/sessions/{sid}/resume", headers=AUTH_HEADER)
    assert resp.status_code == 409


def test_ac_f2_resume_returns_409_when_cancelled(client, fake_runner):
    """AC-F2 UNWANTED: cancelled を resume すると 409."""
    store = fake_runner["store"]
    sid = _seed_session(store, workspace_id=100, status="cancelled")
    resp = client.post(f"/api/sessions/{sid}/resume", headers=AUTH_HEADER)
    assert resp.status_code == 409


def test_ac_f7_resume_returns_401_without_auth(client, fake_runner):
    """AC-F7 UNWANTED: auth なし → 401."""
    resp = client.post("/api/sessions/1/resume")
    assert resp.status_code == 401


def test_resume_returns_404_for_unknown_session(client, fake_runner):
    """404: 不存在 session を resume → 404."""
    resp = client.post("/api/sessions/999999/resume", headers=AUTH_HEADER)
    assert resp.status_code == 404


def test_resume_returns_409_for_unknown_checkpoint(client, fake_runner):
    """409: 存在しない checkpoint_id 指定 → 409."""
    store = fake_runner["store"]
    sid = _seed_session(store, workspace_id=100, status="paused")
    resp = client.post(
        f"/api/sessions/{sid}/resume",
        headers=AUTH_HEADER,
        json={"checkpoint_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["detail"]["code"] == "sessions.checkpoint_not_found"


# ══════════════════════════════════════════════════════════════════════════
# AC-F3 / AC-F8 / AC-F9: POST /api/sessions/{id}/rollback
# ══════════════════════════════════════════════════════════════════════════


def test_ac_f3_rollback_restores_state_and_emits_audit(
    client, fake_runner, _capture_audit,
):
    """AC-F3 EVENT: rollback で session 状態が checkpoint 値に復元 + audit emit."""
    store = fake_runner["store"]
    sid = _seed_session(store, workspace_id=100, status="running")
    # pause で checkpoint 作成 (status_at_checkpoint='running')
    pause_resp = client.post(
        f"/api/sessions/{sid}/pause", headers=AUTH_HEADER,
    )
    cp_id = pause_resp.json()["checkpoint_id"]
    # 状態は paused
    rec_paused = asyncio.run(store.get_session(sid))
    assert rec_paused is not None
    assert rec_paused.status == "paused"

    # workspace_admin として rollback
    resp = client.post(
        f"/api/sessions/{sid}/rollback",
        headers=AUTH_HEADER,
        params={"actor_user_id": "admin-001"},
        json={"checkpoint_id": cp_id},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "rolled_back_at" in body

    # 状態は checkpoint 時の "running" に復元
    rec = asyncio.run(store.get_session(sid))
    assert rec is not None
    assert rec.status == "running"
    assert rec.resume_choice == "from_checkpoint"

    # AC-F3: audit log emit が呼ばれる
    rollback_audits = [
        e for e in _capture_audit
        if e["event_type"] == "sessions.rolled_back"
    ]
    assert len(rollback_audits) == 1
    audit = rollback_audits[0]
    assert audit["user_id"] == "admin-001"
    assert audit["detail"]["session_id"] == sid
    assert audit["detail"]["checkpoint_id"] == cp_id
    assert audit["detail"]["restored_status"] == "running"


def test_ac_f8_rollback_returns_rolled_back_at(client, fake_runner):
    """AC-F8 EVENT: 2xx + rolled_back_at (ISO-8601)."""
    store = fake_runner["store"]
    sid = _seed_session(store, workspace_id=100, status="running")
    pause_resp = client.post(
        f"/api/sessions/{sid}/pause", headers=AUTH_HEADER,
    )
    cp_id = pause_resp.json()["checkpoint_id"]

    resp = client.post(
        f"/api/sessions/{sid}/rollback",
        headers=AUTH_HEADER,
        json={"checkpoint_id": cp_id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "T" in body["rolled_back_at"]


def test_ac_f9_rollback_returns_401_without_auth(client, fake_runner):
    """AC-F9 UNWANTED: auth なし → 401."""
    resp = client.post(
        "/api/sessions/1/rollback",
        json={"checkpoint_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 401


def test_rollback_returns_404_for_unknown_session(client, fake_runner):
    """404: 不存在 session の rollback → 404."""
    resp = client.post(
        "/api/sessions/999999/rollback",
        headers=AUTH_HEADER,
        json={"checkpoint_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 404


def test_rollback_returns_409_for_unknown_checkpoint(client, fake_runner):
    """409: 指定 checkpoint が session 配下に無い → 409."""
    store = fake_runner["store"]
    sid = _seed_session(store, workspace_id=100, status="paused")
    resp = client.post(
        f"/api/sessions/{sid}/rollback",
        headers=AUTH_HEADER,
        json={"checkpoint_id": "11111111-1111-1111-1111-111111111111"},
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["detail"]["code"] == "sessions.checkpoint_not_found"


def test_rollback_requires_checkpoint_id_in_body(client, fake_runner):
    """422: body に checkpoint_id 無し → 422."""
    store = fake_runner["store"]
    sid = _seed_session(store, workspace_id=100, status="paused")
    resp = client.post(
        f"/api/sessions/{sid}/rollback",
        headers=AUTH_HEADER,
        json={},
    )
    # FastAPI が pydantic validation で 422 を返す
    assert resp.status_code == 422


def test_rollback_returns_422_for_invalid_session_id(client, fake_runner):
    """422: session_id <= 0 → 422."""
    resp = client.post(
        "/api/sessions/0/rollback",
        headers=AUTH_HEADER,
        json={"checkpoint_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 422


# ══════════════════════════════════════════════════════════════════════════
# Service unit tests (sessions_v3) — direct invariants
# ══════════════════════════════════════════════════════════════════════════


def test_service_pause_raises_for_invalid_id():
    """service: pause_session(0) → ValueError."""
    from services import sessions_v3
    store = InMemorySessionStore()
    with pytest.raises(ValueError):
        asyncio.run(sessions_v3.pause_session(store, 0))


def test_service_pause_raises_not_found():
    """service: pause unknown → SessionNotFoundError."""
    from services import sessions_v3
    store = InMemorySessionStore()
    with pytest.raises(sessions_v3.SessionNotFoundError):
        asyncio.run(sessions_v3.pause_session(store, 12345))


def test_service_resume_raises_state_conflict_for_running():
    """service: running を resume → SessionStateConflictError (AC-F2)."""
    from services import sessions_v3
    store = InMemorySessionStore()
    rec = SessionRecord(prompt="t", workspace_id=10, status="running")
    sid = asyncio.run(store.create_session(rec)).id
    with pytest.raises(sessions_v3.SessionStateConflictError):
        asyncio.run(sessions_v3.resume_session(store, sid))


def test_service_pause_then_rollback_restores_status():
    """service: pause で checkpoint 作成 → rollback で status 復元."""
    from services import sessions_v3
    store = InMemorySessionStore()
    rec = SessionRecord(prompt="t", workspace_id=10, status="running")
    sid = asyncio.run(store.create_session(rec)).id
    pause_result = asyncio.run(
        sessions_v3.pause_session(store, sid, actor_user_id="u1"),
    )
    cp_id = pause_result["checkpoint_id"]
    # paused に
    rec_after_pause = asyncio.run(store.get_session(sid))
    assert rec_after_pause is not None
    assert rec_after_pause.status == "paused"
    # rollback で running に戻る
    result = asyncio.run(
        sessions_v3.rollback_session(
            store, sid, checkpoint_id=cp_id, actor_user_id="admin",
        ),
    )
    assert result["restored_status"] == "running"
    rec_after_rb = asyncio.run(store.get_session(sid))
    assert rec_after_rb is not None
    assert rec_after_rb.status == "running"


def test_service_rollback_unknown_checkpoint_raises():
    """service: 未存在 checkpoint → CheckpointNotFoundError."""
    from services import sessions_v3
    store = InMemorySessionStore()
    rec = SessionRecord(prompt="t", workspace_id=10, status="paused")
    sid = asyncio.run(store.create_session(rec)).id
    with pytest.raises(sessions_v3.CheckpointNotFoundError):
        asyncio.run(
            sessions_v3.rollback_session(
                store, sid, checkpoint_id="no-such-cp",
            ),
        )


def test_service_pause_returns_unique_checkpoint_ids():
    """service: 連続 pause すると checkpoint_id は重複しない."""
    from services import sessions_v3
    store = InMemorySessionStore()
    rec = SessionRecord(prompt="t", workspace_id=10, status="running")
    sid = asyncio.run(store.create_session(rec)).id
    cp1 = asyncio.run(sessions_v3.pause_session(store, sid))["checkpoint_id"]
    # resume して再度 running に
    asyncio.run(sessions_v3.resume_session(store, sid))
    cp2 = asyncio.run(sessions_v3.pause_session(store, sid))["checkpoint_id"]
    assert cp1 != cp2
