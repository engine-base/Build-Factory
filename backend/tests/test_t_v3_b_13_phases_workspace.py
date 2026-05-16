"""T-V3-B-13 / F-008: Phase management backend (workspace-scoped) tests.

Endpoints under test:
  GET  /api/workspaces/{id}/phases
  POST /api/workspaces/{id}/phases
  POST /api/workspaces/{id}/phases/{phase_id}/gate

Covers all 12 functional EARS AC + selected regression AC (Pydantic 422, RLS-aware
project resolution via service mocks). DB is mocked at service layer.

AC mapping (functional):
  AC-F1: gate pass → unlock next phase                   → test_gate_pass_unlocks_next_phase
  AC-F2: gate not met → 409 + failing_conditions         → test_gate_not_met_returns_409
  AC-F3: > 10 phases → 409                                → test_create_phase_max_reached_409
  AC-F4: list 200 + contract                              → test_list_phases_returns_200_with_contract
  AC-F5: list without auth (empty user_id) → 401          → test_list_phases_empty_user_id_returns_401
  AC-F6: list invalid input → 422                         → test_list_phases_invalid_workspace_id_*
  AC-F7: create valid → 2xx + phase_id                    → test_create_phase_returns_200_with_phase_id
  AC-F8: create without auth → 401                        → test_create_phase_empty_actor_returns_401
  AC-F9: create invalid body → 422                        → test_create_phase_missing_name_returns_422
  AC-F10: gate valid → 2xx + unlocked_phase_id            → test_gate_pass_returns_unlocked_phase_id
  AC-F11: gate without auth → 401                         → test_gate_empty_actor_returns_401
  AC-F12: gate invalid body → 422                         → test_gate_invalid_phase_id_returns_422
"""
from __future__ import annotations

import os
from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


# ──────────────────────────────────────────────────────────────────────────
# Mock helpers
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_ws_and_phases(monkeypatch):
    """workspace_service + phase_service の薄いモック."""
    from services import workspace_service as ws
    from services import phase_service as ps

    state: dict[str, Any] = {
        "workspaces": {1: {"id": 1, "name": "alpha", "status": "active"}},
        "members": {(1, "admin_user"): {"user_id": "admin_user", "role": "admin"},
                    (1, "viewer_user"): {"user_id": "viewer_user", "role": "viewer"}},
        "phases_by_ws": {1: [
            {"id": 10, "phase_no": 1, "name": "hearing",
             "status": "in_progress", "project_id": 100, "notes": None},
            {"id": 11, "phase_no": 2, "name": "requirements",
             "status": "pending", "project_id": 100, "notes": None},
        ]},
        "phase_count": {1: 2},
        "audits": [],
    }

    async def fake_get_workspace(wid):
        return state["workspaces"].get(wid)

    async def fake_get_member(wid, user_id):
        return state["members"].get((wid, user_id))

    async def fake_list_phases_for_workspace(wid):
        return state["phases_by_ws"].get(wid, [])

    async def fake_count_phases(wid):
        return state["phase_count"].get(wid, 0)

    async def fake_create_phase_for_workspace(*, workspace_id, name, gate_conditions=None):
        cnt = state["phase_count"].get(workspace_id, 0)
        if cnt >= 10:
            err = ps.InvalidPhaseInput(
                f"max_phases_reached: workspace {workspace_id} already has "
                f"{cnt} phases (limit=10)"
            )
            raise err
        if not name or not name.strip():
            raise ps.InvalidPhaseInput("name must not be empty")
        new_id = 1000 + cnt
        new_phase = {
            "id": new_id,
            "phase_no": cnt + 1,
            "name": name.strip(),
            "status": "pending",
            "project_id": 100,
            "notes": None,
        }
        state["phases_by_ws"].setdefault(workspace_id, []).append(new_phase)
        state["phase_count"][workspace_id] = cnt + 1
        return new_phase

    async def fake_evaluate_gate(*, workspace_id, phase_id, force=False):
        from datetime import datetime as _dt
        phases = state["phases_by_ws"].get(workspace_id, [])
        target = next((p for p in phases if p["id"] == phase_id), None)
        if not target:
            raise ps.PhaseNotFound(
                f"phase not found in workspace {workspace_id}: {phase_id}"
            )
        if not force and target["status"] != "completed":
            err = ps.InvalidPhaseInput(
                "gate_conditions_not_met: ['phase_not_completed']"
            )
            err.failing_conditions = ["phase_not_completed"]
            raise err
        # find next phase (phase_no > current)
        nxt = next(
            (p for p in phases if p["phase_no"] > target["phase_no"]
             and p["status"] != "skipped"),
            None,
        )
        unlocked_id = nxt["id"] if nxt else None
        return {
            "unlocked_phase_id": unlocked_id,
            "evaluated_at": _dt.utcnow().isoformat() + "Z",
            "passed": True,
        }

    async def fake_audit(event_type, *, user_id, detail):
        state["audits"].append((event_type, user_id, detail))

    monkeypatch.setattr(ws, "get_workspace", fake_get_workspace)
    monkeypatch.setattr(ws, "get_member", fake_get_member)
    monkeypatch.setattr(ps, "list_phases_for_workspace", fake_list_phases_for_workspace)
    monkeypatch.setattr(ps, "count_phases_for_workspace", fake_count_phases)
    monkeypatch.setattr(ps, "create_phase_for_workspace", fake_create_phase_for_workspace)
    monkeypatch.setattr(ps, "evaluate_gate_and_unlock_next", fake_evaluate_gate)

    # router 内 _audit_ws の参照先 (memory_service.emit_event)
    try:
        from services import memory_service as ms
        monkeypatch.setattr(ms, "emit_event", fake_audit)
    except Exception:
        pass

    return state


