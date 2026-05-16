"""T-V3-B-25 / F-018: Notifications backend tests (list + read + read-all).

3-tier AC mapping (functional only — backend-only task, structural is empty):
  AC-F1 STATE-DRIVEN  : While unread → included in unread_count
  AC-F2 EVENT-DRIVEN  : read-all (no category) → 全 unread を既読化
  AC-F3 EVENT-DRIVEN  : GET valid → 200 + items
  AC-F4 UNWANTED      : GET missing/invalid auth → 401
  AC-F5 UNWANTED      : GET invalid filter (bad type) → 422
  AC-F6 EVENT-DRIVEN  : POST /{id}/read valid → 200 + read_at
  AC-F7 UNWANTED      : POST /{id}/read missing auth → 401
  AC-F8 EVENT-DRIVEN  : POST /read-all valid → 200 + marked_count
  AC-F9 UNWANTED      : POST /read-all missing auth → 401

NOTE on auth: DEV_BYPASS=1 default → DEV_USER returned for missing creds.
401 path はテスト用に明示的に bypass を解除して assert する.
"""
from __future__ import annotations

import importlib
import os
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# ──────────────────────────────────────────────────────────────────────
# fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    os.environ.setdefault("BUILD_FACTORY_DEV_BYPASS_AUTH", "1")
    os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:54321")
    os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
    os.environ.setdefault(
        "SUPABASE_JWT_SECRET",
        "test-jwt-secret-must-be-at-least-32-chars-long",
    )
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def empty_rows():
    """list / count を空に固定する patch (graceful empty fallback と等価)."""
    with patch("services.notifications._safe_fetch_rows", return_value=[]):
        yield


@pytest.fixture()
def sample_rows():
    """list_notifications / count_unread に sample row を返させる patch.

    DEV_USER の sub = "00000000-0000-0000-0000-000000000001" に紐づく 3 件:
      - id=10 unread (event_type="pr.merged")
      - id=11 unread (event_type="task.assigned")
      - id=12 read   (event_type="pr.commented")
    """
    rows = [
        {
            "id": 10,
            "workspace_id": 1,
            "recipient_user_id": "00000000-0000-0000-0000-000000000001",
            "event_type": "pr.merged",
            "title": "PR #123 merged",
            "body": "review approved",
            "link_url": "/prs/123",
            "is_read": False,
            "priority": "normal",
            "detail": {"pr_id": 123},
            "created_at": "2026-05-16T12:00:00+00:00",
            "read_at": None,
        },
        {
            "id": 11,
            "workspace_id": 1,
            "recipient_user_id": "00000000-0000-0000-0000-000000000001",
            "event_type": "task.assigned",
            "title": "Task T-V3-B-25 assigned",
            "body": None,
            "link_url": None,
            "is_read": False,
            "priority": "high",
            "detail": {},
            "created_at": "2026-05-16T11:00:00+00:00",
            "read_at": None,
        },
        {
            "id": 12,
            "workspace_id": 1,
            "recipient_user_id": "00000000-0000-0000-0000-000000000001",
            "event_type": "pr.commented",
            "title": "PR #100 commented",
            "body": "looks good",
            "link_url": "/prs/100",
            "is_read": True,
            "priority": "low",
            "detail": {},
            "created_at": "2026-05-15T09:00:00+00:00",
            "read_at": "2026-05-15T10:00:00+00:00",
        },
    ]

    def fetch_side_effect(sql: str, params: list[Any]) -> list[dict[str, Any]]:
        if "COUNT(*)" in sql:
            # unread_only branch only (is_read = 0)
            if "is_read = 0" in sql:
                unread = [r for r in rows if not r["is_read"]]
                # category filter
                # params order: [recipient, (category like)?]
                if len(params) >= 2 and isinstance(params[1], str):
                    prefix = params[1].rstrip("%")
                    unread = [r for r in unread if r["event_type"].startswith(prefix)]
                return [{"cnt": len(unread)}]
            return [{"cnt": len(rows)}]
        # SELECT id ... — filter unread_only / category by SQL signature
        filtered = list(rows)
        if "is_read = 0" in sql:
            filtered = [r for r in filtered if not r["is_read"]]
        # event_type LIKE in params
        if any(isinstance(p, str) and p.endswith("%") for p in params):
            prefix = next(p for p in params if isinstance(p, str) and p.endswith("%"))[:-1]
            filtered = [r for r in filtered if r["event_type"].startswith(prefix)]
        return filtered

    with patch(
        "services.notifications._safe_fetch_rows",
        side_effect=fetch_side_effect,
    ):
        yield rows


