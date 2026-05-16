"""T-V3-B-18 / F-012: Violations backend router tests.

AC マッピング (docs/audit/2026-05-16_v3/T-V3-B-18.md):

  AC-F1 EVENT-DRIVEN : approve by workspace_admin → resume originating session.
  AC-F2 UNWANTED     : approve already-resolved → 409.
  AC-F3 EVENT-DRIVEN : GET /api/workspaces/{id}/violations 2xx + violations[].
  AC-F4 UNWANTED     : GET violations without auth → 401.
  AC-F5 UNWANTED     : GET violations invalid input (path/query) → 422.
  AC-F6 EVENT-DRIVEN : POST approve valid input → 2xx + approved_at.
  AC-F7 UNWANTED     : POST approve without auth → 401.
  AC-F8 EVENT-DRIVEN : POST reject valid input → 2xx + rejected_at.
  AC-F9 UNWANTED     : POST reject without auth → 401.

Implementation under test:
  - backend/routers/violations.py
  - backend/services/violations.py (façade)
  - backend/schemas/violations.py
"""
from __future__ import annotations

import os

# pytest collection 前に Supabase env を default 埋めしておく
# (services.supabase_client が import 時に env 必須をチェックするため)
os.environ.setdefault("SUPABASE_URL", "http://localhost")
os.environ.setdefault("SUPABASE_ANON_KEY", "anon-test")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "service-test")
os.environ.setdefault("SUPABASE_JWT_SECRET", "secret-test")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from services import violations as svc  # noqa: E402
from services import red_lines as _rl  # noqa: E402


WS = "ws-T-V3-B-18"
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


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


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


def _seed_pending(session_id: str = "s-seed", text: str = "DROP TABLE users;") -> str:
    """Create a pending violation in WS via the underlying detector."""
    out = _rl.evaluate_action(WS, target_text=text, session_id=session_id)
    assert out["violations"], "seed precondition failed: detector did not produce a violation"
    return out["violations"][0]["violation_id"]


# ─────────────────────────────────────────────────────────────────────────────
# Service façade smoke (services.violations re-exports must match services.red_lines)
# ─────────────────────────────────────────────────────────────────────────────


def test_service_facade_constants_match_red_lines():
    """services.violations re-exports must mirror services.red_lines constants."""
    assert svc.VIOLATION_PENDING == _rl.VIOLATION_PENDING
    assert svc.VIOLATION_APPROVED == _rl.VIOLATION_APPROVED
    assert svc.VIOLATION_REJECTED == _rl.VIOLATION_REJECTED
    assert svc.VIOLATION_STATUSES == frozenset({
        _rl.VIOLATION_PENDING, _rl.VIOLATION_APPROVED, _rl.VIOLATION_REJECTED,
    })


def test_service_facade_errors_are_aliases():
    """Error classes must alias red_lines counterparts so router catch-all works."""
    assert svc.ViolationServiceError is _rl.RedLineServiceError
    assert svc.ViolationNotFound is _rl.ViolationNotFound
    assert svc.ViolationAlreadyResolved is _rl.ViolationAlreadyResolved
    assert svc.InvalidViolationInput is _rl.InvalidRedLineInput


# ─────────────────────────────────────────────────────────────────────────────
# AC-F3: GET /api/workspaces/{id}/violations  happy path
# ─────────────────────────────────────────────────────────────────────────────