# ──────────────────────────────────────────────────────────────────────────
# AC-F4 / AC-R5: GET /api/workspaces/{id}/phases  (200 + contract)
# ──────────────────────────────────────────────────────────────────────────


def test_list_phases_returns_200_with_contract(client, mock_ws_and_phases):
    """AC-F4 EVENT: list 正常レスポンスは phases + current_phase_id を含む."""
    r = client.get("/api/workspaces/1/phases")
    assert r.status_code == 200
    body = r.json()
    assert "phases" in body
    assert isinstance(body["phases"], list)
    assert len(body["phases"]) == 2
    assert "current_phase_id" in body
    # in_progress = phase id 10
    assert body["current_phase_id"] == 10


def test_list_phases_current_phase_falls_back_to_pending(client, monkeypatch):
    """current_phase_id: in_progress なし → 最初の pending."""
    from services import phase_service as ps

    async def fake(wid):
        return [
            {"id": 200, "phase_no": 1, "status": "completed"},
            {"id": 201, "phase_no": 2, "status": "pending"},
        ]
    monkeypatch.setattr(ps, "list_phases_for_workspace", fake)
    r = client.get("/api/workspaces/1/phases")
    assert r.status_code == 200
    assert r.json()["current_phase_id"] == 201


def test_list_phases_current_phase_none_when_all_completed(client, monkeypatch):
    """完了済みのみ → current_phase_id is None."""
    from services import phase_service as ps

    async def fake(wid):
        return [
            {"id": 300, "phase_no": 1, "status": "completed"},
            {"id": 301, "phase_no": 2, "status": "completed"},
        ]
    monkeypatch.setattr(ps, "list_phases_for_workspace", fake)
    r = client.get("/api/workspaces/1/phases")
    assert r.status_code == 200
    assert r.json()["current_phase_id"] is None


# ──────────────────────────────────────────────────────────────────────────
# AC-F5: GET 401 (empty user_id)
# ──────────────────────────────────────────────────────────────────────────


def test_list_phases_empty_user_id_returns_401(client, mock_ws_and_phases):
    """AC-F5 UNWANTED: 空 user_id は 401."""
    r = client.get("/api/workspaces/1/phases", params={"user_id": "   "})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "phases.unauthorized"


