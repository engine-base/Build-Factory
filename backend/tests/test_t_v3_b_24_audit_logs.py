"""T-V3-B-24 / F-018: Audit logs backend tests (list + export.csv + export.json).

3-tier AC mapping (functional only — backend-only task, structural is empty):
  AC-F1 EVENT-DRIVEN  : >90 days range → 422 filter_too_broad
  AC-F2 EVENT-DRIVEN  : valid auth + filter → 200 + items + total
  AC-F3 UNWANTED      : missing/invalid auth → 401
  AC-F4 UNWANTED      : invalid filter (bad date / type) → 422
  AC-F5 EVENT-DRIVEN  : valid auth + filter → 200 csv_body
  AC-F6 UNWANTED      : missing/invalid auth → 401 (csv)
  AC-F7 UNWANTED      : invalid filter → 422 (csv)
  AC-F8 EVENT-DRIVEN  : valid auth + filter → 200 + json_body
  AC-F9 UNWANTED      : missing/invalid auth → 401 (json)
  AC-F10 UNWANTED     : invalid filter → 422 (json)

NOTE on auth: DEV_BYPASS=1 default → DEV_USER returned for missing creds.
401 path はテスト用に明示的に bypass を解除して assert する.
"""
from __future__ import annotations

import csv as csv_mod
import importlib
import io
import json
import os
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# ──────────────────────────────────────────────────────────────────────
# fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    os.environ.setdefault("BUILD_FACTORY_DEV_BYPASS_AUTH", "1")
    os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:54321")
    os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
    os.environ.setdefault(
        "SUPABASE_JWT_SECRET",
        "test-jwt-secret-must-be-at-least-32-chars-long",
    )
    # main は cached import なので 1 回読み込んだ後は再利用
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def empty_rows():
    """list_audit_logs を空に固定する patch."""
    with patch("services.audit_logs._safe_fetch_rows", return_value=[]):
        yield


@pytest.fixture()
def sample_rows():
    """list_audit_logs に sample row を返させる patch."""
    rows = [
        {
            "id": 101,
            "workspace_id": 1,
            "actor_user_id": "user-001",
            "actor_persona": "devon",
            "action": "bf_tasks.update",
            "resource_type": "bf_tasks",
            "resource_id": 42,
            "payload": {"changed": {"status": "done"}},
            "success": True,
            "created_at": "2026-05-16T12:00:00+00:00",
        },
        {
            "id": 100,
            "workspace_id": 1,
            "actor_user_id": "user-002",
            "actor_persona": "preston",
            "action": "workspaces.update",
            "resource_type": "workspaces",
            "resource_id": 1,
            "payload": {"changed": {"name": "new name"}},
            "success": True,
            "created_at": "2026-05-15T08:30:00+00:00",
        },
    ]
    # count_audit_logs uses count_only branch — return cnt
    def fetch_rows_side_effect(sql: str, params: list[Any]) -> list[dict[str, Any]]:
        if "COUNT(*)" in sql:
            return [{"cnt": len(rows)}]
        return rows
    with patch(
        "services.audit_logs._safe_fetch_rows",
        side_effect=fetch_rows_side_effect,
    ):
        yield rows


# ──────────────────────────────────────────────────────────────────────
# Service unit tests (normalize_filter / validate_date_range / rows_to_csv)
# ──────────────────────────────────────────────────────────────────────


def test_service_normalize_iso_date_only():
    from services.audit_logs import normalize_iso
    out = normalize_iso("2026-05-16", "from")
    assert out is not None
    assert "2026-05-16" in out
    assert "+00:00" in out


def test_service_normalize_iso_full_iso():
    from services.audit_logs import normalize_iso
    out = normalize_iso("2026-05-16T12:30:00+00:00", "from")
    assert out is not None
    assert "2026-05-16" in out


def test_service_normalize_iso_invalid_raises():
    from services.audit_logs import AuditLogFilterError, normalize_iso
    with pytest.raises(AuditLogFilterError) as exc:
        normalize_iso("not-a-date", "from")
    assert exc.value.code == "audit_logs.invalid_date"


def test_service_validate_date_range_within_90_days_ok():
    from services.audit_logs import normalize_iso, validate_date_range
    f = normalize_iso("2026-01-01", "from")
    t = normalize_iso("2026-03-01", "to")
    # 約 59 日 → OK
    validate_date_range(f, t)


