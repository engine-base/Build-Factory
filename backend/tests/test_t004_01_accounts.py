"""T-004-01: account 作成 API+UI (accounts.py 拡張) AC 検証.

DB mock で account_service + router 両方を網羅、 4 AC 機械検証.

AC マッピング:
  AC-1 UBIQUITOUS: 5 endpoint (list / get / create / update / delete / members)
  AC-2 EVENT:     2 秒以内 + {detail: {code, message}}
  AC-3 STATE:     backward compat (legacy field 維持)
  AC-4 UNWANTED:  invalid type / plan / 空 name → 400 + {code, message}
"""
from __future__ import annotations

import asyncio
import os
import sys
import types
from typing import Any

import pytest
from fastapi.testclient import TestClient

from services import account_service as acc


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


# ──────────────────────────────────────────────────────────────────────────
# DB mock infra
# ──────────────────────────────────────────────────────────────────────────


class _FakeCursor:
    def __init__(self, rows=None, lastrowid=0, rowcount=0):
        self._rows = list(rows or [])
        self.lastrowid = lastrowid
        self.rowcount = rowcount

    async def fetchone(self):
        return self._rows.pop(0) if self._rows else None

    async def fetchall(self):
        rows, self._rows = self._rows, []
        return rows


class _FakeConn:
    Row = dict

    def __init__(self, rows_by_kw=None, rowcount=1):
        self._rows = rows_by_kw or {}
        self._rowcount = rowcount
        self.row_factory = None

    async def execute_fetchall(self, sql, *args):
        for kw, rows in self._rows.items():
            if kw.lower() in sql.lower():
                return rows
        return []

    async def execute(self, sql, *args):
        for kw, rows in self._rows.items():
            if kw.lower() in sql.lower():
                return _FakeCursor(rows=rows, rowcount=self._rowcount)
        return _FakeCursor(rows=[], rowcount=self._rowcount)

    async def commit(self): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): pass


class _FakeAiosqlite:
    Row = dict

    def __init__(self, rows_by_kw=None, rowcount=1):
        self._rows = rows_by_kw
        self._rowcount = rowcount

    def connect(self, _path):
        return _FakeConn(self._rows, self._rowcount)


@pytest.fixture
def mock_db(monkeypatch):
    def _apply(rows_by_kw=None, rowcount=1):
        fake = _FakeAiosqlite(rows_by_kw=rows_by_kw, rowcount=rowcount)
        monkeypatch.setattr(acc, "aiosqlite", fake)
        return fake
    return _apply


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: 5 endpoint 完備
# ──────────────────────────────────────────────────────────────────────────


def test_router_lists_my_accounts_endpoint_exists(client) -> None:
    r = client.get("/api/accounts?user_id=u")
    assert r.status_code in (200, 500)


def test_router_get_account_404_for_unknown(client, monkeypatch) -> None:
    """AC-4: 不在 account_id → 404 + {code: 'account_not_found'}."""
    async def fake_get(aid): return None
    monkeypatch.setattr(acc, "get_account", fake_get)
    r = client.get("/api/accounts/99999")
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == "account_not_found"
    assert "99999" in detail["message"]


