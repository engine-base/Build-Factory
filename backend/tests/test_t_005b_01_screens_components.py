"""T-005b-01: screens/components 統一 read view.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : service 5 公開 API / router 3 endpoints / 既存
                       design_frames + design_mocks 無改変 (REUSE).
  AC-2 EVENT-DRIVEN  : list_all / count_by_type が dict 返却 / 2 秒以内.
  AC-3 STATE-DRIVEN  : read-only / audit_logs 書込なし / 既存 CRUD 互換.
  AC-4 UNWANTED      : invalid workspace_id で 400 / 不正 type_filter で ValueError /
                       limit 超過で 422 / hardcoded secret なし.
"""
from __future__ import annotations

import json as _json
import os
import re
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE = REPO_ROOT / "backend" / "services" / "screens_components.py"
ROUTER = REPO_ROOT / "backend" / "routers" / "screens_components.py"
EXISTING_FRAMES = REPO_ROOT / "backend" / "routers" / "design_frames.py"
EXISTING_MOCKS = REPO_ROOT / "backend" / "routers" / "design_mocks.py"


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def _stub_db(monkeypatch):
    """DB を stub 化 (実 DB なしで test)."""
    sample_frames = [
        {"id": 1, "workspace_id": 5, "branch_id": "main",
         "name": "Dashboard", "frame_type": "web",
         "url": "https://example.com/dash", "created_at": "2026-05-12",
         "updated_at": "2026-05-12"},
        {"id": 2, "workspace_id": 5, "branch_id": "main",
         "name": "MobileHome", "frame_type": "mobile",
         "url": None, "created_at": "2026-05-12", "updated_at": "2026-05-12"},
        {"id": 3, "workspace_id": 5, "branch_id": "main",
         "name": "Button", "frame_type": "component",
         "url": None, "created_at": "2026-05-12", "updated_at": "2026-05-12"},
        {"id": 4, "workspace_id": 5, "branch_id": "main",
         "name": "Modal", "frame_type": "partial",
         "url": None, "created_at": "2026-05-12", "updated_at": "2026-05-12"},
    ]
    sample_mocks = [
        {"id": 10, "workspace_id": 5, "name": "Mock1",
         "type": "frame", "penpot_file_id": "p1",
         "created_at": "2026-05-12", "updated_at": "2026-05-12"},
    ]

    from services import screens_components as sc

    class FakeDB:
        @staticmethod
        def fetchall(query, params):
            if "design_frames" in query:
                return [r for r in sample_frames if r["workspace_id"] == params[0]]
            if "design_mocks" in query:
                return [r for r in sample_mocks if r["workspace_id"] == params[0]]
            return []

    monkeypatch.setattr(sc, "_get_db_module", lambda: FakeDB)
    yield FakeDB


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS
# ══════════════════════════════════════════════════════════════════════


def test_ac1_service_exists():
    assert SERVICE.exists()


def test_ac1_router_exists():
    assert ROUTER.exists()


def test_ac1_service_public_api():
    from services import screens_components as sc
    for sym in (
        "list_screens", "list_components", "list_all", "count_by_type",
        "categorize_by_type",
        "SCREEN_TYPES", "COMPONENT_TYPES", "ALL_TYPES",
        "MAX_LIMIT", "DEFAULT_LIMIT",
    ):
        assert hasattr(sc, sym), f"missing service.{sym}"


def test_ac1_endpoints_registered():
    from main import app
    paths = [getattr(r, "path", "") for r in app.routes]
    assert "/api/workspaces/{workspace_id}/screens-components" in paths
    assert "/api/workspaces/{workspace_id}/screens-components/counts" in paths
    assert "/api/workspaces/{workspace_id}/screens-components/health" in paths


def test_ac1_existing_routers_unchanged():
    """既存 design_frames / design_mocks routers は本 PR で改変なし (REUSE)."""
    assert EXISTING_FRAMES.exists()
    assert EXISTING_MOCKS.exists()
    # 既存 routers に screens_components への依存を入れていないこと
    for path in (EXISTING_FRAMES, EXISTING_MOCKS):
        src = path.read_text(encoding="utf-8")
        assert "from services.screens_components" not in src
        assert "from routers.screens_components" not in src


def test_ac1_categorize_by_type_pure_function():
    from services import screens_components as sc
    assert sc.categorize_by_type("web") == "screen"
    assert sc.categorize_by_type("mobile") == "screen"
    assert sc.categorize_by_type("desktop") == "screen"
    assert sc.categorize_by_type("tablet") == "screen"
    assert sc.categorize_by_type("component") == "component"
    assert sc.categorize_by_type("partial") == "component"
    assert sc.categorize_by_type("fragment") == "component"
    assert sc.categorize_by_type("bogus") == "unknown"
    assert sc.categorize_by_type("") == "unknown"
    assert sc.categorize_by_type(None) == "unknown"  # type: ignore
    # 大文字も OK
    assert sc.categorize_by_type("WEB") == "screen"


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: list / count + 2 秒以内
# ══════════════════════════════════════════════════════════════════════


def test_ac2_list_screens_returns_screen_kind(_stub_db):
    from services import screens_components as sc
    out = sc.list_screens(5)
    assert all(r["kind"] == "screen" for r in out)
    assert all(r["source"] == "design_frames" for r in out)
    # web + mobile → 2 件
    assert len(out) == 2