def test_service_validate_date_range_over_90_days_raises():
    """AC-F1: >90 days → filter_too_broad."""
    from services.audit_logs import (
        AuditLogFilterError,
        normalize_iso,
        validate_date_range,
    )
    f = normalize_iso("2026-01-01", "from")
    t = normalize_iso("2026-05-15", "to")  # 134 days
    with pytest.raises(AuditLogFilterError) as exc:
        validate_date_range(f, t)
    assert exc.value.code == "audit_logs.filter_too_broad"


def test_service_validate_date_range_single_bound_raises():
    """from だけ指定で to 無し → filter_too_broad (dual-bound 必須)."""
    from services.audit_logs import (
        AuditLogFilterError,
        normalize_iso,
        validate_date_range,
    )
    f = normalize_iso("2026-01-01", "from")
    with pytest.raises(AuditLogFilterError) as exc:
        validate_date_range(f, None)
    assert exc.value.code == "audit_logs.filter_too_broad"


def test_service_validate_date_range_both_none_ok():
    from services.audit_logs import validate_date_range
    validate_date_range(None, None)  # no raise


def test_service_validate_date_range_from_after_to_raises():
    from services.audit_logs import (
        AuditLogFilterError,
        normalize_iso,
        validate_date_range,
    )
    f = normalize_iso("2026-05-01", "from")
    t = normalize_iso("2026-01-01", "to")
    with pytest.raises(AuditLogFilterError) as exc:
        validate_date_range(f, t)
    assert exc.value.code == "audit_logs.invalid_date"


def test_service_normalize_filter_full():
    from services.audit_logs import normalize_filter
    f = normalize_filter(
        workspace_id=1,
        from_="2026-04-01",
        to="2026-05-01",
        user_id="u-1",
        action="bf_tasks.update",
    )
    assert f.workspace_id == 1
    assert f.user_id == "u-1"
    assert f.action == "bf_tasks.update"
    assert f.from_iso is not None
    assert f.to_iso is not None


def test_service_rows_to_csv_header_and_payload():
    """AC-F5: csv_body string with header + payload column."""
    from services.audit_logs import CSV_COLUMNS, rows_to_csv
    rows = [
        {
            "id": 1,
            "workspace_id": 1,
            "actor_user_id": "u-1",
            "actor_persona": None,
            "action": "bf_tasks.update",
            "resource_type": "bf_tasks",
            "resource_id": 99,
            "payload": {"changed": {"status": "done"}},
            "success": True,
            "created_at": "2026-05-16T00:00:00+00:00",
        },
    ]
    body = rows_to_csv(rows)
    assert body.startswith(",".join(CSV_COLUMNS))
    # CSV parse
    reader = csv_mod.reader(io.StringIO(body))
    header = next(reader)
    assert header == list(CSV_COLUMNS)
    row = next(reader)
    assert row[0] == "1"
    assert row[5] == "bf_tasks.update"
    # payload column = JSON-encoded
    payload_obj = json.loads(row[9])
    assert payload_obj == {"changed": {"status": "done"}}


def test_service_rows_to_csv_empty_only_header():
    from services.audit_logs import CSV_COLUMNS, rows_to_csv
    body = rows_to_csv([])
    assert body.strip() == ",".join(CSV_COLUMNS)


# ──────────────────────────────────────────────────────────────────────
# Router: GET /api/audit-logs (list) — AC-F2/F3/F4
# ──────────────────────────────────────────────────────────────────────


def test_list_ac_f2_valid_returns_200_with_items_total(client, sample_rows):
    """AC-F2: valid → 200 + items + total."""
    r = client.get("/api/audit-logs")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "items" in body
    assert "total" in body
    assert isinstance(body["items"], list)
    assert len(body["items"]) == 2
    assert body["total"] == 2
    # contract check on AuditLog item
    first = body["items"][0]
    assert {"id", "action", "created_at", "payload", "success"}.issubset(first.keys())


