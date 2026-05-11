"""T-004-04: 招待受入 API + signup — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-004 で lookup / accept / signup endpoint 公開
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit_logs emit + RLS は migration 側で担保
  AC-4 UNWANTED      : invalid token / expired / 既使用 / email mismatch は 4xx + structured
                       かつ persistent state mutate しない
"""
from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient


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
def _fake_ws(monkeypatch):
    """workspace_service の lookup/accept を fake in-memory store で差し替え."""
    import services.workspace_service as wsvc

    store: dict[str, dict] = {
        # 有効
        "VALID_TOK_AAAA12345": {
            "id": 1, "workspace_id": 10, "email": "alice@example.com",
            "role": "contributor", "status": "pending",
            "expires_at": "2999-12-31T00:00:00", "invited_by": "owner",
        },
        # 期限切れ
        "EXP_TOK_BBBB12345": {
            "id": 2, "workspace_id": 20, "email": "bob@example.com",
            "role": "viewer", "status": "expired",
            "expires_at": "2020-01-01T00:00:00", "invited_by": "owner",
        },
        # 既使用
        "USED_TOK_CCCC12345": {
            "id": 3, "workspace_id": 30, "email": "carol@example.com",
            "role": "admin", "status": "accepted",
            "expires_at": "2999-12-31T00:00:00", "invited_by": "owner",
        },
    }
    accepted: list[dict] = []

    async def fake_lookup(token):
        if not token or not token.strip():
            return None
        inv = store.get(token.strip())
        if not inv:
            return None
        d = dict(inv)
        from datetime import datetime
        try:
            d["is_expired"] = (
                datetime.fromisoformat(d["expires_at"]) < datetime.now()
            )
        except Exception:
            d["is_expired"] = False
        return d

    async def fake_accept(token, user_id):
        inv = store.get(token)
        if not inv:
            raise wsvc.InvitationNotFoundError(f"not found: {token}")
        if inv["status"] == "accepted":
            raise wsvc.InvitationAlreadyUsedError("already")
        if inv["status"] == "expired":
            raise wsvc.InvitationExpiredError("expired")
        # 状態更新
        inv["status"] = "accepted"
        result = {
            "workspace_id": inv["workspace_id"],
            "user_id": user_id,
            "role": inv["role"],
        }
        accepted.append(result)
        return result

    monkeypatch.setattr(wsvc, "lookup_invitation", fake_lookup)
    monkeypatch.setattr(wsvc, "accept_invitation", fake_accept)
    yield {"store": store, "accepted": accepted}


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint 公開
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_lookup_endpoint_exists(client):
    r = client.get("/api/invitations/lookup/VALID_TOK_AAAA12345")
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is True
    assert body["workspace_id"] == 10
    # PII を含むことに注意 (admin 用 endpoint): id は除外されている
    assert "id" not in body


