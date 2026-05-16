"""T-V3-B-23 / F-017: Observability backend tests.

Covered endpoints:
  - GET  /api/observability/cost-summary/export.csv  (AC-F5/F6)
  - POST /api/workspaces/{id}/token-limit            (AC-F7/F8/F9)
  - GET  /api/workspaces/{id}/token-limit            (補完)

AC マッピング (1:1):
  AC-F1 EVENT-DRIVEN  : cost-summary (既存 T-017-03 で担保) — smoke 確認
  AC-F2 STATE-DRIVEN  : monthly >= 80% で cost_limit_warning emit
  AC-F3 UNWANTED      : monthly > limit で cost_limit_breached emit (block)
  AC-F4 UBIQUITOUS    : cost_service.record_cost が tokens/cost/provider 必須 (REUSE)
  AC-F5 EVENT-DRIVEN  : export.csv が 200 + text/csv + csv header
  AC-F6 UNWANTED      : export.csv に auth 無し → 401
  AC-F7 EVENT-DRIVEN  : token-limit POST が 201 + limit_usd_per_month + updated_at
  AC-F8 UNWANTED      : token-limit POST 無 auth → 401
  AC-F9 UNWANTED      : token-limit POST validation 失敗 → 422 + field-level map
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest
from fastapi.testclient import TestClient


REPO_ROOT_MARK = "T-V3-B-23"


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client_authed():
    """Default: BUILD_FACTORY_DEV_BYPASS_AUTH=1 → masato dev user 注入.

    env は test 終了時に元の値に戻す (他 test が SUPABASE 設定状態に依存するため).
    """
    saved = {
        "BUILD_FACTORY_DEV_BYPASS_AUTH":
            os.environ.get("BUILD_FACTORY_DEV_BYPASS_AUTH"),
        "DISABLE_BACKGROUND_WORKERS":
            os.environ.get("DISABLE_BACKGROUND_WORKERS"),
    }
    os.environ["BUILD_FACTORY_DEV_BYPASS_AUTH"] = "1"
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    # auth_middleware は import 時に env を読むので reload
    import importlib
    import services.auth_middleware as am
    importlib.reload(am)
    from main import app
    yield TestClient(app, raise_server_exceptions=False)
    # restore
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    importlib.reload(am)


@pytest.fixture
def client_no_auth(monkeypatch):
    """BUILD_FACTORY_DEV_BYPASS_AUTH=0 で 401 path をテスト."""
    monkeypatch.setenv("BUILD_FACTORY_DEV_BYPASS_AUTH", "0")
    import importlib
    import services.auth_middleware as am
    importlib.reload(am)
    from main import app
    yield TestClient(app, raise_server_exceptions=False)
    # restore for other tests
    monkeypatch.setenv("BUILD_FACTORY_DEV_BYPASS_AUTH", "1")
    importlib.reload(am)


@pytest.fixture(autouse=True)
def _capture_audit(monkeypatch):
    captured: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({
            "event_type": event_type,
            "session_id": session_id,
            "user_id": user_id,
            "detail": detail or {},
        })
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)
    yield captured


@pytest.fixture
def fake_db_layer(monkeypatch):
    """token_limit_service の DB layer を in-memory dict で差し替え.

    workspace_exists / upsert / select の 3 操作を模擬.
    """
    state: dict[str, Any] = {
        "workspaces": {1, 2, 3, 42},  # 存在する workspace_id
        "token_limits": {},  # key=(workspace_id, provider) → row dict
    }

    class _Cursor:
        def __init__(self, rows):
            self._rows = rows

        async def fetchall(self):
            return self._rows

    class _Row(dict):
        pass

    class _FakeDB:
        row_factory = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def execute(self, sql: str, params: Any = ()):
            sql_l = sql.strip().upper()
            if sql_l.startswith("CREATE TABLE"):
                return _Cursor([])
            if "FROM WORKSPACES" in sql_l and "SELECT 1" in sql_l:
                wid = params[0] if params else None
                if wid in state["workspaces"]:
                    return _Cursor([(1,)])
                return _Cursor([])
            if sql_l.startswith("INSERT INTO TOKEN_LIMITS"):
                wid, provider, limit, ratio, updated_at = params
                state["token_limits"][(wid, provider)] = _Row({
                    "workspace_id": wid,
                    "provider_key": provider,
                    "limit_usd_per_month": limit,
                    "soft_threshold_ratio": ratio,
                    "is_enforced": 1,
                    "updated_at": updated_at,
                })
                return _Cursor([])
            if "FROM TOKEN_LIMITS" in sql_l and "SELECT" in sql_l:
                wid, provider = params
                row = state["token_limits"].get((wid, provider))
                if row is None:
                    return _Cursor([])
                return _Cursor([row])
            return _Cursor([])

        async def commit(self):
            pass

    class _FakeModule:
        Row = _Row

        @staticmethod
        def connect(path):
            return _FakeDB()

    import services.token_limit_service as svc

    def _patched_db():
        return _FakeModule

    monkeypatch.setattr(svc, "_db", _patched_db)
    monkeypatch.setattr(svc, "_db_path", lambda: "/tmp/fake-test.db")
    return state


# ──────────────────────────────────────────────────────────────────────
# AC-F1: cost-summary smoke (existing endpoint untouched)
# ──────────────────────────────────────────────────────────────────────


def test_ac_f1_cost_summary_overview_returns_200(client_authed):
    """T-V3-B-23 AC-F1 cross-ref: T-017-03 の cost-summary が引き続き 200.

    本タスクでは既存 cost-summary endpoint を破壊していないことを担保.
    """
    resp = client_authed.get("/api/observability/cost-summary?dimension=overview")
    assert resp.status_code == 200
    body = resp.json()
    assert "total_usd" in body
    assert "items" in body


# ──────────────────────────────────────────────────────────────────────
# AC-F5: cost-summary export.csv (authed)
# ──────────────────────────────────────────────────────────────────────


def test_ac_f5_export_csv_returns_text_csv(client_authed):
    """AC-F5 EVENT: authed caller で 200 + text/csv + header 行."""
    resp = client_authed.get(
        "/api/observability/cost-summary/export.csv?dimension=overview"
    )
    assert resp.status_code == 200, resp.text
    ctype = resp.headers.get("content-type", "")
    assert ctype.startswith("text/csv"), f"unexpected ctype: {ctype}"
    body = resp.text
    first_line = body.splitlines()[0]
    assert first_line == "label,cost_usd,input_tokens,output_tokens,share"


def test_ac_f5_export_csv_has_total_footer(client_authed):
    """AC-F5: __TOTAL__ 行が必ず出力 (集計結果が空でも footer 必須)."""
    resp = client_authed.get(
        "/api/observability/cost-summary/export.csv?dimension=overview"
    )
    assert resp.status_code == 200
    lines = resp.text.splitlines()
    assert any(line.startswith("__TOTAL__,") for line in lines), (
        f"missing __TOTAL__ footer in:\n{resp.text!r}"
    )


def test_ac_f5_export_csv_content_disposition(client_authed):
    """AC-F5: Content-Disposition attachment + filename."""
    resp = client_authed.get(
        "/api/observability/cost-summary/export.csv?dimension=provider"
    )
    cd = resp.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert "cost-summary-provider" in cd


def test_ac_f5_export_csv_workspace_id_query_in_filename(client_authed):
    """AC-F5: workspace_id query が filename に反映."""
    resp = client_authed.get(
        "/api/observability/cost-summary/export.csv?dimension=overview&workspace_id=42"
    )
    cd = resp.headers.get("content-disposition", "")
    assert "ws42" in cd, f"missing ws42 in CD: {cd}"


def test_ac_f5_export_csv_invalid_dimension_400(client_authed):
    """AC-F5: invalid dimension は CSV 出力前に 400 で reject (既存 _validate_dimension)."""
    resp = client_authed.get(
        "/api/observability/cost-summary/export.csv?dimension=unknown"
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "cost_dashboard.invalid_dimension"


def test_ac_f5_export_csv_accepts_date_only_from(client_authed):
    """AC-F5: features.json の from/to は 'date?' なので YYYY-MM-DD を許容."""
    resp = client_authed.get(
        "/api/observability/cost-summary/export.csv?dimension=overview&from=2026-01-01"
    )
    assert resp.status_code == 200


# ──────────────────────────────────────────────────────────────────────
# AC-F6: cost-summary export.csv requires auth (401)
# ──────────────────────────────────────────────────────────────────────


def test_ac_f6_export_csv_without_auth_returns_401(client_no_auth):
    """AC-F6 UNWANTED: BUILD_FACTORY_DEV_BYPASS_AUTH=0 + no Bearer で 401."""
    resp = client_no_auth.get(
        "/api/observability/cost-summary/export.csv?dimension=overview"
    )
    assert resp.status_code == 401, resp.text


# ──────────────────────────────────────────────────────────────────────
# AC-F7: POST /api/workspaces/{id}/token-limit (authed)
# ──────────────────────────────────────────────────────────────────────


def test_ac_f7_token_limit_post_returns_201_with_contract(
    client_authed, fake_db_layer,
):
    """AC-F7 EVENT: authed + valid body → 201 + features.json#F-017 contract."""
    resp = client_authed.post(
        "/api/workspaces/1/token-limit",
        json={"limit_usd_per_month": 250.0},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["limit_usd_per_month"] == 250.0
    assert body["workspace_id"] == 1
    assert "updated_at" in body
    assert body["provider_key"] == "anthropic"


def test_ac_f7_token_limit_post_emits_audit(
    client_authed, fake_db_layer, _capture_audit,
):
    """AC-F7 audit: 'cost_limit_updated' event emit (features.json#F-017 audit_logs)."""
    resp = client_authed.post(
        "/api/workspaces/2/token-limit",
        json={"limit_usd_per_month": 100.0},
    )
    assert resp.status_code == 201
    event_types = [e["event_type"] for e in _capture_audit]
    assert "cost_limit_updated" in event_types
    matching = [e for e in _capture_audit if e["event_type"] == "cost_limit_updated"]
    assert matching[-1]["detail"]["workspace_id"] == 2
    assert matching[-1]["detail"]["limit_usd_per_month"] == 100.0


def test_ac_f7_token_limit_get_returns_persisted_value(
    client_authed, fake_db_layer,
):
    """AC-F7 round-trip: POST → GET で同じ値."""
    client_authed.post(
        "/api/workspaces/3/token-limit",
        json={"limit_usd_per_month": 500.5},
    )
    resp = client_authed.get("/api/workspaces/3/token-limit")
    assert resp.status_code == 200
    assert resp.json()["limit_usd_per_month"] == 500.5


def test_ac_f7_token_limit_post_workspace_not_found_404(
    client_authed, fake_db_layer,
):
    """AC: workspace_id 不在は 404 (state mutate なし)."""
    resp = client_authed.post(
        "/api/workspaces/9999/token-limit",
        json={"limit_usd_per_month": 50.0},
    )
    assert resp.status_code == 404, resp.text


# ──────────────────────────────────────────────────────────────────────
# AC-F8: POST token-limit without auth (401)
# ──────────────────────────────────────────────────────────────────────


def test_ac_f8_token_limit_post_without_auth_returns_401(client_no_auth):
    """AC-F8 UNWANTED: auth 無しは 401."""
    resp = client_no_auth.post(
        "/api/workspaces/1/token-limit",
        json={"limit_usd_per_month": 100.0},
    )
    assert resp.status_code == 401, resp.text


# ──────────────────────────────────────────────────────────────────────
# AC-F9: POST token-limit validation (422 + field-level map)
# ──────────────────────────────────────────────────────────────────────


def test_ac_f9_token_limit_missing_field_422(client_authed):
    """AC-F9 UNWANTED: limit_usd_per_month 欠落 → 422 (pydantic field-level)."""
    resp = client_authed.post(
        "/api/workspaces/1/token-limit",
        json={},
    )
    assert resp.status_code == 422
    # FastAPI default は detail=[{loc, msg, type}]
    detail = resp.json()["detail"]
    assert isinstance(detail, list)
    # 少なくとも 1 件 limit_usd_per_month を指す violation
    locs = [str(item.get("loc")) for item in detail]
    assert any("limit_usd_per_month" in loc for loc in locs), locs


def test_ac_f9_token_limit_negative_value_422(client_authed, fake_db_layer):
    """AC-F9 UNWANTED: 負値は service 層で reject → 422 + field-level map."""
    resp = client_authed.post(
        "/api/workspaces/1/token-limit",
        json={"limit_usd_per_month": -10},
    )
    assert resp.status_code == 422, resp.text
    body = resp.json()
    detail = body["detail"]
    assert detail["code"] == "workspaces.token_limit.invalid"
    assert "errors" in detail
    assert "limit_usd_per_month" in detail["errors"]


def test_ac_f9_token_limit_string_value_422(client_authed):
    """AC-F9: string は pydantic で 422 (number 型違反)."""
    resp = client_authed.post(
        "/api/workspaces/1/token-limit",
        json={"limit_usd_per_month": "not-a-number"},
    )
    assert resp.status_code == 422


def test_ac_f9_token_limit_excessive_value_422(client_authed, fake_db_layer):
    """AC-F9: sanity ceiling (> 1e9) は service 層で reject."""
    resp = client_authed.post(
        "/api/workspaces/1/token-limit",
        json={"limit_usd_per_month": 1e10},
    )
    assert resp.status_code == 422


# ──────────────────────────────────────────────────────────────────────
# AC-F2 + AC-F3: STATE-DRIVEN warning / UNWANTED breach
# ──────────────────────────────────────────────────────────────────────


def _run(coro):
    """asyncio.run wrapper (Python 3.11+ で event loop が破棄済でも動く)."""
    return asyncio.new_event_loop().run_until_complete(coro)


def test_ac_f2_warning_at_80pct_emits_cost_limit_warning(
    fake_db_layer, _capture_audit, monkeypatch,
):
    """AC-F2 STATE: monthly >= 80% で cost_limit_warning emit."""
    import services.cost_service as cs
    import services.token_limit_service as svc

    # limit を upsert
    _run(svc.set_token_limit(1, 100.0, actor_user_id="masato"))

    async def fake_monthly(workspace_id, **kwargs):
        return 85.0  # 85% — should trigger warning

    monkeypatch.setattr(cs, "monthly_cost", fake_monthly)

    result = _run(svc.check_workspace_within_limit(1))
    assert result["warning_at_80pct"] is True
    assert result["exceeded"] is False
    event_types = [e["event_type"] for e in _capture_audit]
    assert "cost_limit_warning" in event_types


def test_ac_f3_breach_emits_cost_limit_breached(
    fake_db_layer, _capture_audit, monkeypatch,
):
    """AC-F3 UNWANTED: monthly > limit で cost_limit_breached emit + exceeded=True.

    呼び出し元の LLM invocation runner はこの exceeded フラグで 429
    (budget_exceeded) を返す責任を負う.
    """
    import services.cost_service as cs
    import services.token_limit_service as svc

    _run(svc.set_token_limit(2, 100.0, actor_user_id="masato"))

    async def fake_monthly(workspace_id, **kwargs):
        return 150.0  # > limit

    monkeypatch.setattr(cs, "monthly_cost", fake_monthly)

    result = _run(svc.check_workspace_within_limit(2))
    assert result["exceeded"] is True
    event_types = [e["event_type"] for e in _capture_audit]
    assert "cost_limit_breached" in event_types


# ──────────────────────────────────────────────────────────────────────
# AC-F4 UBIQUITOUS: cost_service.record_cost REUSE invariant
# ──────────────────────────────────────────────────────────────────────


def test_ac_f4_cost_entry_has_required_fields():
    """AC-F4 UBIQUITOUS: CostEntry が tokens/cost/provider 必須フィールド保有."""
    from services.cost_service import CostEntry
    entry = CostEntry(
        session_id=1, workspace_id=1, provider="anthropic",
        model="claude-opus-4-7",
        input_tokens=100, output_tokens=50, cost_usd=0.01,
    )
    # F-017 contract: tokens_used + cost_usd + provider tags
    assert entry.provider == "anthropic"
    assert entry.cost_usd == 0.01
    assert entry.input_tokens == 100
    assert entry.output_tokens == 50


# ──────────────────────────────────────────────────────────────────────
# regression: service-layer invariants
# ──────────────────────────────────────────────────────────────────────


def test_validate_limit_rejects_bool():
    """bool は Python int subclass だが拒否 (TypeError ガード)."""
    from services.token_limit_service import InvalidLimitError, validate_limit
    with pytest.raises(InvalidLimitError):
        validate_limit(True)


def test_validate_limit_rejects_none():
    from services.token_limit_service import InvalidLimitError, validate_limit
    with pytest.raises(InvalidLimitError):
        validate_limit(None)


def test_validate_limit_accepts_zero():
    from services.token_limit_service import validate_limit
    assert validate_limit(0) == 0.0


def test_validate_limit_rounds_to_4_decimals():
    from services.token_limit_service import validate_limit
    assert validate_limit(123.456789) == 123.4568


def test_event_constants_match_features_audit_logs():
    """features.json#F-017 audit_logs: cost_limit_updated / cost_limit_breached."""
    from services.token_limit_service import (
        EVENT_COST_LIMIT_BREACHED,
        EVENT_COST_LIMIT_UPDATED,
        EVENT_COST_LIMIT_WARNING,
    )
    assert EVENT_COST_LIMIT_UPDATED == "cost_limit_updated"
    assert EVENT_COST_LIMIT_BREACHED == "cost_limit_breached"
    assert EVENT_COST_LIMIT_WARNING == "cost_limit_warning"


def test_csv_export_csv_safe_quoting(client_authed):
    """RFC 4180: csv module で quoting 済 (label に comma が来ても破壊しない)."""
    resp = client_authed.get(
        "/api/observability/cost-summary/export.csv?dimension=overview"
    )
    assert resp.status_code == 200
    # csv parser でラウンドトリップ可能なはず
    import csv as _csv
    import io as _io
    reader = _csv.reader(_io.StringIO(resp.text))
    rows = list(reader)
    assert rows[0] == ["label", "cost_usd", "input_tokens", "output_tokens", "share"]
    # __TOTAL__ row 必ず最後
    assert rows[-1][0] == "__TOTAL__"
