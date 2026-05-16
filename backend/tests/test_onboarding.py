"""T-V3-B-29 / F-027: Onboarding backend tests (GET / advance / skip).

AC マッピング (audit: docs/audit/2026-05-16_v3/T-V3-B-29.md):
  AC-F1 EVENT-DRIVEN  : POST /advance valid → persist + next_step
  AC-F2 UNWANTED      : POST /skip required step → 409
  AC-F3 EVENT-DRIVEN  : GET /onboarding → 2xx with state
  AC-F4 UNWANTED      : GET unauthorized → 401
  AC-F5 UNWANTED      : invalid body → 422
  AC-F6 EVENT-DRIVEN  : POST /advance valid auth → 2xx
  AC-F7 UNWANTED      : POST /advance unauthorized → 401
  AC-F8 UNWANTED      : POST /advance invalid body → 422
  AC-F9 EVENT-DRIVEN  : POST /skip valid auth → 2xx
  AC-F10 UNWANTED     : POST /skip unauthorized → 401

DB は Postgres (psycopg) でテスト時に到達不可なので、 service 層の `_db` を
in-memory FakeDb に差し替える (test_lifecycle_mocked.py と同じパターン).
"""
from __future__ import annotations

import os
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient


# Supabase env stub (import-time guard回避)
os.environ.setdefault("SUPABASE_URL", "https://stub.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "stub-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "stub-service-key")
os.environ.setdefault("SUPABASE_JWT_SECRET", "stub-jwt-secret")
os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")


# ────────────────────────────────────────────────────────────
# in-memory fake DB (test_lifecycle_mocked.py 流)
# ────────────────────────────────────────────────────────────

class _InMemoryStore:
    """user_id -> row dict のシンプル store. すべての test sess で共有."""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}

    def reset(self) -> None:
        self.rows.clear()


_STORE = _InMemoryStore()


class _FakeCursor:
    def __init__(self, rows=None):
        self._rows = list(rows or [])

    async def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    async def fetchall(self):
        rows, self._rows = self._rows, []
        return rows


class _FakeConn:
    row_factory = None

    async def execute(self, sql: str, params: tuple = ()):  # type: ignore[override]
        sql_l = sql.strip().lower()
        if sql_l.startswith("create table"):
            return _FakeCursor()
        if sql_l.startswith("select"):
            uid = params[0] if params else None
            row = _STORE.rows.get(uid)
            return _FakeCursor([row] if row else [])
        if sql_l.startswith("insert"):
            # INSERT ... ON CONFLICT(user_id) DO UPDATE
            # params order: user_id, current_step, completed_steps_json,
            # skipped_steps_json, completed_at, skipped_at, payload_json
            (
                user_id, current_step, completed_steps, skipped_steps,
                completed_at, skipped_at, payload,
            ) = params
            _STORE.rows[user_id] = {
                "id": len(_STORE.rows) + 1,
                "user_id": user_id,
                "current_step": current_step,
                "completed_steps": completed_steps,
                "skipped_steps": skipped_steps,
                "completed_at": completed_at,
                "skipped_at": skipped_at,
                "payload": payload,
                "updated_at": "2026-05-16T00:00:00Z",
                "created_at": "2026-05-16T00:00:00Z",
            }
            return _FakeCursor()
        if sql_l.startswith("delete"):
            _STORE.rows.clear()
            return _FakeCursor()
        return _FakeCursor()

    async def commit(self) -> None:
        pass

    async def __aenter__(self) -> "_FakeConn":
        return self

    async def __aexit__(self, *a: Any) -> None:
        pass


class _FakeDb:
    Row = dict

    def connect(self, _path: Any) -> _FakeConn:
        return _FakeConn()