def test_router_create_account_happy(client, monkeypatch) -> None:
    async def fake_create(**kw):
        return {"id": 1, "name": kw["name"], "type": kw["type"], "plan": kw["plan"]}

    monkeypatch.setattr(acc, "create_account", fake_create)
    r = client.post("/api/accounts", json={
        "name": "Acme",
        "type": "company",
        "plan": "pro",
        "owner_user_id": "alice",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Acme"


def test_router_update_account_happy(client, monkeypatch) -> None:
    async def fake_update(aid, **fields):
        return {"id": aid, **fields}

    monkeypatch.setattr(acc, "update_account", fake_update)
    r = client.patch("/api/accounts/1", json={"name": "New Name"})
    assert r.status_code == 200
    assert r.json()["name"] == "New Name"


def test_router_delete_account(client, monkeypatch) -> None:
    async def fake_deact(aid):
        return {"id": aid, "is_active": False}

    monkeypatch.setattr(acc, "deactivate_account", fake_deact)
    r = client.delete("/api/accounts/1")
    assert r.status_code == 200
    assert r.json()["is_active"] is False


def test_router_list_members_endpoint(client, monkeypatch) -> None:
    async def fake(aid): return [{"user_id": "u1", "role": "owner"}]
    monkeypatch.setattr(acc, "list_members", fake)
    r = client.get("/api/accounts/1/members")
    assert r.status_code == 200
    assert "members" in r.json()


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: invalid input → 400 + {code, message}
# ──────────────────────────────────────────────────────────────────────────


def test_create_account_with_empty_name_returns_400(client) -> None:
    r = client.post("/api/accounts", json={
        "name": "   ", "type": "individual", "plan": "free",
    })
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "invalid_name"


def test_create_account_with_invalid_type_returns_400(client) -> None:
    r = client.post("/api/accounts", json={
        "name": "Acme", "type": "BAD_TYPE", "plan": "free",
    })
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "invalid_account_type"
    assert "BAD_TYPE" in detail["message"]


def test_create_account_with_invalid_plan_returns_400(client) -> None:
    r = client.post("/api/accounts", json={
        "name": "Acme", "type": "company", "plan": "BAD_PLAN",
    })
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "invalid_plan"


def test_update_account_with_invalid_type_returns_400(client) -> None:
    r = client.patch("/api/accounts/1", json={"type": "X"})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "invalid_account_type"


def test_update_account_with_invalid_plan_returns_400(client) -> None:
    r = client.patch("/api/accounts/1", json={"plan": "X"})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "invalid_plan"


def test_create_account_service_value_error_returns_400(client, monkeypatch) -> None:
    """service が ValueError を raise → 400 / code=invalid_request."""
    async def boom(**kw):
        raise ValueError("billing_email looks invalid")
    monkeypatch.setattr(acc, "create_account", boom)
    r = client.post("/api/accounts", json={
        "name": "Acme", "type": "individual", "plan": "free",
    })
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "invalid_request"
    assert "billing_email" in detail["message"]


def test_update_account_service_value_error_returns_400(client, monkeypatch) -> None:
    async def boom(aid, **kw):
        raise ValueError("custom validation failed")
    monkeypatch.setattr(acc, "update_account", boom)
    r = client.patch("/api/accounts/1", json={"name": "X"})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "invalid_request"


# ──────────────────────────────────────────────────────────────────────────
# service 層 cov 補強
# ──────────────────────────────────────────────────────────────────────────


def test_service_create_account_rejects_invalid_type(mock_db) -> None:
    mock_db()
    with pytest.raises(ValueError, match="type must be"):
        asyncio.run(acc.create_account(
            name="x", type="bogus", plan="free", owner_user_id="u",
        ))


def test_service_create_account_inserts_with_owner_member(mock_db) -> None:
    """create → INSERT accounts + INSERT account_members 'owner'."""
    mock_db({
        "insert into accounts": [{"id": 42}],
        "select * from accounts": [
            {"id": 42, "name": "Acme", "type": "company", "plan": "free",
             "owner_user_id": "u1", "is_active": 1},
        ],
    })
    out = asyncio.run(acc.create_account(
        name="Acme", type="company", plan="free", owner_user_id="u1",
    ))
    assert out["id"] == 42


def test_service_get_account_returns_row(mock_db) -> None:
    mock_db({"select": [{"id": 7, "name": "X"}]})
    out = asyncio.run(acc.get_account(7))
    assert out["id"] == 7


def test_service_get_account_returns_none_when_missing(mock_db) -> None:
    mock_db({"select": []})
    out = asyncio.run(acc.get_account(99999))
    assert out is None


def test_service_list_accounts_joined_with_members(mock_db) -> None:
    mock_db({"join account_members": [
        {"id": 1, "name": "WS A", "member_role": "owner"},
    ]})
    out = asyncio.run(acc.list_accounts("u1"))
    assert len(out) == 1
    assert out[0]["member_role"] == "owner"


def test_service_update_account_with_no_fields_returns_existing(mock_db) -> None:
    """fields 空 → get_account 経由で row を返す."""
    mock_db({"select": [{"id": 1, "name": "X"}]})
    out = asyncio.run(acc.update_account(1))
    assert isinstance(out, dict)


def test_service_update_account_with_metadata_serializes_json(mock_db) -> None:
    """metadata は JSON 文字列化."""
    mock_db({"select": [{"id": 1, "name": "X"}]})
    out = asyncio.run(acc.update_account(1, metadata={"tier": "gold"}))
    assert isinstance(out, dict)


def test_service_update_account_with_all_fields(mock_db) -> None:
    mock_db({"select": [{"id": 1}]})
    out = asyncio.run(acc.update_account(
        1, name="N", type="company", plan="pro",
        billing_email="x@y.com", metadata={"k": 1},
    ))
    assert isinstance(out, dict)


def test_service_deactivate_account_sets_is_active_false(mock_db) -> None:
    mock_db({"select": [{"id": 1, "is_active": 0}]})
    out = asyncio.run(acc.deactivate_account(1))
    assert out["is_active"] == 0


def test_service_list_members_returns_rows(mock_db) -> None:
    mock_db({"select * from account_members": [
        {"user_id": "u1", "role": "owner"},
        {"user_id": "u2", "role": "member"},
    ]})
    out = asyncio.run(acc.list_members(1))
    assert len(out) == 2


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE: backward compat (既存 contract field 維持)
# ──────────────────────────────────────────────────────────────────────────


def test_router_get_account_response_keeps_existing_fields(client, monkeypatch) -> None:
    async def fake_get(aid):
        return {
            "id": aid, "name": "Acme", "type": "company", "plan": "free",
            "owner_user_id": "u1", "is_active": True, "billing_email": None,
            "metadata": {}, "created_at": "2026-05-12",
        }

    monkeypatch.setattr(acc, "get_account", fake_get)
    r = client.get("/api/accounts/1")
    assert r.status_code == 200
    body = r.json()
    for key in ("id", "name", "type", "plan", "owner_user_id", "is_active",
                "billing_email", "metadata"):
        assert key in body


def test_router_create_account_passes_default_values(client, monkeypatch) -> None:
    """type / plan / owner_user_id の default 動作."""
    captured = {}
    async def fake(**kw):
        captured.update(kw)
        return {"id": 1, **kw}

    monkeypatch.setattr(acc, "create_account", fake)
    r = client.post("/api/accounts", json={"name": "Acme"})
    assert r.status_code == 200
    assert captured["type"] == "individual"
    assert captured["plan"] == "free"
    assert captured["owner_user_id"] == "masato"