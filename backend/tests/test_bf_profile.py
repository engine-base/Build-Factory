"""T-023-01: bf_profile の AC テスト.

AC reference: docs/task-decomposition/2026-05-09_v1/tickets.json T-023-01
  - UBIQUITOUS: 5 項目を編集できる
  - EVENT: PATCH で dirty fields を upsert + 成功 toast
  - STATE: dirty 時のみ save 有効
  - UNWANTED: 5xx 時 input を保持

backend 側で検証する具体的振る舞い:
  - invalid theme は 422 (UNWANTED)
  - upsert 成功時 audit_logs に profile.updated を emit
  - GET は default を返す (DB 不在ケース)
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from services.bf_profile import VALID_THEMES, upsert_profile


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


# ─────────────────────────────────────────────────────────
# AC: UBIQUITOUS — display_name / role_text / bio / theme / avatar_url
# ─────────────────────────────────────────────────────────
def test_valid_themes_set() -> None:
    assert VALID_THEMES == {"light", "dark", "system"}


def test_router_get_returns_default_for_unknown(client) -> None:
    r = client.get("/api/bf-profile", params={"user_id": "unknown_user_zzz"})
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == "unknown_user_zzz"
    assert body["theme"] == "light"  # default


def test_router_get_user_id_required(client) -> None:
    r = client.get("/api/bf-profile")
    assert r.status_code == 422  # missing required query param


# ─────────────────────────────────────────────────────────
# AC: EVENT-DRIVEN — PATCH で 5 fields すべてが upsert される
# ─────────────────────────────────────────────────────────
def test_router_patch_with_valid_data_returns_dict(client) -> None:
    r = client.patch(
        "/api/bf-profile",
        params={"user_id": "test_user_xyz"},
        json={"display_name": "Test User", "theme": "dark", "bio": "hello"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == "test_user_xyz"


def test_router_patch_all_five_fields(client) -> None:
    r = client.patch(
        "/api/bf-profile",
        params={"user_id": "test_user_full"},
        json={
            "display_name": "Full Name",
            "role_text": "Engineer",
            "bio": "Bio text",
            "theme": "system",
            "avatar_url": "https://example.com/a.png",
        },
    )
    assert r.status_code == 200


# ─────────────────────────────────────────────────────────
# AC: UNWANTED — invalid theme → 422
# ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_invalid_theme_raises_value_error() -> None:
    with pytest.raises(ValueError):
        await upsert_profile("u1", theme="rainbow")


def test_router_patch_invalid_theme_returns_422(client) -> None:
    r = client.patch(
        "/api/bf-profile",
        params={"user_id": "u1"},
        json={"theme": "rainbow"},
    )
    assert r.status_code == 422
    body = r.json()
    detail = body.get("detail")
    # FastAPI HTTPException(detail=dict) 形式
    assert isinstance(detail, dict)
    assert detail.get("code") == "invalid_theme"


# ─────────────────────────────────────────────────────────
# AC: EVENT — profile.updated event が audit_logs に流れる
# DB を mock して upsert を成功扱いにし、 emit_event が呼ばれることを確認。
# ─────────────────────────────────────────────────────────
class _FakeConn:
    async def execute(self, *a, **kw): return None
    async def commit(self): return None
    async def fetchone(self): return None
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return None


class _FakeDb:
    Row = dict
    def connect(self, _path):
        return _FakeConn()


@pytest.mark.asyncio
async def test_upsert_emits_audit_event(monkeypatch) -> None:
    events: list[tuple] = []

    async def fake_emit(event_type: str, **kw) -> int:
        events.append((event_type, kw))
        return 1

    monkeypatch.setattr("services.bf_profile._db", lambda: _FakeDb())
    monkeypatch.setattr("services.memory_service.emit_event", fake_emit)

    # upsert: DB は mock、 get_profile は None を返すので default 値で構成される
    await upsert_profile("test_audit_user", display_name="X", theme="light")

    assert any(e[0] == "profile.updated" for e in events), (
        f"profile.updated audit event not emitted: {events}"
    )
    detail = next(e[1] for e in events if e[0] == "profile.updated")
    assert "test_audit_user" == detail.get("user_id")
    assert set(detail["detail"]["changed_fields"]) == {"display_name", "theme"}