def test_ac_f3_get_workspace_violations_returns_2xx_and_list(client):
    """AC-F3: 2xx with `violations` and `count` matching list length."""
    vid1 = _seed_pending("s-list-1", "DROP TABLE accounts;")
    vid2 = _seed_pending("s-list-2", "DROP TABLE secrets;")
    r = client.get(f"/api/workspaces/{WS}/violations", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "violations" in body
    assert isinstance(body["violations"], list)
    ids = [v["violation_id"] for v in body["violations"]]
    assert vid1 in ids and vid2 in ids
    assert body["count"] == len(body["violations"])
    # All violations must belong to the queried workspace (RLS contract).
    assert all(v["workspace_id"] == WS for v in body["violations"])


def test_ac_f3_get_workspace_violations_status_filter(client):
    """AC-F3 + filter: ?status=approved must only return approved records."""
    vid_pending = _seed_pending("s-pending", "DROP TABLE p;")
    vid_to_approve = _seed_pending("s-approve", "DROP TABLE q;")
    svc.approve_violation(
        vid_to_approve, actor_user_id="admin@example.com",
        reason="false positive in staging",
    )
    r = client.get(
        f"/api/workspaces/{WS}/violations?status=approved",
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 200
    ids = [v["violation_id"] for v in r.json()["violations"]]
    assert vid_to_approve in ids
    assert vid_pending not in ids
    assert all(v["status"] == svc.VIOLATION_APPROVED for v in r.json()["violations"])


def test_ac_f3_empty_workspace_returns_empty_list(client):
    """Workspace with no violations returns 200 / empty list / count=0."""
    r = client.get("/api/workspaces/ws-empty/violations", headers=ADMIN_HEADERS)
    assert r.status_code == 200
    assert r.json() == {"violations": [], "count": 0}


# ─────────────────────────────────────────────────────────────────────────────
# AC-F4: GET violations 401
# ─────────────────────────────────────────────────────────────────────────────


def test_ac_f4_get_violations_without_auth_returns_401(client):
    r = client.get(f"/api/workspaces/{WS}/violations")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "red_lines.unauthorized"


def test_ac_f4_get_violations_empty_bearer_returns_401(client):
    r = client.get(
        f"/api/workspaces/{WS}/violations",
        headers={"Authorization": "Bearer  ", "X-User-Id": "x"},
    )
    assert r.status_code == 401


def test_ac_f4_get_violations_member_role_returns_403(client):
    """Admin-only endpoint must reject member role with 403 (not 200/401)."""
    r = client.get(f"/api/workspaces/{WS}/violations", headers=MEMBER_HEADERS)
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "red_lines.forbidden"


# ─────────────────────────────────────────────────────────────────────────────
# AC-F5: GET violations 422 (invalid input)
# ─────────────────────────────────────────────────────────────────────────────


def test_ac_f5_get_violations_blank_workspace_returns_422(client):
    """Blank-only workspace_id (`%20`) must be a 422 with field-level error."""
    r = client.get("/api/workspaces/%20/violations", headers=ADMIN_HEADERS)
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "red_lines.invalid_input"
    assert any(
        e["loc"] == ["path", "workspace_id"] for e in detail["errors"]
    )


def test_ac_f5_get_violations_unknown_status_returns_422(client):
    """?status=foo (not in pending/approved/rejected) → 422."""
    r = client.get(
        f"/api/workspaces/{WS}/violations?status=foo",
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["code"] == "red_lines.invalid_input"
    assert any(e["loc"] == ["query", "status"] for e in detail["errors"])


# ─────────────────────────────────────────────────────────────────────────────
# AC-F1 / AC-F6: POST approve happy path
# ─────────────────────────────────────────────────────────────────────────────


def test_ac_f6_approve_returns_201_with_approved_at(client):
    """AC-F6: approve returns 201 + approved_at + resumed_session_id."""
    vid = _seed_pending("s-ap-1", "DROP TABLE u;")
    r = client.post(
        f"/api/violations/{vid}/approve",
        json={"reason": "false positive — staging-only"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == svc.VIOLATION_APPROVED
    assert body["approved_at"]
    assert body["resolved_at"] == body["approved_at"]
    assert body["resolution_reason"] == "false positive — staging-only"


def test_ac_f1_approve_resumes_originating_session(client):
    """AC-F1: after approve, originating session is no longer blocked."""
    vid = _seed_pending("s-ap-2", "DROP TABLE v;")
    assert _rl.is_session_blocked("s-ap-2") is True
    r = client.post(
        f"/api/violations/{vid}/approve",
        json={"reason": "investigated"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 201
    assert r.json()["resumed_session_id"] == "s-ap-2"
    assert _rl.is_session_blocked("s-ap-2") is False


# ─────────────────────────────────────────────────────────────────────────────
# AC-F2: POST approve 409 (already-resolved)
# ─────────────────────────────────────────────────────────────────────────────


def test_ac_f2_approve_already_resolved_returns_409(client):
    """AC-F2: second approve on a resolved violation → 409 Conflict."""
    vid = _seed_pending("s-ap-3", "DROP TABLE w;")
    r1 = client.post(
        f"/api/violations/{vid}/approve",
        json={"reason": "first"},
        headers=ADMIN_HEADERS,
    )
    assert r1.status_code == 201
    r2 = client.post(
        f"/api/violations/{vid}/approve",
        json={"reason": "second"},
        headers=ADMIN_HEADERS,
    )
    assert r2.status_code == 409
    assert r2.json()["detail"]["code"] == "red_lines.violation_already_resolved"


def test_ac_f2_reject_after_approve_returns_409(client):
    """AC-F2 (extension): reject after approve also 409 — state machine is one-shot."""
    vid = _seed_pending("s-ap-4", "DROP TABLE x;")
    client.post(
        f"/api/violations/{vid}/approve",
        json={"reason": "approved"},
        headers=ADMIN_HEADERS,
    )
    r = client.post(
        f"/api/violations/{vid}/reject",
        json={"reason": "changed my mind"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 409


# ─────────────────────────────────────────────────────────────────────────────
# AC-F7: POST approve 401
# ─────────────────────────────────────────────────────────────────────────────


def test_ac_f7_approve_without_auth_returns_401(client):
    vid = _seed_pending("s-ap-5", "DROP TABLE y;")
    r = client.post(f"/api/violations/{vid}/approve", json={"reason": "x"})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "red_lines.unauthorized"


def test_ac_f7_approve_with_blank_bearer_returns_401(client):
    vid = _seed_pending("s-ap-6", "DROP TABLE z;")
    r = client.post(
        f"/api/violations/{vid}/approve",
        json={"reason": "x"},
        headers={"Authorization": "Bearer", "X-User-Id": "u"},
    )
    assert r.status_code == 401


def test_ac_f7_approve_member_role_returns_403(client):
    """Member role must be rejected with 403 before reaching service layer."""
    vid = _seed_pending("s-ap-7", "DROP TABLE a;")
    r = client.post(
        f"/api/violations/{vid}/approve",
        json={"reason": "x"},
        headers=MEMBER_HEADERS,
    )
    assert r.status_code == 403


def test_approve_missing_reason_returns_422(client):
    """422 with field-level error map (reason required, non-empty)."""
    vid = _seed_pending("s-ap-8", "DROP TABLE b;")
    r = client.post(
        f"/api/violations/{vid}/approve",
        json={},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["code"] == "red_lines.invalid_input"
    locs = [tuple(e["loc"]) for e in detail["errors"]]
    assert ("reason",) in locs


def test_approve_empty_reason_returns_422(client):
    vid = _seed_pending("s-ap-9", "DROP TABLE c;")
    r = client.post(
        f"/api/violations/{vid}/approve",
        json={"reason": ""},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 422


def test_approve_non_object_body_returns_422(client):
    vid = _seed_pending("s-ap-10", "DROP TABLE d;")
    r = client.post(
        f"/api/violations/{vid}/approve",
        json=["not", "an", "object"],
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 422


def test_approve_unknown_violation_returns_404(client):
    r = client.post(
        "/api/violations/non-existent-vid/approve",
        json={"reason": "x"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "red_lines.violation_not_found"


# ─────────────────────────────────────────────────────────────────────────────
# AC-F8: POST reject happy path
# ─────────────────────────────────────────────────────────────────────────────


def test_ac_f8_reject_returns_201_with_rejected_at(client):
    """AC-F8: reject returns 201 + rejected_at."""
    vid = _seed_pending("s-rj-1", "DROP TABLE e;")
    r = client.post(
        f"/api/violations/{vid}/reject",
        json={"reason": "confirmed malicious"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == svc.VIOLATION_REJECTED
    assert body["rejected_at"]
    assert body["resolved_at"] == body["rejected_at"]
    assert body["resolution_reason"] == "confirmed malicious"


def test_ac_f8_reject_keeps_session_blocked(client):
    """After reject, originating session must remain blocked."""
    vid = _seed_pending("s-rj-2", "DROP TABLE f;")
    assert _rl.is_session_blocked("s-rj-2") is True
    r = client.post(
        f"/api/violations/{vid}/reject",
        json={"reason": "rejected"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 201
    # Session must NOT be unblocked (admin denied).
    assert _rl.is_session_blocked("s-rj-2") is True


# ─────────────────────────────────────────────────────────────────────────────
# AC-F9: POST reject 401
# ─────────────────────────────────────────────────────────────────────────────


def test_ac_f9_reject_without_auth_returns_401(client):
    vid = _seed_pending("s-rj-3", "DROP TABLE g;")
    r = client.post(f"/api/violations/{vid}/reject", json={"reason": "x"})
    assert r.status_code == 401


def test_ac_f9_reject_with_blank_bearer_returns_401(client):
    vid = _seed_pending("s-rj-4", "DROP TABLE h;")
    r = client.post(
        f"/api/violations/{vid}/reject",
        json={"reason": "x"},
        headers={"Authorization": "bearer", "X-User-Id": "u"},
    )
    assert r.status_code == 401


def test_ac_f9_reject_member_role_returns_403(client):
    vid = _seed_pending("s-rj-5", "DROP TABLE i;")
    r = client.post(
        f"/api/violations/{vid}/reject",
        json={"reason": "x"},
        headers=MEMBER_HEADERS,
    )
    assert r.status_code == 403


def test_reject_missing_reason_returns_422(client):
    vid = _seed_pending("s-rj-6", "DROP TABLE j;")
    r = client.post(
        f"/api/violations/{vid}/reject",
        json={},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 422
    locs = [tuple(e["loc"]) for e in r.json()["detail"]["errors"]]
    assert ("reason",) in locs


def test_reject_unknown_violation_returns_404(client):
    r = client.post(
        "/api/violations/does-not-exist/reject",
        json={"reason": "x"},
        headers=ADMIN_HEADERS,
    )
    assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Regression: get-by-id still works (T-V3-B-17 endpoint preserved)
# ─────────────────────────────────────────────────────────────────────────────


def test_get_violation_by_id_still_works(client):
    vid = _seed_pending("s-detail-1", "DROP TABLE k;")
    r = client.get(f"/api/violations/{vid}", headers=ADMIN_HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["violation_id"] == vid
    assert body["status"] == svc.VIOLATION_PENDING


def test_get_violation_unknown_id_returns_404(client):
    r = client.get("/api/violations/unknown-vid", headers=ADMIN_HEADERS)
    assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# RLS / workspace isolation (E-032 row-level isolation contract)
# ─────────────────────────────────────────────────────────────────────────────


def test_workspace_isolation_violations_do_not_leak(client):
    """E-032 RLS contract: a violation in WS-A must not be visible from WS-B."""
    # Seed in default WS
    _seed_pending("s-iso-1", "DROP TABLE leak;")
    # Query a completely different workspace
    r = client.get("/api/workspaces/ws-other-isolated/violations",
                   headers=ADMIN_HEADERS)
    assert r.status_code == 200
    assert r.json() == {"violations": [], "count": 0}