# ────────────────────────────────────────────────────────────
# fixtures
# ────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    os.environ["BUILD_FACTORY_DEV_BYPASS_AUTH"] = "1"
    from main import app
    yield TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _patch_db(monkeypatch):
    """services.onboarding の _db を in-memory FakeDb に差し替える."""
    from services import onboarding as svc

    _STORE.reset()
    monkeypatch.setattr(svc, "_db", lambda: _FakeDb())
    monkeypatch.setattr(svc, "_db_path", lambda: ":memory:")
    yield
    _STORE.reset()


# ────────────────────────────────────────────────────────────
# AC-F3 / AC-F4: GET /api/me/onboarding
# ────────────────────────────────────────────────────────────

def test_get_onboarding_returns_default_state_for_new_user(client: TestClient) -> None:
    """AC-F3: GET /api/me/onboarding → 200 + default (welcome / not completed)."""
    r = client.get("/api/me/onboarding")
    assert r.status_code == 200
    body = r.json()
    assert body["current_step"] == "welcome"
    assert body["completed"] is False
    assert body["completed_steps"] == []
    assert body["skipped_steps"] == []
    assert "state" in body
    assert "steps" in body["state"]
    assert len(body["state"]["steps"]) == 3


def test_get_onboarding_unauthorized_returns_401(client: TestClient, monkeypatch) -> None:
    """AC-F4: DEV_BYPASS off + no token → 401."""
    from services import auth_middleware as am
    monkeypatch.setattr(am, "DEV_BYPASS", False)
    r = client.get("/api/me/onboarding")
    assert r.status_code == 401


# ────────────────────────────────────────────────────────────
# AC-F1 / AC-F6: POST /api/me/onboarding/advance
# ────────────────────────────────────────────────────────────

def test_advance_first_step_returns_next_step(client: TestClient) -> None:
    """AC-F1 / AC-F6: advance(welcome) → next_step=workspace_setup, completed=false."""
    r = client.post("/api/me/onboarding/advance", json={"step": "welcome", "payload": {}})
    assert r.status_code == 201
    body = r.json()
    assert body["next_step"] == "workspace_setup"
    assert body["completed"] is False
    assert body["current_step"] == "workspace_setup"


def test_advance_full_flow_completes_onboarding(client: TestClient) -> None:
    """AC-F1: 3 step 全完了で completed=true / completed_at が set される."""
    client.post("/api/me/onboarding/advance", json={"step": "welcome", "payload": {}})
    client.post("/api/me/onboarding/advance", json={"step": "workspace_setup", "payload": {"ws_id": 1}})
    r = client.post("/api/me/onboarding/advance", json={"step": "ai_employee_intro", "payload": {}})
    assert r.status_code == 201
    body = r.json()
    assert body["next_step"] is None
    assert body["completed"] is True

    # GET で確認
    g = client.get("/api/me/onboarding").json()
    assert g["completed"] is True
    assert g["completed_at"] is not None
    assert sorted(g["completed_steps"]) == sorted(["welcome", "workspace_setup", "ai_employee_intro"])


# ────────────────────────────────────────────────────────────
# AC-F5 / AC-F8: 422 invalid body
# ────────────────────────────────────────────────────────────

def test_advance_missing_step_returns_422(client: TestClient) -> None:
    """AC-F5 / AC-F8: body 必須 field 欠落 → Pydantic 422."""
    r = client.post("/api/me/onboarding/advance", json={"payload": {}})
    assert r.status_code == 422


def test_advance_unknown_step_returns_422(client: TestClient) -> None:
    """AC-F8 / svc UnknownStepError: STEP_IDS 外の step → 422."""
    r = client.post(
        "/api/me/onboarding/advance",
        json={"step": "non_existent_step", "payload": {}},
    )
    assert r.status_code == 422
    body = r.json()
    assert body["detail"]["code"] == "unknown_step"


# ────────────────────────────────────────────────────────────
# AC-F2 / AC-F9: skip
# ────────────────────────────────────────────────────────────

def test_skip_required_step_returns_409(client: TestClient) -> None:
    """AC-F2: required=True step (welcome) を skip → 409 + code=required_step_skip."""
    r = client.post("/api/me/onboarding/skip", json={"step": "welcome"})
    assert r.status_code == 409
    body = r.json()
    assert body["detail"]["code"] == "required_step_skip"


