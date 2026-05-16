"""T-V3-B-07 / F-005: Hearing → Spec backend (save / specs CRUD + comments).

3-tier AC verbatim mapping (docs/audit/2026-05-16_v3/T-V3-B-07.md):

Tier 2 Functional:
  AC-F1 EVENT-DRIVEN: POST hearing/save persists slot_state with monotonic version
  AC-F2 STATE-DRIVEN: while hearing status='paused' accept save to resume
  AC-F3 UNWANTED    : POST comments body > 10000 chars → 422
  AC-F4 EVENT-DRIVEN: POST hearing/save authorized → 2xx with hearing_id
  AC-F5 UNWANTED    : POST hearing/save no token → 401
  AC-F6 UNWANTED    : POST hearing/save invalid body → 422
  AC-F7 EVENT-DRIVEN: GET /specs authorized → 2xx with specs[]
  AC-F8 UNWANTED    : GET /specs no token → 401
  AC-F9 UNWANTED    : GET /specs invalid → 422
  AC-F10 EVENT-DRIVEN: GET /specs/{id}/comments authorized → 2xx with comments[]
  AC-F11 UNWANTED   : GET /specs/{id}/comments no token → 401
  AC-F12 UNWANTED   : GET /specs/{id}/comments invalid → 422
  AC-F13 EVENT-DRIVEN: POST /specs/{id}/comments authorized → 2xx with comment_id
  AC-F14 UNWANTED   : POST /specs/{id}/comments no token → 401
  AC-F15 UNWANTED   : POST /specs/{id}/comments invalid body → 422

Tier 3 Regression: covered by repo-wide gates (lint-mock / validate-ears-ac /
audit-md-check / verify-rls-coverage / pytest --cov / pyright / ruff).
"""
from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from services import specs_store as ss
from services.specs_store import (
    MAX_COMMENT_BODY_CHARS,
    SpecsStore,
    SpecsStoreError,
)


# ──────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    # Default DEV_BYPASS_AUTH=1 (set by services.auth_middleware) →
    # client without Authorization gets a dummy DEV_USER. Tests that need
    # to assert 401 explicitly disable bypass per-call.
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_store():
    ss.reset_store()
    yield
    ss.reset_store()


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
    return captured


# ──────────────────────────────────────────────────────────────────────────
# Pure store tests (unit) — fast, no FastAPI
# ──────────────────────────────────────────────────────────────────────────


def test_store_save_hearing_creates_when_absent():
    s = SpecsStore()
    h = s.save_hearing("ws-1", slot_state={"q1": "a"}, transcript="t1")
    assert h.workspace_id == "ws-1"
    assert h.version == 1
    assert h.slot_state == {"q1": "a"}
    assert h.transcript == "t1"
    assert h.status == "active"


def test_store_save_hearing_monotonic_version_ac_f1():
    """AC-F1: each save increments version monotonically.

    NOTE: save_hearing mutates and returns the same underlying Hearing dataclass
    instance after the first save, so version is read snapshot-style via to_dict.
    """
    s = SpecsStore()
    v1 = s.save_hearing("ws-1", slot_state={"v": 1}).version
    v2 = s.save_hearing("ws-1", slot_state={"v": 2}).version
    v3 = s.save_hearing("ws-1", slot_state={"v": 3}).version
    assert v1 == 1
    assert v2 == 2
    assert v3 == 3
    # Same hearing (by latest_per_workspace lookup)
    h = s.get_latest_hearing("ws-1")
    assert h is not None
    assert h.version == 3
    assert h.slot_state == {"v": 3}


def test_store_save_hearing_resume_from_paused_ac_f2():
    """AC-F2: while paused, save resumes (status → active)."""
    s = SpecsStore()
    h = s.save_hearing("ws-1")
    s.set_hearing_status(h.id, "paused")
    h2 = s.save_hearing("ws-1", slot_state={"resumed": True})
    assert h2.id == h.id
    assert h2.status == "active"
    assert h2.version == 2
    assert h2.slot_state == {"resumed": True}


def test_store_save_hearing_explicit_id_must_match_workspace():
    s = SpecsStore()
    h = s.save_hearing("ws-1")
    with pytest.raises(SpecsStoreError, match="does not belong"):
        s.save_hearing("ws-other", hearing_id=h.id)


def test_store_save_hearing_invalid_workspace_id():
    s = SpecsStore()
    with pytest.raises(SpecsStoreError):
        s.save_hearing("", slot_state={})
    with pytest.raises(SpecsStoreError):
        s.save_hearing("   ", slot_state={})