def test_list_phases_non_member_returns_403(client, mock_ws_and_phases):
    """member でない user_id 指定 → 403."""
    r = client.get("/api/workspaces/1/phases", params={"user_id": "stranger"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "phases.forbidden"


def test_list_phases_member_user_id_returns_200(client, mock_ws_and_phases):
    """member user_id 指定 → 200."""
    r = client.get("/api/workspaces/1/phases", params={"user_id": "admin_user"})
    assert r.status_code == 200


# ──────────────────────────────────────────────────────────────────────────
# AC-F6: GET 422 (invalid path / workspace_id <= 0)
# ──────────────────────────────────────────────────────────────────────────


def test_list_phases_invalid_workspace_id_zero(client, mock_ws_and_phases):
    """AC-F6 UNWANTED: workspace_id <= 0 → 400/422."""
    r = client.get("/api/workspaces/0/phases")
    assert r.status_code in (400, 422)


def test_list_phases_invalid_workspace_id_string(client, mock_ws_and_phases):
    """AC-F6 UNWANTED: path int 違反 → Pydantic 422."""
    r = client.get("/api/workspaces/abc/phases")
    assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────────
# AC-F7: POST /api/workspaces/{id}/phases  → 200 + phase_id
# ──────────────────────────────────────────────────────────────────────────


def test_create_phase_returns_200_with_phase_id(client, mock_ws_and_phases):
    """AC-F7 EVENT: 正常 → 200 + phase_id."""
    r = client.post(
        "/api/workspaces/1/phases",
        json={"name": "architecture", "gate_conditions": ["spec_done"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert "phase_id" in body
    assert body["name"] == "architecture"


def test_create_phase_with_member_admin_actor_succeeds(client, mock_ws_and_phases):
    """admin role の actor_user_id 指定 → 200."""
    r = client.post(
        "/api/workspaces/1/phases",
        json={"name": "review", "actor_user_id": "admin_user"},
    )
    assert r.status_code == 200


# ──────────────────────────────────────────────────────────────────────────
# AC-F8: POST create 401 (empty actor)
# ──────────────────────────────────────────────────────────────────────────


def test_create_phase_empty_actor_returns_401(client, mock_ws_and_phases):
    """AC-F8 UNWANTED: actor_user_id が空文字 → 401."""
    r = client.post(
        "/api/workspaces/1/phases",
        json={"name": "foo", "actor_user_id": "   "},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "phases.unauthorized"


def test_create_phase_non_admin_actor_returns_403(client, mock_ws_and_phases):
    """非 admin role の actor → 403."""
    r = client.post(
        "/api/workspaces/1/phases",
        json={"name": "foo", "actor_user_id": "viewer_user"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "phases.forbidden"


# ──────────────────────────────────────────────────────────────────────────
# AC-F9: POST create 422 (missing/invalid name)
# ──────────────────────────────────────────────────────────────────────────


def test_create_phase_missing_name_returns_422(client, mock_ws_and_phases):
    """AC-F9 UNWANTED: name 欠落 → Pydantic 422."""
    r = client.post("/api/workspaces/1/phases", json={})
    assert r.status_code == 422


def test_create_phase_empty_name_returns_422(client, mock_ws_and_phases):
    """AC-F9 UNWANTED: 空 name → 422 (service 層 reject)."""
    r = client.post("/api/workspaces/1/phases", json={"name": "  "})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "phases.invalid_name"


def test_create_phase_workspace_not_found_returns_404(client, mock_ws_and_phases):
    """存在しない workspace_id → 404."""
    r = client.post("/api/workspaces/9999/phases", json={"name": "x"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "workspaces.not_found"


# ──────────────────────────────────────────────────────────────────────────
# AC-F3 / AC-R: POST create 409 (max 10 phases)
# ──────────────────────────────────────────────────────────────────────────


def test_create_phase_max_reached_409(client, mock_ws_and_phases):
    """AC-F3 UNWANTED: phase 数が 10 に達した workspace は 409."""
    state = mock_ws_and_phases
    # state を 10 件に詰める
    state["phase_count"][1] = 10
    r = client.post(
        "/api/workspaces/1/phases",
        json={"name": "overflow"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "phases.max_phases_reached"


# ──────────────────────────────────────────────────────────────────────────
# AC-F1 / AC-F10: POST gate  (200 + unlocked)
# ──────────────────────────────────────────────────────────────────────────


def test_gate_pass_unlocks_next_phase(client, mock_ws_and_phases):
    """AC-F1 EVENT + AC-F10: gate 条件達成 → unlock next phase."""
    state = mock_ws_and_phases
    # phase id 10 を completed にしておく
    state["phases_by_ws"][1][0]["status"] = "completed"
    r = client.post("/api/workspaces/1/phases/10/gate", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["unlocked_phase_id"] == 11  # 次の phase
    assert "evaluated_at" in body
    assert body["passed"] is True


def test_gate_pass_returns_unlocked_phase_id(client, mock_ws_and_phases):
    """AC-F10 EVENT: 正常 → 2xx + unlocked_phase_id を含む."""
    state = mock_ws_and_phases
    state["phases_by_ws"][1][0]["status"] = "completed"
    r = client.post(
        "/api/workspaces/1/phases/10/gate",
        json={"actor_user_id": "admin_user"},
    )
    assert r.status_code == 200
    assert "unlocked_phase_id" in r.json()


def test_gate_force_bypasses_status_check(client, mock_ws_and_phases):
    """force=True なら pending phase でも unlock."""
    r = client.post(
        "/api/workspaces/1/phases/10/gate", json={"force": True},
    )
    assert r.status_code == 200


# ──────────────────────────────────────────────────────────────────────────
# AC-F2: POST gate 409 (conditions not met)
# ──────────────────────────────────────────────────────────────────────────


def test_gate_not_met_returns_409(client, mock_ws_and_phases):
    """AC-F2 UNWANTED: 条件未達 → 409 + failing_conditions."""
    # default: phase id 10 は in_progress (not completed) → gate fail
    r = client.post("/api/workspaces/1/phases/10/gate", json={})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "phases.gate_conditions_not_met"
    assert "failing_conditions" in detail
    assert isinstance(detail["failing_conditions"], list)
    assert len(detail["failing_conditions"]) >= 1


def test_gate_phase_not_in_workspace_returns_404(client, mock_ws_and_phases):
    """workspace 外の phase_id → 404."""
    r = client.post("/api/workspaces/1/phases/99999/gate", json={})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "phases.not_found"


# ──────────────────────────────────────────────────────────────────────────
# AC-F11: POST gate 401 (empty actor)
# ──────────────────────────────────────────────────────────────────────────


def test_gate_empty_actor_returns_401(client, mock_ws_and_phases):
    """AC-F11 UNWANTED: actor_user_id 空 → 401."""
    r = client.post(
        "/api/workspaces/1/phases/10/gate",
        json={"actor_user_id": "  "},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "phases.unauthorized"


def test_gate_non_admin_actor_returns_403(client, mock_ws_and_phases):
    """非 admin role の actor → 403."""
    r = client.post(
        "/api/workspaces/1/phases/10/gate",
        json={"actor_user_id": "viewer_user"},
    )
    assert r.status_code == 403


# ──────────────────────────────────────────────────────────────────────────
# AC-F12: POST gate 422 (invalid path / body)
# ──────────────────────────────────────────────────────────────────────────


def test_gate_invalid_phase_id_returns_422(client, mock_ws_and_phases):
    """AC-F12 UNWANTED: phase_id <= 0 → 422."""
    r = client.post("/api/workspaces/1/phases/0/gate", json={})
    assert r.status_code in (400, 422)


def test_gate_invalid_phase_id_string(client, mock_ws_and_phases):
    """AC-F12 UNWANTED: phase_id が int でない → Pydantic 422."""
    r = client.post("/api/workspaces/1/phases/abc/gate", json={})
    assert r.status_code == 422


def test_gate_workspace_not_found_returns_404(client, mock_ws_and_phases):
    """存在しない workspace_id → 404."""
    r = client.post("/api/workspaces/9999/phases/10/gate", json={})
    assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────────
# Service-layer pure tests (no router)
# ──────────────────────────────────────────────────────────────────────────


def test_extract_gate_conditions_from_notes():
    """phase.notes JSON から gate_conditions を抽出."""
    from services.phase_service import _extract_gate_conditions
    p = {"notes": '{"gate_conditions": ["a", "b"]}'}
    assert _extract_gate_conditions(p) == ["a", "b"]


def test_extract_gate_conditions_no_notes_returns_empty():
    from services.phase_service import _extract_gate_conditions
    assert _extract_gate_conditions({}) == []
    assert _extract_gate_conditions({"notes": None}) == []


def test_extract_gate_conditions_malformed_json_returns_empty():
    from services.phase_service import _extract_gate_conditions
    assert _extract_gate_conditions({"notes": "not json"}) == []
    assert _extract_gate_conditions({"notes": '{"x":1}'}) == []


def test_max_phases_constant_is_10():
    """F-008 policies: max_phases_per_workspace = 10."""
    from services.phase_service import MAX_PHASES_PER_WORKSPACE
    assert MAX_PHASES_PER_WORKSPACE == 10