def test_skip_optional_step_succeeds(client: TestClient) -> None:
    """AC-F9: optional step (ai_employee_intro) を skip → 201 + skipped_at."""
    # 前提: welcome / workspace_setup を完了
    client.post("/api/me/onboarding/advance", json={"step": "welcome", "payload": {}})
    client.post("/api/me/onboarding/advance", json={"step": "workspace_setup", "payload": {}})

    r = client.post(
        "/api/me/onboarding/skip",
        json={"step": "ai_employee_intro", "reason": "user prefers to explore later"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["skipped_at"] is not None
    assert body["completed"] is True


# ────────────────────────────────────────────────────────────
# AC-F7 / AC-F10: 401 unauthorized
# ────────────────────────────────────────────────────────────

def test_advance_unauthorized_returns_401(client: TestClient, monkeypatch) -> None:
    """AC-F7: DEV_BYPASS off + no token → 401."""
    from services import auth_middleware as am
    monkeypatch.setattr(am, "DEV_BYPASS", False)
    r = client.post(
        "/api/me/onboarding/advance",
        json={"step": "welcome", "payload": {}},
    )
    assert r.status_code == 401


def test_skip_unauthorized_returns_401(client: TestClient, monkeypatch) -> None:
    """AC-F10: DEV_BYPASS off + no token → 401."""
    from services import auth_middleware as am
    monkeypatch.setattr(am, "DEV_BYPASS", False)
    r = client.post("/api/me/onboarding/skip", json={"step": "ai_employee_intro"})
    assert r.status_code == 401


# ────────────────────────────────────────────────────────────
# 追加 step-out-of-order 検証 (svc.StepOutOfOrderError → 409)
# ────────────────────────────────────────────────────────────

def test_advance_out_of_order_returns_409(client: TestClient) -> None:
    """先頭 step を完了せず後 step を advance → 409 step_out_of_order."""
    r = client.post(
        "/api/me/onboarding/advance",
        json={"step": "ai_employee_intro", "payload": {}},
    )
    assert r.status_code == 409
    body = r.json()
    assert body["detail"]["code"] == "step_out_of_order"


def test_advance_already_completed_step_returns_409(client: TestClient) -> None:
    """既完了 step を再度 advance → 409."""
    client.post("/api/me/onboarding/advance", json={"step": "welcome", "payload": {}})
    r = client.post("/api/me/onboarding/advance", json={"step": "welcome", "payload": {}})
    assert r.status_code == 409


# ────────────────────────────────────────────────────────────
# service 層 pure-unit
# ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_svc_get_state_default_for_unknown_user() -> None:
    from services import onboarding as svc

    state = await svc.get_state("non-existent-user-id-xyz")
    assert state["current_step"] == "welcome"
    assert state["completed"] is False
    assert state["completed_steps"] == []


@pytest.mark.asyncio
async def test_svc_advance_unknown_step_raises() -> None:
    from services import onboarding as svc

    with pytest.raises(svc.UnknownStepError):
        await svc.advance("u1", "bogus_step", {})


@pytest.mark.asyncio
async def test_svc_skip_required_step_raises() -> None:
    from services import onboarding as svc

    with pytest.raises(svc.RequiredStepSkipError):
        await svc.skip("u1", "welcome")


def test_svc_step_ids_constants() -> None:
    """service 層が公開する STEP_IDS / ONBOARDING_STEPS の整合性検証."""
    from services import onboarding as svc

    assert svc.STEP_IDS == ["welcome", "workspace_setup", "ai_employee_intro"]
    welcome = next(s for s in svc.ONBOARDING_STEPS if s["id"] == "welcome")
    assert welcome["required"] is True
    intro = next(s for s in svc.ONBOARDING_STEPS if s["id"] == "ai_employee_intro")
    assert intro["required"] is False
