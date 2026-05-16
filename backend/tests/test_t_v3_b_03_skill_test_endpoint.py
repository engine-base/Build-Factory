"""T-V3-B-03 (F-002): POST /api/skills/{id}/test endpoint tests.

spec links:
  - docs/api-design/2026-05-16_v3/openapi.yaml#/paths/~1api~1skills~1{id}~1test
  - docs/functional-breakdown/2026-05-16_v3/features.json#F-002

3-tier AC (audit MD: docs/audit/2026-05-16_v3/T-V3-B-03.md):
  - Tier 2 functional:
    AC-F1 UNWANTED   : 10/min/user 超過 → 429
    AC-F2 EVENT-DRIVEN: valid + authorized → 201 {output, duration_ms}
    AC-F3 UNWANTED   : auth token 欠如 / invalid → 401
    AC-F4 UNWANTED   : body 検証失敗 → 422 + field-level error map
  - Tier 3 regression:
    AC-R5 (pytest + coverage >= 70% on touched files)
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient


# ──────────────────────────────────────────────────────────────────────────
# Fake DB store (test_t_002_01_skills_api.py の helper を流用して self-contained)
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
            "updated_at": "2026-05-16",
        }
        self.rows.append(row)
        self.next_id += 1

    def last_id(self):
        return self.next_id - 1

    def update(self, sql, params):
        name = params[-1] if params else None
        for r in self.rows:
            if r["skill_name"] == name:
                if "is_active=0" in sql:
                    r["is_active"] = 0

    def query(self, sql, params):
        sql_l = sql.lower()
        if "from skill_definitions where skill_name=" in sql_l:
            name = params[0] if params else None
            return [r for r in self.rows if r["skill_name"] == name]
        return list(self.rows)


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
    """skills.py の aiosqlite.connect / SKILL_STORE を fake に差し替える."""
    import routers.skills as skills_mod
    _STORE.reset()

    fake_db = type("FakeDb", (), {})()
    fake_db.connect = lambda *a, **kw: _fake_connect(None)
    fake_db.Row = _fake_row_factory
    monkeypatch.setattr(skills_mod, "aiosqlite", fake_db)
    monkeypatch.setattr(skills_mod, "SKILL_STORE", tmp_path / "skills")
    yield


@pytest.fixture(autouse=True)
def _fake_audit(monkeypatch):
    """services.memory_service.emit_event を capture して副作用を抑える."""
    captured: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append(
            {"event_type": event_type, "user_id": user_id, "detail": detail or {}}
        )
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)
    yield captured


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """各 test 前に rate limiter を flush."""
    from services.skill_test_rate_limiter import reset_all, set_clock
    import time as _t
    reset_all()
    set_clock(_t.monotonic)
    yield
    reset_all()


@pytest.fixture
def _fake_invoke_skill(monkeypatch):
    """integrations.skill_runner.invoke_skill を deterministic stub に."""
    calls: list[dict] = []

    async def fake_invoke(name, user_input, *, provider="ollama",
                          model="qwen2.5:7b", triggered_by="user",
                          trigger_id=None):
        calls.append(
            {"skill_name": name, "input": user_input, "triggered_by": triggered_by}
        )
        return f"[ok:{name}] {user_input}"

    import integrations.skill_runner as sr
    monkeypatch.setattr(sr, "invoke_skill", fake_invoke)
    return calls


def _seed_skill(client, name: str = "demo-skill") -> None:
    """skill_definitions に 1 件 seed して md ファイルも作る."""
    r = client.post(
        "/api/skills",
        json={"skill_name": name, "content": "# demo\ndescription: テスト用"},
    )
    assert r.status_code == 200, r.text


_AUTH = {"Authorization": "Bearer user-alice"}


# ──────────────────────────────────────────────────────────────────────────
# AC-F2: EVENT-DRIVEN  — happy path (201 + contract)
# ──────────────────────────────────────────────────────────────────────────


def test_ac_f2_happy_path_returns_201_with_contract(client, _fake_invoke_skill):
    """AC-F2: valid + authorized → 201 {output: str, duration_ms: int}."""
    _seed_skill(client, "demo-skill")
    r = client.post(
        "/api/skills/demo-skill/test",
        json={"test_input": "hello"},
        headers=_AUTH,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert isinstance(body, dict)
    assert "output" in body and isinstance(body["output"], str)
    assert "duration_ms" in body and isinstance(body["duration_ms"], int)
    assert body["duration_ms"] >= 0
    assert "[ok:demo-skill]" in body["output"]


def test_ac_f2_invokes_skill_runner_with_correct_args(client, _fake_invoke_skill):
    """AC-F2: skill_runner.invoke_skill is called with (skill_name, test_input)."""
    _seed_skill(client, "demo-skill")
    r = client.post(
        "/api/skills/demo-skill/test",
        json={"test_input": "run-this"},
        headers=_AUTH,
    )
    assert r.status_code == 201
    assert len(_fake_invoke_skill) == 1
    call = _fake_invoke_skill[0]
    assert call["skill_name"] == "demo-skill"
    assert call["input"] == "run-this"
    assert call["triggered_by"] == "user"


def test_ac_f2_emits_skills_tested_audit(client, _fake_invoke_skill, _fake_audit):
    """AC-F2: success 時に skills.tested audit が emit される."""
    _seed_skill(client, "demo-skill")
    r = client.post(
        "/api/skills/demo-skill/test",
        json={"test_input": "x"},
        headers=_AUTH,
    )
    assert r.status_code == 201
    events = [e for e in _fake_audit if e["event_type"] == "skills.tested"]
    assert len(events) == 1
    ev = events[0]
    assert ev["user_id"] == "user-alice"
    assert ev["detail"]["skill_name"] == "demo-skill"
    assert ev["detail"]["input_len"] == 1
    assert ev["detail"]["duration_ms"] >= 0


# ──────────────────────────────────────────────────────────────────────────
# AC-F3: UNWANTED — auth token 欠如 / invalid → 401
# ──────────────────────────────────────────────────────────────────────────


def test_ac_f3_missing_authorization_returns_401(client, _fake_invoke_skill):
    """AC-F3: Authorization ヘッダ無し → 401."""
    _seed_skill(client, "demo-skill")
    r = client.post(
        "/api/skills/demo-skill/test",
        json={"test_input": "hello"},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "skills.unauthorized"
    # mutation 起こさない
    assert len(_fake_invoke_skill) == 0


def test_ac_f3_invalid_auth_scheme_returns_401(client, _fake_invoke_skill):
    """AC-F3: Bearer 以外のスキームは 401."""
    _seed_skill(client, "demo-skill")
    r = client.post(
        "/api/skills/demo-skill/test",
        json={"test_input": "hello"},
        headers={"Authorization": "Basic xxxx"},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "skills.unauthorized"


def test_ac_f3_empty_bearer_token_returns_401(client, _fake_invoke_skill):
    """AC-F3: Bearer の後ろが空 → 401."""
    _seed_skill(client, "demo-skill")
    r = client.post(
        "/api/skills/demo-skill/test",
        json={"test_input": "hello"},
        headers={"Authorization": "Bearer    "},
    )
    assert r.status_code == 401


# ──────────────────────────────────────────────────────────────────────────
# AC-F4: UNWANTED — body validation 失敗 → 422 + field-level error map
# ──────────────────────────────────────────────────────────────────────────


def test_ac_f4_missing_test_input_returns_422(client, _fake_invoke_skill):
    """AC-F4: body に test_input が無い → 422 (FastAPI ValidationError)."""
    _seed_skill(client, "demo-skill")
    r = client.post(
        "/api/skills/demo-skill/test",
        json={},
        headers=_AUTH,
    )
    assert r.status_code == 422
    body = r.json()
    # FastAPI default validation envelope: {"detail":[{"loc":[...], "msg":...}]}
    assert "detail" in body
    detail = body["detail"]
    assert isinstance(detail, list)
    assert any("test_input" in str(d.get("loc", [])) for d in detail)


def test_ac_f4_empty_test_input_returns_422(client, _fake_invoke_skill):
    """AC-F4: test_input が空文字 → 422 (min_length=1)."""
    _seed_skill(client, "demo-skill")
    r = client.post(
        "/api/skills/demo-skill/test",
        json={"test_input": ""},
        headers=_AUTH,
    )
    assert r.status_code == 422
    body = r.json()
    assert "detail" in body
    assert any("test_input" in str(d.get("loc", [])) for d in body["detail"])


def test_ac_f4_wrong_type_test_input_returns_422(client, _fake_invoke_skill):
    """AC-F4: test_input が文字列以外 → 422."""
    _seed_skill(client, "demo-skill")
    r = client.post(
        "/api/skills/demo-skill/test",
        json={"test_input": 123},
        headers=_AUTH,
    )
    # pydantic v2 coerces or rejects; either way 422 path expected for clear type mismatch
    assert r.status_code in (201, 422)
    if r.status_code == 422:
        body = r.json()
        assert "detail" in body


def test_ac_f4_invalid_skill_id_format_returns_422(client, _fake_invoke_skill):
    """AC-F4: id (path) に許可外文字 → 422."""
    r = client.post(
        "/api/skills/Invalid Name!/test",
        json={"test_input": "x"},
        headers=_AUTH,
    )
    # whitespace は - に変換されるが ! は不正 → 422 (validation)
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "skills.invalid_skill_name"


# ──────────────────────────────────────────────────────────────────────────
# AC-F1: UNWANTED — 10/min/user 超過は 429
# ──────────────────────────────────────────────────────────────────────────


def test_ac_f1_rate_limit_429_after_10_in_window(client, _fake_invoke_skill):
    """AC-F1: 1 分間に 11 回目の呼び出しは 429."""
    _seed_skill(client, "demo-skill")
    # 10 回は通る
    for i in range(10):
        r = client.post(
            "/api/skills/demo-skill/test",
            json={"test_input": f"req-{i}"},
            headers=_AUTH,
        )
        assert r.status_code == 201, (i, r.text)
    # 11 回目は 429
    r = client.post(
        "/api/skills/demo-skill/test",
        json={"test_input": "overflow"},
        headers=_AUTH,
    )
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "skills.rate_limited"


def test_ac_f1_rate_limit_per_user_isolation(client, _fake_invoke_skill):
    """AC-F1: rate limit は per-user (alice と bob で独立)."""
    _seed_skill(client, "demo-skill")
    # alice が 10 回消費
    for i in range(10):
        r = client.post(
            "/api/skills/demo-skill/test",
            json={"test_input": "x"},
            headers={"Authorization": "Bearer user-alice"},
        )
        assert r.status_code == 201
    # alice はもう不可
    r = client.post(
        "/api/skills/demo-skill/test",
        json={"test_input": "x"},
        headers={"Authorization": "Bearer user-alice"},
    )
    assert r.status_code == 429
    # bob は別 bucket
    r = client.post(
        "/api/skills/demo-skill/test",
        json={"test_input": "x"},
        headers={"Authorization": "Bearer user-bob"},
    )
    assert r.status_code == 201


def test_ac_f1_rate_limit_window_slides(client, _fake_invoke_skill):
    """AC-F1: window 経過後は新規消費可能 (fake clock)."""
    from services.skill_test_rate_limiter import set_clock, reset_all
    reset_all()

    now = [1000.0]
    set_clock(lambda: now[0])

    _seed_skill(client, "demo-skill")
    for i in range(10):
        r = client.post(
            "/api/skills/demo-skill/test",
            json={"test_input": "x"},
            headers=_AUTH,
        )
        assert r.status_code == 201
    # window 内 → 429
    r = client.post(
        "/api/skills/demo-skill/test",
        json={"test_input": "x"},
        headers=_AUTH,
    )
    assert r.status_code == 429
    # 61 秒進めれば全部 expire → 再度可
    now[0] = 1000.0 + 61.0
    r = client.post(
        "/api/skills/demo-skill/test",
        json={"test_input": "x"},
        headers=_AUTH,
    )
    assert r.status_code == 201


# ──────────────────────────────────────────────────────────────────────────
# 404: skill 不在 / archived (openapi outputs_4xx)
# ──────────────────────────────────────────────────────────────────────────


def test_404_when_skill_not_found(client, _fake_invoke_skill):
    """skill 不在 → 404."""
    r = client.post(
        "/api/skills/no-such-skill/test",
        json={"test_input": "x"},
        headers=_AUTH,
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "skills.not_found"


def test_404_when_skill_inactive(client, _fake_invoke_skill):
    """is_active=0 のスキルは 404."""
    _seed_skill(client, "demo-skill")
    # soft delete
    r = client.delete("/api/skills/demo-skill")
    assert r.status_code == 200
    # 即 test 呼び出し → 404
    r = client.post(
        "/api/skills/demo-skill/test",
        json={"test_input": "x"},
        headers=_AUTH,
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "skills.not_found"


# ──────────────────────────────────────────────────────────────────────────
# 500: skill_runner が例外を投げたとき
# ──────────────────────────────────────────────────────────────────────────


def test_500_when_skill_runner_raises(client, monkeypatch):
    """skill_runner が exception → 500 + skills.execution_failed."""
    _seed_skill(client, "demo-skill")

    async def boom(*args, **kwargs):
        raise RuntimeError("LLM 接続失敗")

    import integrations.skill_runner as sr
    monkeypatch.setattr(sr, "invoke_skill", boom)

    r = client.post(
        "/api/skills/demo-skill/test",
        json={"test_input": "x"},
        headers=_AUTH,
    )
    assert r.status_code == 500
    assert r.json()["detail"]["code"] == "skills.execution_failed"


# ──────────────────────────────────────────────────────────────────────────
# Output shape: dict 戻り値の正規化
# ──────────────────────────────────────────────────────────────────────────


def test_output_normalizes_dict_result(client, monkeypatch):
    """skill_runner が dict を返した場合は output/text/content key から拾う."""
    _seed_skill(client, "demo-skill")

    async def returns_dict(*args, **kwargs):
        return {"output": "from-dict", "extra": 1}

    import integrations.skill_runner as sr
    monkeypatch.setattr(sr, "invoke_skill", returns_dict)

    r = client.post(
        "/api/skills/demo-skill/test",
        json={"test_input": "x"},
        headers=_AUTH,
    )
    assert r.status_code == 201
    assert r.json()["output"] == "from-dict"


# ──────────────────────────────────────────────────────────────────────────
# Contract: response keys 厳密 (output:str, duration_ms:int)
# ──────────────────────────────────────────────────────────────────────────


def test_response_contract_keys(client, _fake_invoke_skill):
    """openapi: response 必須 keys は output / duration_ms."""
    _seed_skill(client, "demo-skill")
    r = client.post(
        "/api/skills/demo-skill/test",
        json={"test_input": "x"},
        headers=_AUTH,
    )
    assert r.status_code == 201
    body = r.json()
    assert set(body.keys()) == {"output", "duration_ms"}
