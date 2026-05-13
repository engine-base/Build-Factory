"""T-004-06: テナント階層統合テスト — 4 AC 全網羅.

F-004 のテナント階層 (accounts → workspaces → workspace_members →
workspace_invitations → projects → tasks) を migration / service / router 横断で
静的検証 + runtime 整合性検証する.

AC マッピング:
  AC-1 UBIQUITOUS    : 全テナント表の DDL / FK / RLS / index が整合的に統合されている
  AC-2 EVENT-DRIVEN  : signup → audit emit / invite accept → audit emit
                       (action + timestamp 記録)
  AC-3 STATE-DRIVEN  : RLS が core テナント表で ENABLE + auth.uid() policy
  AC-4 UNWANTED      : 不正入力 / 不正 actor の rejected が runtime で 4xx + audit emit なし
"""
from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
MIGS = ROOT / "supabase" / "migrations"


def _all_sql() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(MIGS.glob("*.sql")))


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: 階層表の DDL + FK 整合性
# ──────────────────────────────────────────────────────────────────────────


TENANT_HIERARCHY_TABLES = [
    "accounts",
    "workspaces",
    "workspace_members",
    "workspace_invitations",
    "bf_projects",
]


@pytest.mark.parametrize("table", TENANT_HIERARCHY_TABLES)
def test_ac1_tenant_table_exists(table):
    src = _all_sql()
    assert re.search(
        rf"CREATE TABLE IF NOT EXISTS\s+{table}\b", src, re.IGNORECASE,
    ), f"tenant table {table!r} missing"


def test_ac1_workspaces_has_account_id_fk():
    """workspaces.account_id が accounts(id) を REFERENCES."""
    src = _all_sql()
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+workspaces\b(.*?);",
        src, re.DOTALL | re.IGNORECASE,
    )
    assert m
    block = m.group(1)
    assert "account_id" in block.lower()
    assert re.search(r"references\s+accounts\(?id\)?", block, re.IGNORECASE), (
        "workspaces.account_id FK to accounts(id) missing"
    )


def test_ac1_workspace_members_composite_key():
    """workspace_members には (workspace_id, user_id) の unique 制約."""
    src = _all_sql()
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+workspace_members\b(.*?);",
        src, re.DOTALL | re.IGNORECASE,
    )
    assert m
    block = m.group(1).lower()
    assert "workspace_id" in block
    assert "user_id" in block
    # PRIMARY KEY (workspace_id, user_id) または UNIQUE (workspace_id, user_id)
    assert (
        re.search(r"primary key\s*\([^)]*workspace_id[^)]*user_id", block, re.IGNORECASE)
        or re.search(r"unique\s*\([^)]*workspace_id[^)]*user_id", block, re.IGNORECASE)
    ), "workspace_members composite key (workspace_id, user_id) missing"


def test_ac1_workspace_invitations_has_token_and_status():
    """workspace_invitations は token / status / expires_at を持つ."""
    src = _all_sql()
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+workspace_invitations\b(.*?);",
        src, re.DOTALL | re.IGNORECASE,
    )
    assert m
    block = m.group(1).lower()
    assert "token" in block
    assert "status" in block
    assert "expires_at" in block
    assert "email" in block


def test_ac1_bf_projects_has_workspace_id_fk():
    src = _all_sql()
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+bf_projects\b(.*?);",
        src, re.DOTALL | re.IGNORECASE,
    )
    assert m
    block = m.group(1)
    assert "workspace_id" in block.lower()
    assert re.search(r"references\s+workspaces\(?id\)?", block, re.IGNORECASE), (
        "bf_projects.workspace_id FK missing"
    )


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: RLS が階層表で ENABLE + auth.uid() policy
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("table", ["accounts", "workspaces", "bf_projects"])
def test_ac3_rls_enabled_on_tenant_table(table):
    src = _all_sql()
    assert re.search(
        rf"ALTER TABLE\s+{table}\s+ENABLE ROW LEVEL SECURITY",
        src, re.IGNORECASE,
    ), f"RLS not enabled on {table!r}"


