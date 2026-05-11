"""T-001-10: seed.sql + BF_ENV guard — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : seed.sql + BF_ENV guard が F-001 通りに実装されている
  AC-2 EVENT-DRIVEN  : 全 endpoint で 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit_logs emit + actor 検証 (CLAUDE.md §5.3)
  AC-4 UNWANTED      : prod / invalid input は 4xx + structured / persistent state 不変
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


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


@pytest.fixture
def _bf_env_dev(monkeypatch):
    monkeypatch.setenv("BF_ENV", "dev")


@pytest.fixture
def _bf_env_test(monkeypatch):
    monkeypatch.setenv("BF_ENV", "test")


@pytest.fixture
def _bf_env_prod(monkeypatch):
    monkeypatch.setenv("BF_ENV", "prod")


@pytest.fixture
def _bf_env_invalid(monkeypatch):
    monkeypatch.setenv("BF_ENV", "garbage")


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: seed.sql + BF_ENV guard が存在
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_seed_sql_file_exists():
    """AC-1: supabase/seed.sql が存在."""
    from services.bf_env_guard import seed_sql_path
    p = seed_sql_path()
    assert p.exists()
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "BEGIN" in text and "COMMIT" in text
    assert "ON CONFLICT" in text  # idempotent
    assert "BF_ENV" in text  # コメントで guard 言及


def test_ac1_bf_env_guard_module_loads():
    """AC-1: bf_env_guard module の public API が揃っている."""
    from services import bf_env_guard as guard
    for sym in ("current_env", "validate_env", "is_destructive_allowed",
                "require_non_prod", "read_seed_sql", "BFEnvGuardError",
                "BFInvalidEnvError", "DESTRUCTIVE_ALLOWED_ENVS", "VALID_ENVS"):
        assert hasattr(guard, sym), f"missing {sym}"
    assert "dev" in guard.DESTRUCTIVE_ALLOWED_ENVS
    assert "prod" not in guard.DESTRUCTIVE_ALLOWED_ENVS


def test_ac1_bf_env_status_endpoint_exists(client, _bf_env_dev):
    """AC-1: GET /api/admin/bf-env が status を返す."""
    r = client.get("/api/admin/bf-env")
    assert r.status_code == 200
    body = r.json()
    assert body["bf_env"] == "dev"
    assert body["destructive_allowed"] is True
    assert body["is_prod"] is False


def test_ac1_seed_preview_endpoint_exists(client):
    """AC-1: GET /api/admin/seed/preview が seed.sql の head を返す."""
    r = client.get("/api/admin/seed/preview")
    assert r.status_code == 200
    body = r.json()
    assert "preview" in body
    assert "total_lines" in body
    assert body["total_lines"] > 0


def test_ac1_seed_run_endpoint_exists(client, _bf_env_dev):
    """AC-1: POST /api/admin/seed/run が定義 (dry_run で成功)."""
    r = client.post(
        "/api/admin/seed/run",
        json={"actor_user_id": "masato", "dry_run": True},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "dry_run"


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured response
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_bf_env_endpoint_returns_within_2s(client, _bf_env_dev):
    t0 = time.perf_counter()
    r = client.get("/api/admin/bf-env")
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_seed_preview_returns_within_2s(client):
    t0 = time.perf_counter()
    r = client.get("/api/admin/seed/preview")
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_seed_run_dry_returns_within_2s(client, _bf_env_dev):
    t0 = time.perf_counter()
    r = client.post(
        "/api/admin/seed/run",
        json={"actor_user_id": "masato", "dry_run": True},
    )
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_uses_detail_code_message(client, _bf_env_dev):
    """AC-2: 4xx error は {detail:{code,message}} 形式."""
    r = client.post("/api/admin/seed/run", json={"actor_user_id": "  "})
    assert r.status_code == 401
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "seed.unauthorized"
    assert "message" in body["detail"]


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: audit_logs emit + actor 検証
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_seed_run_dry_emits_audit(client, _bf_env_dev, _capture_audit):
    """AC-3: dry_run でも audit_logs に seed.run.dry_run を emit."""
    client.post(
        "/api/admin/seed/run",
        json={"actor_user_id": "masato", "dry_run": True},
    )
    events = [e for e in _capture_audit if e["event_type"] == "seed.run.dry_run"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "masato"
    assert events[0]["detail"]["bf_env"] == "dev"


def test_ac3_seed_run_denied_in_prod_emits_audit(client, _bf_env_prod, _capture_audit):
    """AC-3: prod で denied でも audit 残す (誰がいつ試みたか追跡)."""
    client.post(
        "/api/admin/seed/run",
        json={"actor_user_id": "attacker", "dry_run": True},
    )
    events = [e for e in _capture_audit if e["event_type"] == "seed.run.denied"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "attacker"
    assert events[0]["detail"]["bf_env"] == "prod"


def test_ac3_actor_required():
    """AC-3: actor_user_id が必須 (空文字 NG)."""
    from main import app
    c = TestClient(app, raise_server_exceptions=False)
    r = c.post("/api/admin/seed/run", json={"actor_user_id": ""})
    assert r.status_code in (401, 422)


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: prod / invalid input は 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_prod_denies_seed_run(client, _bf_env_prod):
    """AC-4: BF_ENV=prod で seed.run は 403 forbidden_in_env."""
    r = client.post(
        "/api/admin/seed/run",
        json={"actor_user_id": "masato", "dry_run": True},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "seed.forbidden_in_env"


def test_ac4_staging_denies_seed_run(client, monkeypatch):
    """AC-4: BF_ENV=staging も seed.run 禁止 (RLS 検査用 read-only env)."""
    monkeypatch.setenv("BF_ENV", "staging")
    r = client.post(
        "/api/admin/seed/run",
        json={"actor_user_id": "masato", "dry_run": True},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "seed.forbidden_in_env"


def test_ac4_invalid_bf_env_rejected(client, _bf_env_invalid):
    """AC-4: BF_ENV=garbage で seed.run は 400 invalid_bf_env."""
    r = client.post(
        "/api/admin/seed/run",
        json={"actor_user_id": "masato", "dry_run": True},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "seed.invalid_bf_env"


def test_ac4_confirm_token_required_when_not_dry_run(client, _bf_env_dev):
    """AC-4: dry_run=False で confirm='I_UNDERSTAND' 無しは 400."""
    r = client.post(
        "/api/admin/seed/run",
        json={"actor_user_id": "masato", "dry_run": False},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "seed.confirm_required"


def test_ac4_empty_actor_rejected(client, _bf_env_dev):
    """AC-4: 空 actor は 401 unauthorized."""
    r = client.post(
        "/api/admin/seed/run",
        json={"actor_user_id": "   ", "dry_run": True},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "seed.unauthorized"


def test_ac4_preview_invalid_max_lines_rejected(client):
    """AC-4: max_lines<=0 は 400."""
    r = client.get("/api/admin/seed/preview", params={"max_lines": 0})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "seed.invalid_max_lines"


def test_ac4_prod_does_not_mutate_or_run_seed(client, _bf_env_prod, _capture_audit):
    """AC-4 UNWANTED: prod 経路で applied audit は emit されない (実行されていない)."""
    client.post(
        "/api/admin/seed/run",
        json={"actor_user_id": "x", "dry_run": False, "confirm": "I_UNDERSTAND"},
    )
    applied = [e for e in _capture_audit if e["event_type"] == "seed.run.applied"]
    assert len(applied) == 0


# ──────────────────────────────────────────────────────────────────────────
# guard module 単体テスト
# ──────────────────────────────────────────────────────────────────────────


def test_guard_require_non_prod_in_dev_no_raise(_bf_env_dev):
    from services.bf_env_guard import require_non_prod
    require_non_prod("test op")  # no raise


def test_guard_require_non_prod_in_prod_raises(_bf_env_prod):
    from services.bf_env_guard import require_non_prod, BFEnvGuardError
    with pytest.raises(BFEnvGuardError):
        require_non_prod("test op")


def test_guard_validate_env_rejects_garbage(_bf_env_invalid):
    from services.bf_env_guard import validate_env, BFInvalidEnvError
    with pytest.raises(BFInvalidEnvError):
        validate_env()


def test_guard_is_prod_true_in_prod(_bf_env_prod):
    from services.bf_env_guard import is_prod
    assert is_prod() is True


def test_guard_is_destructive_allowed_dev(_bf_env_dev):
    from services.bf_env_guard import is_destructive_allowed
    assert is_destructive_allowed() is True


def test_guard_is_destructive_allowed_prod_false(_bf_env_prod):
    from services.bf_env_guard import is_destructive_allowed
    assert is_destructive_allowed() is False


def test_guard_default_env_is_dev(monkeypatch):
    """BF_ENV 未設定なら default = dev."""
    monkeypatch.delenv("BF_ENV", raising=False)
    from services.bf_env_guard import current_env
    assert current_env() == "dev"


def test_seed_sql_text_idempotent():
    """seed.sql は ON CONFLICT を使い idempotent."""
    from services.bf_env_guard import read_seed_sql
    text = read_seed_sql()
    # 各 INSERT に ON CONFLICT がある
    inserts = text.count("INSERT INTO")
    on_conflict = text.count("ON CONFLICT")
    assert on_conflict >= inserts, (
        f"all INSERTs must have ON CONFLICT (inserts={inserts}, on_conflict={on_conflict})"
    )


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client, _bf_env_dev):
    cases = [
        ("POST", "/api/admin/seed/run", {"actor_user_id": "  "}),
        ("POST", "/api/admin/seed/run", {"actor_user_id": "x", "dry_run": False}),
        ("GET", "/api/admin/seed/preview?max_lines=0", None),
    ]
    for method, path, payload in cases:
        if method == "GET":
            r = client.get(path)
        else:
            r = client.post(path, json=payload)
        assert 400 <= r.status_code < 500, f"{path}: {r.status_code}"
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
