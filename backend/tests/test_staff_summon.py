"""T-003-02: AI 社員召喚 API の smoke test.

minimal scope:
  - 存在しない employee_id / name で 404 相当 (status="not_found")
  - employee_id_or_name の int/str 両方を受理
  - E2E: POST /api/staff/{id}/summon が 404 を返す (存在しない employee)
"""
from __future__ import annotations

import asyncio
import os

import pytest
from fastapi.testclient import TestClient

from services.staff_summon import summon


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


def test_summon_returns_not_found_for_invalid_id() -> None:
    result = asyncio.run(summon(99999999, prompt="hi"))
    assert result["status"] == "not_found"
    assert result["ok"] is False
    assert result["employee"] is None


def test_summon_returns_not_found_for_invalid_name() -> None:
    result = asyncio.run(summon("__no_such_persona__", prompt="hi"))
    assert result["status"] == "not_found"
    assert result["ok"] is False


def test_summon_endpoint_404_for_nonexistent(client) -> None:
    r = client.post(
        "/api/staff/99999999/summon",
        json={"prompt": "hi"},
    )
    assert r.status_code == 404


def test_summon_endpoint_404_for_nonexistent_name(client) -> None:
    r = client.post(
        "/api/staff/__no_such__/summon",
        json={"prompt": "hi"},
    )
    assert r.status_code == 404