def test_ac1_accept_endpoint_exists(client):
    r = client.post(
        "/api/invitations/accept",
        json={"token": "VALID_TOK_AAAA12345", "user_id": "alice@example.com"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["workspace_id"] == 10
    assert body["role"] == "contributor"


def test_ac1_signup_endpoint_exists(client, _fake_ws):
    # store を re-init するため fresh token 用にもう一回追加
    _fake_ws["store"]["NEW_TOK_DDDD12345"] = {
        "id": 4, "workspace_id": 40, "email": "newuser@example.com",
        "role": "contributor", "status": "pending",
        "expires_at": "2999-12-31T00:00:00", "invited_by": "owner",
    }
    r = client.post(
        "/api/invitations/signup",
        json={
            "email": "newuser@example.com",
            "display_name": "New User",
            "token": "NEW_TOK_DDDD12345",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "newuser@example.com"
    assert body["workspace_id"] == 40


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_lookup_returns_within_2s(client):
    t0 = time.perf_counter()
    r = client.get("/api/invitations/lookup/VALID_TOK_AAAA12345")
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_accept_returns_within_2s(client, _fake_ws):
    _fake_ws["store"]["PERF_TOK_EEEE12345"] = {
        "id": 5, "workspace_id": 50, "email": "p@e.co",
        "role": "viewer", "status": "pending",
        "expires_at": "2999-12-31T00:00:00", "invited_by": "owner",
    }
    t0 = time.perf_counter()
    r = client.post(
        "/api/invitations/accept",
        json={"token": "PERF_TOK_EEEE12345", "user_id": "p@e.co"},
    )
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.post("/api/invitations/accept",
                     json={"token": "short", "user_id": "u"})
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "invitations.invalid_token"
    assert "message" in body["detail"]


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: audit emit
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_accept_emits_audit(client, _fake_ws, _capture_audit):
    _fake_ws["store"]["AUDIT_TOK_FFFF12345"] = {
        "id": 6, "workspace_id": 60, "email": "x@e.co",
        "role": "admin", "status": "pending",
        "expires_at": "2999-12-31T00:00:00", "invited_by": "owner",
    }
    client.post("/api/invitations/accept",
                 json={"token": "AUDIT_TOK_FFFF12345", "user_id": "x@e.co"})
    events = [e for e in _capture_audit
              if e["event_type"] == "workspaces.invitation.accepted"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "x@e.co"
    assert events[0]["detail"]["workspace_id"] == 60


def test_ac3_signup_emits_audit_with_email_hash(client, _fake_ws, _capture_audit):
    _fake_ws["store"]["SIGNUP_TOK_GGGG1234"] = {
        "id": 7, "workspace_id": 70, "email": "su@e.co",
        "role": "contributor", "status": "pending",
        "expires_at": "2999-12-31T00:00:00", "invited_by": "owner",
    }
    client.post(
        "/api/invitations/signup",
        json={"email": "su@e.co", "display_name": "Signup User",
               "token": "SIGNUP_TOK_GGGG1234"},
    )
    events = [e for e in _capture_audit
              if e["event_type"] == "workspaces.signup.completed"]
    assert len(events) >= 1
    # PII (email 平文) を audit に残さない
    assert "su@e.co" not in str(events[0]["detail"])
    assert "email_hash" in events[0]["detail"]


def test_ac3_lookup_does_not_mutate_state(client, _fake_ws, _capture_audit):
    """AC-3: lookup は read-only (audit emit / store mutate なし)."""
    before = len(_fake_ws["accepted"])
    client.get("/api/invitations/lookup/VALID_TOK_AAAA12345")
    after = len(_fake_ws["accepted"])
    assert before == after
    # 該当 audit event なし
    audit_evt = [e for e in _capture_audit
                  if e["event_type"].startswith("workspaces.invitation.")]
    assert len(audit_evt) == 0


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_unknown_token_returns_404(client):
    r = client.post("/api/invitations/accept",
                     json={"token": "UNKNOWN_TOK_XXXX1234", "user_id": "u"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "invitations.not_found"


def test_ac4_expired_token_returns_410(client):
    r = client.post("/api/invitations/accept",
                     json={"token": "EXP_TOK_BBBB12345", "user_id": "bob@e.co"})
    assert r.status_code == 410
    assert r.json()["detail"]["code"] == "invitations.expired"


def test_ac4_already_used_token_returns_409(client):
    r = client.post("/api/invitations/accept",
                     json={"token": "USED_TOK_CCCC12345", "user_id": "c@e.co"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "invitations.already_used"


def test_ac4_short_token_rejected(client):
    r = client.post("/api/invitations/accept",
                     json={"token": "short", "user_id": "u"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invitations.invalid_token"


def test_ac4_long_token_rejected_on_lookup(client):
    r = client.get("/api/invitations/lookup/" + "x" * 201)
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invitations.token_too_long"


def test_ac4_empty_user_id_rejected(client):
    r = client.post("/api/invitations/accept",
                     json={"token": "VALID_TOK_AAAA12345", "user_id": "  "})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "invitations.unauthorized"


def test_ac4_signup_invalid_email_rejected(client):
    r = client.post(
        "/api/invitations/signup",
        json={"email": "not-an-email", "display_name": "X",
               "token": "VALID_TOK_AAAA12345"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invitations.invalid_email"


def test_ac4_signup_empty_display_name_rejected(client):
    r = client.post(
        "/api/invitations/signup",
        json={"email": "x@e.co", "display_name": "  ",
               "token": "VALID_TOK_AAAA12345"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invitations.invalid_display_name"


def test_ac4_signup_email_mismatch_returns_403(client, _fake_ws):
    _fake_ws["store"]["MISMATCH_TOK_HHHH123"] = {
        "id": 8, "workspace_id": 80, "email": "expected@e.co",
        "role": "contributor", "status": "pending",
        "expires_at": "2999-12-31T00:00:00", "invited_by": "owner",
    }
    r = client.post(
        "/api/invitations/signup",
        json={"email": "different@e.co", "display_name": "X",
               "token": "MISMATCH_TOK_HHHH123"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "invitations.email_mismatch"


def test_ac4_signup_expired_token_returns_410(client):
    r = client.post(
        "/api/invitations/signup",
        json={"email": "bob@example.com", "display_name": "X",
               "token": "EXP_TOK_BBBB12345"},
    )
    assert r.status_code == 410
    assert r.json()["detail"]["code"] == "invitations.expired"


def test_ac4_rejected_does_not_emit_audit(client, _capture_audit, _fake_ws):
    """AC-4 UNWANTED: 失敗時に audit emit / accepted mutate なし."""
    before_accepted = len(_fake_ws["accepted"])
    client.post("/api/invitations/accept",
                 json={"token": "EXP_TOK_BBBB12345", "user_id": "b@e.co"})
    client.post("/api/invitations/accept",
                 json={"token": "UNKNOWN_TOK_XXXX1234", "user_id": "u"})
    after_accepted = len(_fake_ws["accepted"])
    assert before_accepted == after_accepted
    success_events = [
        e for e in _capture_audit
        if e["event_type"] in ("workspaces.invitation.accepted",
                                  "workspaces.signup.completed")
    ]
    assert len(success_events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client, _fake_ws):
    cases = [
        ("POST", "/api/invitations/accept",
         {"token": "short", "user_id": "u"}),
        ("POST", "/api/invitations/accept",
         {"token": "VALID_TOK_AAAA12345", "user_id": "  "}),
        ("POST", "/api/invitations/accept",
         {"token": "UNKNOWN_TOK_XXXX1234", "user_id": "u"}),
        ("POST", "/api/invitations/accept",
         {"token": "EXP_TOK_BBBB12345", "user_id": "u"}),
        ("POST", "/api/invitations/accept",
         {"token": "USED_TOK_CCCC12345", "user_id": "u"}),
        ("POST", "/api/invitations/signup",
         {"email": "not-email", "display_name": "X", "token": "VALID_TOK_AAAA12345"}),
        ("POST", "/api/invitations/signup",
         {"email": "x@e.co", "display_name": "  ", "token": "VALID_TOK_AAAA12345"}),
        ("GET", "/api/invitations/lookup/" + "x" * 201, None),
        ("GET", "/api/invitations/lookup/UNKNOWN_TOK_xxxx", None),
    ]
    for method, path, payload in cases:
        if method == "GET":
            r = client.get(path)
        else:
            r = client.post(path, json=payload)
        assert 400 <= r.status_code < 500, f"{path}: {r.status_code}"
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
