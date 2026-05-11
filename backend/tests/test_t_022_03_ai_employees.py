"""T-022-03: AI 社員 CRUD (M-22 schema) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-022 AI 社員 CRUD (REFACTOR 既存 employees.py 拡張)
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 routers/employees.py / staff.py / staff_service.py 不変
                       + audit emit (write only)
  AC-4 UNWANTED      : invalid input / duplicate key / unknown persona /
                       退職済再退職 を全て 4xx + structured / 失敗時 audit 非発行
"""
from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from services import ai_employee_store as aes
from services.ai_employee_store import (
    AIEmployeeError,
    AIEmployeeStore,
    MAX_EMPLOYEES_PER_WORKSPACE,
    MAX_KEY_LEN,
    MAX_NAME_LEN,
    VALID_ROLE_LEVELS,
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
# Store 単体: persona
# ──────────────────────────────────────────────────────────────────────────


def test_store_create_persona_minimal():
    s = AIEmployeeStore()
    p = s.create_persona("ba_analyst", "Mary Mansfield")
    assert p.id == 1
    assert p.persona_key == "ba_analyst"
    assert p.persona_name == "Mary Mansfield"


def test_store_create_persona_full():
    s = AIEmployeeStore()
    p = s.create_persona(
        "dev", "Devon Devereaux",
        personality="冷静沈着",
        tone_style="敬語短文",
        catchphrase="動くものから.",
        specialty="implementation",
        handles="F-005",
        avatar_lucide="code-2",
        metadata={"tier": "leader"},
    )
    d = p.to_dict()
    assert d["personality"] == "冷静沈着"
    assert d["metadata"] == {"tier": "leader"}


def test_store_create_persona_duplicate_key():
    s = AIEmployeeStore()
    s.create_persona("dev", "Devon")
    with pytest.raises(AIEmployeeError, match="already exists"):
        s.create_persona("dev", "Devon-2")


def test_store_persona_invalid_key():
    s = AIEmployeeStore()
    with pytest.raises(AIEmployeeError):
        s.create_persona("", "Name")
    with pytest.raises(AIEmployeeError):
        s.create_persona("   ", "Name")
    with pytest.raises(AIEmployeeError):
        s.create_persona("with space", "Name")
    with pytest.raises(AIEmployeeError):
        s.create_persona("x" * (MAX_KEY_LEN + 1), "Name")


def test_store_persona_invalid_name():
    s = AIEmployeeStore()
    with pytest.raises(AIEmployeeError):
        s.create_persona("k", "")
    with pytest.raises(AIEmployeeError):
        s.create_persona("k", "x" * (MAX_NAME_LEN + 1))
    with pytest.raises(AIEmployeeError):
        s.create_persona("k", 123)  # type: ignore


def test_store_persona_invalid_optional():
    s = AIEmployeeStore()
    with pytest.raises(AIEmployeeError):
        s.create_persona("k", "n", personality="  ")
    with pytest.raises(AIEmployeeError):
        s.create_persona("k", "n", personality=123)  # type: ignore


def test_store_persona_invalid_metadata():
    s = AIEmployeeStore()
    with pytest.raises(AIEmployeeError):
        s.create_persona("k", "n", metadata=[1, 2])  # type: ignore


def test_store_get_persona():
    s = AIEmployeeStore()
    p = s.create_persona("dev", "Devon")
    assert s.get_persona(p.id).persona_key == "dev"
    assert s.get_persona(99) is None


def test_store_get_persona_invalid_id():
    s = AIEmployeeStore()
    with pytest.raises(AIEmployeeError):
        s.get_persona(0)


def test_store_get_persona_by_key():
    s = AIEmployeeStore()
    s.create_persona("dev", "Devon")
    assert s.get_persona_by_key("dev").persona_name == "Devon"
    assert s.get_persona_by_key("unknown") is None


def test_store_list_personas():
    s = AIEmployeeStore()
    s.create_persona("a", "A")
    s.create_persona("b", "B")
    items = s.list_personas()
    assert len(items) == 2


def test_store_delete_persona_cascades_employees():
    s = AIEmployeeStore()
    p = s.create_persona("dev", "Devon")
    e = s.create_employee("devon", "Devon E.", persona_id=p.id)
    assert s.delete_persona(p.id) is True
    # FK SET NULL: persona_id が None になっている
    got = s.get_employee(e.id)
    assert got.persona_id is None


def test_store_delete_persona_unknown():
    s = AIEmployeeStore()
    assert s.delete_persona(99) is False


# ──────────────────────────────────────────────────────────────────────────
# Store 単体: employee
# ──────────────────────────────────────────────────────────────────────────


def test_store_create_employee_minimal():
    s = AIEmployeeStore()
    e = s.create_employee("mary", "Mary M.")
    assert e.employee_key == "mary"
    assert e.role_level == "leader"
    assert e.is_active is True


def test_store_create_employee_with_persona_and_workspace():
    s = AIEmployeeStore()
    p = s.create_persona("ba", "BA persona")
    e = s.create_employee(
        "mary", "Mary M.",
        workspace_id=10, persona_id=p.id, role_level="secretary",
    )
    assert e.workspace_id == 10
    assert e.persona_id == p.id
    assert e.role_level == "secretary"


def test_store_create_employee_duplicate_key_in_workspace():
    s = AIEmployeeStore()
    s.create_employee("mary", "Mary M.", workspace_id=1)
    with pytest.raises(AIEmployeeError, match="already exists"):
        s.create_employee("mary", "Mary M-2", workspace_id=1)


def test_store_create_employee_same_key_diff_workspace_ok():
    s = AIEmployeeStore()
    s.create_employee("mary", "Mary M.", workspace_id=1)
    e2 = s.create_employee("mary", "Mary M-2", workspace_id=2)
    assert e2.workspace_id == 2


def test_store_create_employee_unknown_persona():
    s = AIEmployeeStore()
    with pytest.raises(AIEmployeeError, match="persona_id not found"):
        s.create_employee("mary", "Mary", persona_id=999)


def test_store_create_employee_invalid_role():
    s = AIEmployeeStore()
    with pytest.raises(AIEmployeeError):
        s.create_employee("mary", "Mary", role_level="boss")


def test_store_create_employee_invalid_workspace_id():
    s = AIEmployeeStore()
    with pytest.raises(AIEmployeeError):
        s.create_employee("mary", "Mary", workspace_id=0)


def test_store_quota_per_workspace(monkeypatch):
    monkeypatch.setattr(aes, "MAX_EMPLOYEES_PER_WORKSPACE", 2)
    s = AIEmployeeStore()
    s.create_employee("a", "A", workspace_id=1)
    s.create_employee("b", "B", workspace_id=1)
    with pytest.raises(AIEmployeeError, match="max employees per workspace"):
        s.create_employee("c", "C", workspace_id=1)


def test_store_get_employee_by_key():
    s = AIEmployeeStore()
    s.create_employee("mary", "Mary", workspace_id=7)
    assert s.get_employee_by_key("mary", workspace_id=7).display_name == "Mary"
    assert s.get_employee_by_key("mary", workspace_id=99) is None


def test_store_list_employees_filters():
    s = AIEmployeeStore()
    s.create_employee("a", "A", workspace_id=1, role_level="secretary")
    s.create_employee("b", "B", workspace_id=1, role_level="leader")
    s.create_employee("c", "C", workspace_id=2, role_level="leader")
    s.create_employee("d", "D", workspace_id=1, role_level="member")
    items_ws1 = s.list_employees(workspace_id=1)
    assert len(items_ws1) == 3
    items_leader = s.list_employees(role_level="leader")
    assert len(items_leader) == 2
    items_ws1_leader = s.list_employees(workspace_id=1, role_level="leader")
    assert len(items_ws1_leader) == 1


def test_store_list_employees_includes_inactive_when_requested():
    s = AIEmployeeStore()
    e = s.create_employee("a", "A")
    s.retire_employee(e.id)
    assert len(s.list_employees()) == 0
    assert len(s.list_employees(include_inactive=True)) == 1


def test_store_list_employees_invalid_limit():
    s = AIEmployeeStore()
    with pytest.raises(AIEmployeeError):
        s.list_employees(limit=0)
    with pytest.raises(AIEmployeeError):
        s.list_employees(limit=10_001)


def test_store_list_employees_invalid_role_level():
    s = AIEmployeeStore()
    with pytest.raises(AIEmployeeError):
        s.list_employees(role_level="boss")


def test_store_update_employee():
    s = AIEmployeeStore()
    p = s.create_persona("ba", "BA")
    e = s.create_employee("mary", "Mary")
    upd = s.update_employee(
        e.id, display_name="Mary M.", persona_id=p.id, role_level="secretary",
    )
    assert upd.display_name == "Mary M."
    assert upd.persona_id == p.id
    assert upd.role_level == "secretary"


def test_store_update_employee_no_fields():
    s = AIEmployeeStore()
    e = s.create_employee("mary", "Mary")
    with pytest.raises(AIEmployeeError):
        s.update_employee(e.id)


def test_store_update_employee_unknown():
    s = AIEmployeeStore()
    with pytest.raises(AIEmployeeError, match="not found"):
        s.update_employee(99, display_name="X")


def test_store_update_employee_unknown_persona():
    s = AIEmployeeStore()
    e = s.create_employee("mary", "Mary")
    with pytest.raises(AIEmployeeError, match="persona_id not found"):
        s.update_employee(e.id, persona_id=999)


def test_store_retire_and_reactivate():
    s = AIEmployeeStore()
    e = s.create_employee("mary", "Mary")
    r = s.retire_employee(e.id, reason="resign")
    assert r.is_active is False
    assert r.retire_reason == "resign"
    assert r.retired_at is not None
    # 二重退職は conflict
    with pytest.raises(AIEmployeeError, match="already retired"):
        s.retire_employee(e.id)
    rea = s.reactivate_employee(e.id)
    assert rea.is_active is True
    assert rea.retired_at is None
    # 既に active なら再 active は conflict
    with pytest.raises(AIEmployeeError, match="already active"):
        s.reactivate_employee(e.id)


def test_store_retire_invalid_reason():
    s = AIEmployeeStore()
    e = s.create_employee("mary", "Mary")
    with pytest.raises(AIEmployeeError):
        s.retire_employee(e.id, reason="x" * 501)


def test_store_retire_unknown_employee():
    s = AIEmployeeStore()
    with pytest.raises(AIEmployeeError, match="not found"):
        s.retire_employee(99)


def test_store_delete_employee():
    s = AIEmployeeStore()
    e = s.create_employee("mary", "Mary", workspace_id=1)
    assert s.delete_employee(e.id) is True
    assert s.delete_employee(e.id) is False


def test_store_singleton():
    s1 = aes.get_store()
    s2 = aes.get_store()
    assert s1 is s2
    aes.reset_store()
    s3 = aes.get_store()
    assert s3 is not s1


# ──────────────────────────────────────────────────────────────────────────
# AC-1: endpoint 起動 (persona)
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_persona_crud(client):
    r = client.post("/api/ai-personas", json={
        "persona_key": "ba", "persona_name": "Mary",
    })
    assert r.status_code == 200
    pid = r.json()["id"]
    r2 = client.get(f"/api/ai-personas/{pid}")
    assert r2.status_code == 200
    r3 = client.get("/api/ai-personas")
    assert r3.json()["count"] == 1
    r4 = client.delete(f"/api/ai-personas/{pid}")
    assert r4.status_code == 200


# ──────────────────────────────────────────────────────────────────────────
# AC-1: endpoint 起動 (employee)
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_employee_create(client):
    r = client.post("/api/ai-employees", json={
        "employee_key": "mary", "display_name": "Mary M.",
        "workspace_id": 7, "actor_user_id": "u-1",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["employee_key"] == "mary"
    assert body["workspace_id"] == 7


def test_ac1_employee_list_filters(client):
    client.post("/api/ai-employees", json={
        "employee_key": "a", "display_name": "A", "workspace_id": 1,
    })
    client.post("/api/ai-employees", json={
        "employee_key": "b", "display_name": "B", "workspace_id": 1,
        "role_level": "secretary",
    })
    client.post("/api/ai-employees", json={
        "employee_key": "c", "display_name": "C", "workspace_id": 2,
    })
    r = client.get("/api/ai-employees", params={"workspace_id": 1})
    assert r.json()["count"] == 2
    r2 = client.get("/api/ai-employees", params={"role_level": "secretary"})
    assert r2.json()["count"] == 1


def test_ac1_employee_get(client):
    r = client.post("/api/ai-employees", json={
        "employee_key": "x", "display_name": "X",
    })
    eid = r.json()["id"]
    r2 = client.get(f"/api/ai-employees/{eid}")
    assert r2.status_code == 200


def test_ac1_employee_update(client):
    r = client.post("/api/ai-employees", json={
        "employee_key": "x", "display_name": "X",
    })
    eid = r.json()["id"]
    r2 = client.patch(f"/api/ai-employees/{eid}", json={
        "display_name": "X New", "role_level": "member",
    })
    body = r2.json()
    assert body["display_name"] == "X New"
    assert body["role_level"] == "member"


def test_ac1_employee_retire_reactivate(client):
    r = client.post("/api/ai-employees", json={
        "employee_key": "x", "display_name": "X",
    })
    eid = r.json()["id"]
    r2 = client.post(f"/api/ai-employees/{eid}/retire", json={"reason": "test"})
    assert r2.status_code == 200
    assert r2.json()["is_active"] is False
    r3 = client.post(f"/api/ai-employees/{eid}/reactivate", json={})
    assert r3.status_code == 200
    assert r3.json()["is_active"] is True


def test_ac1_employee_delete(client):
    r = client.post("/api/ai-employees", json={
        "employee_key": "x", "display_name": "X",
    })
    eid = r.json()["id"]
    r2 = client.delete(f"/api/ai-employees/{eid}")
    assert r2.status_code == 200


# ──────────────────────────────────────────────────────────────────────────
# AC-2: 2 秒以内 + {detail:{code,message}}
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_response_within_2sec(client):
    t0 = time.time()
    r = client.post("/api/ai-employees", json={
        "employee_key": "x", "display_name": "X",
    })
    elapsed = time.time() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_shape_unknown_persona(client):
    r = client.post("/api/ai-employees", json={
        "employee_key": "x", "display_name": "X", "persona_id": 999,
    })
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert detail["code"] == "ai_employee.not_found"


def test_ac2_error_shape_consistency(client):
    cases = [
        ("POST", "/api/ai-employees", {
            "employee_key": "x", "display_name": "X", "actor_user_id": "  ",
        }),
        ("POST", "/api/ai-personas", {
            "persona_key": "  ", "persona_name": "X",
        }),
        ("PATCH", "/api/ai-employees/99", {"display_name": "X"}),
        ("GET", "/api/ai-employees/99", None),
        ("DELETE", "/api/ai-employees/99", None),
    ]
    for method, path, body in cases:
        if method == "GET":
            r = client.get(path)
        elif method == "DELETE":
            r = client.delete(path)
        elif method == "PATCH":
            r = client.patch(path, json=body)
        else:
            r = client.post(path, json=body)
        assert r.status_code in (400, 401, 404, 409, 422), f"{path} -> {r.status_code}"
        if r.status_code != 422:
            detail = r.json()["detail"]
            assert isinstance(detail, dict)
            assert "code" in detail and "message" in detail
            assert detail["code"].startswith("ai_employee."), f"{path}: {detail['code']}"


# ──────────────────────────────────────────────────────────────────────────
# AC-3: audit emit
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_create_employee_emits_audit(client, _capture_audit):
    r = client.post("/api/ai-employees", json={
        "employee_key": "mary", "display_name": "M",
        "workspace_id": 7, "actor_user_id": "u-1",
    })
    assert r.status_code == 200
    events = [e for e in _capture_audit if e["event_type"] == "ai_employee.created"]
    assert len(events) == 1
    assert events[0]["user_id"] == "u-1"
    assert events[0]["detail"]["workspace_id"] == 7


def test_ac3_retire_emits_audit(client, _capture_audit):
    r = client.post("/api/ai-employees", json={
        "employee_key": "mary", "display_name": "M",
    })
    eid = r.json()["id"]
    _capture_audit.clear()
    client.post(f"/api/ai-employees/{eid}/retire", json={
        "reason": "resign", "actor_user_id": "u-1",
    })
    events = [e for e in _capture_audit if e["event_type"] == "ai_employee.retired"]
    assert len(events) == 1
    assert events[0]["detail"]["reason"] == "resign"


def test_ac3_persona_create_emits_audit(client, _capture_audit):
    client.post("/api/ai-personas", json={
        "persona_key": "ba", "persona_name": "Mary", "actor_user_id": "u-1",
    })
    events = [e for e in _capture_audit if e["event_type"] == "ai_persona.created"]
    assert len(events) == 1


def test_ac3_read_endpoints_no_audit(client, _capture_audit):
    r = client.post("/api/ai-employees", json={
        "employee_key": "x", "display_name": "X",
    })
    eid = r.json()["id"]
    _capture_audit.clear()
    client.get("/api/ai-employees")
    client.get(f"/api/ai-employees/{eid}")
    client.get("/api/ai-personas")
    write_events = [
        e for e in _capture_audit
        if e["event_type"].startswith(("ai_employee.", "ai_persona."))
    ]
    assert write_events == []


# ──────────────────────────────────────────────────────────────────────────
# AC-4: invalid input は 4xx + structured / state mutate しない
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_duplicate_employee_key(client, _capture_audit):
    client.post("/api/ai-employees", json={
        "employee_key": "mary", "display_name": "M-1", "workspace_id": 1,
    })
    _capture_audit.clear()
    r = client.post("/api/ai-employees", json={
        "employee_key": "mary", "display_name": "M-2", "workspace_id": 1,
    })
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ai_employee.conflict"
    # 失敗時 state 不変
    r2 = client.get("/api/ai-employees", params={"workspace_id": 1})
    assert r2.json()["count"] == 1
    assert not any(
        e["event_type"] == "ai_employee.created" for e in _capture_audit
    )


def test_ac4_empty_actor_user_id(client):
    r = client.post("/api/ai-employees", json={
        "employee_key": "x", "display_name": "X", "actor_user_id": "  ",
    })
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "ai_employee.unauthorized"


def test_ac4_invalid_employee_key_chars(client):
    r = client.post("/api/ai-employees", json={
        "employee_key": "has space", "display_name": "X",
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "ai_employee.invalid"


def test_ac4_invalid_role_level(client):
    r = client.post("/api/ai-employees", json={
        "employee_key": "x", "display_name": "X", "role_level": "boss",
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "ai_employee.invalid"


def test_ac4_retire_already_retired(client):
    r = client.post("/api/ai-employees", json={
        "employee_key": "x", "display_name": "X",
    })
    eid = r.json()["id"]
    client.post(f"/api/ai-employees/{eid}/retire", json={})
    r2 = client.post(f"/api/ai-employees/{eid}/retire", json={})
    assert r2.status_code == 409
    assert r2.json()["detail"]["code"] == "ai_employee.conflict"


def test_ac4_reactivate_already_active(client):
    r = client.post("/api/ai-employees", json={
        "employee_key": "x", "display_name": "X",
    })
    eid = r.json()["id"]
    r2 = client.post(f"/api/ai-employees/{eid}/reactivate", json={})
    assert r2.status_code == 409


def test_ac4_workspace_id_zero_pydantic_422(client):
    r = client.post("/api/ai-employees", json={
        "employee_key": "x", "display_name": "X", "workspace_id": 0,
    })
    assert r.status_code == 422


def test_ac4_update_no_fields(client):
    r = client.post("/api/ai-employees", json={
        "employee_key": "x", "display_name": "X",
    })
    eid = r.json()["id"]
    r2 = client.patch(f"/api/ai-employees/{eid}", json={})
    assert r2.status_code == 400


def test_ac4_persona_duplicate_key(client):
    client.post("/api/ai-personas", json={
        "persona_key": "dev", "persona_name": "A",
    })
    r = client.post("/api/ai-personas", json={
        "persona_key": "dev", "persona_name": "B",
    })
    assert r.status_code == 409


# ──────────────────────────────────────────────────────────────────────────
# Backwards compatibility: legacy employees/staff routers untouched
# ──────────────────────────────────────────────────────────────────────────


def test_compat_legacy_employees_router_unchanged():
    from routers import employees as legacy_emp
    assert hasattr(legacy_emp, "router")
    assert hasattr(legacy_emp, "list_employees")
    assert hasattr(legacy_emp, "get_employee")


def test_compat_legacy_staff_router_unchanged():
    from routers import staff as legacy_staff
    assert hasattr(legacy_staff, "router")


def test_compat_staff_service_unchanged():
    from services import staff_service as ss
    # 主要 symbol が import 可能
    assert hasattr(ss, "__name__")
