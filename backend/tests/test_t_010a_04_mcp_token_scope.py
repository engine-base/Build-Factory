"""T-010a-04: MCP token scope (workspace 単位) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-010a で issue / list / verify / revoke endpoint 公開
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit emit + list で token を mask
  AC-4 UNWANTED      : invalid input は 4xx + structured / persistent state mutate しない
"""
from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from services import mcp_token as svc


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_store():
    svc.reset_store()
    yield
    svc.reset_store()


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
# Service 単体
# ──────────────────────────────────────────────────────────────────────────


def test_service_issue_returns_token_with_scopes():
    r = svc.issue_token(1, ["spec:read"], issued_by="alice")
    assert r["workspace_id"] == 1
    assert r["scopes"] == ["spec:read"]
    assert r["token"].startswith("mcp_")
    assert r["revoked_at"] is None


def test_service_verify_valid_token():
    r = svc.issue_token(1, ["spec:read"])
    out = svc.verify_token(r["token"], required_scope="spec:read", workspace_id=1)
    assert out["valid"] is True


def test_service_verify_scope_denied():
    r = svc.issue_token(1, ["spec:read"])
    out = svc.verify_token(r["token"], required_scope="progress:write", workspace_id=1)
    assert out["valid"] is False
    assert out["reason"] == "scope_denied"


def test_service_verify_wildcard_scope():
    r = svc.issue_token(1, ["*"])
    out = svc.verify_token(r["token"], required_scope="progress:write", workspace_id=1)
    assert out["valid"] is True


def test_service_verify_workspace_mismatch():
    r = svc.issue_token(1, ["spec:read"])
    out = svc.verify_token(r["token"], workspace_id=2)
    assert out["valid"] is False
    assert out["reason"] == "workspace_mismatch"


def test_service_verify_revoked():
    r = svc.issue_token(1, ["spec:read"])
    svc.revoke_token(r["id"])
    out = svc.verify_token(r["token"])
    assert out["valid"] is False
    assert out["reason"] == "revoked"


def test_service_verify_unknown_token():
    out = svc.verify_token("mcp_unknown_xxxxxxx")
    assert out["valid"] is False
    assert out["reason"] == "not_found"


def test_service_verify_empty_token():
    out = svc.verify_token("  ")
    assert out["valid"] is False
    assert out["reason"] == "empty_token"


def test_service_invalid_workspace_id():
    with pytest.raises(svc.MCPTokenError):
        svc.issue_token(0, ["spec:read"])


def test_service_empty_scopes():
    with pytest.raises(svc.MCPTokenError):
        svc.issue_token(1, [])


def test_service_unknown_scope():
    with pytest.raises(svc.MCPTokenError):
        svc.issue_token(1, ["unknown:scope"])


def test_service_duplicate_scopes():
    with pytest.raises(svc.MCPTokenError):
        svc.issue_token(1, ["spec:read", "spec:read"])


def test_service_expires_in_days_out_of_range():
    with pytest.raises(svc.MCPTokenError):
        svc.issue_token(1, ["spec:read"], expires_in_days=0)
    with pytest.raises(svc.MCPTokenError):
        svc.issue_token(1, ["spec:read"], expires_in_days=366)


def test_service_list_filters_by_workspace_and_revoked():
    r1 = svc.issue_token(1, ["spec:read"])
    r2 = svc.issue_token(2, ["spec:read"])
    svc.issue_token(1, ["progress:write"])
    svc.revoke_token(r1["id"])

    active_ws1 = svc.list_tokens(1)
    assert len(active_ws1) == 1  # r1 は revoked

    all_ws1 = svc.list_tokens(1, include_revoked=True)
    assert len(all_ws1) == 2

    ws2 = svc.list_tokens(2)
    assert len(ws2) == 1 and ws2[0]["workspace_id"] == 2


def test_service_list_masks_token_value():
    r = svc.issue_token(1, ["spec:read"])
    listed = svc.list_tokens(1)
    assert "..." in listed[0]["token"]
    assert listed[0]["token"] != r["token"]


