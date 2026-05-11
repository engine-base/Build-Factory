"""T-004-05: Owner 移譲 AC テスト.

AC reference: docs/task-decomposition/2026-05-09_v1/tickets.json T-004-05
  - UBIQUITOUS: 既存メンバーへ owner を移譲できる
  - EVENT:      current を ws_admin に降格、 new を owner に昇格 (atomic)
  - STATE:      非 owner ユーザーは移譲できない (UI/BE 両方)
  - UNWANTED:   target が member でない → 400 (code=target_not_member)
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from services.workspace_service import (
    transfer_ownership, NotOwnerError, TargetNotMemberError,
)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


# ─────────────────────────────────────────────────────────
# Service レイヤ: get_member を mock
# ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_transfer_current_not_owner_raises(monkeypatch) -> None:
    """STATE: current_owner_id が実際の owner でなければ NotOwnerError"""
    async def fake_get(workspace_id, user_id):
        return {"user_id": user_id, "role": "contributor"}

    monkeypatch.setattr("services.workspace_service.get_member", fake_get)

    with pytest.raises(NotOwnerError):
        await transfer_ownership(
            1, current_owner_id="alice", new_owner_id="bob",
        )


@pytest.mark.asyncio
async def test_transfer_target_not_member_raises(monkeypatch) -> None:
    """UNWANTED: target がメンバーでなければ TargetNotMemberError"""
    async def fake_get(workspace_id, user_id):
        if user_id == "alice":
            return {"user_id": "alice", "role": "owner"}
        return None  # bob は未参加

    monkeypatch.setattr("services.workspace_service.get_member", fake_get)

    with pytest.raises(TargetNotMemberError):
        await transfer_ownership(
            1, current_owner_id="alice", new_owner_id="bob",
        )


@pytest.mark.asyncio
async def test_transfer_same_user_raises_value_error() -> None:
    """ValueError: 同一 user_id 同士の移譲は意味がない"""
    with pytest.raises(ValueError):
        await transfer_ownership(
            1, current_owner_id="alice", new_owner_id="alice",
        )


# ─────────────────────────────────────────────────────────
# Router レイヤ: 4xx 系
# ─────────────────────────────────────────────────────────
def test_router_transfer_not_owner_returns_403(client, monkeypatch) -> None:
    async def fake(*a, **kw):
        raise NotOwnerError("user X is not the owner")

    monkeypatch.setattr("routers.workspaces.ws.transfer_ownership", fake)

    r = client.post(
        "/api/workspaces/1/transfer-ownership",
        json={"current_owner_id": "alice", "new_owner_id": "bob"},
    )
    assert r.status_code == 403
    detail = r.json().get("detail")
    assert isinstance(detail, dict) and detail.get("code") == "not_owner"


def test_router_transfer_target_not_member_returns_400(client, monkeypatch) -> None:
    async def fake(*a, **kw):
        raise TargetNotMemberError("bob is not a member")

    monkeypatch.setattr("routers.workspaces.ws.transfer_ownership", fake)

    r = client.post(
        "/api/workspaces/1/transfer-ownership",
        json={"current_owner_id": "alice", "new_owner_id": "bob"},
    )
    assert r.status_code == 400
    detail = r.json().get("detail")
    assert isinstance(detail, dict) and detail.get("code") == "target_not_member"


def test_router_transfer_same_user_returns_400(client) -> None:
    r = client.post(
        "/api/workspaces/1/transfer-ownership",
        json={"current_owner_id": "alice", "new_owner_id": "alice"},
    )
    # service の ValueError → 400 (invalid_request)
    assert r.status_code in (400, 403)