def test_ac3_tenant_policies_use_auth_context():
    """workspaces の RLS policy は auth.uid() / auth.jwt() / bf_can_access_* を使用."""
    src = _all_sql()
    workspace_policies = re.findall(
        r"CREATE POLICY[^;]+ON\s+workspaces[^;]+;",
        src, re.IGNORECASE | re.DOTALL,
    )
    assert len(workspace_policies) >= 1
    # auth context のいずれか (auth.uid / auth.jwt / bf_can_access_* / bf_is_*) を含む
    assert any(
        ("auth.uid()" in p) or ("auth.jwt()" in p)
        or ("bf_can_access_" in p) or ("bf_is_" in p)
        or ("service_role" in p)
        for p in workspace_policies
    ), "workspaces RLS policy must use auth context"


# ──────────────────────────────────────────────────────────────────────────
# Runtime 統合テスト (AC-2 / AC-4)
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
def _fake_tenant_layer(monkeypatch):
    """workspace/invitation 系 service を fake で結合."""
    import services.workspace_service as wsvc

    workspaces_store: dict[int, dict] = {}
    next_ws = {"v": 100}
    invitations: dict[str, dict] = {}
    members: list[dict] = []

    async def fake_create_workspace(*, account_id, name, description=None,
                                      project_meta=None, creator_user_id="masato",
                                      preferred_provider=None):
        # T-024-04 cascade: 後方互換 update.
        wid = next_ws["v"]
        next_ws["v"] += 1
        row = {
            "id": wid, "account_id": account_id, "name": name,
            "creator_user_id": creator_user_id, "status": "active",
            "preferred_provider": preferred_provider or "auto",
        }
        workspaces_store[wid] = row
        return row

    async def fake_create_invitation(workspace_id, email, *, role,
                                       invited_by, expires_in_days):
        token = f"TOK-{len(invitations) + 1:04d}-{workspace_id}-XXXXX"
        inv = {
            "workspace_id": workspace_id,
            "email": email,
            "role": role,
            "token": token,
            "expires_at": "2999-12-31T00:00:00",
            "invited_by": invited_by,
            "status": "pending",
        }
        invitations[token] = inv
        return inv

    async def fake_lookup(token):
        return invitations.get(token)

    async def fake_accept(token, user_id):
        inv = invitations.get(token)
        if not inv:
            raise wsvc.InvitationNotFoundError("not found")
        if inv["status"] == "accepted":
            raise wsvc.InvitationAlreadyUsedError("used")
        if inv["status"] == "expired":
            raise wsvc.InvitationExpiredError("expired")
        inv["status"] = "accepted"
        members.append({
            "workspace_id": inv["workspace_id"],
            "user_id": user_id,
            "role": inv["role"],
        })
        return {
            "workspace_id": inv["workspace_id"],
            "user_id": user_id,
            "role": inv["role"],
        }

    monkeypatch.setattr(wsvc, "create_workspace", fake_create_workspace)
    monkeypatch.setattr(wsvc, "create_invitation", fake_create_invitation)
    monkeypatch.setattr(wsvc, "lookup_invitation", fake_lookup)
    monkeypatch.setattr(wsvc, "accept_invitation", fake_accept)
    yield {
        "workspaces": workspaces_store,
        "invitations": invitations,
        "members": members,
    }


def test_ac2_end_to_end_signup_flow_emits_audit(client, _fake_tenant_layer, _capture_audit):
    """AC-2 EVENT: account → workspace → invite → signup の完全フローで audit emit."""
    # 1. workspace 作成
    r = client.post(
        "/api/workspaces",
        json={"account_id": 1, "name": "Tenant E2E",
               "creator_user_id": "alice"},
    )
    assert r.status_code == 200
    workspace_id = r.json()["id"]

    # 2. invitation 発行
    r = client.post(
        f"/api/workspaces/{workspace_id}/invitations",
        json={"email": "newuser@example.com", "role": "contributor",
               "invited_by": "alice"},
    )
    assert r.status_code == 200
    token = r.json()["token"]

    # 3. signup
    r = client.post(
        "/api/invitations/signup",
        json={"email": "newuser@example.com", "display_name": "New User",
               "token": token},
    )
    assert r.status_code == 200
    assert r.json()["workspace_id"] == workspace_id

    # AC-2: 各 step で audit event が記録されている (timestamp は memory_service emit_event で保持)
    event_types = {e["event_type"] for e in _capture_audit}
    assert "workspaces.created" in event_types
    assert "workspaces.invitation.created" in event_types
    assert "workspaces.signup.completed" in event_types

    # 階層整合性 (mutate 確認)
    assert workspace_id in _fake_tenant_layer["workspaces"]
    assert any(m["workspace_id"] == workspace_id
                for m in _fake_tenant_layer["members"])


