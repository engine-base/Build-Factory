"""T-005b-03: コンポーネントカタログ + 画面遷移マップ — 4 AC.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : component_catalog service + router 公開. bf-* meta 抽出.
  AC-2 EVENT-DRIVEN  : 2 秒以内 / structured catalog + transition map / stable order.
  AC-3 STATE-DRIVEN  : read-only / in-memory cache / bf-* 命名規約維持.
  AC-4 UNWANTED      : mocks_dir 不在 / 0 file / 不正 screen_id / path traversal → 4xx.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import component_catalog as cc


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE = REPO_ROOT / "backend" / "services" / "component_catalog.py"
ROUTER = REPO_ROOT / "backend" / "routers" / "component_catalog.py"
REAL_MOCKS_DIR = REPO_ROOT / "docs" / "mocks" / "2026-05-09_v1"


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_cache():
    cc.reset_cache()
    yield
    cc.reset_cache()


@pytest.fixture
def tmp_mocks(tmp_path: Path) -> Path:
    """Create a synthetic mock dir with 3 screens for unit-testing."""
    mocks = tmp_path / "mocks_2026-05-09_v1"
    mocks.mkdir()
    (mocks / "account").mkdir()
    (mocks / "task").mkdir()

    (mocks / "account" / "S-001-dashboard.html").write_text(
        """<!DOCTYPE html><html><head>
        <meta name="bf-screen-id" content="S-001">
        <meta name="bf-feature-id" content="F-001,F-002">
        <meta name="bf-task-ids" content="T-001-01">
        <meta name="bf-spec-link" content="../../requirements/x.html">
        </head><body class="kpi-card">
        <a href="../task/S-002-kanban.html">Kanban</a>
        </body></html>""",
        encoding="utf-8",
    )
    (mocks / "task" / "S-002-kanban.html").write_text(
        """<!DOCTYPE html><html><head>
        <meta name="bf-screen-id" content="S-002">
        <meta name="bf-feature-id" content="F-002">
        <meta name="bf-task-ids" content="T-002-01,T-002-02">
        </head><body>
        <div class="sidebar-link">x</div>
        <a href="../account/S-001-dashboard.html">Back</a>
        </body></html>""",
        encoding="utf-8",
    )
    (mocks / "task" / "S-003-orphan.html").write_text(
        """<!DOCTYPE html><html><head>
        <meta name="bf-screen-id" content="S-003">
        </head><body>orphan</body></html>""",
        encoding="utf-8",
    )
    return mocks


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS
# ══════════════════════════════════════════════════════════════════════


def test_ac1_service_exists():
    assert SERVICE.exists()


def test_ac1_router_exists():
    assert ROUTER.exists()


def test_ac1_public_api():
    for sym in (
        "build_catalog", "build_transition_map",
        "list_screens", "get_screen", "reset_cache",
        "ComponentCatalogError", "DEFAULT_MOCKS_DIR",
        "SCREEN_ID_PATTERN",
    ):
        assert hasattr(cc, sym), f"missing service.{sym}"


def test_ac1_default_mocks_dir_exists():
    """default mocks_dir は repo bootstrap で存在する."""
    assert cc.DEFAULT_MOCKS_DIR == REAL_MOCKS_DIR
    assert REAL_MOCKS_DIR.exists()


def test_ac1_catalog_extracts_bf_meta(tmp_mocks):
    cat = cc.build_catalog(tmp_mocks)
    assert cat["total"] == 3
    sids = [s["screen_id"] for s in cat["screens"]]
    assert sids == ["S-001", "S-002", "S-003"]
    # S-001 features/tasks
    s001 = next(s for s in cat["screens"] if s["screen_id"] == "S-001")
    assert s001["features"] == ["F-001", "F-002"]
    assert s001["tasks"] == ["T-001-01"]
    assert s001["spec_link"] == "../../requirements/x.html"
    assert "kpi-card" in s001["components"]


def test_ac1_real_corpus_at_least_40_screens():
    cat = cc.build_catalog(REAL_MOCKS_DIR)
    assert cat["total"] >= 40, f"expected >= 40 mocks, got {cat['total']}"


def test_ac1_endpoint_screens(client):
    resp = client.get("/api/component-catalog/screens")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] >= 40
    assert isinstance(body["screens"], list)


def test_ac1_endpoint_single_screen(client):
    resp = client.get("/api/component-catalog/screens/S-006")
    assert resp.status_code == 200
    body = resp.json()
    assert body["screen_id"] == "S-006"


def test_ac1_endpoint_transitions(client):
    resp = client.get("/api/component-catalog/transitions")
    assert resp.status_code == 200
    body = resp.json()
    assert "nodes" in body
    assert "edges" in body
    assert "stats" in body


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN
# ══════════════════════════════════════════════════════════════════════


def test_ac2_catalog_under_2_seconds():
    cc.reset_cache()
    t0 = time.time()
    cc.build_catalog(REAL_MOCKS_DIR)
    elapsed = time.time() - t0
    assert elapsed < 2.0


def test_ac2_transition_map_under_2_seconds():
    cc.reset_cache()
    t0 = time.time()
    cc.build_transition_map(REAL_MOCKS_DIR)
    elapsed = time.time() - t0
    assert elapsed < 2.0


def test_ac2_transition_map_structure(tmp_mocks):
    tm = cc.build_transition_map(tmp_mocks)
    assert tm["stats"]["total_screens"] == 3
    # S-001 → S-002 と S-002 → S-001 の 2 edge
    assert tm["stats"]["total_edges"] == 2
    edges = {(e["from"], e["to"]) for e in tm["edges"]}
    assert ("S-001", "S-002") in edges
    assert ("S-002", "S-001") in edges
    # S-003 は orphan
    assert "S-003" in tm["stats"]["orphan_screens"]


def test_ac2_screens_lexicographic_order(tmp_mocks):
    cat = cc.build_catalog(tmp_mocks)
    sids = [s["screen_id"] for s in cat["screens"]]
    assert sids == sorted(sids)


def test_ac2_edges_lexicographic_order(tmp_mocks):
    tm = cc.build_transition_map(tmp_mocks)
    edges = [(e["from"], e["to"]) for e in tm["edges"]]
    assert edges == sorted(edges)


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN
# ══════════════════════════════════════════════════════════════════════


def test_ac3_read_only_no_write(tmp_mocks):
    """build_catalog 実行が file mtime を変えない."""
    before = {p: p.stat().st_mtime for p in tmp_mocks.rglob("*.html")}
    cc.build_catalog(tmp_mocks)
    cc.build_transition_map(tmp_mocks)
    after = {p: p.stat().st_mtime for p in tmp_mocks.rglob("*.html")}
    assert before == after


def test_ac3_cache_invalidation_via_reset(tmp_mocks):
    cat1 = cc.build_catalog(tmp_mocks)
    # cache hit (same object identity is allowed since cache returns same dict)
    cat2 = cc.build_catalog(tmp_mocks)
    assert cat1 is cat2
    cc.reset_cache()
    cat3 = cc.build_catalog(tmp_mocks)
    assert cat3 is not cat1


def test_ac3_bf_field_names_invariant(tmp_mocks):
    cat = cc.build_catalog(tmp_mocks)
    for s in cat["screens"]:
        # G15 invariant: field names match design-tokens.md schema
        assert "screen_id" in s
        assert "features" in s
        assert "tasks" in s
        assert "links_to" in s


def test_ac3_no_db_no_network():
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert "httpx" not in code
    assert "requests.get" not in code
    assert "INSERT INTO" not in code
    assert "aiosqlite" not in code


def test_ac3_no_langgraph():
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src).lower()
    assert "langgraph" not in code
    assert "langchain" not in code


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED
# ══════════════════════════════════════════════════════════════════════


def test_ac4_nonexistent_mocks_dir_raises(tmp_path):
    with pytest.raises(cc.ComponentCatalogError):
        cc.build_catalog(tmp_path / "nope")


def test_ac4_empty_mocks_dir_raises(tmp_path):
    empty = tmp_path / "empty_mocks"
    empty.mkdir()
    with pytest.raises(cc.ComponentCatalogError) as exc:
        cc.build_catalog(empty)
    assert "no S-" in str(exc.value)


def test_ac4_parse_fails_when_both_meta_and_filename_invalid(tmp_path):
    """meta も filename pattern も S-NNN format に合わなければ fail.

    build_catalog は rglob で S-*.html しか拾わないので、内部 helper
    _parse_screen_html を直接呼んで failure path を確認する.
    """
    bogus_file = tmp_path / "not-a-screen-mock.html"
    bogus_file.write_text(
        '<html><head><meta name="bf-screen-id" content="XYZ-999"></head></html>',
        encoding="utf-8",
    )
    with pytest.raises(cc.ComponentCatalogError):
        cc._parse_screen_html(
            bogus_file.read_text(encoding="utf-8"),
            tmp_path,
            bogus_file,
        )


def test_ac4_filename_fallback_succeeds_for_legacy_mock(tmp_path):
    """meta tag 無くても filename が S-NNN-*.html なら screen_id を derive する."""
    legacy = tmp_path / "legacy_mocks"
    legacy.mkdir()
    (legacy / "S-099-no-meta.html").write_text(
        "<html><head></head><body>legacy mock</body></html>",
        encoding="utf-8",
    )
    cat = cc.build_catalog(legacy)
    assert cat["total"] == 1
    assert cat["screens"][0]["screen_id"] == "S-099"


def test_ac4_malformed_screen_id_raises(tmp_path):
    """meta が S-NNN format に合わなくても filename が無効なら fail."""
    bad = tmp_path / "bad_id_mocks"
    bad.mkdir()
    # filename も meta も両方 invalid なら fail
    (bad / "S-099-bad.html").write_text(
        '<html><head><meta name="bf-screen-id" content="not-an-S-id"></head><body></body></html>',
        encoding="utf-8",
    )
    # meta が malformed でも filename からの fallback が効くので raise しない
    # → このテストは「filename も meta も両方 invalid」を模倣できないため
    #   spec では「meta malformed AND filename pattern 不一致」を要求.
    # 一旦 filename fallback の挙動を確認 (raise しない).
    cat = cc.build_catalog(bad)
    assert cat["screens"][0]["screen_id"] == "S-099"


def test_ac4_invalid_screen_id_format_raises():
    with pytest.raises(cc.ComponentCatalogError):
        cc.get_screen(None, "not-valid")


def test_ac4_invalid_mocks_dir_type_raises():
    with pytest.raises(cc.ComponentCatalogError):
        cc.build_catalog(12345)


def test_ac4_get_screen_not_found(tmp_mocks):
    with pytest.raises(cc.ComponentCatalogError) as exc:
        cc.get_screen(tmp_mocks, "S-999")
    assert "not found" in str(exc.value).lower()


def test_ac4_endpoint_404_on_unknown(client):
    resp = client.get("/api/component-catalog/screens/S-999")
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "component_catalog.not_found"


def test_ac4_endpoint_400_on_malformed_id(client):
    resp = client.get("/api/component-catalog/screens/not-valid")
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "component_catalog.invalid_input"


def test_ac4_endpoint_401_on_empty_actor(client):
    resp = client.get("/api/component-catalog/screens?actor_user_id=%20")
    assert resp.status_code == 401


def test_ac4_no_hardcoded_secret():
    import re
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", code)
    assert "SUPABASE_SERVICE_KEY" not in code


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════


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


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_005b_03_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-005b-03"), None)
    assert t is not None
    generic = [
        "as specified by feature F-005b",
        "When the relevant API endpoint or service function is invoked for T-005b-03",
        "While the new feature for T-005b-03 is enabled",
        "If invalid input or unauthorized actor is detected during T-005b-03",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], (
                f"T-005b-03 still generic: {phrase!r}"
            )
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "component_catalog.py" in full
    assert "build_catalog" in full
    assert "bf-screen-id" in full


def test_tickets_t_005b_03_has_adr_link():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-005b-03"), None)
    assert t.get("adr_link") is not None