@pytest.fixture()
def mutating_db():
    """mark_as_read / mark_all_as_read 用. _safe_execute は影響行数を返す."""
    with patch("services.notifications._safe_execute", return_value=1) as exec_mock, \
         patch("services.notifications._safe_fetch_rows", return_value=[{"1": 1}]):
        yield exec_mock


# ──────────────────────────────────────────────────────────────────────
# Service unit tests
# ──────────────────────────────────────────────────────────────────────


def test_service_normalize_filter_minimal():
    from services.notifications import normalize_filter
    f = normalize_filter(recipient_user_id="user-1")
    assert f.recipient_user_id == "user-1"
    assert f.unread_only is False
    assert f.category is None


def test_service_normalize_filter_full():
    from services.notifications import normalize_filter
    f = normalize_filter(
        recipient_user_id="user-1", unread_only=True, category="pr."
    )
    assert f.unread_only is True
    assert f.category == "pr."


def test_service_normalize_filter_empty_category_becomes_none():
    from services.notifications import normalize_filter
    f = normalize_filter(recipient_user_id="user-1", category="   ")
    assert f.category is None


def test_service_normalize_filter_invalid_recipient_raises():
    from services.notifications import NotificationFilterError, normalize_filter
    with pytest.raises(NotificationFilterError) as exc:
        normalize_filter(recipient_user_id="")
    assert exc.value.code == "notifications.invalid_filter"


def test_service_normalize_filter_category_too_long_raises():
    from services.notifications import NotificationFilterError, normalize_filter
    with pytest.raises(NotificationFilterError) as exc:
        normalize_filter(recipient_user_id="u-1", category="x" * 101)
    assert exc.value.code == "notifications.invalid_filter"


@pytest.mark.asyncio
async def test_service_list_notifications_empty_fallback():
    """graceful empty fallback: table 不存在 → 空 list."""
    from services.notifications import NormalizedFilter, list_notifications
    with patch("services.notifications._safe_fetch_rows", return_value=[]):
        rows = await list_notifications(NormalizedFilter(recipient_user_id="u-1"))
    assert rows == []


@pytest.mark.asyncio
async def test_service_count_unread_empty_fallback():
    from services.notifications import count_unread
    with patch("services.notifications._safe_fetch_rows", return_value=[]):
        cnt = await count_unread("u-1")
    assert cnt == 0


@pytest.mark.asyncio
async def test_service_mark_as_read_returns_iso():
    """正常系: mark_as_read は ISO-8601 string を返す."""
    from services.notifications import mark_as_read
    with patch("services.notifications._safe_execute", return_value=1):
        out = await mark_as_read(42, "u-1")
    assert out is not None
    assert "T" in out and "+00:00" in out


@pytest.mark.asyncio
async def test_service_mark_as_read_zero_affected_no_exists_returns_none():
    """affected=0 + row 不存在 → None (404 path)."""
    from services.notifications import mark_as_read
    with patch("services.notifications._safe_execute", return_value=0), \
         patch("services.notifications._safe_fetch_rows", return_value=[]):
        out = await mark_as_read(42, "u-1")
    assert out is None


@pytest.mark.asyncio
async def test_service_mark_as_read_invalid_id_raises():
    from services.notifications import NotificationFilterError, mark_as_read
    with pytest.raises(NotificationFilterError):
        await mark_as_read(0, "u-1")


@pytest.mark.asyncio
async def test_service_mark_all_as_read_zero_no_unread():
    from services.notifications import mark_all_as_read
    with patch("services.notifications._safe_execute", return_value=0):
        cnt = await mark_all_as_read("u-1")
    assert cnt == 0


@pytest.mark.asyncio
async def test_service_mark_all_as_read_count():
    from services.notifications import mark_all_as_read
    with patch("services.notifications._safe_execute", return_value=5):
        cnt = await mark_all_as_read("u-1", category="pr.")
    assert cnt == 5


@pytest.mark.asyncio
async def test_service_mark_all_as_read_invalid_recipient_raises():
    from services.notifications import NotificationFilterError, mark_all_as_read
    with pytest.raises(NotificationFilterError):
        await mark_all_as_read("")


# ──────────────────────────────────────────────────────────────────────
# Router: GET /api/notifications — AC-F1/F3/F4/F5
# ──────────────────────────────────────────────────────────────────────


def test_list_ac_f3_valid_returns_items(client, sample_rows):
    """AC-F3: valid → 200 + items (3 件)."""
    r = client.get("/api/notifications")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "items" in body
    assert "unread_count" in body
    assert isinstance(body["items"], list)
    assert len(body["items"]) == 3
    first = body["items"][0]
    assert {"id", "event_type", "title", "is_read"}.issubset(first.keys())