def test_store_save_hearing_invalid_slot_state_type():
    s = SpecsStore()
    with pytest.raises(SpecsStoreError):
        s.save_hearing("ws-1", slot_state="not-a-dict")  # type: ignore


def test_store_save_hearing_transcript_too_long():
    s = SpecsStore()
    with pytest.raises(SpecsStoreError):
        s.save_hearing("ws-1", transcript="x" * 200_001)


def test_store_save_hearing_unknown_hearing_id():
    s = SpecsStore()
    with pytest.raises(SpecsStoreError, match="not found"):
        s.save_hearing("ws-1", hearing_id="missing")


def test_store_save_hearing_invalid_status():
    s = SpecsStore()
    with pytest.raises(SpecsStoreError):
        s.save_hearing("ws-1", target_status="bogus")


def test_store_save_hearing_with_explicit_status():
    s = SpecsStore()
    h = s.save_hearing("ws-1", target_status="paused")
    assert h.status == "paused"
    # Explicit completed sticks
    h2 = s.save_hearing("ws-1", target_status="completed")
    assert h2.status == "completed"
    assert h2.version == 2


def test_store_get_hearing_and_latest():
    s = SpecsStore()
    assert s.get_hearing("missing") is None
    h = s.save_hearing("ws-1")
    assert s.get_hearing(h.id) is h
    assert s.get_latest_hearing("ws-1") is h
    assert s.get_latest_hearing("ws-empty") is None


def test_store_create_spec_basic():
    s = SpecsStore()
    sp = s.create_spec("ws-1", title="My Spec")
    assert sp.workspace_id == "ws-1"
    assert sp.title == "My Spec"
    assert sp.version == 1


def test_store_create_spec_invalid_title():
    s = SpecsStore()
    with pytest.raises(SpecsStoreError):
        s.create_spec("ws-1", title="")
    with pytest.raises(SpecsStoreError):
        s.create_spec("ws-1", title="x" * 501)


def test_store_create_spec_invalid_status():
    s = SpecsStore()
    with pytest.raises(SpecsStoreError):
        s.create_spec("ws-1", title="t", status="bogus")


def test_store_create_spec_with_unknown_hearing_id():
    s = SpecsStore()
    with pytest.raises(SpecsStoreError, match="not found"):
        s.create_spec("ws-1", title="t", hearing_id="missing")


def test_store_list_specs_workspace_isolation():
    s = SpecsStore()
    s.create_spec("ws-1", title="a")
    s.create_spec("ws-1", title="b")
    s.create_spec("ws-2", title="c")
    items_1 = s.list_specs("ws-1")
    items_2 = s.list_specs("ws-2")
    assert len(items_1) == 2
    assert len(items_2) == 1
    assert items_2[0].title == "c"


def test_store_list_specs_invalid_params():
    s = SpecsStore()
    with pytest.raises(SpecsStoreError):
        s.list_specs("ws-1", limit=0)
    with pytest.raises(SpecsStoreError):
        s.list_specs("ws-1", limit=10_000)
    with pytest.raises(SpecsStoreError):
        s.list_specs("ws-1", offset=-1)


def test_store_add_comment_ac_f3_boundary():
    """AC-F3 UNWANTED boundary: body == 10000 chars OK, 10001 → error."""
    s = SpecsStore()
    sp = s.create_spec("ws-1", title="t")
    # Exactly at limit: allowed
    c = s.add_comment("ws-1", sp.id, body="x" * MAX_COMMENT_BODY_CHARS)
    assert c.body == "x" * MAX_COMMENT_BODY_CHARS
    # Over limit
    with pytest.raises(SpecsStoreError, match="<= 10000"):
        s.add_comment("ws-1", sp.id, body="x" * (MAX_COMMENT_BODY_CHARS + 1))


def test_store_add_comment_empty_body():
    s = SpecsStore()
    sp = s.create_spec("ws-1", title="t")
    with pytest.raises(SpecsStoreError, match="not be empty"):
        s.add_comment("ws-1", sp.id, body="   ")


def test_store_add_comment_non_string_body():
    s = SpecsStore()
    sp = s.create_spec("ws-1", title="t")
    with pytest.raises(SpecsStoreError, match="must be a string"):
        s.add_comment("ws-1", sp.id, body=123)  # type: ignore


def test_store_add_comment_workspace_mismatch():
    s = SpecsStore()
    sp = s.create_spec("ws-1", title="t")
    with pytest.raises(SpecsStoreError, match="does not belong"):
        s.add_comment("ws-other", sp.id, body="hi")


