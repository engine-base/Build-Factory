"""T-018-01: audit_logs trigger (主要テーブルに変更検出) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-018 主要 5 テーブル (workspaces/bf_projects/bf_tasks/
                       skill_definitions/ai_employees) に trigger 設置 + endpoint
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit_logs 自身に trigger 設置禁止 (再帰防止) を強制
  AC-4 UNWANTED      : invalid table / 監視対象外 / audit_logs 自身は 4xx +
                       structured / persistent state mutate しない
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import audit_trigger as at
from services.audit_trigger import (
    AUDITED_TABLES,
    AuditTriggerError,
    EXCLUDED_TABLES,
    VALID_OPS,
    audit_event_action,
    expected_trigger_name,
    is_audited,
    is_excluded,
    list_audited_tables,
    parse_changed_columns,
)


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase" / "migrations" / "20260513000000_audit_logs_triggers.sql"


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


# ──────────────────────────────────────────────────────────────────────────
# Service 単体
# ──────────────────────────────────────────────────────────────────────────


def test_service_audited_tables_count():
    assert len(AUDITED_TABLES) == 5
    assert "workspaces" in AUDITED_TABLES
    assert "audit_logs" not in AUDITED_TABLES


def test_service_excluded_includes_audit_logs():
    assert "audit_logs" in EXCLUDED_TABLES


def test_service_valid_ops():
    assert set(VALID_OPS) == {"insert", "update", "delete"}


def test_service_audit_event_action():
    assert audit_event_action("workspaces", "update") == "workspaces.update"
    assert audit_event_action("bf_tasks", "insert") == "bf_tasks.insert"


def test_service_audit_event_action_invalid_table():
    with pytest.raises(AuditTriggerError):
        audit_event_action("not_audited", "insert")


def test_service_audit_event_action_excluded_table():
    with pytest.raises(AuditTriggerError):
        audit_event_action("audit_logs", "insert")


def test_service_audit_event_action_invalid_op():
    with pytest.raises(AuditTriggerError):
        audit_event_action("workspaces", "bogus")


def test_service_audit_event_action_empty_table():
    with pytest.raises(AuditTriggerError):
        audit_event_action("  ", "insert")


def test_service_parse_changed_columns():
    payload = {"changed": {"status": "active"}, "before_id": 1}
    assert parse_changed_columns(payload) == {"status": "active"}


def test_service_parse_changed_columns_none():
    assert parse_changed_columns(None) == {}


def test_service_parse_changed_columns_invalid():
    with pytest.raises(AuditTriggerError):
        parse_changed_columns("not-dict")
    with pytest.raises(AuditTriggerError):
        parse_changed_columns({"changed": "not-dict"})


def test_service_is_audited():
    assert is_audited("workspaces") is True
    assert is_audited("not_audited") is False
    assert is_audited("WORKSPACES") is True  # case-insensitive


def test_service_is_excluded():
    assert is_excluded("audit_logs") is True
    assert is_excluded("workspaces") is False


def test_service_expected_trigger_name():
    assert expected_trigger_name("workspaces") == "trg_audit_workspaces"
    with pytest.raises(AuditTriggerError):
        expected_trigger_name("not_audited")


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: 主要 5 テーブルに trigger 設置 (migration 静的検証)
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_migration_file_exists():
    assert MIGRATION.exists(), f"migration missing: {MIGRATION}"


def test_ac1_migration_defines_trigger_function():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE OR REPLACE FUNCTION bf_audit_row_change" in sql
    assert "RETURNS TRIGGER" in sql


@pytest.mark.parametrize("table", AUDITED_TABLES)
def test_ac1_migration_creates_trigger_for_table(table):
    sql = MIGRATION.read_text(encoding="utf-8")
    # ループ内で動的に CREATE TRIGGER しているので table 名が target_tables 配列にあること
    assert f"'{table}'" in sql, f"table {table} not in trigger target_tables"


def test_ac1_migration_drops_existing_trigger():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "DROP TRIGGER IF EXISTS" in sql


def test_ac1_migration_uses_security_definer():
    """SECURITY DEFINER で実行 (RLS bypass + 一貫した actor 取得)."""
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "SECURITY DEFINER" in sql


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured error
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_list_endpoint_within_2s(client):
    t0 = time.perf_counter()
    r = client.get("/api/audit-triggers")
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_get_endpoint_within_2s(client):
    t0 = time.perf_counter()
    r = client.get("/api/audit-triggers/workspaces")
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.get("/api/audit-triggers/audit_logs")
    assert r.status_code == 403
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "audit.excluded_table"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: audit_logs 自身への trigger 設置禁止 + payload contract
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_audit_logs_not_in_trigger_target():
    sql = MIGRATION.read_text(encoding="utf-8")
    # target_tables 配列内に 'audit_logs' が含まれないこと
    target_block = re.search(
        r"target_tables\s+TEXT\[\]\s*:=\s*ARRAY\[(.*?)\];",
        sql, re.DOTALL,
    )
    assert target_block is not None
    assert "'audit_logs'" not in target_block.group(1)


def test_ac3_trigger_emits_payload_structure():
    """trigger function が payload に before/after/changed を含むこと."""
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "jsonb_build_object('after'" in sql       # INSERT
    assert "jsonb_build_object('before'" in sql      # DELETE
    assert "'changed'" in sql                           # UPDATE


def test_ac3_trigger_resource_type_uses_table_name():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "resource_type" in sql
    assert "v_table" in sql


def test_ac3_action_format_consistent_with_service():
    """trigger が生成する action と service.audit_event_action() が一致."""
    expected = "workspaces.update"
    assert audit_event_action("workspaces", "update") == expected
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "v_table || '.update'" in sql


def test_ac3_actor_user_id_from_session():
    """current_setting('bf.actor_user_id') を参照."""
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "current_setting('bf.actor_user_id'" in sql


def test_ac3_endpoint_lists_5_tables(client):
    r = client.get("/api/audit-triggers")
    body = r.json()
    assert body["count"] == 5
    table_names = {t["table"] for t in body["tables"]}
    assert table_names == set(AUDITED_TABLES)


def test_ac3_endpoint_returns_3_actions_per_table(client):
    r = client.get("/api/audit-triggers/workspaces")
    body = r.json()
    assert set(body["actions"]) == {
        "workspaces.insert", "workspaces.update", "workspaces.delete",
    }


def test_ac3_excluded_in_list_response(client):
    r = client.get("/api/audit-triggers")
    assert "audit_logs" in r.json()["excluded"]


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_audit_logs_get_returns_403(client):
    """audit_logs は recursion guard で 403."""
    r = client.get("/api/audit-triggers/audit_logs")
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "audit.excluded_table"


def test_ac4_unknown_table_returns_404(client):
    r = client.get("/api/audit-triggers/never_audited")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "audit.not_audited"


def test_ac4_case_normalization(client):
    """大文字でも小文字化されて lookup される."""
    r = client.get("/api/audit-triggers/WORKSPACES")
    assert r.status_code == 200
    assert r.json()["table"] == "workspaces"


def test_ac4_no_drop_without_if_exists():
    """migration の DROP TRIGGER は全て IF EXISTS 付き."""
    sql = MIGRATION.read_text(encoding="utf-8")
    drops = re.findall(r"DROP TRIGGER[^\n;]+", sql)
    for d in drops:
        assert "IF EXISTS" in d, f"DROP without IF EXISTS: {d}"


def test_ac4_migration_no_destructive_outside_trigger():
    """migration は TRUNCATE / DELETE star を含まない."""
    sql = MIGRATION.read_text(encoding="utf-8")
    clean = re.sub(r"--.*$", "", sql, flags=re.MULTILINE)
    assert not re.search(r"^\s*TRUNCATE\b", clean, re.MULTILINE | re.IGNORECASE)
    bare_delete = re.findall(r"DELETE\s+FROM\s+\w+\s*;", clean, re.IGNORECASE)
    assert not bare_delete


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    cases = [
        "/api/audit-triggers/audit_logs",
        "/api/audit-triggers/never_audited",
    ]
    for path in cases:
        r = client.get(path)
        assert 400 <= r.status_code < 500, f"{path}: {r.status_code}"
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
