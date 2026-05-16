"""T-V3-B-04 (F-003): AI 社員 backend (org-chart / test / clone-from-user).

12 件の functional AC を全件カバー + service-layer 単体テスト.

AC マッピング (audit/2026-05-16_v3/T-V3-B-04.md と完全一致):
  AC-F1 : EVENT-DRIVEN GET /org-chart → 非 archived の hierarchical tree
  AC-F2 : STATE-DRIVEN opt-in FALSE → 403
  AC-F3 : UNWANTED rate-limit >20/min/workspace → 429
  AC-F4 : EVENT-DRIVEN GET /org-chart 2xx contract (tree)
  AC-F5 : UNWANTED GET /org-chart 認証なし → 401
  AC-F6 : EVENT-DRIVEN POST /{id}/test 2xx contract (output)
  AC-F7 : UNWANTED POST /{id}/test 認証なし → 401
  AC-F8 : UNWANTED POST /{id}/test validation → 422
  AC-F9 : UNWANTED POST /{id}/test rate-limit → 429
  AC-F10: EVENT-DRIVEN POST /{id}/clone-from-user 2xx contract (clone_id)
  AC-F11: UNWANTED POST /{id}/clone-from-user 認証なし → 401
  AC-F12: UNWANTED POST /{id}/clone-from-user validation → 422
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from services import ai_employee_store as aes
from services.ai_employee_store import (
    AIEmployeeStore,
    CloneOptInError,
    RateLimitError,
    TEST_RATE_LIMIT_PER_MIN,
)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_store():
    aes.reset_store()
    yield
    aes.reset_store()


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


# ──────────────────────────────────────────────────────────────────────────
# Service / store unit tests (T-V3-B-04 internal helpers)
# ──────────────────────────────────────────────────────────────────────────


def test_store_create_employee_with_parent_same_workspace():
    s = AIEmployeeStore()
    root = s.create_employee("ceo", "CEO", workspace_id=1, role_level="leader")
    child = s.create_employee(
        "lead", "Lead", workspace_id=1, role_level="leader",
        parent_employee_id=root.id,
    )
    assert child.parent_employee_id == root.id


def test_store_parent_must_match_workspace():
    s = AIEmployeeStore()
    root = s.create_employee("ceo", "CEO", workspace_id=1)
    with pytest.raises(aes.AIEmployeeError, match="same workspace"):
        s.create_employee(
            "x", "X", workspace_id=2, parent_employee_id=root.id,
        )


def test_store_parent_must_exist():
    s = AIEmployeeStore()
    with pytest.raises(aes.AIEmployeeError, match="parent_employee_id not found"):
        s.create_employee("x", "X", workspace_id=1, parent_employee_id=999)


def test_store_build_org_chart_tree_shape():
    s = AIEmployeeStore()
    a = s.create_employee("a", "A", workspace_id=1)
    b = s.create_employee("b", "B", workspace_id=1, parent_employee_id=a.id)
    s.create_employee("c", "C", workspace_id=1, parent_employee_id=b.id)
    s.create_employee("d", "D", workspace_id=1, parent_employee_id=a.id)
    result = s.build_org_chart(workspace_id=1)
    assert result["total"] == 4
    assert len(result["tree"]) == 1
    root = result["tree"][0]
    assert root["employee_key"] == "a"
    assert len(root["children"]) == 2
    keys = sorted(c["employee_key"] for c in root["children"])
    assert keys == ["b", "d"]
    assert root["children"][0]["employee_key"] == "b"
    assert len(root["children"][0]["children"]) == 1
    assert root["children"][0]["children"][0]["employee_key"] == "c"


def test_store_build_org_chart_excludes_inactive_by_default():
    s = AIEmployeeStore()
    a = s.create_employee("a", "A", workspace_id=1)
    s.create_employee("b", "B", workspace_id=1, parent_employee_id=a.id)
    s.retire_employee(a.id, reason="test")
    # 非 active を除外 (AC-F1: 非 archived のみ)
    result = s.build_org_chart(workspace_id=1)
    assert result["total"] == 1
    assert result["tree"][0]["employee_key"] == "b"
    # include_inactive=True で復帰
    full = s.build_org_chart(workspace_id=1, include_inactive=True)
    assert full["total"] == 2


def test_store_build_org_chart_workspace_isolation():
    s = AIEmployeeStore()
    s.create_employee("a", "A", workspace_id=1)
    s.create_employee("b", "B", workspace_id=2)
    r1 = s.build_org_chart(workspace_id=1)
    r2 = s.build_org_chart(workspace_id=2)
    assert r1["total"] == 1 and r1["tree"][0]["employee_key"] == "a"
    assert r2["total"] == 1 and r2["tree"][0]["employee_key"] == "b"


def test_store_test_employee_returns_contract():
    s = AIEmployeeStore()
    e = s.create_employee("dev", "Devon", workspace_id=1)
    out = s.test_employee(e.id, input_prompt="hello")
    assert "output" in out and "tokens_used" in out and "cost_usd" in out
    assert out["tokens_used"] >= 1
    assert out["cost_usd"] > 0
    assert "Devon" in out["output"]


def test_store_test_employee_rate_limit():
    s = AIEmployeeStore()
    e = s.create_employee("dev", "Devon", workspace_id=42)
    for _ in range(TEST_RATE_LIMIT_PER_MIN):
        s.test_employee(e.id, input_prompt="ok")
    with pytest.raises(RateLimitError):
        s.test_employee(e.id, input_prompt="too many")


def test_store_test_employee_rate_limit_per_workspace():
    s = AIEmployeeStore()
    a = s.create_employee("a", "A", workspace_id=1)
    b = s.create_employee("b", "B", workspace_id=2)
    for _ in range(TEST_RATE_LIMIT_PER_MIN):
        s.test_employee(a.id, input_prompt="x")
    # workspace 2 はまだ余裕がある
    out = s.test_employee(b.id, input_prompt="y")
    assert out["output"]


def test_store_clone_requires_opt_in():
    s = AIEmployeeStore()
    e = s.create_employee("base", "Base", workspace_id=1)
    with pytest.raises(CloneOptInError):
        s.clone_from_user(e.id, user_id="u-1", opt_in_acknowledged=True)


def test_store_clone_requires_acknowledged():
    s = AIEmployeeStore()
    e = s.create_employee("base", "Base", workspace_id=1)
    s.set_user_clone_opt_in("u-1", opted_in=True)
    with pytest.raises(CloneOptInError, match="not acknowledged"):
        s.clone_from_user(e.id, user_id="u-1", opt_in_acknowledged=False)


def test_store_clone_success_creates_record():
    s = AIEmployeeStore()
    e = s.create_employee("base", "Base", workspace_id=7)
    s.set_user_clone_opt_in("u-2", opted_in=True)
    rec = s.clone_from_user(e.id, user_id="u-2", opt_in_acknowledged=True)
    assert rec.is_opted_in is True
    assert rec.base_employee_id == e.id
    assert rec.user_id == "u-2"
    assert rec.workspace_id == 7
    assert "u-2" in rec.namespace
    assert rec.clone_uuid


def test_store_clone_duplicate_user():
    s = AIEmployeeStore()
    e = s.create_employee("base", "Base", workspace_id=1)
    s.set_user_clone_opt_in("u", opted_in=True)
    s.clone_from_user(e.id, user_id="u", opt_in_acknowledged=True)
    with pytest.raises(aes.AIEmployeeError, match="already exists"):
        s.clone_from_user(e.id, user_id="u", opt_in_acknowledged=True)


# ──────────────────────────────────────────────────────────────────────────
# AC-F1 / AC-F4: GET /api/ai-employees/org-chart success
# ──────────────────────────────────────────────────────────────────────────


def test_ac_f1_f4_org_chart_returns_tree(client):
    """AC-F1 + AC-F4: hierarchical tree of non-archived employees / 2xx with contract."""
    r0 = client.post("/api/ai-employees", json={
        "employee_key": "ceo", "display_name": "CEO",
        "workspace_id": 1, "actor_user_id": "u-1",
    })
    parent_id = r0.json()["id"]
    client.post("/api/ai-employees", json={
        "employee_key": "lead", "display_name": "Lead",
        "workspace_id": 1, "parent_employee_id": parent_id,
        "actor_user_id": "u-1",
    })
    r = client.get(
        "/api/ai-employees/org-chart",
        params={"workspace_id": 1, "actor_user_id": "u-1"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "tree" in body and "total" in body
    assert body["total"] == 2
    assert len(body["tree"]) == 1
    assert body["tree"][0]["employee_key"] == "ceo"
    assert len(body["tree"][0]["children"]) == 1
    assert body["tree"][0]["children"][0]["employee_key"] == "lead"


def test_ac_f1_org_chart_excludes_retired(client):
    """AC-F1: 非 archived (retired) employee は tree から除外."""
    r0 = client.post("/api/ai-employees", json={
        "employee_key": "ceo", "display_name": "CEO",
        "workspace_id": 1, "actor_user_id": "u-1",
    })
    ceo_id = r0.json()["id"]
    client.post(f"/api/ai-employees/{ceo_id}/retire", json={"reason": "left"})
    r = client.get(
        "/api/ai-employees/org-chart",
        params={"workspace_id": 1, "actor_user_id": "u-1"},
    )
    assert r.status_code == 200
    assert r.json()["total"] == 0


# ──────────────────────────────────────────────────────────────────────────
# AC-F5: GET /org-chart without auth → 401
# ──────────────────────────────────────────────────────────────────────────


def test_ac_f5_org_chart_unauthorized_no_actor(client):
    r = client.get("/api/ai-employees/org-chart")
    assert r.status_code == 401
    detail = r.json()["detail"]
    assert detail["code"] == "ai_employee.unauthorized"


def test_ac_f5_org_chart_unauthorized_blank_actor(client):
    r = client.get(
        "/api/ai-employees/org-chart",
        params={"actor_user_id": "   "},
    )
    assert r.status_code == 401


# ──────────────────────────────────────────────────────────────────────────
# AC-F6: POST /{id}/test success → 2xx contract
# ──────────────────────────────────────────────────────────────────────────


def test_ac_f6_test_employee_returns_contract(client, _capture_audit):
    r0 = client.post("/api/ai-employees", json={
        "employee_key": "dev", "display_name": "Devon",
        "workspace_id": 1, "actor_user_id": "u-1",
    })
    eid = r0.json()["id"]
    r = client.post(
        f"/api/ai-employees/{eid}/test",
        json={"input_prompt": "hi", "actor_user_id": "u-1"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "output" in body
    assert isinstance(body["tokens_used"], int) and body["tokens_used"] >= 1
    assert isinstance(body["cost_usd"], (int, float))
    # audit emit (AC-3 STATE-DRIVEN): ai_employee_invocation
    assert any(e["event_type"] == "ai_employee_invocation" for e in _capture_audit)


# ──────────────────────────────────────────────────────────────────────────
# AC-F7: POST /{id}/test without auth → 401
# ──────────────────────────────────────────────────────────────────────────


def test_ac_f7_test_employee_unauthorized(client):
    r0 = client.post("/api/ai-employees", json={
        "employee_key": "dev", "display_name": "Devon", "workspace_id": 1,
        "actor_user_id": "u-1",
    })
    eid = r0.json()["id"]
    # actor_user_id missing entirely → 422 (Pydantic) ではなく
    # 空文字 / 空白 → 401 (AC-F7 explicit unauthorized check)
    r = client.post(
        f"/api/ai-employees/{eid}/test",
        json={"input_prompt": "x", "actor_user_id": "   "},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "ai_employee.unauthorized"


# ──────────────────────────────────────────────────────────────────────────
# AC-F8: POST /{id}/test validation → 422
# ──────────────────────────────────────────────────────────────────────────


def test_ac_f8_test_employee_validation_empty_prompt(client):
    r0 = client.post("/api/ai-employees", json={
        "employee_key": "dev", "display_name": "Devon", "workspace_id": 1,
        "actor_user_id": "u-1",
    })
    eid = r0.json()["id"]
    r = client.post(
        f"/api/ai-employees/{eid}/test",
        json={"input_prompt": "", "actor_user_id": "u-1"},
    )
    assert r.status_code == 422


def test_ac_f8_test_employee_validation_missing_field(client):
    r0 = client.post("/api/ai-employees", json={
        "employee_key": "dev", "display_name": "Devon", "workspace_id": 1,
        "actor_user_id": "u-1",
    })
    eid = r0.json()["id"]
    r = client.post(
        f"/api/ai-employees/{eid}/test",
        json={"actor_user_id": "u-1"},
    )
    assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────────
# AC-F3 / AC-F9: POST /{id}/test > 20/min/workspace → 429
# ──────────────────────────────────────────────────────────────────────────


def test_ac_f3_f9_test_employee_rate_limit(client):
    r0 = client.post("/api/ai-employees", json={
        "employee_key": "dev", "display_name": "Devon", "workspace_id": 99,
        "actor_user_id": "u-1",
    })
    eid = r0.json()["id"]
    # 20 successful calls
    for _ in range(TEST_RATE_LIMIT_PER_MIN):
        r = client.post(
            f"/api/ai-employees/{eid}/test",
            json={"input_prompt": "p", "actor_user_id": "u-1"},
        )
        assert r.status_code == 200
    # 21st call → 429
    r = client.post(
        f"/api/ai-employees/{eid}/test",
        json={"input_prompt": "p", "actor_user_id": "u-1"},
    )
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "ai_employee.rate_limited"


# ──────────────────────────────────────────────────────────────────────────
# AC-F10: POST /{id}/clone-from-user success → 2xx contract
# ──────────────────────────────────────────────────────────────────────────


def test_ac_f10_clone_from_user_success(client, _capture_audit):
    r0 = client.post("/api/ai-employees", json={
        "employee_key": "base", "display_name": "Base",
        "workspace_id": 7, "actor_user_id": "u-1",
    })
    eid = r0.json()["id"]
    aes.get_store().set_user_clone_opt_in("u-source", opted_in=True)
    r = client.post(
        f"/api/ai-employees/{eid}/clone-from-user",
        json={
            "user_id": "u-source",
            "opt_in_acknowledged": True,
            "actor_user_id": "u-1",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert "clone_id" in body and body["clone_id"]
    assert "namespace" in body and "u-source" in body["namespace"]
    assert body["base_employee_id"] == eid
    assert body["workspace_id"] == 7
    # AC-3 audit emit: ai_employee_clone
    assert any(e["event_type"] == "ai_employee_clone" for e in _capture_audit)


# ──────────────────────────────────────────────────────────────────────────
# AC-F2: clone opt-in FALSE → 403
# ──────────────────────────────────────────────────────────────────────────


def test_ac_f2_clone_blocked_when_user_not_opted_in(client):
    r0 = client.post("/api/ai-employees", json={
        "employee_key": "base", "display_name": "Base",
        "workspace_id": 7, "actor_user_id": "u-1",
    })
    eid = r0.json()["id"]
    # user は opt-in 未承諾
    r = client.post(
        f"/api/ai-employees/{eid}/clone-from-user",
        json={
            "user_id": "u-no-optin",
            "opt_in_acknowledged": True,
            "actor_user_id": "u-1",
        },
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "ai_employee.forbidden"


def test_ac_f2_clone_blocked_when_request_not_acknowledged(client):
    r0 = client.post("/api/ai-employees", json={
        "employee_key": "base", "display_name": "Base",
        "workspace_id": 7, "actor_user_id": "u-1",
    })
    eid = r0.json()["id"]
    aes.get_store().set_user_clone_opt_in("u-ok", opted_in=True)
    r = client.post(
        f"/api/ai-employees/{eid}/clone-from-user",
        json={
            "user_id": "u-ok",
            "opt_in_acknowledged": False,
            "actor_user_id": "u-1",
        },
    )
    assert r.status_code == 403


# ──────────────────────────────────────────────────────────────────────────
# AC-F11: POST /clone-from-user without auth → 401
# ──────────────────────────────────────────────────────────────────────────


def test_ac_f11_clone_unauthorized(client):
    r0 = client.post("/api/ai-employees", json={
        "employee_key": "base", "display_name": "Base",
        "workspace_id": 7, "actor_user_id": "u-1",
    })
    eid = r0.json()["id"]
    r = client.post(
        f"/api/ai-employees/{eid}/clone-from-user",
        json={
            "user_id": "u",
            "opt_in_acknowledged": True,
            "actor_user_id": "   ",
        },
    )
    assert r.status_code == 401


# ──────────────────────────────────────────────────────────────────────────
# AC-F12: POST /clone-from-user validation → 422
# ──────────────────────────────────────────────────────────────────────────


def test_ac_f12_clone_validation_missing_user_id(client):
    r0 = client.post("/api/ai-employees", json={
        "employee_key": "base", "display_name": "Base",
        "workspace_id": 7, "actor_user_id": "u-1",
    })
    eid = r0.json()["id"]
    r = client.post(
        f"/api/ai-employees/{eid}/clone-from-user",
        json={"opt_in_acknowledged": True, "actor_user_id": "u-1"},
    )
    assert r.status_code == 422


def test_ac_f12_clone_validation_wrong_type(client):
    r0 = client.post("/api/ai-employees", json={
        "employee_key": "base", "display_name": "Base",
        "workspace_id": 7, "actor_user_id": "u-1",
    })
    eid = r0.json()["id"]
    r = client.post(
        f"/api/ai-employees/{eid}/clone-from-user",
        json={
            "user_id": "u",
            "opt_in_acknowledged": 12345,  # int → bool 強制失敗 (Pydantic v2 strict)
            "actor_user_id": "u-1",
        },
    )
    assert r.status_code == 422


def test_ac_f12_clone_validation_empty_user_id(client):
    r0 = client.post("/api/ai-employees", json={
        "employee_key": "base", "display_name": "Base",
        "workspace_id": 7, "actor_user_id": "u-1",
    })
    eid = r0.json()["id"]
    r = client.post(
        f"/api/ai-employees/{eid}/clone-from-user",
        json={
            "user_id": "",
            "opt_in_acknowledged": True,
            "actor_user_id": "u-1",
        },
    )
    assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────────
# 404: employee_id 不在
# ──────────────────────────────────────────────────────────────────────────


def test_test_employee_not_found(client):
    r = client.post(
        "/api/ai-employees/9999/test",
        json={"input_prompt": "x", "actor_user_id": "u-1"},
    )
    assert r.status_code == 404


def test_clone_from_user_employee_not_found(client):
    aes.get_store().set_user_clone_opt_in("u", opted_in=True)
    r = client.post(
        "/api/ai-employees/9999/clone-from-user",
        json={
            "user_id": "u",
            "opt_in_acknowledged": True,
            "actor_user_id": "u-1",
        },
    )
    assert r.status_code == 404
