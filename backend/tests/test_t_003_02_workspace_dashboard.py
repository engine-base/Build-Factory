"""T-003-02: AI 社員召喚 API + Workspace Dashboard — 7 AC 1:1.

AC マッピング:
  AC-1 UBIQUITOUS    : 5 KPI cards (progress, completed_tasks, running_sessions,
                       monthly_cost_jpy, pending_approvals).
  AC-2 EVENT-DRIVEN  : dashboard load 800ms (P95) 以内.
  AC-3 STATE (#1)    : 実行中 session で pulse-dot animation (UI / mock_link).
                       backend は running_sessions count を提供 (UI 側で animation).
  AC-3 STATE (#2)    : handoff は claude-agent-sdk Subagent 経由 / LangGraph 禁止.
  AC-4 OPTIONAL      : 複数 workspace で quick switch (UI / 既存 list_workspaces).
  AC-5 UNWANTED (#1) : 権限なし workspace は 403 + dashboard render しない.
  AC-5 UNWANTED (#2) : handoff path への LangGraph import → lint で fail.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import workspace_dashboard as wd
from services.workspace_dashboard import (
    DASHBOARD_KPI_KEYS,
    DashboardStatsError,
    get_dashboard_stats,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _fake_db(monkeypatch):
    """workspace_service の get_workspace / get_member を mock (DB 不要)."""
    workspaces: dict[int, dict] = {1: {"id": 1, "name": "ws1"}}
    members: dict[tuple[int, str], dict] = {(1, "alice"): {"role": "admin"}}

    async def fake_get_workspace(wid):
        return workspaces.get(wid)

    async def fake_get_member(wid, user_id):
        return members.get((wid, user_id))

    import services.workspace_service as ws_mod
    monkeypatch.setattr(ws_mod, "get_workspace", fake_get_workspace)
    monkeypatch.setattr(ws_mod, "get_member", fake_get_member)
    yield {"workspaces": workspaces, "members": members}


class _FakeDBConn:
    """psycopg/aiosqlite connection を全 stub する dummy."""
    async def __aenter__(self):
        return self
    async def __aexit__(self, *a):
        pass
    async def execute(self, *a, **k):  # pragma: no cover (stubbed away)
        return self
    async def fetchone(self):  # pragma: no cover
        return None


@pytest.fixture
def stub_db_stats(monkeypatch):
    """workspace_dashboard 内部の DB 関数を stub (sqlite/postgres 不要)."""
    state = {
        "total_tasks": 10,
        "completed_tasks": 4,
        "running_sessions": 2,
        "monthly_cost_jpy": 1234.5,
        "pending_approvals": 3,
    }

    async def fake_count_tasks(db, wid):
        return state["total_tasks"], state["completed_tasks"]

    async def fake_count_running(db, wid):
        return state["running_sessions"]

    async def fake_sum_cost(db, wid, *, now):
        return state["monthly_cost_jpy"]

    async def fake_count_pending(db, wid):
        return state["pending_approvals"]

    def fake_connect(_path):
        return _FakeDBConn()

    monkeypatch.setattr(wd, "_count_tasks", fake_count_tasks)
    monkeypatch.setattr(wd, "_count_running_sessions", fake_count_running)
    monkeypatch.setattr(wd, "_sum_monthly_cost", fake_sum_cost)
    monkeypatch.setattr(wd, "_count_pending_approvals", fake_count_pending)
    monkeypatch.setattr(wd.aiosqlite, "connect", fake_connect)
    return state


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS: 5 KPI cards
# ══════════════════════════════════════════════════════════════════════


def test_ac1_dashboard_kpi_keys_exactly_5():
    assert set(DASHBOARD_KPI_KEYS) == {
        "progress", "completed_tasks", "running_sessions",
        "monthly_cost_jpy", "pending_approvals",
    }
    assert len(DASHBOARD_KPI_KEYS) == 5


def test_ac1_get_dashboard_stats_returns_all_5_kpi(stub_db_stats):
    out = asyncio.run(get_dashboard_stats(1))
    for key in DASHBOARD_KPI_KEYS:
        assert key in out
    # 値の整合
    assert out["progress"] == round(4 / 10, 6)
    assert out["completed_tasks"] == 4
    assert out["running_sessions"] == 2
    assert out["monthly_cost_jpy"] == 1234.5
    assert out["pending_approvals"] == 3


def test_ac1_progress_zero_when_no_tasks(stub_db_stats):
    stub_db_stats["total_tasks"] = 0
    stub_db_stats["completed_tasks"] = 0
    out = asyncio.run(get_dashboard_stats(1))
    assert out["progress"] == 0.0


def test_ac1_progress_full_when_all_completed(stub_db_stats):
    stub_db_stats["total_tasks"] = 5
    stub_db_stats["completed_tasks"] = 5
    out = asyncio.run(get_dashboard_stats(1))
    assert out["progress"] == 1.0


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: 800ms (P95) 以内
# ══════════════════════════════════════════════════════════════════════


def test_ac2_dashboard_within_800ms(stub_db_stats):
    """単発 stub 環境では 800ms 余裕で達成. duration_ms field 検証."""
    t0 = time.time()
    out = asyncio.run(get_dashboard_stats(1))
    elapsed_ms = (time.time() - t0) * 1000
    assert elapsed_ms < 800
    assert out["duration_ms"] < 800


def test_ac2_dashboard_p95_over_20_runs(stub_db_stats):
    """20 回実行して全 800ms 以内 (P95 検証)."""
    times = []
    for _ in range(20):
        t0 = time.time()
        asyncio.run(get_dashboard_stats(1))
        times.append((time.time() - t0) * 1000)
    times.sort()
    p95 = times[int(len(times) * 0.95) - 1]
    assert p95 < 800, f"P95={p95:.1f}ms exceeded 800ms"


def test_ac2_endpoint_within_800ms(client, stub_db_stats):
    t0 = time.time()
    r = client.get("/api/workspaces/1/dashboard")
    elapsed_ms = (time.time() - t0) * 1000
    assert r.status_code == 200
    assert elapsed_ms < 800


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE (#1): running_sessions count 提供 (UI animation 用)
# ══════════════════════════════════════════════════════════════════════


def test_ac3_state1_running_sessions_count_provided(stub_db_stats):
    """UI が pulse-dot animation を出すため running_sessions count が返る."""
    out = asyncio.run(get_dashboard_stats(1))
    assert "running_sessions" in out
    assert isinstance(out["running_sessions"], int)


def test_ac3_state1_running_sessions_status_includes_executing():
    """RUNNING_SESSION_STATUSES に running / executing / in_progress 含む."""
    assert "running" in wd.RUNNING_SESSION_STATUSES
    assert "executing" in wd.RUNNING_SESSION_STATUSES
    assert "in_progress" in wd.RUNNING_SESSION_STATUSES


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE (#2): handoff は SDK Subagent / LangGraph 禁止
# ══════════════════════════════════════════════════════════════════════


def test_ac3_state2_workspace_dashboard_no_langgraph_import():
    """workspace_dashboard.py 内に LangGraph / LangChain import が無い."""
    src = (REPO_ROOT / "backend" / "services" / "workspace_dashboard.py").read_text(encoding="utf-8")
    for forbidden in ("import langgraph", "from langgraph", "import langchain", "from langchain"):
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert forbidden not in line, f"forbidden import: {forbidden}"


def test_ac3_state2_secretary_chat_no_langgraph():
    src = (REPO_ROOT / "backend" / "services" / "secretary_chat.py").read_text(encoding="utf-8")
    for forbidden in ("import langgraph", "from langgraph", "import langchain", "from langchain"):
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert forbidden not in line


def test_ac3_state2_delegation_service_no_langgraph():
    src = (REPO_ROOT / "backend" / "services" / "delegation_service.py").read_text(encoding="utf-8")
    for forbidden in ("import langgraph", "from langgraph", "import langchain", "from langchain"):
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert forbidden not in line


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL: quick switch (複数 workspace 一覧 endpoint 利用)
# ══════════════════════════════════════════════════════════════════════


def test_ac4_list_workspaces_endpoint_available(client):
    """sidebar quick switch に必要な /api/workspaces 一覧 endpoint が登録されている.
    (DB 接続を要するため status code は問わず, 404 でない=routing 成立を確認)."""
    routes = [getattr(r, "path", "") for r in client.app.routes]
    assert "/api/workspaces" in routes


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED (#1): 権限なし workspace は 403
# ══════════════════════════════════════════════════════════════════════


def test_ac5_endpoint_returns_404_for_unknown_workspace(client, stub_db_stats):
    r = client.get("/api/workspaces/99999/dashboard")
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == "workspaces.not_found"


def test_ac5_endpoint_returns_403_for_non_member(client, stub_db_stats):
    """user_id 指定で member でない場合 403."""
    r = client.get(
        "/api/workspaces/1/dashboard",
        params={"user_id": "stranger"},
    )
    assert r.status_code == 403
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == "workspaces.forbidden"


def test_ac5_endpoint_does_not_render_dashboard_on_403(client, stub_db_stats):
    r = client.get(
        "/api/workspaces/1/dashboard",
        params={"user_id": "stranger"},
    )
    assert r.status_code == 403
    # AC-5: dashboard を render しない (KPI key を含まない)
    body = r.json()
    assert "progress" not in body
    assert "completed_tasks" not in body


def test_ac5_endpoint_allows_member(client, stub_db_stats):
    r = client.get(
        "/api/workspaces/1/dashboard",
        params={"user_id": "alice"},
    )
    assert r.status_code == 200


def test_ac5_endpoint_invalid_workspace_id_400(client, stub_db_stats):
    r = client.get("/api/workspaces/0/dashboard")
    assert r.status_code == 400


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED (#2): lint で LangGraph 機械検知
# ══════════════════════════════════════════════════════════════════════


def test_ac5_lint_check_no_langgraph_covers_handoff_path():
    """check_no_langgraph targets に secretary_chat / delegation_service が含まれる."""
    script = (REPO_ROOT / "scripts" / "lint-mock.sh").read_text(encoding="utf-8")
    assert "secretary_chat.py" in script
    assert "delegation_service.py" in script


def test_ac5_lint_check_no_langgraph_passes_on_clean_code():
    r = subprocess.run(
        ["bash", "scripts/lint-mock.sh", "--no-langgraph"],
        capture_output=True, text=True, timeout=30, cwd=str(REPO_ROOT),
    )
    assert r.returncode == 0, f"lint failed: {r.stdout} {r.stderr}"
    assert "OK" in r.stdout


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED (validation)
# ══════════════════════════════════════════════════════════════════════


def test_validate_workspace_id_rejects_non_positive():
    for bad in (0, -1, True, False, "1", None):
        with pytest.raises(DashboardStatsError):
            asyncio.run(get_dashboard_stats(bad))


def test_endpoint_4xx_form_uniformity(client, stub_db_stats):
    cases = [
        ("/api/workspaces/0/dashboard", {}, 400),
        ("/api/workspaces/99999/dashboard", {}, 404),
        ("/api/workspaces/1/dashboard", {"user_id": "stranger"}, 403),
        ("/api/workspaces/1/dashboard", {"user_id": ""}, 400),
    ]
    for path, params, expected in cases:
        r = client.get(path, params=params)
        assert r.status_code == expected, f"{path} {params}: {r.status_code}: {r.text}"
        detail = r.json()["detail"]
        assert isinstance(detail, dict)
        assert detail.get("code", "").startswith("workspaces.")
        assert isinstance(detail.get("message", ""), str) and detail["message"]


# ══════════════════════════════════════════════════════════════════════
# Cross-reference: tickets + ADR + mock_link
# ══════════════════════════════════════════════════════════════════════


def test_ticket_t_003_02_has_7_ac():
    import json
    tj = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.loads(tj.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-003-02"), None)
    assert t is not None
    assert len(t["acceptance_criteria"]) == 7
    assert t.get("critical") is True
    assert "T-M28-01" in t["deps"]


def test_mock_link_exists():
    """S-012-workspace-dashboard.html mock が存在."""
    mock = REPO_ROOT / "docs" / "mocks" / "2026-05-09_v1" / "workspace" / "S-012-workspace-dashboard.html"
    assert mock.exists()


def test_module_docstring_documents_ac():
    doc = wd.__doc__ or ""
    for ac in ("AC-1", "AC-2", "AC-3", "AC-5"):
        assert ac in doc
    assert "5 KPI" in doc