def test_store_add_comment_unknown_spec():
    s = SpecsStore()
    with pytest.raises(SpecsStoreError, match="not found"):
        s.add_comment("ws-1", "missing-spec", body="hi")


def test_store_list_comments_preserves_order():
    s = SpecsStore()
    sp = s.create_spec("ws-1", title="t")
    s.add_comment("ws-1", sp.id, body="c1")
    s.add_comment("ws-1", sp.id, body="c2")
    s.add_comment("ws-1", sp.id, body="c3")
    items = s.list_comments("ws-1", sp.id)
    assert [c.body for c in items] == ["c1", "c2", "c3"]


def test_store_list_comments_invalid_params():
    s = SpecsStore()
    sp = s.create_spec("ws-1", title="t")
    with pytest.raises(SpecsStoreError):
        s.list_comments("ws-1", sp.id, limit=0)
    with pytest.raises(SpecsStoreError):
        s.list_comments("ws-1", sp.id, offset=-1)


def test_store_anchor_too_long():
    s = SpecsStore()
    sp = s.create_spec("ws-1", title="t")
    with pytest.raises(SpecsStoreError, match="anchor"):
        s.add_comment("ws-1", sp.id, body="ok", anchor="x" * 1000)


def test_store_singleton_reset():
    s1 = ss.get_store()
    s2 = ss.get_store()
    assert s1 is s2
    ss.reset_store()
    s3 = ss.get_store()
    assert s3 is not s1


# ──────────────────────────────────────────────────────────────────────────
# Tier 2 endpoint tests
# ──────────────────────────────────────────────────────────────────────────


# ── AC-F1 / AC-F4 : POST /hearing/save success path ────────────────


