"""T-005-04: 仕様書 HTML 生成 (spec_html_generator + requirements router) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-005 で spec HTML 生成 service + endpoint 公開
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 router endpoint 不変 + audit emit
  AC-4 UNWANTED      : invalid input / 不正 workspace は 4xx + structured
                       かつ persistent state mutate しない
"""
from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from services.spec_html_generator import (
    SpecHtmlError,
    SpecMeta,
    SpecSection,
    build_sections_from_view,
    render_spec_html,
)


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
def _fake_view(monkeypatch):
    """requirements_service.get_aggregated_view を fake."""
    import services.requirements_service as rs

    async def fake_view(workspace_id):
        return {
            "tabs": {
                "overview": [
                    {"label": "目的", "value": "AI 開発工場 OS"},
                    {"label": "ターゲット", "value": "受託 / SaaS / 個人"},
                ],
                "features": [
                    {"label": "F-001", "value": "FastAPI 基盤"},
                    {"label": "F-005", "value": "要件定義"},
                ],
            },
        }

    monkeypatch.setattr(rs, "get_aggregated_view", fake_view)
    yield


# ──────────────────────────────────────────────────────────────────────────
# Service 単体: render_spec_html
# ──────────────────────────────────────────────────────────────────────────


def test_render_basic_returns_valid_html():
    meta = SpecMeta(project_name="Test Project", workspace_id=1, version="v1")
    sections = [
        SpecSection(title="概要", bullet_items=["項目1", "項目2"]),
    ]
    out = render_spec_html(meta, sections)
    assert "<!doctype html>" in out.lower()
    assert "Test Project" in out
    assert "概要" in out
    assert "項目1" in out
    assert "</html>" in out


def test_render_no_sections_shows_placeholder():
    meta = SpecMeta(project_name="X", workspace_id=1)
    out = render_spec_html(meta, [])
    assert "セクションなし" in out


def test_render_escapes_html_in_project_name():
    meta = SpecMeta(project_name='<script>alert("xss")</script>', workspace_id=1)
    out = render_spec_html(meta, [])
    assert "<script>" not in out  # escaped
    assert "&lt;script&gt;" in out


def test_render_escapes_bullet_items():
    meta = SpecMeta(project_name="X", workspace_id=1)
    sections = [SpecSection(title="Risk", bullet_items=["<img src=x>"])]
    out = render_spec_html(meta, sections)
    assert "<img" not in out
    assert "&lt;img" in out


def test_render_empty_project_name_raises():
    with pytest.raises(SpecHtmlError):
        render_spec_html(SpecMeta(project_name="   ", workspace_id=1), [])


def test_render_invalid_workspace_id_raises():
    with pytest.raises(SpecHtmlError):
        render_spec_html(SpecMeta(project_name="X", workspace_id=0), [])


def test_render_non_meta_raises():
    with pytest.raises(SpecHtmlError):
        render_spec_html({"project_name": "X"}, [])  # not SpecMeta


def test_render_includes_workspace_id_meta_tag():
    meta = SpecMeta(project_name="X", workspace_id=42)
    out = render_spec_html(meta, [])
    assert 'name="workspace-id" content="42"' in out


def test_build_sections_from_view_orders_correctly():
    view = {
        "tabs": {
            "overview": [{"label": "概要", "value": "テスト"}],
            "features": [{"label": "F1", "value": "feature1"}],
            "risks": [{"label": "リスク", "value": "高"}],
        },
    }
    sections = build_sections_from_view(view)
    titles = [s.title for s in sections]
    assert any("概要" in t for t in titles)
    assert any("機能一覧" in t for t in titles)
    assert any("リスク" in t for t in titles)


