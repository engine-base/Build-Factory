"""T-V3-B-17: Red-lines backend (F-012) — full AC coverage.

EARS AC mapping (audit MD docs/audit/2026-05-16_v3/T-V3-B-17.md):

  AC-F1  UBIQUITOUS    : evaluate_action() pattern-checks every action.
  AC-F2  EVENT-DRIVEN  : block hit → pending violation row created.
  AC-F3  UNWANTED      : pending state blocks session resume.
  AC-F4  EVENT-DRIVEN  : approve → session unblocked.
  AC-F5  UNWANTED      : re-approving already-resolved → 409.
  AC-F6  EVENT-DRIVEN  : GET red-lines 2xx + red_lines key.
  AC-F7  UNWANTED      : GET red-lines without auth → 401.
  AC-F8  UNWANTED      : GET red-lines invalid input → 422.
  AC-F9  EVENT-DRIVEN  : POST red-lines 2xx + red_line_id.
  AC-F10 UNWANTED      : POST red-lines without auth → 401.
  AC-F11 UNWANTED      : POST red-lines invalid input → 422.
  AC-F12 EVENT-DRIVEN  : POST red-lines/test 2xx + matched.
  AC-F13 UNWANTED      : POST red-lines/test without auth → 401.
  AC-F14 UNWANTED      : POST red-lines/test invalid input → 422.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from services import red_lines as svc


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


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


WS = "ws-001"
ADMIN_HEADERS = {
    "Authorization": "Bearer test-token",
    "X-User-Id": "admin@example.com",
    "X-User-Role": "workspace_admin",
}
MEMBER_HEADERS = {
    "Authorization": "Bearer test-token",
    "X-User-Id": "member@example.com",
    "X-User-Role": "member",
}


# ──────────────────────────────────────────────────────────────────────
# Service-level AC tests (AC-F1 / AC-F2 / AC-F3 / AC-F4 / AC-F5)
# ──────────────────────────────────────────────────────────────────────


def test_ac_f1_evaluate_runs_pattern_check_on_every_action():
    """AC-F1: every AI-initiated action is checked against active patterns."""
    out = svc.evaluate_action(WS, target_text="echo hello world",
                              session_id="s1")
    assert "allowed" in out
    assert "action" in out
    assert out["matched_count"] == 0
    assert out["action"] == "pass"
    assert out["allowed"] is True
    assert out["violations"] == []


def test_ac_f2_block_hit_creates_pending_violation():
    """AC-F2: block-matching action halts execution + creates pending row."""
    payload = "DROP TABLE users;"
    out = svc.evaluate_action(WS, target_text=payload, session_id="s-block-1")
    assert out["allowed"] is False
    assert out["action"] == "block"
    assert len(out["violations"]) >= 1
    v = out["violations"][0]
    assert v["status"] == svc.VIOLATION_PENDING
    assert v["session_id"] == "s-block-1"
    # AC-F2 second half: the violation is persisted in the workspace store
    listed = svc.list_violations(WS, status=svc.VIOLATION_PENDING)
    assert any(x["violation_id"] == v["violation_id"] for x in listed)


def test_ac_f3_pending_session_cannot_resume():
    """AC-F3: while a violation is pending, the originating session is blocked."""
    svc.evaluate_action(WS, target_text="DROP TABLE accounts;",
                        session_id="s-pending")
    assert svc.is_session_blocked("s-pending") is True
    # an unrelated session is not affected
    assert svc.is_session_blocked("s-other") is False


def test_ac_f4_admin_approve_resumes_session():
    """AC-F4: workspace_admin approve resumes the originating session."""
    out = svc.evaluate_action(WS, target_text="DROP TABLE x;",
                              session_id="s-approve")
    vid = out["violations"][0]["violation_id"]
    resolved = svc.approve_violation(vid, actor_user_id="admin@example.com",
                                     reason="False positive: test DB only")
    assert resolved["status"] == svc.VIOLATION_APPROVED
    assert resolved["resumed_session_id"] == "s-approve"
    assert "approved_at" in resolved and resolved["approved_at"]
    assert svc.is_session_blocked("s-approve") is False


def test_ac_f5_double_approve_raises_already_resolved():
    """AC-F5: approving an already-resolved violation raises 409 mapping."""
    out = svc.evaluate_action(WS, target_text="DROP TABLE y;",
                              session_id="s-double")
    vid = out["violations"][0]["violation_id"]
    svc.approve_violation(vid, actor_user_id="admin@example.com",
                          reason="ok")
    with pytest.raises(svc.ViolationAlreadyResolved):
        svc.approve_violation(vid, actor_user_id="admin@example.com",
                              reason="again")


def test_service_reject_keeps_session_blocked():
    """Rejection path: session stays blocked, status flips to rejected."""
    out = svc.evaluate_action(WS, target_text="DROP TABLE z;",
                              session_id="s-reject")
    vid = out["violations"][0]["violation_id"]
    res = svc.reject_violation(vid, actor_user_id="admin@example.com",
                               reason="confirmed malicious")
    assert res["status"] == svc.VIOLATION_REJECTED
    assert "rejected_at" in res and res["rejected_at"]
    assert svc.is_session_blocked("s-reject") is True


# ──────────────────────────────────────────────────────────────────────
# Router-level AC tests (AC-F6 .. AC-F14)
# ──────────────────────────────────────────────────────────────────────


# AC-F6 / AC-F7 / AC-F8 ────────────────────────────────────────────────


def test_ac_f6_get_red_lines_returns_red_lines_array(client):
    """AC-F6: GET /api/workspaces/{id}/red-lines returns 2xx + red_lines."""
    r = client.get(f"/api/workspaces/{WS}/red-lines", headers=MEMBER_HEADERS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "red_lines" in body
    assert isinstance(body["red_lines"], list)
    assert body["count"] == len(body["red_lines"])
    assert body["count"] >= len(svc.VALID_CATEGORIES)  # at least default seeds


def test_ac_f7_get_red_lines_without_auth_returns_401(client):
    """AC-F7: missing Authorization header → 401."""
    r = client.get(f"/api/workspaces/{WS}/red-lines")
    assert r.status_code == 401, r.text
    assert r.json()["detail"]["code"] == "red_lines.unauthorized"


def test_ac_f7_get_red_lines_with_blank_bearer_returns_401(client):
    """AC-F7: empty Bearer token → 401."""
    r = client.get(
        f"/api/workspaces/{WS}/red-lines",
        headers={"Authorization": "Bearer  ", "X-User-Id": "x"},
    )
    assert r.status_code == 401


def test_ac_f8_get_red_lines_invalid_workspace_returns_422(client):
    """AC-F8: empty path / blank workspace_id → 422 field-level errors."""
    # FastAPI rejects an empty path segment with 404 by default; we explicitly
    # check the next clearest invalid input path: blank-only id encoded as `%20`.
    r = client.get(
        "/api/workspaces/%20/red-lines",  # blank-only workspace_id
        headers=MEMBER_HEADERS,
    )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "red_lines.invalid_input"
    assert isinstance(detail.get("errors"), list)
    assert any(e["loc"] == ["path", "workspace_id"] for e in detail["errors"])


# AC-F9 / AC-F10 / AC-F11 ──────────────────────────────────────────────


def test_ac_f9_post_red_lines_returns_201_and_red_line_id(client):
    """AC-F9: valid create returns 201 + red_line_id (per F-012 contract)."""
    payload = {
        "category": "force_push",
        "pattern": r"git\s+push\s+--magic-flag",
        "action": "block",
        "description": "no magic flag",
    }
    r = client.post(
        f"/api/workspaces/{WS}/red-lines",
        json=payload, headers=ADMIN_HEADERS,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert "red_line_id" in body
    assert body["red_line"]["category"] == "force_push"
    assert body["red_line"]["action"] == "block"


def test_ac_f10_post_red_lines_without_auth_returns_401(client):
    """AC-F10: missing Authorization → 401."""
    r = client.post(
        f"/api/workspaces/{WS}/red-lines",
        json={"category": "force_push", "pattern": "x", "action": "block"},
        headers={},
    )
    assert r.status_code == 401


def test_ac_f10_post_red_lines_with_member_role_returns_403(client):
    """Admin-only endpoint rejects member role with 403 (related to AC-F10/AC-F11)."""
    r = client.post(
        f"/api/workspaces/{WS}/red-lines",
        json={"category": "force_push", "pattern": "x", "action": "block"},
        headers=MEMBER_HEADERS,
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "red_lines.forbidden"


def test_ac_f11_post_red_lines_missing_field_returns_422(client):
    """AC-F11: missing required field → 422 with field-level error map."""
    r = client.post(
        f"/api/workspaces/{WS}/red-lines",
        json={"category": "force_push"},  # missing pattern + action
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "red_lines.invalid_input"
    locs = [tuple(e["loc"]) for e in detail["errors"]]
    assert ("pattern",) in locs
    assert ("action",) in locs


def test_ac_f11_post_red_lines_invalid_category_returns_422(client):
    """AC-F11: category outside whitelist → 422."""
    r = client.post(
        f"/api/workspaces/{WS}/red-lines",
        json={"category": "not_a_category", "pattern": "abc", "action": "block"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "red_lines.invalid_input"


def test_ac_f11_post_red_lines_invalid_action_returns_422(client):
    """AC-F11: action outside enum → 422."""
    r = client.post(
        f"/api/workspaces/{WS}/red-lines",
        json={"category": "force_push", "pattern": "abc", "action": "nuke"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 422


def test_ac_f11_post_red_lines_invalid_regex_returns_422(client):
    """AC-F11: pattern that fails to compile → 422 (not 500)."""
    r = client.post(
        f"/api/workspaces/{WS}/red-lines",
        json={"category": "force_push", "pattern": "((", "action": "block"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 422


# AC-F12 / AC-F13 / AC-F14 ─────────────────────────────────────────────


def test_ac_f12_post_red_lines_test_returns_matched(client):
    """AC-F12: POST /api/workspaces/{id}/red-lines/test → 201 + matched array."""
    r = client.post(
        f"/api/workspaces/{WS}/red-lines/test",
        json={"sample_text": "DROP TABLE prod_users;"},
        headers=MEMBER_HEADERS,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert "matched" in body
    assert isinstance(body["matched"], list)
    assert any(m["action"] == "block" for m in body["matched"])
    assert body["would_block"] is True


def test_ac_f12_post_red_lines_test_no_match_returns_empty(client):
    r = client.post(
        f"/api/workspaces/{WS}/red-lines/test",
        json={"sample_text": "harmless text without dangerous patterns"},
        headers=MEMBER_HEADERS,
    )
    assert r.status_code == 201
    assert r.json()["matched"] == []
    assert r.json()["would_block"] is False


def test_ac_f13_post_red_lines_test_without_auth_returns_401(client):
    r = client.post(
        f"/api/workspaces/{WS}/red-lines/test",
        json={"sample_text": "anything"},
    )
    assert r.status_code == 401


def test_ac_f14_post_red_lines_test_missing_sample_returns_422(client):
    r = client.post(
        f"/api/workspaces/{WS}/red-lines/test",
        json={},  # missing sample_text
        headers=MEMBER_HEADERS,
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["code"] == "red_lines.invalid_input"
    locs = [tuple(e["loc"]) for e in detail["errors"]]
    assert ("sample_text",) in locs


def test_ac_f14_post_red_lines_test_empty_sample_returns_422(client):
    r = client.post(
        f"/api/workspaces/{WS}/red-lines/test",
        json={"sample_text": ""},
        headers=MEMBER_HEADERS,
    )
    assert r.status_code == 422


def test_ac_f14_post_red_lines_test_non_object_body_returns_422(client):
    """Body must be JSON object, not array/string."""
    r = client.post(
        f"/api/workspaces/{WS}/red-lines/test",
        json=["not", "an", "object"],
        headers=MEMBER_HEADERS,
    )
    assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────
# Approve / reject router (AC-F4 / AC-F5 via HTTP)
# ──────────────────────────────────────────────────────────────────────


def _create_pending_violation_via_service(session_id: str = "s-http"):
    out = svc.evaluate_action(
        WS, target_text="DROP TABLE prod_users;", session_id=session_id,
    )
    return out["violations"][0]["violation_id"]


def test_ac_f4_approve_endpoint_resolves_violation(client):
    """AC-F4 HTTP: workspace_admin approve → 201 + approved_at."""
    vid = _create_pending_violation_via_service("s-http-1")
    r = client.post(
        f"/api/violations/{vid}/approve",
        json={"reason": "false positive — internal staging"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == svc.VIOLATION_APPROVED
    assert body["approved_at"]
    assert body["resumed_session_id"] == "s-http-1"
    # session is unblocked
    assert svc.is_session_blocked("s-http-1") is False


def test_ac_f5_approve_already_resolved_returns_409(client):
    """AC-F5 HTTP: re-approving a resolved violation → 409 Conflict."""
    vid = _create_pending_violation_via_service("s-http-2")
    r1 = client.post(
        f"/api/violations/{vid}/approve",
        json={"reason": "first approve"},
        headers=ADMIN_HEADERS,
    )
    assert r1.status_code == 201
    r2 = client.post(
        f"/api/violations/{vid}/approve",
        json={"reason": "second approve"},
        headers=ADMIN_HEADERS,
    )
    assert r2.status_code == 409
    assert r2.json()["detail"]["code"] == "red_lines.violation_already_resolved"


def test_approve_violation_without_auth_returns_401(client):
    vid = _create_pending_violation_via_service("s-http-3")
    r = client.post(
        f"/api/violations/{vid}/approve",
        json={"reason": "x"},
    )
    assert r.status_code == 401


def test_approve_violation_member_role_returns_403(client):
    vid = _create_pending_violation_via_service("s-http-4")
    r = client.post(
        f"/api/violations/{vid}/approve",
        json={"reason": "x"},
        headers=MEMBER_HEADERS,
    )
    assert r.status_code == 403


def test_approve_violation_unknown_id_returns_404(client):
    r = client.post(
        "/api/violations/non-existent-violation-uuid/approve",
        json={"reason": "x"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 404


def test_approve_violation_missing_reason_returns_422(client):
    vid = _create_pending_violation_via_service("s-http-5")
    r = client.post(
        f"/api/violations/{vid}/approve",
        json={},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 422


def test_reject_endpoint_keeps_session_blocked(client):
    vid = _create_pending_violation_via_service("s-http-rej")
    r = client.post(
        f"/api/violations/{vid}/reject",
        json={"reason": "confirmed malicious"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 201
    assert r.json()["status"] == svc.VIOLATION_REJECTED
    assert svc.is_session_blocked("s-http-rej") is True


def test_get_violations_lists_workspace_violations(client):
    _create_pending_violation_via_service("s-list-1")
    _create_pending_violation_via_service("s-list-2")
    r = client.get(
        f"/api/workspaces/{WS}/violations",
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 2
    assert all(v["workspace_id"] == WS for v in body["violations"])


def test_get_violations_filter_by_status(client):
    vid = _create_pending_violation_via_service("s-list-3")
    svc.approve_violation(vid, actor_user_id="admin@example.com",
                          reason="ok")
    r = client.get(
        f"/api/workspaces/{WS}/violations?status={svc.VIOLATION_APPROVED}",
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200
    assert all(v["status"] == svc.VIOLATION_APPROVED
               for v in r.json()["violations"])


def test_get_violations_member_role_returns_403(client):
    r = client.get(
        f"/api/workspaces/{WS}/violations", headers=MEMBER_HEADERS,
    )
    assert r.status_code == 403


# ──────────────────────────────────────────────────────────────────────
# Defensive / regression: deterministic ordering + idempotency
# ──────────────────────────────────────────────────────────────────────


def test_list_red_lines_deterministic_order(client):
    """list_red_lines() returns defaults first then customs in stable order."""
    r1 = client.get(f"/api/workspaces/{WS}/red-lines", headers=MEMBER_HEADERS)
    r2 = client.get(f"/api/workspaces/{WS}/red-lines", headers=MEMBER_HEADERS)
    assert r1.status_code == 200 and r2.status_code == 200
    ids1 = [rl["red_line_id"] for rl in r1.json()["red_lines"]]
    ids2 = [rl["red_line_id"] for rl in r2.json()["red_lines"]]
    assert ids1 == ids2


def test_workspace_isolation(client):
    """Custom rule in WS-A must NOT leak to WS-B."""
    client.post(
        "/api/workspaces/ws-a/red-lines",
        json={"category": "force_push", "pattern": "abc", "action": "block"},
        headers=ADMIN_HEADERS,
    )
    rb = client.get("/api/workspaces/ws-b/red-lines", headers=MEMBER_HEADERS)
    assert rb.status_code == 200
    for rl in rb.json()["red_lines"]:
        # only defaults must be present (no custom workspace_id=ws-a leaks)
        if not rl.get("is_default", False):
            assert rl["workspace_id"] != "ws-a"
