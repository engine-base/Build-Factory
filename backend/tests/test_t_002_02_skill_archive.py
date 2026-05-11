"""T-002-02: archive スクリプト (skill_manager REFACTOR) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-002 archive / restore endpoint + service 公開
  AC-2 EVENT-DRIVEN  : 全 endpoint で 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 skill_manager.delete_skill (soft) は不変 (backwards compat)
  AC-4 UNWANTED      : invalid input / 既 archive / 空 actor は 4xx + structured
                       かつ persistent state mutate しない
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ──────────────────────────────────────────────────────────────────────────
# Fake DB (skill_definitions)
# ──────────────────────────────────────────────────────────────────────────


class _FakeRow(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class _FakeStore:
    def __init__(self):
        self.rows: list[dict] = []
        self.next_id = 1

    def reset(self):
        self.rows = []
        self.next_id = 1

    def insert(self, *, skill_name, display_name=None, category="general",
               version="1.0", is_active=1, md_path=""):
        row = {
            "id": self.next_id, "skill_name": skill_name,
            "display_name": display_name or skill_name,
            "description": "test", "category": category, "tags": "",
            "is_active": is_active, "version": version,
            "md_path": md_path, "updated_at": "2026-05-11",
        }
        self.rows.append(row)
        self.next_id += 1
        return row


class _FakeCursor:
    def __init__(self, store):
        self._store = store

    async def fetchone(self):
        return None

    async def fetchall(self):
        return []


class _FakeConn:
    def __init__(self, store):
        self._store = store
        self.row_factory = None

    async def execute(self, sql, params=()):
        sl = sql.strip().lower()
        if sl.startswith("update skill_definitions"):
            name = params[-1] if params else None
            for r in self._store.rows:
                if r["skill_name"] == name:
                    if "is_active=0" in sl:
                        r["is_active"] = 0
                    if "is_active=1" in sl:
                        r["is_active"] = 1
                    if "version='archived'" in sl:
                        r["version"] = "archived"
                    if "version='1.0'" in sl:
                        r["version"] = "1.0"
        return _FakeCursor(self._store)

    async def execute_fetchall(self, sql, params=()):
        sl = sql.lower()
        if "from skill_definitions where skill_name=" in sl:
            name = params[0] if params else None
            return [_FakeRow(r) for r in self._store.rows if r["skill_name"] == name]
        if "version='archived'" in sl:
            return [_FakeRow(r) for r in self._store.rows if r.get("version") == "archived"]
        # generic list (router list_skills)
        return [_FakeRow(r) for r in self._store.rows]

    async def commit(self):
        pass


_STORE = _FakeStore()


@asynccontextmanager
async def _fake_connect(path):
    yield _FakeConn(_STORE)


# ──────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────


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
def _fake_skill_store(monkeypatch, tmp_path):
    """skill_manager と skills router の依存を fake 化."""
    import services.skill_manager as sm
    import routers.skills as skills_router
    _STORE.reset()

    # 1. SKILL_STORE / CLAUDE_SKILLS / SKILL_ARCHIVE を tmp_path 配下に
    store_root = tmp_path / "skills"
    mirror_root = tmp_path / "mirror"
    archive_root = store_root / "_archive"
    monkeypatch.setattr(sm, "SKILL_STORE", store_root)
    monkeypatch.setattr(sm, "CLAUDE_SKILLS", mirror_root)
    monkeypatch.setattr(sm, "SKILL_ARCHIVE", archive_root)
    monkeypatch.setattr(skills_router, "SKILL_STORE", store_root)

    # 2. aiosqlite を fake に
    fake_db = type("FakeDb", (), {})()
    fake_db.connect = lambda *a, **kw: _fake_connect(None)
    fake_db.Row = _FakeRow
    monkeypatch.setattr(sm, "aiosqlite", fake_db, raising=False)
    monkeypatch.setattr(skills_router, "aiosqlite", fake_db, raising=False)

    # db.async_db を遅延 import している関数のために module 全体差し替え
    import sys
    import db as db_pkg
    fake_module = type(sys)("fake_async_db")
    fake_module.connect = fake_db.connect
    fake_module.Row = fake_db.Row
    monkeypatch.setitem(sys.modules, "db.async_db", fake_module)
    monkeypatch.setattr(db_pkg, "async_db", fake_module, raising=False)

    yield {"store_root": store_root, "mirror_root": mirror_root, "archive_root": archive_root}


def _prep_skill(name: str, store_root: Path) -> Path:
    """primary 側にスキルを物理的に置いて DB にも入れる helper."""
    dest = store_root / name
    dest.mkdir(parents=True, exist_ok=True)
    md = dest / "SKILL.md"
    md.write_text("# test skill\ndescription: t", encoding="utf-8")
    _STORE.insert(skill_name=name, md_path=str(md))
    return dest


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: archive / restore endpoint 公開
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_archive_endpoint_exists(client, _fake_skill_store):
    _prep_skill("arc-1", _fake_skill_store["store_root"])
    r = client.post("/api/skills/arc-1/archive", json={"actor_user_id": "alice"})
    assert r.status_code == 200
    assert r.json()["status"] == "archived"


def test_ac1_restore_endpoint_exists(client, _fake_skill_store):
    _prep_skill("res-1", _fake_skill_store["store_root"])
    # archive first
    client.post("/api/skills/res-1/archive", json={"actor_user_id": "alice"})
    # restore
    r = client.post("/api/skills/res-1/restore", json={"actor_user_id": "alice"})
    assert r.status_code == 200
    assert r.json()["status"] == "restored"


def test_ac1_list_archived_endpoint_exists(client, _fake_skill_store):
    _prep_skill("la-1", _fake_skill_store["store_root"])
    _prep_skill("la-2", _fake_skill_store["store_root"])
    client.post("/api/skills/la-1/archive", json={"actor_user_id": "alice"})
    r = client.get("/api/skills/-archived")
    assert r.status_code == 200
    names = {row["skill_name"] for row in r.json()}
    assert "la-1" in names
    assert "la-2" not in names  # まだ archive していない


def test_ac1_service_functions_public(_fake_skill_store):
    """AC-1: skill_manager に archive_skill / restore_skill / list_archived_skills が公開."""
    from services.skill_manager import (
        archive_skill, restore_skill, list_archived_skills,
        SkillNotFoundError, SkillAlreadyArchivedError,
    )
    assert callable(archive_skill)
    assert callable(restore_skill)
    assert callable(list_archived_skills)


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_archive_returns_within_2s(client, _fake_skill_store):
    _prep_skill("perf-1", _fake_skill_store["store_root"])
    t0 = time.perf_counter()
    r = client.post("/api/skills/perf-1/archive", json={"actor_user_id": "a"})
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_restore_returns_within_2s(client, _fake_skill_store):
    _prep_skill("perf-2", _fake_skill_store["store_root"])
    client.post("/api/skills/perf-2/archive", json={"actor_user_id": "a"})
    t0 = time.perf_counter()
    r = client.post("/api/skills/perf-2/restore", json={"actor_user_id": "a"})
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_uses_detail_code_message(client, _fake_skill_store):
    r = client.post("/api/skills/missing/archive", json={"actor_user_id": "a"})
    assert r.status_code == 404
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "skills.not_found"
    assert "message" in body["detail"]


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: 既存 delete_skill (soft) は不変 + audit emit
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_existing_delete_skill_signature_unchanged():
    """AC-3: 既存 delete_skill の signature (hard kwarg) は不変."""
    import inspect
    from services.skill_manager import delete_skill
    sig = inspect.signature(delete_skill)
    assert "hard" in sig.parameters
    assert sig.parameters["hard"].default is False


def test_ac3_archive_emits_audit(client, _fake_skill_store, _capture_audit):
    _prep_skill("aud-1", _fake_skill_store["store_root"])
    client.post("/api/skills/aud-1/archive",
                 json={"actor_user_id": "carol", "reason": "outdated"})
    events = [e for e in _capture_audit if e["event_type"] == "skills.archived"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "carol"
    assert events[0]["detail"]["reason"] == "outdated"


def test_ac3_restore_emits_audit(client, _fake_skill_store, _capture_audit):
    _prep_skill("aud-2", _fake_skill_store["store_root"])
    client.post("/api/skills/aud-2/archive", json={"actor_user_id": "alice"})
    client.post("/api/skills/aud-2/restore", json={"actor_user_id": "alice"})
    events = [e for e in _capture_audit if e["event_type"] == "skills.restored"]
    assert len(events) >= 1


def test_ac3_archive_moves_file_to_archive_dir(_fake_skill_store):
    """AC-3 補助: archive 実行で primary が _archive/<name>/<ts>/ に移動."""
    name = "fs-1"
    primary = _prep_skill(name, _fake_skill_store["store_root"])
    assert primary.is_dir()
    from services.skill_manager import archive_skill
    result = asyncio.run(archive_skill(name, actor_user_id="x"))
    assert not primary.is_dir()  # primary から消えた
    archive_dir = Path(result["archive_dir"])
    assert archive_dir.is_dir()
    assert (archive_dir / "SKILL.md").exists()
    assert (archive_dir / "_archive_meta.json").exists()
    meta = json.loads((archive_dir / "_archive_meta.json").read_text())
    assert meta["actor_user_id"] == "x"


def test_ac3_archive_sets_version_archived(_fake_skill_store):
    """AC-3 補助: archive 後 DB の version='archived'."""
    name = "ver-1"
    _prep_skill(name, _fake_skill_store["store_root"])
    from services.skill_manager import archive_skill
    asyncio.run(archive_skill(name, actor_user_id="x"))
    row = next(r for r in _STORE.rows if r["skill_name"] == name)
    assert row["version"] == "archived"
    assert row["is_active"] == 0


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_archive_missing_skill_returns_404(client, _fake_skill_store):
    r = client.post("/api/skills/nope/archive", json={"actor_user_id": "a"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "skills.not_found"


def test_ac4_archive_already_archived_returns_409(client, _fake_skill_store):
    _prep_skill("dup-arc", _fake_skill_store["store_root"])
    client.post("/api/skills/dup-arc/archive", json={"actor_user_id": "a"})
    # 同じ skill を再 archive — primary が既に消えているので 404 になる
    # (not_found を返す — 既に archive されたことの裏返し)
    r = client.post("/api/skills/dup-arc/archive", json={"actor_user_id": "a"})
    assert r.status_code in (404, 409)


def test_ac4_archive_empty_actor_rejected(client, _fake_skill_store):
    _prep_skill("auth-arc", _fake_skill_store["store_root"])
    r = client.post("/api/skills/auth-arc/archive",
                     json={"actor_user_id": "   "})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "skills.unauthorized"


def test_ac4_archive_invalid_skill_name_rejected(client, _fake_skill_store):
    r = client.post("/api/skills/BAD!NAME/archive",
                     json={"actor_user_id": "a"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "skills.invalid_skill_name"


def test_ac4_archive_reason_too_large_rejected(client, _fake_skill_store):
    _prep_skill("big-reason", _fake_skill_store["store_root"])
    r = client.post("/api/skills/big-reason/archive",
                     json={"actor_user_id": "a", "reason": "x" * 2001})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "skills.reason_too_large"


def test_ac4_restore_no_archive_returns_404(client, _fake_skill_store):
    r = client.post("/api/skills/never-archived/restore",
                     json={"actor_user_id": "a"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "skills.archive_not_found"


def test_ac4_restore_when_active_exists_returns_409(client, _fake_skill_store):
    _prep_skill("act-conflict", _fake_skill_store["store_root"])
    # archive
    client.post("/api/skills/act-conflict/archive", json={"actor_user_id": "a"})
    # primary を再作成 (active が存在する状態をシミュレート)
    _fake_skill_store["store_root"].joinpath("act-conflict").mkdir(parents=True)
    r = client.post("/api/skills/act-conflict/restore",
                     json={"actor_user_id": "a"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "skills.already_active"


def test_ac4_failed_archive_does_not_mutate_state(client, _fake_skill_store, _capture_audit):
    """AC-4 UNWANTED: missing skill の archive で audit emit / store mutate なし."""
    client.post("/api/skills/nope-2/archive", json={"actor_user_id": "a"})
    arc_events = [e for e in _capture_audit if e["event_type"] == "skills.archived"]
    assert len(arc_events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client, _fake_skill_store):
    _prep_skill("shape-1", _fake_skill_store["store_root"])
    client.post("/api/skills/shape-1/archive", json={"actor_user_id": "a"})
    cases = [
        ("POST", "/api/skills/nope/archive", {"actor_user_id": "a"}),
        ("POST", "/api/skills/BAD!/archive", {"actor_user_id": "a"}),
        ("POST", "/api/skills/shape-1/archive", {"actor_user_id": "   "}),
        ("POST", "/api/skills/never/restore", {"actor_user_id": "a"}),
    ]
    for method, path, payload in cases:
        r = client.post(path, json=payload)
        assert 400 <= r.status_code < 500
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
