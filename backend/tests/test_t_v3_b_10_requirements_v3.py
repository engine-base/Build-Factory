"""T-V3-B-10: Requirements backend v3 (F-006) — CRUD / versions / task comments.

AC マッピング (docs/audit/2026-05-16_v3/T-V3-B-10.md Tier 2):
  AC-F1  EVENT-DRIVEN PUT requirements persist + return version+1
  AC-F2  UNWANTED      PUT items が EARS 違反 → 422 + offending indices
  AC-F3  EVENT-DRIVEN POST versions snapshot + return version_id
  AC-F4  EVENT-DRIVEN GET 2xx + {requirements, version}
  AC-F5  UNWANTED     GET no auth → 401
  AC-F6  UNWANTED     GET body validation → 422 (path id)
  AC-F7  EVENT-DRIVEN PUT 2xx + {id, version}
  AC-F8  UNWANTED     PUT no auth → 401
  AC-F9  UNWANTED     PUT body validation → 422
  AC-F10 EVENT-DRIVEN POST 2xx + {version_id, version_number}
  AC-F11 UNWANTED     POST no auth → 401
  AC-F12 UNWANTED     POST body validation → 422
  AC-F13 EVENT-DRIVEN POST /api/tasks/{id}/comments → 2xx + comment_id
  AC-F14 UNWANTED     no auth → 401
  AC-F15 UNWANTED     body validation → 422

Impl:
  backend/services/requirements_v3_service.py
  backend/routers/requirements.py (lines after T-005-03 download endpoint)
  backend/routers/tasks.py (POST /tasks/{id}/comments)
  supabase/migrations/20260516000000_bf_requirements_versions_comments.sql
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    REPO_ROOT / "supabase" / "migrations"
    / "20260516000000_bf_requirements_versions_comments.sql"
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    # DEV_BYPASS は module import 時に決まるため, テスト時に default 値 (=1) であることを確認.
    os.environ.setdefault("BUILD_FACTORY_DEV_BYPASS_AUTH", "1")
    # Supabase env vars: 実 DB は使わないので dummy 値で OK.
    os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:54321")
    os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
    os.environ.setdefault("SUPABASE_JWT_SECRET", "x" * 32)
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _fake_v3_service(monkeypatch):
    """requirements_v3_service の DB アクセスを in-memory に置き換える.

    pure-function (validate_ears_items / EarsValidationError) はそのまま使い,
    DB 依存の persist 系のみを fake 化する. これにより
    pytest が Supabase Postgres 接続無しで router レベルの contract test を完走できる.
    """
    import services.requirements_v3_service as rv3

    # in-memory store: { workspace_id: {"items": [...], "version": int} }
    store: dict[int, dict] = {}
    versions: dict[int, list[dict]] = {}
    comments: list[dict] = []
    _state = {"comment_seq": 0, "version_seq": 0}

    async def fake_list_requirements(workspace_id: int) -> dict:
        s = store.get(int(workspace_id), {"items": [], "version": 0})
        return {"requirements": list(s["items"]), "version": s["version"]}

    async def fake_upsert_requirements(
        workspace_id: int, items: list, *, actor_user_id=None,
    ) -> dict:
        # 本物の validator を使う (EARS 違反検出は契約の一部)
        offending = rv3.validate_ears_items(items)
        if offending:
            raise rv3.EarsValidationError(
                offending_indices=offending,
                field_errors=rv3._build_field_errors(offending),
            )
        ws = int(workspace_id)
        prev = store.get(ws, {"version": 0})
        new_version = (prev.get("version") or 0) + 1
        store[ws] = {
            "items": [
                {**it, "version": new_version, "item_index": i}
                for i, it in enumerate(items)
            ],
            "version": new_version,
        }
        return {"id": str(ws), "version": new_version}

    async def fake_create_version(
        workspace_id: int, message: str, *, actor_user_id=None,
    ) -> dict:
        ws = int(workspace_id)
        _state["version_seq"] += 1
        seq = _state["version_seq"]
        ver_list = versions.setdefault(ws, [])
        version_number = len(ver_list) + 1
        snap = store.get(ws, {"items": [], "version": 0})
        ver_list.append({
            "version_id": str(seq),
            "version_number": version_number,
            "message": message,
            "snapshot": snap,
            "actor_user_id": actor_user_id,
        })
        return {
            "version_id": str(seq),
            "version_number": version_number,
        }

    async def fake_add_task_comment(
        task_id: int, body: str, *, actor_user_id=None,
        enforce_task_exists: bool = False,
    ) -> dict:
        if not isinstance(body, str) or not body.strip():
            raise ValueError("body must be a non-empty string")
        _state["comment_seq"] += 1
        seq = _state["comment_seq"]
        comments.append({
            "id": seq, "task_id": int(task_id),
            "body": body, "author_user_id": actor_user_id,
        })
        return {"comment_id": str(seq)}

    monkeypatch.setattr(rv3, "list_requirements", fake_list_requirements)
    monkeypatch.setattr(rv3, "upsert_requirements", fake_upsert_requirements)
    monkeypatch.setattr(rv3, "create_version", fake_create_version)
    monkeypatch.setattr(rv3, "add_task_comment", fake_add_task_comment)

    yield {
        "store": store,
        "versions": versions,
        "comments": comments,
    }


@pytest.fixture
def _disable_auth_bypass(monkeypatch):
    """401 テスト用: DEV_BYPASS を OFF にする."""
    import services.auth_middleware as am
    monkeypatch.setattr(am, "DEV_BYPASS", False)
    yield


# ──────────────────────────────────────────────────────────────────────────
# Section A: EARS form validator (pure function)
# ──────────────────────────────────────────────────────────────────────────


def test_validate_ears_items_accepts_all_5_forms():
    """EARS 5 形式の正規パターンを全件 accept."""
    from services.requirements_v3_service import validate_ears_items, VALID_EARS_TYPES

    items = [
        {"ears_type": "UBIQUITOUS",   "text": "The system shall log every API call."},
        {"ears_type": "EVENT-DRIVEN", "text": "When a user signs up, the system shall send an email."},
        {"ears_type": "STATE-DRIVEN", "text": "While a task is in_progress, the system shall block deletion."},
        {"ears_type": "OPTIONAL",     "text": "Where 2FA is enabled, the system shall require TOTP."},
        {"ears_type": "UNWANTED",     "text": "If a user attempts SQL injection, the system shall not execute."},
    ]
    assert validate_ears_items(items) == []
    assert set(VALID_EARS_TYPES) == {
        "UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED",
    }


def test_validate_ears_items_rejects_invalid_prefix():
    """EVENT-DRIVEN なのに 'When' で始まらない → 違反."""
    from services.requirements_v3_service import validate_ears_items
    items = [
        {"ears_type": "EVENT-DRIVEN", "text": "The system shall do X."},  # 接頭辞欠落
        {"ears_type": "UNWANTED", "text": "If invalid, the system shall not act."},
    ]
    offending = validate_ears_items(items)
    assert offending == [0]


def test_validate_ears_items_rejects_missing_shall_clause():
    """`the system shall` が無いと違反."""
    from services.requirements_v3_service import validate_ears_items
    items = [
        {"ears_type": "EVENT-DRIVEN", "text": "When X happens, do Y."},  # shall 無し
    ]
    assert validate_ears_items(items) == [0]


def test_validate_ears_items_rejects_unknown_enum():
    """ears_type が enum 外 → 違反."""
    from services.requirements_v3_service import validate_ears_items
    items = [{"ears_type": "MAYBE", "text": "The system shall do nothing."}]
    assert validate_ears_items(items) == [0]


def test_validate_ears_items_rejects_empty_text_and_non_dict():
    from services.requirements_v3_service import validate_ears_items
    items = [
        {"ears_type": "UBIQUITOUS", "text": ""},
        "not-a-dict",  # type: ignore[list-item]
    ]
    assert validate_ears_items(items) == [0, 1]


# ──────────────────────────────────────────────────────────────────────────
# Section B: GET /api/workspaces/{id}/requirements (AC-F4 / AC-F5 / AC-F6)
# ──────────────────────────────────────────────────────────────────────────


def test_ac_f4_get_requirements_returns_2xx_with_contract(client):
    """AC-F4: GET 認可済み呼び出し → 2xx + {requirements, version}."""
    res = client.get("/api/workspaces/1/requirements")
    assert res.status_code == 200, res.text
    body = res.json()
    assert "requirements" in body
    assert "version" in body
    assert isinstance(body["requirements"], list)
    assert isinstance(body["version"], int)


def test_ac_f5_get_requirements_returns_401_without_auth(client, _disable_auth_bypass):
    """AC-F5: GET no auth → 401."""
    res = client.get("/api/workspaces/1/requirements")
    assert res.status_code == 401, res.text


def test_ac_f6_get_requirements_path_validation_422(client):
    """AC-F6: workspace_id <= 0 → 422 (field-level error map)."""
    # FastAPI は path int の負値も受けるが, router 内 _v3_workspace_id_or_422 で reject
    res = client.get("/api/workspaces/0/requirements")
    assert res.status_code == 422, res.text
    body = res.json()
    assert body["detail"]["code"] == "validation_error"
    assert any(e["loc"] == ["path", "id"] for e in body["detail"]["errors"])


# ──────────────────────────────────────────────────────────────────────────
# Section C: PUT /api/workspaces/{id}/requirements (AC-F1 / AC-F2 / AC-F7~F9)
# ──────────────────────────────────────────────────────────────────────────


VALID_PUT_BODY = {
    "items": [
        {
            "ears_type": "EVENT-DRIVEN",
            "text": "When a user logs in, the system shall record the session.",
            "title": "session record",
            "category": "functional",
        },
        {
            "ears_type": "UNWANTED",
            "text": "If a token is expired, the system shall not grant access.",
        },
    ],
}


def test_ac_f1_and_f7_put_requirements_persists_and_increments_version(client):
    """AC-F1 / AC-F7: PUT EARS-conformant → persist + version+1, response {id, version}."""
    res1 = client.put("/api/workspaces/42/requirements", json=VALID_PUT_BODY)
    assert res1.status_code == 200, res1.text
    body1 = res1.json()
    assert body1["id"] == "42"
    assert body1["version"] == 1, body1

    # 同じ workspace に再 PUT → version+1
    res2 = client.put("/api/workspaces/42/requirements", json=VALID_PUT_BODY)
    assert res2.status_code == 200, res2.text
    body2 = res2.json()
    assert body2["version"] == 2

    # GET で persist 確認 + version 値が response と一致
    res_get = client.get("/api/workspaces/42/requirements")
    assert res_get.status_code == 200
    g = res_get.json()
    assert g["version"] == 2
    assert len(g["requirements"]) == len(VALID_PUT_BODY["items"])


def test_ac_f2_put_requirements_returns_422_with_offending_indices(client):
    """AC-F2: items が EARS 違反 → 422 + offending indices."""
    body = {
        "items": [
            {"ears_type": "EVENT-DRIVEN", "text": "When X, the system shall act."},  # OK
            {"ears_type": "EVENT-DRIVEN", "text": "no When prefix here."},  # NG
            {"ears_type": "MAYBE", "text": "The system shall do nothing."},  # NG enum
        ],
    }
    res = client.put("/api/workspaces/100/requirements", json=body)
    assert res.status_code == 422, res.text
    detail = res.json()["detail"]
    assert detail["code"] == "ears_validation_failed"
    assert detail["offending_indices"] == [1, 2]
    assert isinstance(detail["errors"], list)
    assert all("loc" in e and "code" in e for e in detail["errors"])


def test_ac_f8_put_requirements_returns_401_without_auth(client, _disable_auth_bypass):
    """AC-F8: PUT no auth → 401."""
    res = client.put("/api/workspaces/1/requirements", json=VALID_PUT_BODY)
    assert res.status_code == 401, res.text


def test_ac_f9_put_requirements_body_validation_422(client):
    """AC-F9: PUT 不正 body (items 欠落) → 422."""
    res = client.put("/api/workspaces/1/requirements", json={})
    assert res.status_code == 422, res.text


def test_ac_f9_put_requirements_invalid_item_shape_422(client):
    """AC-F9: items 要素が text を欠く → 422 (Pydantic 検証)."""
    res = client.put(
        "/api/workspaces/1/requirements",
        json={"items": [{"ears_type": "UBIQUITOUS"}]},
    )
    assert res.status_code == 422, res.text


# ──────────────────────────────────────────────────────────────────────────
# Section D: POST /api/workspaces/{id}/requirements/versions (AC-F3 / AC-F10~F12)
# ──────────────────────────────────────────────────────────────────────────


def test_ac_f3_and_f10_post_versions_snapshots_and_returns_version_id(client):
    """AC-F3 / AC-F10: 現在の requirements を snapshot → version_id + version_number."""
    # 事前に PUT で requirements 投入
    put_res = client.put("/api/workspaces/55/requirements", json=VALID_PUT_BODY)
    assert put_res.status_code == 200

    res = client.post(
        "/api/workspaces/55/requirements/versions",
        json={"message": "initial snapshot"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["version_id"] is not None
    assert body["version_number"] == 1

    # 2 回目の snapshot で version_number が +1
    res2 = client.post(
        "/api/workspaces/55/requirements/versions",
        json={"message": "second snapshot"},
    )
    assert res2.status_code == 201, res2.text
    body2 = res2.json()
    assert body2["version_number"] == 2
    assert body2["version_id"] != body["version_id"]


def test_ac_f11_post_versions_returns_401_without_auth(client, _disable_auth_bypass):
    """AC-F11: POST versions no auth → 401."""
    res = client.post(
        "/api/workspaces/1/requirements/versions",
        json={"message": "x"},
    )
    assert res.status_code == 401, res.text


def test_ac_f12_post_versions_body_validation_422(client):
    """AC-F12: POST versions の message 欠落 → 422."""
    res = client.post("/api/workspaces/1/requirements/versions", json={})
    assert res.status_code == 422, res.text


# ──────────────────────────────────────────────────────────────────────────
# Section E: POST /api/tasks/{id}/comments (AC-F13 / AC-F14 / AC-F15)
# ──────────────────────────────────────────────────────────────────────────


def test_ac_f13_post_task_comment_returns_2xx_with_comment_id(client):
    """AC-F13: POST comment → 201 + comment_id."""
    res = client.post(
        "/api/tasks/123/comments",
        json={"body": "this is a comment on task 123"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["comment_id"] is not None
    assert isinstance(body["comment_id"], str)


def test_ac_f14_post_task_comment_returns_401_without_auth(client, _disable_auth_bypass):
    """AC-F14: POST comment no auth → 401."""
    res = client.post("/api/tasks/1/comments", json={"body": "hello"})
    assert res.status_code == 401, res.text


def test_ac_f15_post_task_comment_body_validation_422_empty(client):
    """AC-F15: body が空文字列 → 422."""
    res = client.post("/api/tasks/1/comments", json={"body": ""})
    assert res.status_code == 422, res.text


def test_ac_f15_post_task_comment_body_validation_422_missing(client):
    """AC-F15: body field 欠落 → 422."""
    res = client.post("/api/tasks/1/comments", json={})
    assert res.status_code == 422, res.text


def test_ac_f15_post_task_comment_invalid_task_id_422(client):
    """AC-F15: task_id <= 0 → 422."""
    res = client.post("/api/tasks/0/comments", json={"body": "x"})
    assert res.status_code == 422, res.text


# ──────────────────────────────────────────────────────────────────────────
# Section F: Migration / RLS static invariants (Tier 3 AC-R4)
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def migration_sql() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


def test_migration_creates_bf_requirements_table(migration_sql):
    assert re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+bf_requirements\s*\(",
        migration_sql, re.IGNORECASE,
    )


def test_migration_creates_bf_requirement_versions_table(migration_sql):
    assert re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+bf_requirement_versions\s*\(",
        migration_sql, re.IGNORECASE,
    )


def test_migration_creates_bf_task_comments_table(migration_sql):
    assert re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+bf_task_comments\s*\(",
        migration_sql, re.IGNORECASE,
    )


def test_migration_enables_rls_on_all_three_tables(migration_sql):
    for tbl in ("bf_requirements", "bf_requirement_versions", "bf_task_comments"):
        assert re.search(
            rf"ALTER\s+TABLE\s+{tbl}\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY",
            migration_sql, re.IGNORECASE,
        ), f"RLS not enabled on {tbl}"


def test_migration_has_service_role_and_member_policies(migration_sql):
    """RLS 設計: service_role 全権 + workspace_member の SELECT/ALL."""
    for tbl in ("bf_requirements", "bf_requirement_versions", "bf_task_comments"):
        # service_role 全権 (ALL)
        assert re.search(
            rf"CREATE\s+POLICY\s+{tbl}_service_role_all\s+ON\s+{tbl}",
            migration_sql, re.IGNORECASE,
        ), f"service_role policy missing on {tbl}"
        # workspace_member SELECT
        assert re.search(
            rf"CREATE\s+POLICY\s+{tbl}_workspace_member_select\s+ON\s+{tbl}",
            migration_sql, re.IGNORECASE,
        ), f"member SELECT policy missing on {tbl}"
        # workspace_member write (ALL)
        assert re.search(
            rf"CREATE\s+POLICY\s+{tbl}_workspace_member_write\s+ON\s+{tbl}",
            migration_sql, re.IGNORECASE,
        ), f"member write policy missing on {tbl}"


def test_migration_bf_requirements_has_ears_type_check(migration_sql):
    """bf_requirements.ears_type は 5 形式の CHECK 制約."""
    # CREATE TABLE block 抜き出し
    m = re.search(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+bf_requirements\s*\((.*?)\);",
        migration_sql, re.DOTALL | re.IGNORECASE,
    )
    assert m, "bf_requirements DDL block not found"
    body = m.group(1)
    assert "UBIQUITOUS" in body
    assert "EVENT-DRIVEN" in body
    assert "STATE-DRIVEN" in body
    assert "OPTIONAL" in body
    assert "UNWANTED" in body


def test_migration_uses_bf_can_access_workspace_helper(migration_sql):
    """RLS policy は既存 helper bf_can_access_workspace(ws_id) を使う."""
    assert "bf_can_access_workspace" in migration_sql


def test_migration_task_comments_links_workspace_via_bf_projects(migration_sql):
    """bf_task_comments.task_id → bf_tasks → bf_projects.workspace_id チェーン."""
    # RLS section に JOIN bf_projects が含まれていること
    rls_section = migration_sql[
        migration_sql.find("bf_task_comments_workspace_member_select"):
    ]
    assert "bf_projects" in rls_section
    assert "bf_tasks" in rls_section