def test_list_ac_f2_empty_returns_200_empty(client, empty_rows):
    r = client.get("/api/audit-logs")
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_list_ac_f3_missing_auth_returns_401(client, empty_rows):
    """AC-F3: missing/invalid auth → 401.

    DEV_BYPASS=0 + no Authorization → require_user は 401 を返す.
    """
    with patch.dict(os.environ, {"BUILD_FACTORY_DEV_BYPASS_AUTH": "0"}):
        # auth_middleware を reload して DEV_BYPASS 反映
        import services.auth_middleware as am
        importlib.reload(am)
        # main を再 import すると重いので、reload 直後の client で素直に投げる.
        # require_user は依存解決時に最新の get_current_user を参照する.
        r = client.get("/api/audit-logs")
        assert r.status_code == 401, r.text
    # restore
    os.environ["BUILD_FACTORY_DEV_BYPASS_AUTH"] = "1"
    import services.auth_middleware as am
    importlib.reload(am)


def test_list_ac_f4_invalid_date_returns_422(client, empty_rows):
    """AC-F4: invalid date format → 422."""
    r = client.get("/api/audit-logs?from=not-a-date&to=2026-05-01")
    assert r.status_code == 422, r.text
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "audit_logs.invalid_date"


def test_list_ac_f4_single_bound_returns_422(client, empty_rows):
    """AC-F4: only from without to → 422 (filter_too_broad — dual-bound 必須)."""
    r = client.get("/api/audit-logs?from=2026-01-01")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "audit_logs.filter_too_broad"


def test_list_ac_f1_over_90_days_returns_422(client, empty_rows):
    """AC-F1: range > 90 days → 422 filter_too_broad on /api/audit-logs."""
    r = client.get("/api/audit-logs?from=2026-01-01&to=2026-05-01")
    assert r.status_code == 422, r.text
    body = r.json()
    assert body["detail"]["code"] == "audit_logs.filter_too_broad"


def test_list_filter_workspace_id(client, sample_rows):
    r = client.get("/api/audit-logs?workspace_id=1")
    assert r.status_code == 200
    assert r.json()["total"] == 2


def test_list_filter_action(client, sample_rows):
    r = client.get("/api/audit-logs?action=bf_tasks.update")
    assert r.status_code == 200


# ──────────────────────────────────────────────────────────────────────
# Router: GET /api/audit-logs/export.csv — AC-F1/F5/F6/F7
# ──────────────────────────────────────────────────────────────────────


def test_csv_ac_f5_valid_returns_csv_body(client, sample_rows):
    """AC-F5: valid → 200 + text/csv body."""
    r = client.get("/api/audit-logs/export.csv")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    body = r.text
    assert body.startswith("id,created_at,workspace_id,")
    # 2 sample rows + header line
    lines = [ln for ln in body.split("\n") if ln.strip()]
    assert len(lines) >= 3
    assert "bf_tasks.update" in body


def test_csv_ac_f5_valid_json_wrapper_via_as_param(client, sample_rows):
    """AC-F5: ?as=json → JSON wrapper with csv_body field (features.json contract)."""
    r = client.get("/api/audit-logs/export.csv?as=json")
    assert r.status_code == 200
    body = r.json()
    assert "csv_body" in body
    assert isinstance(body["csv_body"], str)
    assert "id,created_at,workspace_id," in body["csv_body"]


def test_csv_ac_f1_over_90_days_returns_422(client, empty_rows):
    """AC-F1: csv export, range > 90 days → 422 filter_too_broad."""
    r = client.get("/api/audit-logs/export.csv?from=2026-01-01&to=2026-05-01")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "audit_logs.filter_too_broad"


def test_csv_ac_f6_missing_auth_returns_401(client, empty_rows):
    """AC-F6: csv export, missing auth → 401."""
    with patch.dict(os.environ, {"BUILD_FACTORY_DEV_BYPASS_AUTH": "0"}):
        import services.auth_middleware as am
        importlib.reload(am)
        r = client.get("/api/audit-logs/export.csv")
        assert r.status_code == 401
    os.environ["BUILD_FACTORY_DEV_BYPASS_AUTH"] = "1"
    import services.auth_middleware as am
    importlib.reload(am)


def test_csv_ac_f7_invalid_filter_returns_422(client, empty_rows):
    """AC-F7: csv export, invalid date → 422."""
    r = client.get("/api/audit-logs/export.csv?from=garbage&to=2026-05-01")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "audit_logs.invalid_date"


def test_csv_content_disposition_attachment(client, sample_rows):
    """attachment header で download UX."""
    r = client.get("/api/audit-logs/export.csv")
    assert r.status_code == 200
    cd = r.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert "audit_logs.csv" in cd


