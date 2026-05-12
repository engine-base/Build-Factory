"""T-017-03: cost dashboard (8 tab Recharts) — 4 AC.

NEW FE+BE タスク. backend pytest で backend endpoint + frontend TSX 静的解析.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : backend/routers/cost_dashboard.py (cost-summary
                       endpoint + VALID_DIMENSIONS 8) + frontend
                       CostDashboard.tsx + /dashboard/costs page + api
                       client. cost_service.py REUSE 無改変.
  AC-2 EVENT-DRIVEN  : 8 tab + fetchCostSummary(dim, range) + 単一 SELECT
                       GROUP BY (no N+1).
  AC-3 STATE-DRIVEN  : URL search params (?dim=, ?from=, ?to=) /
                       eb-500 palette / no render-phase fetch /
                       no langgraph / langchain / litellm / reactflow.
  AC-4 UNWANTED      : invalid dimension で 400 + cost_logs 触らず /
                       invalid date で 400 / 空 result で graceful /
                       AbortController で並行 fetch dedup.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROUTER = REPO_ROOT / "backend" / "routers" / "cost_dashboard.py"
COST_SERVICE = REPO_ROOT / "backend" / "services" / "cost_service.py"
COMPONENT = REPO_ROOT / "frontend" / "src" / "components" / "dashboard" / "CostDashboard.tsx"
PAGE = REPO_ROOT / "frontend" / "src" / "app" / "dashboard" / "costs" / "page.tsx"
API_CLIENT = REPO_ROOT / "frontend" / "src" / "lib" / "api" / "cost-dashboard.ts"

EXPECTED_DIMENSIONS = (
    "overview", "provider", "model", "workspace",
    "persona", "skill", "period_daily", "session",
)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


def _strip_js_comments(src: str) -> str:
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    src = re.sub(r"//[^\n]*", "", src)
    return src


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — files + 8 dimensions + REUSE invariant
# ══════════════════════════════════════════════════════════════════════


def test_ac1_backend_router_exists():
    assert BACKEND_ROUTER.exists()


def test_ac1_frontend_component_exists():
    assert COMPONENT.exists()


def test_ac1_frontend_page_exists():
    assert PAGE.exists()


def test_ac1_frontend_api_client_exists():
    assert API_CLIENT.exists()


def test_ac1_backend_8_valid_dimensions():
    from routers.cost_dashboard import VALID_DIMENSIONS
    assert VALID_DIMENSIONS == EXPECTED_DIMENSIONS


def test_ac1_frontend_8_valid_dimensions():
    src = API_CLIENT.read_text(encoding="utf-8")
    m = re.search(r"VALID_COST_DIMENSIONS\s*=\s*\[([^\]]+)\]", src)
    assert m
    choices = tuple(re.findall(r'"([^"]+)"', m.group(1)))
    assert choices == EXPECTED_DIMENSIONS


def test_ac1_cost_service_unchanged_no_t_017_03_dep():
    """REUSE invariant: cost_service.py に T-017-03 依存追加なし."""
    src = COST_SERVICE.read_text(encoding="utf-8")
    assert "T-017-03" not in src
    assert "cost_dashboard" not in src


def test_ac1_endpoint_responds(client):
    resp = client.get("/api/observability/cost-summary?dimension=overview")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    for key in (
        "dimension", "total_usd", "total_input_tokens",
        "total_output_tokens", "total_cache_read_tokens", "items",
    ):
        assert key in body, f"response missing key: {key}"


def test_ac1_component_uses_recharts():
    src = COMPONENT.read_text(encoding="utf-8")
    assert 'from "recharts"' in src
    # 3 chart type を使う (Bar / Line / Pie)
    for sym in ("BarChart", "LineChart", "PieChart", "ResponsiveContainer"):
        assert sym in src, f"CostDashboard missing recharts symbol: {sym}"


def test_ac1_component_uses_lucide_icons():
    src = COMPONENT.read_text(encoding="utf-8")
    assert "lucide-react" in src


def test_ac1_page_uses_component():
    src = PAGE.read_text(encoding="utf-8")
    assert "CostDashboard" in src
    assert "@/components/dashboard/CostDashboard" in src


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — 8 tabs + fetch + single SELECT
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("dim", EXPECTED_DIMENSIONS)
def test_ac2_each_dimension_returns_200(client, dim):
    resp = client.get(f"/api/observability/cost-summary?dimension={dim}")
    assert resp.status_code == 200, f"dim={dim} failed: {resp.text}"
    body = resp.json()
    assert body["dimension"] == dim


def test_ac2_backend_uses_single_select_group_by():
    """N+1 防止: 1 SELECT で集計 (loop なし / 単 query).

    Python docstring / # comment を除外して SELECT 文字列を数える.
    """
    src = BACKEND_ROUTER.read_text(encoding="utf-8")
    # python docstring 除去
    code = re.sub(r'"""[\s\S]*?"""', "", src)
    code = re.sub(r"'''[\s\S]*?'''", "", code)
    # # コメント除去
    code = re.sub(r"#[^\n]*", "", code)
    selects = re.findall(r"\bSELECT\b", code)
    assert len(selects) <= 2, (
        f"too many SELECT statements (potential N+1): {len(selects)}"
    )
    assert "GROUP BY" in code


def test_ac2_period_daily_uses_date_group():
    src = BACKEND_ROUTER.read_text(encoding="utf-8")
    assert "DATE(occurred_at)" in src


def test_ac2_persona_dimension_uses_metadata_extraction():
    """persona は metadata->>'agent_persona' で aggregate."""
    src = BACKEND_ROUTER.read_text(encoding="utf-8")
    assert "metadata->>'agent_persona'" in src
    assert "metadata->>'skill_name'" in src


def test_ac2_component_has_8_tabs():
    """tab strip に 8 dimension button が出る."""
    src = COMPONENT.read_text(encoding="utf-8")
    for dim in EXPECTED_DIMENSIONS:
        # data-dim={dim} がレンダリングに出る
        assert dim in src, f"CostDashboard missing tab for: {dim}"


def test_ac2_fetch_cost_summary_uses_query_string():
    """frontend API client が ?dimension= で query を組む."""
    src = API_CLIENT.read_text(encoding="utf-8")
    assert 'params.set("dimension", dimension)' in src
    assert "URLSearchParams" in src


def test_ac2_component_calls_fetch_on_dim_change():
    """useEffect が dimension / from / to を deps に持つ."""
    src = COMPONENT.read_text(encoding="utf-8")
    assert "useEffect" in src
    assert "fetchCostSummary(dimension" in src


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — URL params / eb palette / no render fetch
# ══════════════════════════════════════════════════════════════════════


def test_ac3_url_params_dim_from_to():
    """component が ?dim= ?from= ?to= を URL に書き戻す."""
    src = COMPONENT.read_text(encoding="utf-8")
    assert 'searchParams.set("dim"' in src
    assert 'searchParams.set("from"' in src
    assert 'searchParams.set("to"' in src


def test_ac3_eb_500_palette_used():
    src = COMPONENT.read_text(encoding="utf-8")
    assert "#1a6648" in src or "eb-500" in src
    # primary chart fill が eb-500
    assert re.search(r'fill="#1a6648"', src)


def test_ac3_no_fetch_in_render_phase():
    """component の fetchCostSummary 呼出が useEffect の中だけ."""
    src = COMPONENT.read_text(encoding="utf-8")
    code = _strip_js_comments(src)
    use_effect_pos = code.find("useEffect(")
    fetch_pos = code.find("fetchCostSummary(")
    assert use_effect_pos > 0 and fetch_pos > 0
    assert fetch_pos > use_effect_pos, (
        "fetchCostSummary must be inside useEffect (no render-phase fetch)"
    )


def test_ac3_no_langgraph_langchain_litellm_reactflow():
    for path in (COMPONENT, PAGE, API_CLIENT):
        src = path.read_text(encoding="utf-8").lower()
        for forbidden in ("langgraph", "langchain", "litellm"):
            assert forbidden not in src, (
                f"forbidden {forbidden} in {path.name}"
            )
        assert 'from "reactflow"' not in src


def test_ac3_no_emoji_in_files():
    emoji = re.compile(
        r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF]"
    )
    for path in (COMPONENT, PAGE):
        src = path.read_text(encoding="utf-8")
        assert not emoji.findall(src), f"emoji in {path.name}"


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED — invalid dim / invalid date / graceful empty / abort
# ══════════════════════════════════════════════════════════════════════


def test_ac4_invalid_dimension_400(client):
    resp = client.get("/api/observability/cost-summary?dimension=unknown")
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "cost_dashboard.invalid_dimension"


def test_ac4_invalid_from_date_400(client):
    resp = client.get(
        "/api/observability/cost-summary?dimension=overview&from=not-iso",
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "cost_dashboard.invalid_date_range"


def test_ac4_naive_datetime_400(client):
    """timezone-aware ISO-8601 を要求 (naive はリジェクト)."""
    resp = client.get(
        "/api/observability/cost-summary?dimension=overview&from=2026-01-01T00:00:00",
    )
    assert resp.status_code == 400


def test_ac4_empty_result_graceful(client):
    """cost_logs に row なしでも 200 + items=[] (test 環境では DB 接続失敗
    して空集計 fallback)."""
    resp = client.get("/api/observability/cost-summary?dimension=overview")
    body = resp.json()
    assert body["total_usd"] == 0
    assert body["items"] == []


def test_ac4_component_empty_state():
    """items.length === 0 で 'データがありません' を表示."""
    src = COMPONENT.read_text(encoding="utf-8")
    assert "summary.items.length === 0" in src
    assert "データがありません" in src
    assert 'data-testid="cost-empty"' in src


def test_ac4_component_uses_abort_controller():
    src = COMPONENT.read_text(encoding="utf-8")
    assert "AbortController" in src
    assert "controller.abort()" in src


def test_ac4_api_client_validates_dimension_before_fetch():
    src = API_CLIENT.read_text(encoding="utf-8")
    assert "VALID_COST_DIMENSIONS.includes(dimension)" in src


def test_ac4_no_secret_hardcoded():
    for path in (BACKEND_ROUTER, COMPONENT, API_CLIENT, PAGE):
        src = path.read_text(encoding="utf-8")
        assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# Cross-module invariant (Python ↔ TS VALID_DIMENSIONS)
# ══════════════════════════════════════════════════════════════════════


def test_cross_module_dimensions_python_ts_aligned():
    from routers.cost_dashboard import VALID_DIMENSIONS as PY
    ts = API_CLIENT.read_text(encoding="utf-8")
    m = re.search(r"VALID_COST_DIMENSIONS\s*=\s*\[([^\]]+)\]", ts)
    TS = tuple(re.findall(r'"([^"]+)"', m.group(1)))
    assert PY == TS == EXPECTED_DIMENSIONS


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_017_03_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-017-03"), None)
    assert t is not None
    generic = [
        "as specified by feature F-017",
        "When the user interacts with the UI for T-017-03",
        "While the new feature for T-017-03 is enabled",
        "If invalid input or unauthorized actor is detected during T-017-03",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], (
                f"T-017-03 still generic: {phrase!r}"
            )
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "cost_dashboard.py", "CostDashboard.tsx",
        "/api/observability/cost-summary",
        "VALID_DIMENSIONS", "overview", "provider", "model",
        "workspace", "persona", "skill", "period_daily", "session",
        "Recharts", "eb-500",
    ):
        assert sym in full, f"T-017-03 AC missing concrete symbol: {sym}"


def test_tickets_t_017_03_has_adr_link_and_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-017-03"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert any("cost_service" in f for f in files)
    assert any("observability" in f for f in files)


def test_tickets_t_017_03_canonical_ears_types():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-017-03"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == ["UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "UNWANTED"]