def test_list_ac_f3_empty_returns_200_empty(client, empty_rows):
    r = client.get("/api/notifications")
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["unread_count"] == 0


def test_list_ac_f1_unread_count_reflects_unread(client, sample_rows):
    """AC-F1: STATE-DRIVEN — unread のものは unread_count に含まれる.

    sample_rows: id=10/11 unread, id=12 read → unread_count = 2.
    """
    r = client.get("/api/notifications")
    assert r.status_code == 200
    body = r.json()
    assert body["unread_count"] == 2


def test_list_ac_f1_unread_only_filter(client, sample_rows):
    """unread_only=true → items に read を含めない."""
    r = client.get("/api/notifications?unread_only=true")
    assert r.status_code == 200
    body = r.json()
    # id=12 (is_read=True) は含まれない
    ids = {item["id"] for item in body["items"]}
    assert 12 not in ids
    assert {10, 11}.issubset(ids)


def test_list_category_filter(client, sample_rows):
    """category=pr. → event_type が "pr." で始まる行のみ."""
    r = client.get("/api/notifications?category=pr.")
    assert r.status_code == 200
    body = r.json()
    for item in body["items"]:
        assert item["event_type"].startswith("pr.")


def test_list_ac_f4_missing_auth_returns_401(client, empty_rows):
    """AC-F4: missing/invalid auth → 401."""
    with patch.dict(os.environ, {"BUILD_FACTORY_DEV_BYPASS_AUTH": "0"}):
        import services.auth_middleware as am
        importlib.reload(am)
        r = client.get("/api/notifications")
        assert r.status_code == 401, r.text
    os.environ["BUILD_FACTORY_DEV_BYPASS_AUTH"] = "1"
    import services.auth_middleware as am
    importlib.reload(am)


def test_list_ac_f5_invalid_unread_only_returns_422(client, empty_rows):
    """AC-F5: unread_only に bool として parseable でない値 → 422 (FastAPI built-in)."""
    r = client.get("/api/notifications?unread_only=not-a-bool")
    assert r.status_code == 422


def test_list_ac_f5_invalid_category_too_long_returns_422(client, empty_rows):
    """AC-F5: category が 100 chars 超 → 422 (NotificationFilterError)."""
    r = client.get(f"/api/notifications?category={'x' * 101}")
    assert r.status_code == 422
    body = r.json()
    # FastAPI built-in 422 か service-level 422 か.
    assert "detail" in body


# ──────────────────────────────────────────────────────────────────────
# Router: POST /api/notifications/{id}/read — AC-F6/F7
# ──────────────────────────────────────────────────────────────────────


def test_read_ac_f6_valid_returns_read_at(client, mutating_db):
    """AC-F6: valid → 200 + read_at (ISO string)."""
    r = client.post("/api/notifications/42/read")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "read_at" in body
    assert isinstance(body["read_at"], str)
    assert "T" in body["read_at"]


def test_read_ac_f7_missing_auth_returns_401(client):
    """AC-F7: missing auth → 401."""
    with patch.dict(os.environ, {"BUILD_FACTORY_DEV_BYPASS_AUTH": "0"}):
        import services.auth_middleware as am
        importlib.reload(am)
        r = client.post("/api/notifications/42/read")
        assert r.status_code == 401, r.text
    os.environ["BUILD_FACTORY_DEV_BYPASS_AUTH"] = "1"
    import services.auth_middleware as am
    importlib.reload(am)


def test_read_not_found_returns_404(client):
    """row 不存在 / 他人の row → 404."""
    with patch("services.notifications._safe_execute", return_value=0), \
         patch("services.notifications._safe_fetch_rows", return_value=[]):
        r = client.post("/api/notifications/999/read")
        assert r.status_code == 404
        body = r.json()
        assert body["detail"]["code"] == "notifications.not_found"


def test_read_invalid_id_returns_422(client):
    """id <= 0 → 422 (FastAPI path validation gt=0)."""
    r = client.post("/api/notifications/0/read")
    assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────
# Router: POST /api/notifications/read-all — AC-F2/F8/F9
# ──────────────────────────────────────────────────────────────────────


def test_read_all_ac_f8_valid_returns_marked_count(client):
    """AC-F8: valid → 200 + marked_count."""
    with patch("services.notifications._safe_execute", return_value=3):
        r = client.post("/api/notifications/read-all", json={})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["marked_count"] == 3


