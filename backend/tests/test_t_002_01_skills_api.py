"""T-002-01: スキル管理 UI (existing skills.py REFACTOR) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-002 のスキル管理 API (list/get/create/update/delete/run)
  AC-2 EVENT-DRIVEN  : UI 操作 → backend state 反映 + 後続 GET で観測可能
  AC-3 STATE-DRIVEN  : 既存 API contract / route prefix / response shape 不変
  AC-4 UNWANTED      : invalid input / unknown skill / 空 actor は 4xx +
                       {detail:{code,message}} かつ persistent state mutate しない
"""
from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


# ──────────────────────────────────────────────────────────────────────────
# In-memory fake DB (skill_definitions row store)
# ──────────────────────────────────────────────────────────────────────────


class _FakeRow(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class _FakeCursor:
    def __init__(self, store: "_FakeStore"):
        self._store = store
        self._last_row: dict | None = None

    async def fetchone(self):
        return self._last_row

    async def fetchall(self):
        return []


class _FakeConn:
    def __init__(self, store: "_FakeStore"):
        self._store = store
        self.row_factory = None

    async def execute(self, sql: str, params=()):
        sql_l = sql.strip().lower()
        if sql_l.startswith("insert into skill_definitions"):
            self._store.insert(params)
            cur = _FakeCursor(self._store)
            cur._last_row = _FakeRow(id=self._store.last_id())
            return cur
        if sql_l.startswith("update skill_definitions"):
            self._store.update(sql, params)
        return _FakeCursor(self._store)

    async def execute_fetchall(self, sql: str, params=()):
        return [_FakeRow(r) for r in self._store.query(sql, params)]

    async def commit(self):
        pass


class _FakeStore:
    def __init__(self):
        self.rows: list[dict] = []
        self.next_id = 1

    def reset(self):
        self.rows = []
        self.next_id = 1

    def insert(self, params):
        skill_name, display_name, description, category, tags, md_path = params
        if any(r["skill_name"] == skill_name for r in self.rows):
            raise Exception("UNIQUE constraint failed")
        row = {
            "id": self.next_id,
            "skill_name": skill_name,
            "display_name": display_name,
            "description": description,
            "category": category,
            "tags": tags,
            "md_path": md_path,
            "is_active": 1,
            "version": "1.0",
            "updated_at": "2026-05-11",
        }
        self.rows.append(row)
        self.next_id += 1

    def last_id(self):
        return self.next_id - 1

    def update(self, sql, params):
        # WHERE skill_name = ? の last param
        name = params[-1] if params else None
        for r in self.rows:
            if r["skill_name"] == name:
                if "is_active=0" in sql:
                    r["is_active"] = 0
                # 他 fields はそのまま (test では behavior 観測で十分)

    def query(self, sql, params):
        sql_l = sql.lower()
        if "from skill_definitions where skill_name=" in sql_l:
            name = params[0] if params else None
            return [r for r in self.rows if r["skill_name"] == name]
        if "group by category" in sql_l:
            cats: dict[str, int] = {}
            for r in self.rows:
                if r["is_active"]:
                    cats[r["category"]] = cats.get(r["category"], 0) + 1
            return [{"category": c, "count": n} for c, n in cats.items()]
        # list_skills
        rows = list(self.rows)
        return rows


_STORE = _FakeStore()


@asynccontextmanager
async def _fake_connect(path):
    yield _FakeConn(_STORE)


def _fake_row_factory(*args, **kwargs):
    return _FakeRow


# ──────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _fake_db(monkeypatch, tmp_path):
    """skills.py の aiosqlite.connect / SKILL_STORE を fake に置換."""
    import routers.skills as skills_mod
    _STORE.reset()

    fake_db = type("FakeDb", (), {})()
    fake_db.connect = lambda *a, **kw: _fake_connect(None)
    fake_db.Row = _fake_row_factory
    monkeypatch.setattr(skills_mod, "aiosqlite", fake_db)
    monkeypatch.setattr(skills_mod, "SKILL_STORE", tmp_path / "skills")
    yield


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
# AC-1 UBIQUITOUS: list / get / create / update / delete endpoint 公開
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_list_skills_endpoint_exists(client):
    r = client.get("/api/skills")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_ac1_categories_endpoint_exists(client):
    r = client.get("/api/skills/categories")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_ac1_create_skill_endpoint_exists(client):
    r = client.post(
        "/api/skills",
        json={"skill_name": "test-skill", "content": "# Test skill\ndescription: テスト用"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["skill_name"] == "test-skill"
    assert "id" in body


def test_ac1_get_skill_endpoint_exists(client):
    client.post("/api/skills", json={"skill_name": "get-skill", "content": "# get"})
    r = client.get("/api/skills/get-skill")
    assert r.status_code == 200
    assert r.json()["skill_name"] == "get-skill"


def test_ac1_update_skill_endpoint_exists(client):
    client.post("/api/skills", json={"skill_name": "upd-skill", "content": "# initial"})
    r = client.patch("/api/skills/upd-skill", json={"display_name": "Updated"})
    assert r.status_code == 200
    assert r.json()["status"] == "updated"


def test_ac1_delete_skill_endpoint_exists(client):
    client.post("/api/skills", json={"skill_name": "del-skill", "content": "# del"})
    r = client.delete("/api/skills/del-skill")
    assert r.status_code == 200
    assert r.json()["status"] == "deactivated"


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: UI 操作 → backend state 反映
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_create_then_get_reflects_state(client):
    """AC-2: POST 後に GET すると同じ skill が観測できる."""
    client.post(
        "/api/skills",
        json={"skill_name": "flow-skill", "display_name": "Flow",
              "content": "# Flow\n", "actor_user_id": "alice"},
    )
    r = client.get("/api/skills/flow-skill")
    assert r.status_code == 200
    assert r.json()["display_name"] == "Flow"


def test_ac2_delete_then_categories_excludes(client):
    """AC-2: delete (deactivate) 後 categories から消える."""
    client.post("/api/skills", json={"skill_name": "cat-x", "category": "x-cat", "content": "# x"})
    r1 = client.get("/api/skills/categories")
    assert any(c["category"] == "x-cat" for c in r1.json())
    client.delete("/api/skills/cat-x")
    r2 = client.get("/api/skills/categories")
    assert not any(c["category"] == "x-cat" for c in r2.json())


def test_ac2_responses_within_2s(client):
    """AC-2: 主要 endpoint は 2 秒以内."""
    t0 = time.perf_counter()
    client.get("/api/skills")
    client.post("/api/skills", json={"skill_name": "perf-skill", "content": "# perf"})
    client.get("/api/skills/perf-skill")
    client.patch("/api/skills/perf-skill", json={"category": "test"})
    client.delete("/api/skills/perf-skill")
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: 既存 API contract 不変 (backwards compat)
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_route_prefix_unchanged(client):
    """AC-3: route prefix は /api/skills のまま."""
    from routers.skills import router
    assert router.prefix == "/api/skills"


def test_ac3_create_request_schema_backwards_compat(client):
    """AC-3: 既存 SkillCreate field は変更されていない (actor_user_id は optional 追加のみ)."""
    from routers.skills import SkillCreate
    fields = SkillCreate.model_fields
    expected = {"skill_name", "display_name", "description", "category", "tags", "content"}
    assert expected <= set(fields.keys())  # 旧 field 全件保持
    # 旧 caller (actor_user_id 無し) でも作れる
    r = client.post(
        "/api/skills",
        json={"skill_name": "compat-1", "content": "# compat"},
    )
    assert r.status_code == 200


def test_ac3_list_response_shape_unchanged(client):
    """AC-3: list_skills は list[dict] (既存 contract)."""
    client.post("/api/skills", json={"skill_name": "shape-1", "content": "# c"})
    r = client.get("/api/skills")
    assert isinstance(r.json(), list)
    if r.json():
        assert isinstance(r.json()[0], dict)


def test_ac3_audit_emitted_on_create(client, _capture_audit):
    """AC-3 + 監査: created event を emit."""
    client.post(
        "/api/skills",
        json={"skill_name": "aud-1", "content": "# c", "actor_user_id": "alice"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "skills.created"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "alice"


def test_ac3_audit_emitted_on_update(client, _capture_audit):
    client.post("/api/skills", json={"skill_name": "aud-u", "content": "# c"})
    client.patch(
        "/api/skills/aud-u",
        json={"display_name": "Updated", "actor_user_id": "bob"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "skills.updated"]
    assert len(events) >= 1


def test_ac3_audit_emitted_on_delete(client, _capture_audit):
    client.post("/api/skills", json={"skill_name": "aud-d", "content": "# c"})
    client.delete("/api/skills/aud-d?actor_user_id=carol")
    events = [e for e in _capture_audit if e["event_type"] == "skills.deactivated"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "carol"


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + {detail:{code,message}} + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_invalid_skill_name_format_rejected(client):
    """AC-4: skill_name 形式違反は 400 invalid_skill_name."""
    r = client.post(
        "/api/skills",
        json={"skill_name": "Invalid Skill Name!", "content": "# x"},
    )
    # whitespace は - に変換されるが ! は不正
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "skills.invalid_skill_name"


def test_ac4_empty_content_rejected(client):
    r = client.post("/api/skills", json={"skill_name": "empty-c", "content": ""})
    assert r.status_code in (400, 422)


def test_ac4_blank_content_rejected(client):
    r = client.post("/api/skills", json={"skill_name": "blank-c", "content": "   \n"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "skills.invalid_content"


def test_ac4_content_too_large_rejected(client):
    """AC-4: 1MB 超過は 400."""
    big = "a" * 1_000_001
    r = client.post("/api/skills", json={"skill_name": "big-c", "content": big})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "skills.content_too_large"


def test_ac4_empty_actor_rejected(client):
    """AC-4: 空 actor は 401 unauthorized."""
    r = client.post(
        "/api/skills",
        json={"skill_name": "auth-1", "content": "# c", "actor_user_id": "   "},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "skills.unauthorized"


def test_ac4_get_unknown_skill_returns_404(client):
    r = client.get("/api/skills/nonexistent-skill")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "skills.not_found"


def test_ac4_update_unknown_skill_returns_404(client):
    r = client.patch("/api/skills/nope-skill", json={"display_name": "x"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "skills.not_found"


def test_ac4_delete_unknown_skill_returns_404(client):
    r = client.delete("/api/skills/nope-skill")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "skills.not_found"


def test_ac4_duplicate_create_returns_409(client):
    """AC-4: 既存 skill_name の作成は 409 already_exists."""
    client.post("/api/skills", json={"skill_name": "dup-1", "content": "# c"})
    r = client.post("/api/skills", json={"skill_name": "dup-1", "content": "# c2"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "skills.already_exists"


def test_ac4_invalid_limit_rejected(client):
    r = client.get("/api/skills?limit=0")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "skills.invalid_limit"


def test_ac4_run_empty_input_rejected(client):
    r = client.post("/api/skills/some-skill/run", json={"input": ""})
    # name validation は通る (some-skill is valid)、 input が空で reject
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "skills.invalid_input"


def test_ac4_rejected_create_does_not_mutate(client, _capture_audit):
    """AC-4 UNWANTED: rejected create は store mutate しない + audit emit なし."""
    before = len(_STORE.rows)
    client.post("/api/skills", json={"skill_name": "Invalid !", "content": "# x"})
    client.post("/api/skills", json={"skill_name": "ok-1", "content": "   "})
    after = len(_STORE.rows)
    assert after == before
    events = [e for e in _capture_audit if e["event_type"] == "skills.created"]
    assert len(events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    cases = [
        ("POST", "/api/skills", {"skill_name": "BAD!", "content": "# x"}),
        ("POST", "/api/skills", {"skill_name": "ok", "content": "   "}),
        ("POST", "/api/skills", {"skill_name": "ok", "content": "# x", "actor_user_id": "  "}),
        ("GET", "/api/skills/nope", None),
        ("PATCH", "/api/skills/nope", {}),
        ("DELETE", "/api/skills/nope", None),
        ("GET", "/api/skills?limit=0", None),
    ]
    for method, path, payload in cases:
        if method == "GET":
            r = client.get(path)
        elif method == "DELETE":
            r = client.delete(path)
        elif method == "PATCH":
            r = client.patch(path, json=payload)
        else:
            r = client.post(path, json=payload)
        assert 400 <= r.status_code < 500, f"{method} {path}: {r.status_code}"
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
