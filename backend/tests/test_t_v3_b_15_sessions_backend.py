"""T-V3-B-15 / F-010: Sessions backend (list / detail / kill / kill-all) 4 endpoint.

AC マッピング (13 functional + 11 regression):
  AC-F4  EVENT  : GET /api/workspaces/{id}/sessions 2xx + sessions shape
  AC-F5  UNWANT : 401 if missing auth
  AC-F6  UNWANT : 422 if invalid status filter
  AC-F7  EVENT  : GET /api/sessions/{id} 2xx + session + logs_tail_url
  AC-F8  UNWANT : 401 if missing auth
  AC-F9  UNWANT : 422 if invalid session_id (path)
  AC-F10 EVENT  : POST /api/sessions/{id}/kill 2xx + killed_at
  AC-F11 UNWANT : 401 if missing auth
  AC-F12 EVENT  : POST /api/workspaces/{id}/sessions/kill-all 2xx + killed_count
  AC-F13 UNWANT : 401 if missing auth

Pause/resume/rollback (AC-F1〜F3) は T-V3-B-16 で実装する.
"""
from __future__ import annotations

import asyncio
import os

import pytest
from fastapi.testclient import TestClient

from integrations.claude_agent_runner import (
    ClaudeAgentRunner,
    InMemorySessionStore,
    SessionRecord,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


AUTH_HEADER = {"Authorization": "Bearer test-token-T-V3-B-15"}


@pytest.fixture(scope="module")
def client() -> TestClient:
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    # NOTE: lifespan は呼ばないため `with` を使わない (env / DB 接続が不要).
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _capture_audit(monkeypatch):
    """audit emit を fake (T-V3-B-15 では audit 副作用に依存しない)."""
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
# AC-F4 / AC-F5 / AC-F6: GET /api/workspaces/{id}/sessions
# ══════════════════════════════════════════════════════════════════════════


def test_ac_f4_list_returns_sessions_for_workspace(client, fake_runner):
    """AC-F4: 2xx + {sessions: [...]} を返す."""
    store = fake_runner["store"]
    s1 = _seed_session(store, workspace_id=100, status="running")
    s2 = _seed_session(store, workspace_id=100, status="paused")
    _seed_session(store, workspace_id=999, status="running")  # noise

    resp = client.get("/api/workspaces/100/sessions", headers=AUTH_HEADER)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "sessions" in body
    returned_ids = sorted(s["id"] for s in body["sessions"])
    assert returned_ids == sorted([s1, s2])
    # AC-F4 contract: 各 session に id / status / workspace_id を含む
    for s in body["sessions"]:
        assert s["workspace_id"] == 100
        assert "status" in s
        assert "id" in s


def test_ac_f4_list_filters_by_status(client, fake_runner):
    """AC-F4: ?status=running filter."""
    store = fake_runner["store"]
    s1 = _seed_session(store, workspace_id=200, status="running")
    _seed_session(store, workspace_id=200, status="paused")
    _seed_session(store, workspace_id=200, status="cancelled")

    resp = client.get(
        "/api/workspaces/200/sessions",
        params={"status": "running"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["sessions"]) == 1
    assert body["sessions"][0]["id"] == s1


def test_ac_f4_list_status_completed_maps_to_done(client, fake_runner):
    """AC-F4: status=completed (UI 値) は内部の "done" にマップされる."""
    store = fake_runner["store"]
    _seed_session(store, workspace_id=300, status="running")
    s_done = _seed_session(store, workspace_id=300, status="done")

    resp = client.get(
        "/api/workspaces/300/sessions",
        params={"status": "completed"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["sessions"]) == 1
    assert body["sessions"][0]["id"] == s_done


def test_ac_f5_list_returns_401_without_auth(client, fake_runner):
    """AC-F5 UNWANTED: 認証なし → 401."""
    resp = client.get("/api/workspaces/100/sessions")
    assert resp.status_code == 401
    body = resp.json()
    assert body["detail"]["code"] == "sessions.unauthorized"


def test_ac_f5_list_returns_401_with_invalid_auth(client, fake_runner):
    """AC-F5: malformed bearer は 401."""
    resp = client.get(
        "/api/workspaces/100/sessions",
        headers={"Authorization": "NotBearer abc"},
    )
    assert resp.status_code == 401


def test_ac_f6_list_returns_422_for_invalid_status_filter(client, fake_runner):
    """AC-F6 UNWANTED: status enum 外 → 422."""
    resp = client.get(
        "/api/workspaces/100/sessions",
        params={"status": "no-such-status"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"]["code"] == "sessions.invalid_status_filter"


def test_ac_f6_list_returns_422_for_workspace_id_zero(client, fake_runner):
    """AC-F6 UNWANTED: workspace_id <= 0 → 422."""
    resp = client.get("/api/workspaces/0/sessions", headers=AUTH_HEADER)
    assert resp.status_code == 422


# ══════════════════════════════════════════════════════════════════════════
# AC-F7 / AC-F8 / AC-F9: GET /api/sessions/{id}
# ══════════════════════════════════════════════════════════════════════════


def test_ac_f7_detail_returns_session_and_logs_url(client, fake_runner):
    """AC-F7: 2xx + {session, logs_tail_url}."""
    store = fake_runner["store"]
    sid = _seed_session(store, workspace_id=100, status="running")

    resp = client.get(f"/api/sessions/{sid}", headers=AUTH_HEADER)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["session"]["id"] == sid
    assert body["session"]["status"] == "running"
    assert body["logs_tail_url"] == f"/ws/sessions/{sid}/log"


def test_ac_f7_detail_returns_404_for_unknown(client, fake_runner):
    """AC-F7: 不存在 → 404 (validation pass)."""
    resp = client.get("/api/sessions/999999", headers=AUTH_HEADER)
    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"]["code"] == "sessions.not_found"


def test_ac_f8_detail_returns_401_without_auth(client, fake_runner):
    """AC-F8 UNWANTED: auth なし → 401."""
    resp = client.get("/api/sessions/1")
    assert resp.status_code == 401


def test_ac_f9_detail_returns_422_for_invalid_id(client, fake_runner):
    """AC-F9 UNWANTED: session_id <= 0 → 422."""
    resp = client.get("/api/sessions/0", headers=AUTH_HEADER)
    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"]["code"] == "sessions.invalid_session_id"


# ══════════════════════════════════════════════════════════════════════════
# AC-F10 / AC-F11: POST /api/sessions/{id}/kill
# ══════════════════════════════════════════════════════════════════════════


def test_ac_f10_kill_session_returns_killed_at(client, fake_runner):
    """AC-F10: 2xx + killed_at + status=cancelled に遷移."""
    store = fake_runner["store"]
    sid = _seed_session(store, workspace_id=100, status="running")

    resp = client.post(f"/api/sessions/{sid}/kill", headers=AUTH_HEADER)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "killed_at" in body
    # status は cancelled
    rec = asyncio.run(store.get_session(sid))
    assert rec is not None
    assert rec.status == "cancelled"


def test_ac_f10_kill_session_with_actor_records_reason(client, fake_runner):
    """AC-F10: actor_user_id を crash_reason に記録."""
    store = fake_runner["store"]
    sid = _seed_session(store, workspace_id=100, status="running")

    resp = client.post(
        f"/api/sessions/{sid}/kill",
        params={"actor_user_id": "masato"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    rec = asyncio.run(store.get_session(sid))
    assert rec is not None
    assert "masato" in (rec.crash_reason or "")


def test_ac_f10_kill_409_when_already_terminated(client, fake_runner):
    """409 UNWANTED: 既に done / cancelled なら kill 不可."""
    store = fake_runner["store"]
    sid = _seed_session(store, workspace_id=100, status="done")
    resp = client.post(f"/api/sessions/{sid}/kill", headers=AUTH_HEADER)
    assert resp.status_code == 409
    body = resp.json()
    assert body["detail"]["code"] == "sessions.already_terminated"


def test_ac_f10_kill_404_when_session_unknown(client, fake_runner):
    """kill on unknown session → 404."""
    resp = client.post("/api/sessions/999999/kill", headers=AUTH_HEADER)
    assert resp.status_code == 404


def test_ac_f11_kill_returns_401_without_auth(client, fake_runner):
    """AC-F11 UNWANTED: auth なし → 401."""
    resp = client.post("/api/sessions/1/kill")
    assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════
# AC-F12 / AC-F13: POST /api/workspaces/{id}/sessions/kill-all
# ══════════════════════════════════════════════════════════════════════════


def test_ac_f12_kill_all_returns_killed_count(client, fake_runner):
    """AC-F12: workspace 内 active を全 kill, killed_count を返す."""
    store = fake_runner["store"]
    s1 = _seed_session(store, workspace_id=500, status="running")
    s2 = _seed_session(store, workspace_id=500, status="paused")
    s3 = _seed_session(store, workspace_id=500, status="crashed")
    # terminal は skip
    s_done = _seed_session(store, workspace_id=500, status="done")
    s_cancelled = _seed_session(store, workspace_id=500, status="cancelled")
    # other workspace は skip
    s_other = _seed_session(store, workspace_id=600, status="running")

    resp = client.post(
        "/api/workspaces/500/sessions/kill-all", headers=AUTH_HEADER,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["killed_count"] == 3

    # 元 active 3 件は cancelled に
    for sid in (s1, s2, s3):
        rec = asyncio.run(store.get_session(sid))
        assert rec is not None
        assert rec.status == "cancelled"
    # 元 terminal はそのまま
    assert asyncio.run(store.get_session(s_done)).status == "done"  # type: ignore[union-attr]
    assert asyncio.run(store.get_session(s_cancelled)).status == "cancelled"  # type: ignore[union-attr]
    # 他 workspace は無影響
    assert asyncio.run(store.get_session(s_other)).status == "running"  # type: ignore[union-attr]


def test_ac_f12_kill_all_zero_when_no_active(client, fake_runner):
    """AC-F12: active 0 件なら killed_count=0."""
    store = fake_runner["store"]
    _seed_session(store, workspace_id=700, status="done")

    resp = client.post(
        "/api/workspaces/700/sessions/kill-all", headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["killed_count"] == 0


def test_ac_f13_kill_all_returns_401_without_auth(client, fake_runner):
    """AC-F13 UNWANTED: auth なし → 401."""
    resp = client.post("/api/workspaces/100/sessions/kill-all")
    assert resp.status_code == 401


def test_ac_f13_kill_all_returns_422_for_invalid_workspace(client, fake_runner):
    """AC-F13: workspace_id <= 0 → 422."""
    resp = client.post(
        "/api/workspaces/0/sessions/kill-all", headers=AUTH_HEADER,
    )
    assert resp.status_code == 422


# ══════════════════════════════════════════════════════════════════════════
# Service unit tests (sessions_v3) — direct invariants
# ══════════════════════════════════════════════════════════════════════════


def test_service_list_orders_by_started_desc():
    """service: list は (started_at, id) desc で並ぶ."""
    from services import sessions_v3

    store = InMemorySessionStore()
    sids = []
    for i in range(3):
        rec = SessionRecord(prompt=f"p{i}", workspace_id=100, status="running")
        sids.append(asyncio.run(store.create_session(rec)).id)

    result = asyncio.run(
        sessions_v3.list_sessions_for_workspace(store, 100)
    )
    # InMemorySessionStore は started_at=None なので id desc で sort される
    assert [r["id"] for r in result] == sorted(sids, reverse=True)


def test_service_kill_session_raises_for_invalid_id():
    """service: kill_session(0) → ValueError."""
    from services import sessions_v3

    store = InMemorySessionStore()
    with pytest.raises(ValueError):
        asyncio.run(sessions_v3.kill_session(store, 0))


def test_service_kill_session_raises_not_found():
    """service: 未存在 session → SessionNotFoundError."""
    from services import sessions_v3

    store = InMemorySessionStore()
    with pytest.raises(sessions_v3.SessionNotFoundError):
        asyncio.run(sessions_v3.kill_session(store, 12345))


def test_service_kill_all_returns_zero_for_empty_workspace():
    """service: 空 workspace の kill-all → killed_count 0."""
    from services import sessions_v3

    store = InMemorySessionStore()
    result = asyncio.run(sessions_v3.kill_all_sessions(store, 100))
    assert result == {"killed_count": 0}


def test_service_get_detail_includes_logs_tail_url():
    """service: get_session_detail に logs_tail_url が含まれる."""
    from services import sessions_v3

    store = InMemorySessionStore()
    rec = SessionRecord(prompt="t", workspace_id=10, status="running")
    sid = asyncio.run(store.create_session(rec)).id
    assert sid is not None
    detail = asyncio.run(sessions_v3.get_session_detail(store, sid))
    assert detail["logs_tail_url"] == f"/ws/sessions/{sid}/log"
    assert detail["session"]["id"] == sid