def test_ac2_list_components_returns_component_kind(_stub_db):
    from services import screens_components as sc
    out = sc.list_components(5)
    assert all(r["kind"] == "component" for r in out)
    # component + partial → 2 件
    assert len(out) == 2


def test_ac2_list_screens_type_filter(_stub_db):
    from services import screens_components as sc
    out = sc.list_screens(5, type_filter="web")
    assert len(out) == 1
    assert out[0]["type"] == "web"


def test_ac2_list_all_structured_dict(_stub_db):
    from services import screens_components as sc
    out = sc.list_all(5)
    for key in ("workspace_id", "branch_id", "screens", "components",
                "design_mocks_count", "total"):
        assert key in out
    assert out["workspace_id"] == 5
    assert out["total"] == len(out["screens"]) + len(out["components"])


def test_ac2_count_by_type(_stub_db):
    from services import screens_components as sc
    out = sc.count_by_type(5)
    assert "by_type" in out
    assert "total" in out
    # web + mobile + component + partial → 4 frame, type ごと 1 件ずつ
    assert out["by_type"].get("web") == 1
    assert out["by_type"].get("mobile") == 1
    assert out["total"] == 4


def test_ac2_list_within_2sec(_stub_db):
    from services import screens_components as sc
    t0 = time.time()
    sc.list_all(5)
    elapsed = time.time() - t0
    assert elapsed < 2.0


def test_ac2_endpoint_list(client, _stub_db):
    r = client.get("/api/workspaces/5/screens-components")
    assert r.status_code == 200
    body = r.json()
    assert body["workspace_id"] == 5
    assert "screens" in body
    assert "components" in body


def test_ac2_endpoint_counts(client, _stub_db):
    r = client.get("/api/workspaces/5/screens-components/counts")
    assert r.status_code == 200
    body = r.json()
    assert "by_type" in body


def test_ac2_endpoint_health(client):
    r = client.get("/api/workspaces/5/screens-components/health")
    assert r.status_code == 200
    body = r.json()
    assert "db_available" in body
    assert body["max_limit"] == 500
    assert "web" in body["screen_types"]


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: read-only + audit-free
# ══════════════════════════════════════════════════════════════════════


def test_ac3_service_does_not_write_audit_logs():
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert "emit_event" not in code
    assert "from services.memory_service" not in code


def test_ac3_no_db_writes_in_source():
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    # 書込クエリを含まない
    for q in ("INSERT INTO", "UPDATE design_", "DELETE FROM"):
        assert q not in code, f"{q} detected (must be read-only)"


def _strip_comments(src: str) -> str:
    out_lines = []
    in_triple = False
    triple_char = None
    for raw in src.splitlines():
        line = raw
        if in_triple:
            if triple_char in line:
                line = line.split(triple_char, 1)[1]
                in_triple = False
            else:
                continue
        for ch in ('"""', "'''"):
            if ch in line:
                before, _, after = line.partition(ch)
                if ch in after:
                    line = before + after.split(ch, 1)[1]
                else:
                    line = before
                    in_triple = True
                    triple_char = ch
                break
        if "#" in line:
            line = line.split("#", 1)[0]
        if line.strip():
            out_lines.append(line)
    return "\n".join(out_lines)


def test_ac3_existing_frame_endpoint_still_present():
    """既存 design_frames endpoint が main.app に存在."""
    from main import app
    paths = [getattr(r, "path", "") for r in app.routes]
    # design_frames 系 endpoint が残っている
    assert any("/design/frames" in p for p in paths)


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED
# ══════════════════════════════════════════════════════════════════════


def test_ac4_invalid_workspace_id_raises():
    from services import screens_components as sc
    for bad in (0, -1, "5", None, 1.5, True):
        with pytest.raises(ValueError):
            sc.list_screens(bad)


def test_ac4_invalid_type_filter_raises():
    from services import screens_components as sc
    with pytest.raises(ValueError):
        sc.list_screens(5, type_filter="BOGUS")
    with pytest.raises(ValueError):
        # component type は list_screens では reject
        sc.list_screens(5, type_filter="component")
    with pytest.raises(ValueError):
        sc.list_components(5, type_filter="web")  # screen type は components で reject


def test_ac4_invalid_limit_raises():
    from services import screens_components as sc
    for bad in (0, -1, 501, 1000, "100", None):
        with pytest.raises(ValueError):
            sc.list_screens(5, limit=bad)


def test_ac4_endpoint_invalid_workspace_id_400(client):
    r = client.get("/api/workspaces/0/screens-components")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "screens_components.invalid"


def test_ac4_endpoint_oversized_limit_422(client, _stub_db):
    r = client.get("/api/workspaces/5/screens-components?limit=600")
    assert r.status_code == 422  # pydantic Query(le=500)


def test_ac4_no_hardcoded_secrets_in_source():
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", code)
    assert "SUPABASE_SERVICE_KEY" not in code
    assert "Bearer " not in code


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_005b_01_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-005b-01"), None)
    assert t is not None
    generic = [
        "as specified by feature",
        "When the relevant API endpoint or service function is invoked for T-005b-01",
        "While refactoring for T-005b-01 is in progress",
        "If invalid input or unauthorized actor is detected during T-005b-01",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], f"T-005b-01 still generic: {phrase!r}"
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "screens_components.py" in full
    assert "list_screens" in full
    assert "design_frames" in full


def test_tickets_t_005b_01_has_adr_link():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-005b-01"), None)
    assert t.get("adr_link") is not None
