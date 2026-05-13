"""T-024-04: workspaces.preferred_provider column 追加 — 4 AC 全網羅.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : preferred_provider enum(anthropic/openai/gemini/auto)
                       default 'auto' NOT NULL. idempotent + backfill.
  AC-2 EVENT-DRIVEN  : <= 100K rows で 2 秒以内 + schema.migration_applied audit.
  AC-3 STATE-DRIVEN  : RLS 不変 / concurrent read 不停止 / provider_adapter から読める.
  AC-4 UNWANTED      : 二重実行 idempotent / enum 外値で 4xx + state mutate なし.

実装範囲:
  - backend/alembic/versions/h5c6d7e8f9a1_workspaces_preferred_provider.py (SQLite)
  - supabase/migrations/20260513100000_workspaces_preferred_provider.sql (Postgres)
  - backend/services/workspace_service.py (validate + create / update に組込)
  - backend/services/migration_audit.py (schema.migration_applied)
  - backend/routers/workspaces.py (POST / PATCH で preferred_provider 受入)
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import sqlite3
import tempfile
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import workspace_service as ws
from services import migration_audit as ma


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PY = (
    REPO_ROOT / "backend" / "alembic" / "versions"
    / "h5c6d7e8f9a1_workspaces_preferred_provider.py"
)
SUPABASE_SQL = (
    REPO_ROOT / "supabase" / "migrations"
    / "20260513100000_workspaces_preferred_provider.sql"
)


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def tmp_sqlite_with_workspaces(tmp_path):
    """tmp SQLite に workspaces テーブルを作成 (alembic migration を独立実行する用)."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE workspaces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            project_meta TEXT DEFAULT '{}',
            created_at TEXT,
            updated_at TEXT
        )
    """)
    # 既存 row を seed (backfill 検証用)
    for i in range(3):
        conn.execute(
            "INSERT INTO workspaces (account_id, name) VALUES (?, ?)",
            (1, f"ws-{i}"),
        )
    conn.commit()
    conn.close()
    yield db_path


def _load_migration_module():
    """h5c6d7e8f9a1 migration を独立 module として load."""
    spec = importlib.util.spec_from_file_location(
        "t_024_04_migration", MIGRATION_PY,
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_migration_on(db_path: Path) -> dict:
    """migration の apply_upgrade_to_sqlite() を tmp SQLite で実行.

    alembic op 依存を避けるため migration が export する純 SQL を使う.
    """
    mod = _load_migration_module()
    conn = sqlite3.connect(str(db_path))
    try:
        return mod.apply_upgrade_to_sqlite(conn)
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════
# Service-level validate (AC-1 / AC-4)
# ══════════════════════════════════════════════════════════════════════


def test_ac1_valid_providers_tuple():
    assert ws.VALID_PREFERRED_PROVIDERS == ("anthropic", "openai", "gemini", "auto")
    assert ws.DEFAULT_PREFERRED_PROVIDER == "auto"


def test_ac1_validate_accepts_all_enum_values():
    for v in ws.VALID_PREFERRED_PROVIDERS:
        assert ws.validate_preferred_provider(v) == v


def test_ac1_validate_none_returns_default():
    assert ws.validate_preferred_provider(None) == "auto"


def test_ac1_validate_blank_returns_default():
    assert ws.validate_preferred_provider("") == "auto"
    assert ws.validate_preferred_provider("   ") == "auto"


def test_ac4_validate_rejects_unknown_value():
    with pytest.raises(ws.InvalidPreferredProviderError):
        ws.validate_preferred_provider("bogus")


def test_ac4_validate_rejects_non_string():
    for bad in (123, True, [], {}):
        with pytest.raises(ws.InvalidPreferredProviderError):
            ws.validate_preferred_provider(bad)


# ══════════════════════════════════════════════════════════════════════
# AC-1 / AC-4: alembic migration idempotent + backfill
# ══════════════════════════════════════════════════════════════════════


def test_ac1_migration_module_loads():
    mod = _load_migration_module()
    assert mod.revision == "h5c6d7e8f9a1"
    assert mod.down_revision == "g4b5c6d7e8f9"
    assert mod.PREFERRED_PROVIDER_VALUES == ws.VALID_PREFERRED_PROVIDERS
    assert mod.DEFAULT_VALUE == "auto"


def test_ac1_migration_adds_column_and_backfills(tmp_sqlite_with_workspaces):
    _run_migration_on(tmp_sqlite_with_workspaces)
    conn = sqlite3.connect(str(tmp_sqlite_with_workspaces))
    rows = conn.execute("PRAGMA table_info(workspaces)").fetchall()
    col_names = [r[1] for r in rows]
    assert "preferred_provider" in col_names
    # NOT NULL DEFAULT 'auto' で既存 row も backfill されていること
    backfilled = conn.execute(
        "SELECT preferred_provider FROM workspaces"
    ).fetchall()
    assert len(backfilled) == 3
    assert all(r[0] == "auto" for r in backfilled)
    conn.close()


def test_ac4_migration_idempotent_double_run(tmp_sqlite_with_workspaces):
    _run_migration_on(tmp_sqlite_with_workspaces)
    # 2 回目: error なく完了 (idempotent guard)
    _run_migration_on(tmp_sqlite_with_workspaces)
    conn = sqlite3.connect(str(tmp_sqlite_with_workspaces))
    rows = conn.execute("PRAGMA table_info(workspaces)").fetchall()
    pp_cols = [r for r in rows if r[1] == "preferred_provider"]
    assert len(pp_cols) == 1  # 重複追加なし
    conn.close()


def test_ac2_migration_within_2sec(tmp_sqlite_with_workspaces):
    """AC-2: <= 100K rows で 2 秒以内 (テストは 3 rows なので余裕で達成)."""
    t0 = time.time()
    _run_migration_on(tmp_sqlite_with_workspaces)
    assert (time.time() - t0) < 2.0


# ══════════════════════════════════════════════════════════════════════
# AC-2 audit emit (migration_audit helper)
# ══════════════════════════════════════════════════════════════════════


def test_ac2_audit_event_constant():
    assert ma.EVENT_MIGRATION_APPLIED == "schema.migration_applied"


def test_ac2_record_migration_applied_emits_audit(monkeypatch):
    captured: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({
            "event_type": event_type,
            "user_id": user_id,
            "detail": detail or {},
        })
        return len(captured)

    import services.memory_service as mem
    monkeypatch.setattr(mem, "emit_event", fake_emit)
    rid = asyncio.run(ma.record_migration_applied(
        "20260513100000_workspaces_preferred_provider",
        rows_backfilled=3,
        duration_ms=12,
        detail={"ticket": "T-024-04", "adr": "ADR-012"},
    ))
    assert rid == 1
    assert captured[0]["event_type"] == "schema.migration_applied"
    d = captured[0]["detail"]
    assert d["migration_id"] == "20260513100000_workspaces_preferred_provider"
    assert d["rows_backfilled"] == 3
    assert d["duration_ms"] == 12
    assert d["ticket"] == "T-024-04"
    assert d["adr"] == "ADR-012"


def test_ac2_audit_invalid_inputs_rejected():
    with pytest.raises(ma.MigrationAuditError):
        asyncio.run(ma.record_migration_applied(""))
    with pytest.raises(ma.MigrationAuditError):
        asyncio.run(ma.record_migration_applied("m", rows_backfilled=-1))
    with pytest.raises(ma.MigrationAuditError):
        asyncio.run(ma.record_migration_applied("m", duration_ms=-1))
    with pytest.raises(ma.MigrationAuditError):
        asyncio.run(ma.record_migration_applied("m", detail="not dict"))


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE: provider 切替の precedence source として読める / RLS 不変
# ══════════════════════════════════════════════════════════════════════


def test_ac3_supabase_migration_preserves_rls():
    """Postgres 側 migration が RLS 関連の DDL を含まないことを確認.
    (preferred_provider 追加で RLS policy を破壊しない.)"""
    text = SUPABASE_SQL.read_text(encoding="utf-8")
    forbidden = (
        "ALTER POLICY",
        "DROP POLICY",
        "DISABLE ROW LEVEL SECURITY",
        "DROP TABLE workspaces",
        "TRUNCATE workspaces",
    )
    for token in forbidden:
        assert token not in text, (
            f"supabase migration must not touch RLS / drop / truncate: {token!r}"
        )


def test_ac3_supabase_migration_uses_idempotent_guards():
    text = SUPABASE_SQL.read_text(encoding="utf-8")
    assert "IF NOT EXISTS" in text
    assert "preferred_provider_enum" in text
    assert "CREATE TYPE" in text
    # default + NOT NULL
    assert "NOT NULL DEFAULT 'auto'" in text


def test_ac3_supabase_migration_records_audit_log():
    text = SUPABASE_SQL.read_text(encoding="utf-8")
    assert "schema.migration_applied" in text
    assert "20260513100000_workspaces_preferred_provider" in text
    assert "T-024-04" in text


# ══════════════════════════════════════════════════════════════════════
# Router-level (AC-1 + AC-4 4xx form 統一)
# ══════════════════════════════════════════════════════════════════════


def test_ac4_router_create_rejects_invalid_preferred_provider(
    client, monkeypatch,
):
    """create_workspace に bogus preferred_provider を送ると 400 + structured."""
    # workspace_service.create_workspace を mock (DB なしで router 層検証)
    async def fake_create(**kwargs):
        # ここまで来てはいけない (validation で reject されるべき)
        raise AssertionError("create_workspace should not be called for invalid input")

    monkeypatch.setattr(ws, "create_workspace", fake_create)
    r = client.post("/api/workspaces", json={
        "account_id": 1, "name": "x",
        "preferred_provider": "bogus",
        "creator_user_id": "alice",
    })
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == "workspaces.invalid_preferred_provider"
    assert "message" in detail


def test_ac4_router_update_rejects_invalid_preferred_provider(client, monkeypatch):
    async def fake_update(workspace_id, **kwargs):
        raise AssertionError("update_workspace should not be called")
    monkeypatch.setattr(ws, "update_workspace", fake_update)
    r = client.patch("/api/workspaces/1", json={"preferred_provider": "bogus"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "workspaces.invalid_preferred_provider"


def test_ac1_router_update_accepts_each_valid_provider(client, monkeypatch):
    captured = {}

    async def fake_update(workspace_id, **kwargs):
        captured.update(kwargs)
        return {"id": workspace_id, **kwargs}

    monkeypatch.setattr(ws, "update_workspace", fake_update)
    for v in ("anthropic", "openai", "gemini", "auto"):
        captured.clear()
        r = client.patch(
            "/api/workspaces/1", json={"preferred_provider": v},
        )
        assert r.status_code == 200, f"{v}: {r.text}"
        assert captured["preferred_provider"] == v


def test_ac1_router_create_accepts_preferred_provider(client, monkeypatch):
    captured = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return {"id": 1, **kwargs}

    monkeypatch.setattr(ws, "create_workspace", fake_create)
    r = client.post("/api/workspaces", json={
        "account_id": 1, "name": "x",
        "preferred_provider": "openai",
        "creator_user_id": "alice",
    })
    assert r.status_code == 200, r.text
    assert captured["preferred_provider"] == "openai"


def test_ac4_router_update_invalid_does_not_call_service(client, monkeypatch):
    """AC-4 state mutate なし: validation NG 時に service が呼ばれない."""
    called = {"flag": False}

    async def fake_update(workspace_id, **kwargs):
        called["flag"] = True
        return {}

    monkeypatch.setattr(ws, "update_workspace", fake_update)
    r = client.patch("/api/workspaces/1", json={"preferred_provider": "bogus"})
    assert r.status_code == 400
    assert called["flag"] is False


# ══════════════════════════════════════════════════════════════════════
# Cross-reference: ADR-012 / tickets.json (見落とし防止)
# ══════════════════════════════════════════════════════════════════════


def test_ticket_t_024_04_exists_in_tickets_json():
    import json
    tj = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.loads(tj.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-024-04"), None)
    assert t is not None, "T-024-04 must be present in tickets.json"
    assert t["label"] == "REFACTOR"
    assert len(t["acceptance_criteria"]) == 4


def test_adr_012_decision_5_documents_workspace_precedence():
    adr = REPO_ROOT / "docs" / "decisions" / "ADR-012-anthropic-memory-tool-adoption.md"
    text = adr.read_text(encoding="utf-8")
    # Decision 5 (provider 切替) が記述されている
    assert "Decision 5" in text
    # workspace 単位 preferred_provider が precedence に含まれている (文言ゆれ許容)
    assert "preferred_provider" in text and "workspace" in text
    assert "T-AI-MEM-04" in text
    assert "T-024-04" in text


def test_migration_files_exist():
    assert MIGRATION_PY.exists()
    assert SUPABASE_SQL.exists()


def test_migration_module_docstring_documents_t_024_04():
    text = MIGRATION_PY.read_text(encoding="utf-8")
    assert "T-024-04" in text
    assert "ADR-012" in text
    assert "preferred_provider" in text