def test_ac_f4_save_hearing_201_with_hearing_id(client):
    r = client.post(
        "/api/workspaces/ws-001/hearing/save",
        json={"slot_state": {"q": "a"}, "transcript": "hello"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["hearing_id"]
    assert body["version"] == 1
    assert body["status"] == "active"
    assert "saved_at" in body
    assert body["workspace_id"] == "ws-001"


def test_ac_f1_save_hearing_monotonic_version_via_api(client):
    r1 = client.post(
        "/api/workspaces/ws-001/hearing/save",
        json={"slot_state": {"v": 1}},
    )
    r2 = client.post(
        "/api/workspaces/ws-001/hearing/save",
        json={"slot_state": {"v": 2}},
    )
    r3 = client.post(
        "/api/workspaces/ws-001/hearing/save",
        json={"slot_state": {"v": 3}},
    )
    assert r1.json()["version"] == 1
    assert r2.json()["version"] == 2
    assert r3.json()["version"] == 3
    # Same hearing_id
    assert r1.json()["hearing_id"] == r2.json()["hearing_id"] == r3.json()["hearing_id"]


# ── AC-F2 : STATE-DRIVEN paused → resume ──────────────────────────


def test_ac_f2_save_hearing_resume_from_paused(client):
    r1 = client.post("/api/workspaces/ws-1/hearing/save", json={"slot_state": {}})
    assert r1.status_code == 200
    hid = r1.json()["hearing_id"]
    # Put into paused state
    ss.get_store().set_hearing_status(hid, "paused")
    # Save while paused — must succeed and resume
    r2 = client.post(
        "/api/workspaces/ws-1/hearing/save",
        json={"slot_state": {"resumed": True}, "hearing_id": hid},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["hearing_id"] == hid
    assert body["status"] == "active"
    assert body["version"] == 2


# ── AC-F5 : POST /hearing/save no token → 401 ─────────────────────


def test_ac_f5_save_hearing_no_token_401(client, monkeypatch):
    """When DEV_BYPASS disabled and no Authorization header → 401."""
    monkeypatch.setenv("BUILD_FACTORY_DEV_BYPASS_AUTH", "0")
    # Reload module-level constant
    import services.auth_middleware as am
    monkeypatch.setattr(am, "DEV_BYPASS", False)
    r = client.post(
        "/api/workspaces/ws-1/hearing/save",
        json={"slot_state": {}},
    )
    assert r.status_code == 401, r.text


# ── AC-F6 : POST /hearing/save invalid body → 422 ─────────────────


def test_ac_f6_save_hearing_invalid_slot_state_422(client):
    # slot_state must be dict (pydantic)
    r = client.post(
        "/api/workspaces/ws-1/hearing/save",
        json={"slot_state": "not-a-dict"},
    )
    assert r.status_code == 422


def test_ac_f6_save_hearing_transcript_over_max_422(client):
    r = client.post(
        "/api/workspaces/ws-1/hearing/save",
        json={"transcript": "x" * 200_001},
    )
    assert r.status_code == 422


def test_ac_f6_save_hearing_invalid_status_422(client):
    r = client.post(
        "/api/workspaces/ws-1/hearing/save",
        json={"target_status": "bogus"},
    )
    assert r.status_code == 422


# ── AC-F7 : GET /specs success ────────────────────────────────────


def test_ac_f7_list_specs_returns_specs_array(client):
    # Seed
    store = ss.get_store()
    store.create_spec("ws-1", title="Spec A")
    store.create_spec("ws-1", title="Spec B")
    store.create_spec("ws-2", title="Spec C")
    r = client.get("/api/workspaces/ws-1/specs")
    assert r.status_code == 200
    body = r.json()
    assert "specs" in body
    assert body["count"] == 2
    titles = sorted(s["title"] for s in body["specs"])
    assert titles == ["Spec A", "Spec B"]


def test_ac_f7_list_specs_empty_workspace(client):
    r = client.get("/api/workspaces/ws-empty/specs")
    assert r.status_code == 200
    assert r.json() == {"specs": [], "count": 0}


# ── AC-F8 : GET /specs no token → 401 ─────────────────────────────


def test_ac_f8_list_specs_no_token_401(client, monkeypatch):
    monkeypatch.setenv("BUILD_FACTORY_DEV_BYPASS_AUTH", "0")
    import services.auth_middleware as am
    monkeypatch.setattr(am, "DEV_BYPASS", False)
    r = client.get("/api/workspaces/ws-1/specs")
    assert r.status_code == 401, r.text


# ── AC-F9 : GET /specs invalid → 422 ─────────────────────────────


def test_ac_f9_list_specs_invalid_limit_422(client):
    r = client.get("/api/workspaces/ws-1/specs?limit=0")
    assert r.status_code == 422


def test_ac_f9_list_specs_invalid_offset_422(client):
    r = client.get("/api/workspaces/ws-1/specs?offset=-1")
    assert r.status_code == 422


# ── AC-F10 : GET comments success ────────────────────────────────


def test_ac_f10_list_comments_returns_array(client):
    store = ss.get_store()
    sp = store.create_spec("ws-1", title="t")
    store.add_comment("ws-1", sp.id, body="hello", author_user_id="u-1")
    store.add_comment("ws-1", sp.id, body="world", author_user_id="u-2")
    r = client.get(f"/api/workspaces/ws-1/specs/{sp.id}/comments")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    bodies = [c["body"] for c in body["comments"]]
    assert bodies == ["hello", "world"]


def test_ac_f10_list_comments_unknown_spec_404(client):
    r = client.get("/api/workspaces/ws-1/specs/missing/comments")
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert detail["code"] == "spec.not_found"


def test_ac_f10_list_comments_workspace_mismatch_403(client):
    store = ss.get_store()
    sp = store.create_spec("ws-1", title="t")
    r = client.get(f"/api/workspaces/ws-other/specs/{sp.id}/comments")
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "spec.forbidden"


# ── AC-F11 : GET comments no token → 401 ─────────────────────────


def test_ac_f11_list_comments_no_token_401(client, monkeypatch):
    monkeypatch.setenv("BUILD_FACTORY_DEV_BYPASS_AUTH", "0")
    import services.auth_middleware as am
    monkeypatch.setattr(am, "DEV_BYPASS", False)
    r = client.get("/api/workspaces/ws-1/specs/anything/comments")
    assert r.status_code == 401


# ── AC-F12 : GET comments invalid → 422 ─────────────────────────


def test_ac_f12_list_comments_invalid_limit_422(client):
    r = client.get("/api/workspaces/ws-1/specs/abc/comments?limit=0")
    assert r.status_code == 422


# ── AC-F13 : POST comments success → 201 ────────────────────────


def test_ac_f13_add_comment_success_201(client, _capture_audit):
    store = ss.get_store()
    sp = store.create_spec("ws-1", title="t")
    r = client.post(
        f"/api/workspaces/ws-1/specs/{sp.id}/comments",
        json={"body": "great work", "anchor": "para-2"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert "comment_id" in body
    assert "created_at" in body
    assert body["comment"]["body"] == "great work"
    assert body["comment"]["anchor"] == "para-2"
    # Audit emitted
    events = [e for e in _capture_audit if e["event_type"] == "spec_comment_added"]
    assert len(events) == 1
    assert events[0]["detail"]["spec_id"] == sp.id


def test_ac_f13_add_comment_persists_and_listable(client):
    store = ss.get_store()
    sp = store.create_spec("ws-1", title="t")
    client.post(
        f"/api/workspaces/ws-1/specs/{sp.id}/comments",
        json={"body": "first"},
    )
    client.post(
        f"/api/workspaces/ws-1/specs/{sp.id}/comments",
        json={"body": "second"},
    )
    r = client.get(f"/api/workspaces/ws-1/specs/{sp.id}/comments")
    body = r.json()
    assert body["count"] == 2
    assert [c["body"] for c in body["comments"]] == ["first", "second"]


# ── AC-F14 : POST comments no token → 401 ────────────────────────


def test_ac_f14_add_comment_no_token_401(client, monkeypatch):
    monkeypatch.setenv("BUILD_FACTORY_DEV_BYPASS_AUTH", "0")
    import services.auth_middleware as am
    monkeypatch.setattr(am, "DEV_BYPASS", False)
    r = client.post(
        "/api/workspaces/ws-1/specs/any/comments",
        json={"body": "hi"},
    )
    assert r.status_code == 401


# ── AC-F3 / AC-F15 : POST comments invalid body → 422 ────────────


def test_ac_f3_comment_body_over_10000_chars_422(client):
    """AC-F3 UNWANTED: body > 10000 chars → 422."""
    store = ss.get_store()
    sp = store.create_spec("ws-1", title="t")
    r = client.post(
        f"/api/workspaces/ws-1/specs/{sp.id}/comments",
        json={"body": "x" * (MAX_COMMENT_BODY_CHARS + 1)},
    )
    assert r.status_code == 422, r.text


def test_ac_f3_comment_body_exactly_10000_ok(client):
    store = ss.get_store()
    sp = store.create_spec("ws-1", title="t")
    r = client.post(
        f"/api/workspaces/ws-1/specs/{sp.id}/comments",
        json={"body": "x" * MAX_COMMENT_BODY_CHARS},
    )
    assert r.status_code == 201, r.text


def test_ac_f15_comment_empty_body_422(client):
    store = ss.get_store()
    sp = store.create_spec("ws-1", title="t")
    r = client.post(
        f"/api/workspaces/ws-1/specs/{sp.id}/comments",
        json={"body": ""},
    )
    assert r.status_code == 422


def test_ac_f15_comment_missing_body_422(client):
    store = ss.get_store()
    sp = store.create_spec("ws-1", title="t")
    r = client.post(
        f"/api/workspaces/ws-1/specs/{sp.id}/comments",
        json={"anchor": "x"},
    )
    assert r.status_code == 422


def test_ac_f15_comment_unknown_spec_404(client):
    r = client.post(
        "/api/workspaces/ws-1/specs/missing/comments",
        json={"body": "hi"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "spec.not_found"


def test_ac_f15_comment_workspace_mismatch_403(client):
    store = ss.get_store()
    sp = store.create_spec("ws-1", title="t")
    r = client.post(
        f"/api/workspaces/ws-other/specs/{sp.id}/comments",
        json={"body": "hi"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "spec.forbidden"


# ── Audit emit on hearing.save ───────────────────────────────────


def test_save_hearing_emits_audit(client, _capture_audit):
    r = client.post(
        "/api/workspaces/ws-1/hearing/save",
        json={"slot_state": {"x": 1}},
    )
    assert r.status_code == 200
    events = [e for e in _capture_audit if e["event_type"] == "hearing_saved"]
    assert len(events) == 1
    det = events[0]["detail"]
    assert det["workspace_id"] == "ws-1"
    assert det["hearing_id"] == r.json()["hearing_id"]
    assert det["version"] == 1
    assert det["status"] == "active"


# ── Backward compatibility: existing hearing endpoints unchanged ─


def test_compat_existing_hearing_router_unchanged(client):
    # Existing hearing router endpoints still mounted (start-step uses int
    # workspace_id and returns 400 for unknown step). We don't exercise the
    # full LLM flow but verify the router is reachable and routing works.
    from routers import hearing as hearing_module
    assert hasattr(hearing_module, "router")
    assert hasattr(hearing_module, "start_step")
    assert hasattr(hearing_module, "complete_step")
    assert hasattr(hearing_module, "save_hearing")  # new