# ──────────────────────────────────────────────────────────────────────
# Router: GET /api/audit-logs/export.json — AC-F1/F8/F9/F10
# ──────────────────────────────────────────────────────────────────────


def test_json_ac_f8_valid_returns_json_body(client, sample_rows):
    """AC-F8: valid → 200 + json_body (AuditLog[])."""
    r = client.get("/api/audit-logs/export.json")
    assert r.status_code == 200
    body = r.json()
    assert "json_body" in body
    assert isinstance(body["json_body"], list)
    assert len(body["json_body"]) == 2
    item = body["json_body"][0]
    assert "id" in item
    assert "action" in item


def test_json_ac_f8_empty_returns_empty_array(client, empty_rows):
    r = client.get("/api/audit-logs/export.json")
    assert r.status_code == 200
    assert r.json()["json_body"] == []


def test_json_ac_f1_over_90_days_returns_422(client, empty_rows):
    """AC-F1 mapping for export.json."""
    r = client.get("/api/audit-logs/export.json?from=2026-01-01&to=2026-05-01")
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "audit_logs.filter_too_broad"


def test_json_ac_f9_missing_auth_returns_401(client, empty_rows):
    """AC-F9: json export, missing auth → 401."""
    with patch.dict(os.environ, {"BUILD_FACTORY_DEV_BYPASS_AUTH": "0"}):
        import services.auth_middleware as am
        importlib.reload(am)
        r = client.get("/api/audit-logs/export.json")
        assert r.status_code == 401
    os.environ["BUILD_FACTORY_DEV_BYPASS_AUTH"] = "1"
    import services.auth_middleware as am
    importlib.reload(am)


def test_json_ac_f10_invalid_filter_returns_422(client, empty_rows):
    """AC-F10: json export, invalid date → 422."""
    r = client.get("/api/audit-logs/export.json?from=garbage")
    assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────
# Error contract shape (structured detail {code, message})
# ──────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client, empty_rows):
    """3 endpoint 全てで 4xx response の detail が {code, message} 構造."""
    cases = [
        "/api/audit-logs?from=garbage",
        "/api/audit-logs?from=2026-01-01&to=2026-06-01",
        "/api/audit-logs/export.csv?from=garbage",
        "/api/audit-logs/export.csv?from=2026-01-01&to=2026-06-01",
        "/api/audit-logs/export.json?from=garbage",
        "/api/audit-logs/export.json?from=2026-01-01&to=2026-06-01",
    ]
    for path in cases:
        r = client.get(path)
        assert 400 <= r.status_code < 500, f"{path}: {r.status_code}"
        body = r.json()
        assert isinstance(body["detail"], dict), path
        assert isinstance(body["detail"]["code"], str), path
        assert isinstance(body["detail"]["message"], str), path


# ──────────────────────────────────────────────────────────────────────
# Schema imports + module surface
# ──────────────────────────────────────────────────────────────────────


def test_schemas_module_exports():
    from schemas.audit_logs import (
        AuditLog,
        AuditLogCsvExportResponse,
        AuditLogFilter,
        AuditLogJsonExportResponse,
        AuditLogListResponse,
    )
    # smoke: instantiate
    al = AuditLog(id=1, action="x")
    assert al.id == 1
    assert al.action == "x"
    assert AuditLogListResponse(items=[al], total=1).total == 1
    assert AuditLogCsvExportResponse(csv_body="a").csv_body == "a"
    assert AuditLogJsonExportResponse(json_body=[al]).json_body[0].id == 1
    assert AuditLogFilter(workspace_id=1).workspace_id == 1


def test_service_module_exports():
    from services.audit_logs import (
        MAX_RANGE_DAYS,
        AuditLogFilterError,
        count_audit_logs,
        list_audit_logs,
        normalize_filter,
        rows_to_csv,
        validate_date_range,
    )
    assert MAX_RANGE_DAYS == 90
    assert callable(count_audit_logs)
    assert callable(list_audit_logs)
    assert callable(normalize_filter)
    assert callable(rows_to_csv)
    assert callable(validate_date_range)
    assert AuditLogFilterError is not None


def test_router_registered_in_main():
    """audit_logs_router が main.app に include されていること."""
    from main import app
    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    assert "/api/audit-logs" in paths
    assert "/api/audit-logs/export.csv" in paths
    assert "/api/audit-logs/export.json" in paths