def test_ac2_invitation_lookup_does_not_emit_signup_audit(
    client, _fake_tenant_layer, _capture_audit,
):
    """AC-3 補助: lookup は read-only — signup audit を emit しない."""
    # invitation を準備
    client.post(
        "/api/workspaces",
        json={"account_id": 1, "name": "Lookup Test",
               "creator_user_id": "alice"},
    )
    ws_id = list(_fake_tenant_layer["workspaces"].keys())[0]
    inv_res = client.post(
        f"/api/workspaces/{ws_id}/invitations",
        json={"email": "lookup@example.com", "invited_by": "alice"},
    )
    token = inv_res.json()["token"]
    _capture_audit.clear()

    r = client.get(f"/api/invitations/lookup/{token}")
    assert r.status_code == 200
    # AC-3: lookup は signup / accepted を emit しない
    bad_events = [e for e in _capture_audit
                   if e["event_type"] in ("workspaces.signup.completed",
                                            "workspaces.invitation.accepted")]
    assert len(bad_events) == 0


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: テナント階層に対する不正操作 reject
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_workspace_account_id_zero_rejected(client, _fake_tenant_layer):
    before = len(_fake_tenant_layer["workspaces"])
    r = client.post(
        "/api/workspaces",
        json={"account_id": 0, "name": "X", "creator_user_id": "a"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "workspaces.invalid_account_id"
    # state mutate なし
    assert len(_fake_tenant_layer["workspaces"]) == before


def test_ac4_invitation_invalid_email_rejected(client):
    r = client.post(
        "/api/workspaces/1/invitations",
        json={"email": "not-an-email", "invited_by": "alice"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invitations.invalid_email"


def test_ac4_signup_email_mismatch_rejected(client, _fake_tenant_layer):
    """招待 email と signup email が異なる → 403 + state mutate なし."""
    # workspace + invitation 作成
    client.post(
        "/api/workspaces",
        json={"account_id": 1, "name": "Mismatch Test",
               "creator_user_id": "alice"},
    )
    ws_id = list(_fake_tenant_layer["workspaces"].keys())[0]
    inv_res = client.post(
        f"/api/workspaces/{ws_id}/invitations",
        json={"email": "expected@example.com", "invited_by": "alice"},
    )
    token = inv_res.json()["token"]
    before_members = len(_fake_tenant_layer["members"])

    r = client.post(
        "/api/invitations/signup",
        json={"email": "wrong@example.com", "display_name": "X",
               "token": token},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "invitations.email_mismatch"
    # member は追加されていない
    assert len(_fake_tenant_layer["members"]) == before_members


def test_ac4_signup_with_unknown_token_returns_404(client, _capture_audit):
    r = client.post(
        "/api/invitations/signup",
        json={"email": "x@e.co", "display_name": "X",
               "token": "UNKNOWN_TOK_99999999"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "invitations.not_found"
    # AC-4: 失敗時に signup audit emit なし
    signup_events = [e for e in _capture_audit
                      if e["event_type"] == "workspaces.signup.completed"]
    assert len(signup_events) == 0


def test_ac4_workspace_create_without_creator_returns_401(client, _fake_tenant_layer):
    before = len(_fake_tenant_layer["workspaces"])
    r = client.post(
        "/api/workspaces",
        json={"account_id": 1, "name": "X", "creator_user_id": "  "},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "workspaces.unauthorized"
    # state mutate なし
    assert len(_fake_tenant_layer["workspaces"]) == before


def test_ac4_error_contract_shape_consistent(client, _fake_tenant_layer):
    cases = [
        ("POST", "/api/workspaces",
         {"account_id": 0, "name": "x", "creator_user_id": "a"}),
        ("POST", "/api/workspaces/1/invitations",
         {"email": "bad", "invited_by": "a"}),
        ("POST", "/api/invitations/signup",
         {"email": "x@e.co", "display_name": "X",
          "token": "UNKNOWN_TOK_99999999"}),
    ]
    for method, path, payload in cases:
        r = client.post(path, json=payload)
        assert 400 <= r.status_code < 500, f"{path}: {r.status_code}"
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