def test_read_all_ac_f2_no_category_marks_all_unread(client):
    """AC-F2: category 無し → 全 unread を既読化 (marked_count = unread 数)."""
    with patch("services.notifications._safe_execute", return_value=2) as exec_mock:
        r = client.post("/api/notifications/read-all", json={"category": None})
        assert r.status_code == 200
        body = r.json()
        assert body["marked_count"] == 2
        # SQL の WHERE に event_type LIKE が含まれないこと
        call_args = exec_mock.call_args
        sql_str = call_args[0][0]
        assert "event_type LIKE" not in sql_str


def test_read_all_with_category_filter_uses_like(client):
    """category 指定時は event_type LIKE 'pr.%' で絞り込む."""
    with patch("services.notifications._safe_execute", return_value=1) as exec_mock:
        r = client.post("/api/notifications/read-all", json={"category": "pr."})
        assert r.status_code == 200
        assert r.json()["marked_count"] == 1
        sql_str = exec_mock.call_args[0][0]
        params = exec_mock.call_args[0][1]
        assert "event_type LIKE" in sql_str
        assert "pr.%" in params


def test_read_all_ac_f9_missing_auth_returns_401(client):
    """AC-F9: missing auth → 401."""
    with patch.dict(os.environ, {"BUILD_FACTORY_DEV_BYPASS_AUTH": "0"}):
        import services.auth_middleware as am
        importlib.reload(am)
        r = client.post("/api/notifications/read-all", json={})
        assert r.status_code == 401, r.text
    os.environ["BUILD_FACTORY_DEV_BYPASS_AUTH"] = "1"
    import services.auth_middleware as am
    importlib.reload(am)


def test_read_all_empty_body_ok(client):
    """body 完全省略でも valid (Body(default=None))."""
    with patch("services.notifications._safe_execute", return_value=0):
        r = client.post("/api/notifications/read-all")
        assert r.status_code == 200
        assert r.json()["marked_count"] == 0


def test_read_all_zero_marked_returns_200(client):
    """unread が 0 件 → marked_count=0 + 200."""
    with patch("services.notifications._safe_execute", return_value=0):
        r = client.post("/api/notifications/read-all", json={})
        assert r.status_code == 200
        assert r.json()["marked_count"] == 0


# ──────────────────────────────────────────────────────────────────────
# Error contract shape (structured detail {code, message})
# ──────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    """4xx の detail が {code, message} 構造 (notifications.* contract)."""
    with patch("services.notifications._safe_execute", return_value=0), \
         patch("services.notifications._safe_fetch_rows", return_value=[]):
        r = client.post("/api/notifications/99999/read")
        assert r.status_code == 404
        body = r.json()
        assert isinstance(body["detail"], dict)
        assert isinstance(body["detail"]["code"], str)
        assert isinstance(body["detail"]["message"], str)


# ──────────────────────────────────────────────────────────────────────
# Schema imports + module surface
# ──────────────────────────────────────────────────────────────────────


def test_schemas_module_exports():
    from schemas.notifications import (
        Notification,
        NotificationFilter,
        NotificationListResponse,
        NotificationReadAllRequest,
        NotificationReadAllResponse,
        NotificationReadResponse,
    )
    # smoke: instantiate
    n = Notification(
        id=1,
        recipient_user_id="u-1",
        event_type="pr.merged",
        title="hello",
    )
    assert n.id == 1
    assert n.title == "hello"
    assert NotificationListResponse(items=[n], unread_count=1).unread_count == 1
    assert NotificationReadResponse(read_at="2026-05-16T00:00:00+00:00").read_at.startswith("2026")
    assert NotificationReadAllRequest(category="pr.").category == "pr."
    assert NotificationReadAllResponse(marked_count=5).marked_count == 5
    assert NotificationFilter(unread_only=True).unread_only is True


def test_service_module_exports():
    from services.notifications import (
        MAX_ROWS,
        NotificationFilterError,
        count_unread,
        list_notifications,
        mark_all_as_read,
        mark_as_read,
        normalize_filter,
    )
    assert MAX_ROWS == 1_000
    assert callable(count_unread)
    assert callable(list_notifications)
    assert callable(mark_all_as_read)
    assert callable(mark_as_read)
    assert callable(normalize_filter)
    assert NotificationFilterError is not None


def test_router_registered_in_main():
    """notifications_router が main.app に include されていること."""
    from main import app
    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    assert "/api/notifications" in paths
    assert "/api/notifications/{id}/read" in paths
    assert "/api/notifications/read-all" in paths
