"""T-023-05: user_lifecycle (clone opt-in + GDPR deletion) の smoke test.

DB 不在環境では graceful (False / 空 dict) を返す前提で、本テストは
service 層の純粋ロジック + router 層の E2E を確認する。
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from services.user_lifecycle import (
    _execute_after, GRACE_DAYS, request_deletion, get_clone_optin,
)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


def test_grace_days_constant() -> None:
    assert GRACE_DAYS == 30


def test_execute_after_formats_as_iso_30_days_later() -> None:
    s = _execute_after(30)
    # UTC ISO 文字列 → parse 可能
    dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    diff = dt - datetime.now()
    # ±1 hour 程度の余裕で 30 日後
    assert 29 * 24 * 60 * 60 <= diff.total_seconds() <= 31 * 24 * 60 * 60


def test_execute_after_custom_days() -> None:
    s = _execute_after(7)
    dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    diff = dt - datetime.now()
    assert 6 * 24 * 3600 <= diff.total_seconds() <= 8 * 24 * 3600


# ──────────────────────────────────────────
# Router E2E
# ──────────────────────────────────────────

def test_router_clone_optin_get_default_off(client) -> None:
    r = client.get("/api/user/clone-optin", params={"user_id": "fresh_user_xyz"})
    assert r.status_code == 200
    assert r.json()["opted_in"] is False


def test_router_pending_deletions_empty_list(client) -> None:
    r = client.get("/api/user/deletion/pending")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_router_execute_due_dry_run(client) -> None:
    r = client.post("/api/user/deletion/execute-due", params={"dry_run": "true"})
    assert r.status_code == 200
    body = r.json()
    # dry_run なら would_execute / ids 形式 (DB 不在でも 0 件)
    assert "would_execute" in body or "executed" in body