def test_build_sections_empty_view():
    assert build_sections_from_view({}) == []
    assert build_sections_from_view({"tabs": "wrong"}) == []
    assert build_sections_from_view("not-dict") == []


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint 公開
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_generate_endpoint_exists(client):
    r = client.post(
        "/api/workspaces/1/spec/generate-html",
        json={"project_name": "Demo Project", "version": "v1"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "Demo Project" in r.text
    assert "</html>" in r.text


def test_ac1_default_project_name_used(client):
    r = client.post(
        "/api/workspaces/5/spec/generate-html",
        json={"version": "v0.1"},
    )
    assert r.status_code == 200
    assert "Workspace #5" in r.text


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured error
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_returns_within_2s(client):
    t0 = time.perf_counter()
    r = client.post(
        "/api/workspaces/1/spec/generate-html",
        json={"project_name": "X"},
    )
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.post(
        "/api/workspaces/0/spec/generate-html",
        json={"project_name": "x"},
    )
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "requirements.invalid_workspace_id"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: 既存 endpoint + audit emit
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_existing_routes_still_defined():
    from routers.requirements import router
    paths = {r.path for r in router.routes if hasattr(r, "path")}
    expected = {
        "/api/workspaces/{workspace_id}/requirements/start-step",
        "/api/workspaces/{workspace_id}/requirements/reply",
        "/api/workspaces/{workspace_id}/requirements/complete-step",
        "/api/workspaces/{workspace_id}/requirements/state",
        "/api/workspaces/{workspace_id}/requirements/aggregated-view",
        "/api/workspaces/{workspace_id}/requirements/center",
        "/api/workspaces/{workspace_id}/requirements/download/{tab}.{fmt}",
        "/api/workspaces/{workspace_id}/spec/generate-html",
    }
    assert expected <= paths


def test_ac3_generate_emits_audit(client, _capture_audit):
    client.post(
        "/api/workspaces/3/spec/generate-html",
        json={"project_name": "Audit Test", "version": "v2",
               "actor_user_id": "alice"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "requirements.spec.generated"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "alice"
    assert events[0]["detail"]["workspace_id"] == 3
    assert events[0]["detail"]["version"] == "v2"
    assert events[0]["detail"]["html_size"] > 0


def test_ac3_response_attaches_download_filename(client):
    r = client.post(
        "/api/workspaces/9/spec/generate-html",
        json={"project_name": "X", "version": "v5"},
    )
    cd = r.headers.get("content-disposition", "")
    assert 'filename="spec-9-v5.html"' in cd


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_invalid_workspace_id_rejected(client):
    r = client.post(
        "/api/workspaces/0/spec/generate-html",
        json={"project_name": "x"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "requirements.invalid_workspace_id"


def test_ac4_empty_actor_rejected(client):
    r = client.post(
        "/api/workspaces/1/spec/generate-html",
        json={"project_name": "x", "actor_user_id": "  "},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "requirements.unauthorized"


def test_ac4_long_project_name_rejected(client):
    r = client.post(
        "/api/workspaces/1/spec/generate-html",
        json={"project_name": "x" * 201},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "requirements.project_name_too_long"


def test_ac4_empty_version_rejected(client):
    r = client.post(
        "/api/workspaces/1/spec/generate-html",
        json={"project_name": "x", "version": "   "},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "requirements.invalid_version"


def test_ac4_long_version_rejected(client):
    r = client.post(
        "/api/workspaces/1/spec/generate-html",
        json={"project_name": "x", "version": "v" * 51},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "requirements.version_too_long"


def test_ac4_rejected_does_not_emit_audit(client, _capture_audit):
    client.post("/api/workspaces/0/spec/generate-html", json={"project_name": "x"})
    client.post("/api/workspaces/1/spec/generate-html",
                 json={"project_name": "x", "actor_user_id": "  "})
    events = [e for e in _capture_audit if e["event_type"] == "requirements.spec.generated"]
    assert len(events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    cases = [
        {"path": "/api/workspaces/0/spec/generate-html",
         "json": {"project_name": "x"}},
        {"path": "/api/workspaces/1/spec/generate-html",
         "json": {"project_name": "x" * 201}},
        {"path": "/api/workspaces/1/spec/generate-html",
         "json": {"project_name": "x", "version": "   "}},
        {"path": "/api/workspaces/1/spec/generate-html",
         "json": {"project_name": "x", "actor_user_id": "  "}},
    ]
    for c in cases:
        r = client.post(c["path"], json=c["json"])
        assert 400 <= r.status_code < 500
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