def test_service_revoke_returns_false_for_unknown():
    assert svc.revoke_token(9999) is False


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint 公開
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_issue_endpoint_exists(client):
    r = client.post(
        "/api/mcp/tokens",
        json={"workspace_id": 1, "scopes": ["spec:read"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert "token" in body
    assert body["workspace_id"] == 1


def test_ac1_list_endpoint_exists(client):
    client.post("/api/mcp/tokens",
                 json={"workspace_id": 1, "scopes": ["spec:read"]})
    r = client.get("/api/mcp/tokens?workspace_id=1")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1


def test_ac1_verify_endpoint_exists(client):
    issue = client.post(
        "/api/mcp/tokens",
        json={"workspace_id": 1, "scopes": ["spec:read"]},
    ).json()
    r = client.post(
        "/api/mcp/tokens/verify",
        json={"token": issue["token"], "required_scope": "spec:read",
               "workspace_id": 1},
    )
    assert r.status_code == 200
    assert r.json()["valid"] is True


def test_ac1_revoke_endpoint_exists(client):
    issue = client.post(
        "/api/mcp/tokens",
        json={"workspace_id": 1, "scopes": ["spec:read"]},
    ).json()
    r = client.delete(f"/api/mcp/tokens/{issue['id']}")
    assert r.status_code == 200
    assert r.json()["revoked"] is True


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured error
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_issue_within_2s(client):
    t0 = time.perf_counter()
    r = client.post(
        "/api/mcp/tokens",
        json={"workspace_id": 1, "scopes": ["spec:read"]},
    )
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_verify_within_2s(client):
    issue = client.post(
        "/api/mcp/tokens",
        json={"workspace_id": 1, "scopes": ["spec:read"]},
    ).json()
    t0 = time.perf_counter()
    r = client.post("/api/mcp/tokens/verify",
                     json={"token": issue["token"]})
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.post(
        "/api/mcp/tokens",
        json={"workspace_id": 0, "scopes": ["spec:read"]},
    )
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "mcp_tokens.invalid_workspace_id"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: audit emit + token mask
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_issue_emits_audit(client, _capture_audit):
    client.post(
        "/api/mcp/tokens",
        json={"workspace_id": 7, "scopes": ["spec:read", "progress:write"],
               "issued_by": "alice"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "mcp_tokens.issued"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "alice"
    assert events[0]["detail"]["workspace_id"] == 7
    assert set(events[0]["detail"]["scopes"]) == {"spec:read", "progress:write"}


def test_ac3_revoke_emits_audit(client, _capture_audit):
    issue = client.post(
        "/api/mcp/tokens",
        json={"workspace_id": 1, "scopes": ["spec:read"]},
    ).json()
    client.delete(f"/api/mcp/tokens/{issue['id']}?actor_user_id=bob")
    events = [e for e in _capture_audit if e["event_type"] == "mcp_tokens.revoked"]
    assert len(events) >= 1
    assert events[-1]["user_id"] == "bob"


def test_ac3_list_masks_token(client):
    issue = client.post(
        "/api/mcp/tokens",
        json={"workspace_id": 1, "scopes": ["spec:read"]},
    ).json()
    r = client.get("/api/mcp/tokens?workspace_id=1")
    listed = r.json()["tokens"][0]
    # 平文 token を返さない
    assert listed["token"] != issue["token"]
    assert "..." in listed["token"]


def test_ac3_verify_does_not_emit_audit(client, _capture_audit):
    """AC-3 補助: verify は read-only (audit emit なし)."""
    issue = client.post(
        "/api/mcp/tokens",
        json={"workspace_id": 1, "scopes": ["spec:read"]},
    ).json()
    _capture_audit.clear()
    client.post("/api/mcp/tokens/verify",
                 json={"token": issue["token"]})
    bad = [e for e in _capture_audit
            if e["event_type"] in ("mcp_tokens.issued", "mcp_tokens.revoked")]
    assert len(bad) == 0


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_invalid_workspace_id_rejected(client):
    r = client.post(
        "/api/mcp/tokens",
        json={"workspace_id": 0, "scopes": ["spec:read"]},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp_tokens.invalid_workspace_id"


def test_ac4_empty_scopes_rejected(client):
    r = client.post(
        "/api/mcp/tokens",
        json={"workspace_id": 1, "scopes": []},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp_tokens.invalid_scopes"


def test_ac4_unknown_scope_rejected(client):
    r = client.post(
        "/api/mcp/tokens",
        json={"workspace_id": 1, "scopes": ["bogus:scope"]},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp_tokens.invalid"


def test_ac4_expires_in_days_out_of_range(client):
    r = client.post(
        "/api/mcp/tokens",
        json={"workspace_id": 1, "scopes": ["spec:read"],
               "expires_in_days": 0},
    )
    assert r.status_code in (400, 422)


def test_ac4_empty_issued_by_rejected(client):
    r = client.post(
        "/api/mcp/tokens",
        json={"workspace_id": 1, "scopes": ["spec:read"],
               "issued_by": "  "},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "mcp_tokens.unauthorized"


def test_ac4_empty_verify_token_rejected(client):
    r = client.post("/api/mcp/tokens/verify",
                     json={"token": "  "})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp_tokens.invalid_token"


def test_ac4_invalid_verify_scope_rejected(client):
    r = client.post(
        "/api/mcp/tokens/verify",
        json={"token": "mcp_xxx", "required_scope": "bogus:scope"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp_tokens.invalid_scope"


def test_ac4_revoke_unknown_id_returns_404(client):
    r = client.delete("/api/mcp/tokens/99999")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "mcp_tokens.not_found"


def test_ac4_revoke_invalid_id_rejected(client):
    r = client.delete("/api/mcp/tokens/0")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "mcp_tokens.invalid_id"


def test_ac4_rejected_does_not_emit_audit(client, _capture_audit):
    client.post("/api/mcp/tokens",
                 json={"workspace_id": 0, "scopes": ["spec:read"]})
    client.post("/api/mcp/tokens",
                 json={"workspace_id": 1, "scopes": []})
    events = [e for e in _capture_audit if e["event_type"] == "mcp_tokens.issued"]
    assert len(events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    cases = [
        ("POST", "/api/mcp/tokens",
         {"workspace_id": 0, "scopes": ["spec:read"]}),
        ("POST", "/api/mcp/tokens",
         {"workspace_id": 1, "scopes": []}),
        ("POST", "/api/mcp/tokens",
         {"workspace_id": 1, "scopes": ["unknown"]}),
        ("POST", "/api/mcp/tokens",
         {"workspace_id": 1, "scopes": ["spec:read"], "issued_by": "  "}),
        ("POST", "/api/mcp/tokens/verify", {"token": "  "}),
        ("POST", "/api/mcp/tokens/verify",
         {"token": "x", "required_scope": "unknown"}),
        ("DELETE", "/api/mcp/tokens/0", None),
        ("DELETE", "/api/mcp/tokens/99999", None),
    ]
    for method, path, payload in cases:
        if method == "DELETE":
            r = client.delete(path)
        else:
            r = client.post(path, json=payload)
        assert 400 <= r.status_code < 500, f"{path}: {r.status_code}"
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
