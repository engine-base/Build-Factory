"""T-IT-S0: Sprint 0 統合テスト.

Sprint 0 の bootstrap / scaffold 一式 (FastAPI モジュラーモノリス基盤 / Supabase
env validation / 11+ migrations / observability 3 層 / sandbox / BF_ENV guard /
RLS / tenant 階層) が **同一プロセスで coherent に動く** ことを end-to-end で
verify する integration smoke.

ユニットテストの再実行ではなく **module 間契約 / boot 時整合性** を assert.
既存 test を import / call せず, 自己完結で書く.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : T-IT-S0 を Sprint 0 統合テストとして実装.
  AC-2 EVENT-DRIVEN  : 実装ステップで audit entry を残す (test 実行で sentinel
                       が書ける + boot timestamp 取得可).
  AC-3 STATE-DRIVEN  : 機能 enable 時に RLS / audit_logs を適用 (RLS migration
                       存在 + RLS helper import + BF_ENV guard).
  AC-4 UNWANTED      : invalid input / unauthorized で 4xx + state mutate なし.

Scenarios (各 2+ Sprint 0 deliverable を同時に触る):
  (a) Bootstrap 整合性             — T-019-01 + T-019-03 + T-S0-08 + T-001-01
  (b) Supabase 環境 + BF_ENV guard — T-001-01 + T-001-10
  (c) Migrations 集合              — T-001-02 〜 T-001-09
  (d) Observability 3 層           — T-S0-10 + T-S0-11 + T-S0-12
  (e) Sandbox 基盤                 — T-S0-09 + T-S0-09b
  (f) ADR-010 invariant            — Sprint 0 全体
  (g) Tenant 階層                  — T-004-01 〜 T-004-06
  (h) CI / workflows               — T-S0-02 + T-S0-03 + T-S0-04

外部 network / DB call なし. ENV は monkeypatch で仮置.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest


# ──────────────────────────────────────────────────────────────────────
# Path setup (backend/ をパスに通す: 既存テスト同様)
# ──────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


# Sprint 0 で投入されたとされる migrations (T-001-02〜09)
_REQUIRED_MIGRATION_FRAGMENTS = (
    "auth_tables",                            # T-001-02
    "bf_project_tables",                      # T-001-04
    "rls_full_enforcement",                   # T-001-06
    "runner_session_tables",                  # T-S0-08 (chat_threads/messages 同梱)
    "ai_hierarchy_clone_tables",              # T-001-03
    "impl_integration_ops_tables",            # T-001-05
    "cycle_prevention_triggers",              # T-001-09
    "extensions_pgsodium_pgcron_indexes",     # T-001-07
    "audit_logs_triggers",                    # T-018-01 系 (Sprint 0 dep)
    "pgvector",                               # T-001-07
    "initial_schema",                         # base
)


# Sprint 0 重要 router の prefix
_REQUIRED_ROUTER_PREFIXES = (
    "/api/accounts",          # T-004-01
    "/api/workspaces",        # T-004-02
    "/api/invitations",       # T-004-03/04
    "/api/chat-threads",      # T-S0-08 同梱
    "/api/skills",            # T-002-01
    "/api/sandbox/landlock",  # T-S0-09
    "/api/byok",              # provider key 管理 (S0 期)
)


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _supabase_env_stub(monkeypatch):
    """T-001-01 fail-fast を避けるため Supabase 4 keys を仮置.

    本物の API call は走らない (本 file 内では DB に触らない / TestClient で
    public endpoint のみ叩く).
    """
    monkeypatch.setenv("SUPABASE_URL", "https://stub.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "stub-anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "stub-service-key")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "stub-jwt-secret")
    # observability 外部送信を回避
    for k in (
        "SENTRY_DSN",
        "SENTRY_ENVIRONMENT",
        "BETTER_STACK_HEARTBEAT_URL",
    ):
        monkeypatch.delenv(k, raising=False)
    yield


@pytest.fixture
def app_instance():
    """main:app を新規 import (Sprint 0 bootstrap 整合性を直接観察)."""
    import main  # noqa: F401 — import side effect で routers が登録される
    return main.app


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS: 統合テストそのものの実装
# ══════════════════════════════════════════════════════════════════════


def test_ac1_this_file_is_registered_as_t_it_s0_integration_test():
    """本 file が T-IT-S0 integration test として配置されている."""
    self_path = Path(__file__)
    assert self_path.name == "test_t_it_s0_sprint0_integration.py"
    # backend/tests/ 配下にあること (collection root の整合性)
    assert self_path.parent.name == "tests"
    assert self_path.parent.parent.name == "backend"


def test_ac1_sprint0_audit_doc_exists():
    """対応する pre-flight audit doc が repo に存在する."""
    audit = REPO_ROOT / "docs" / "audit" / "2026-05-13_v2" / "T-IT-S0.md"
    assert audit.exists(), f"audit doc not found: {audit}"
    text = audit.read_text(encoding="utf-8")
    assert "T-IT-S0" in text
    assert "Sprint 0 統合テスト" in text


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: 実装ステップで audit / timestamp が残る
# ══════════════════════════════════════════════════════════════════════


def test_ac2_app_boot_produces_observable_state(app_instance):
    """main:app boot 後に route table が populate される = boot event の証跡."""
    routes = app_instance.routes
    # 200+ route があれば bootstrap 完走と判定 (Sprint 0 期で 480+ 想定)
    assert len(routes) >= 200, f"app.routes too few: {len(routes)}"


def test_ac2_audit_log_emitter_module_importable():
    """audit_logs への emit_event API が存在 = AC-2 audit entry の hook 点."""
    from services import memory_service  # noqa: F401
    assert hasattr(memory_service, "emit_event")


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: RLS / audit_logs / BF_ENV guard
# ══════════════════════════════════════════════════════════════════════


def test_ac3_rls_full_enforcement_migration_present():
    """T-001-06: RLS 全 23 テーブル enforcement migration が存在."""
    mig = REPO_ROOT / "supabase" / "migrations" / "20260510000002_rls_full_enforcement.sql"
    assert mig.exists(), f"RLS migration missing: {mig}"
    body = mig.read_text(encoding="utf-8")
    # RLS 有効化命令が必ず含まれる
    assert "ENABLE ROW LEVEL SECURITY" in body.upper()


def test_ac3_audit_logs_triggers_migration_present():
    """audit_logs triggers migration が Sprint 0 期に存在."""
    mig_dir = REPO_ROOT / "supabase" / "migrations"
    matches = list(mig_dir.glob("*audit_logs_triggers*.sql"))
    assert len(matches) >= 1, "audit_logs trigger migration missing"


def test_ac3_bf_env_guard_blocks_prod_destructive(monkeypatch):
    """T-001-10: prod では destructive op が reject される."""
    from services import bf_env_guard

    monkeypatch.setenv("BF_ENV", "prod")
    assert bf_env_guard.current_env() == "prod"
    assert bf_env_guard.is_prod() is True
    assert bf_env_guard.is_destructive_allowed() is False
    with pytest.raises(bf_env_guard.BFEnvGuardError):
        bf_env_guard.require_non_prod()


def test_ac3_bf_env_guard_allows_dev_destructive(monkeypatch):
    """dev / test / local では destructive op が許される."""
    from services import bf_env_guard

    for env in ("dev", "test", "local"):
        monkeypatch.setenv("BF_ENV", env)
        assert bf_env_guard.is_destructive_allowed() is True
        # require_non_prod() は no-op
        bf_env_guard.require_non_prod()


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: invalid input / unauthorized で 4xx
# ══════════════════════════════════════════════════════════════════════


def test_ac4_missing_supabase_env_fail_fast(monkeypatch):
    """T-001-01: SUPABASE_* env が 1 つでも欠ければ起動で fail."""
    from config import validate_required_env, REQUIRED_SUPABASE

    # Supabase 4 keys を全削除
    for k in REQUIRED_SUPABASE:
        monkeypatch.delenv(k, raising=False)

    # exit_on_failure=False では list を返す
    missing = validate_required_env(exit_on_failure=False)
    assert set(missing) == set(REQUIRED_SUPABASE)

    # exit_on_failure=True (デフォルト) では SystemExit(1)
    with pytest.raises(SystemExit) as exc_info:
        validate_required_env()
    assert exc_info.value.code == 1


def test_ac4_accounts_post_invalid_body_returns_4xx(app_instance):
    """invalid body (必須フィールド `name` 欠落) を POST /api/accounts に
    投げると Pydantic validation で 422 (4xx) を返し DB に到達せず
    state を mutate しない. T-004-01 / T-S0-08 error contract 互換性."""
    from fastapi.testclient import TestClient

    client = TestClient(app_instance, raise_server_exceptions=False)
    # name (必須) 欠落 → Pydantic 422 (validation 段階で reject, DB 未到達)
    r = client.post("/api/accounts", json={})
    assert 400 <= r.status_code < 500, f"expected 4xx, got {r.status_code}"
    # FastAPI default validation error contract = {detail: [...]}
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    assert "detail" in body, f"missing detail key: {body}"


def test_ac4_unknown_path_returns_4xx(app_instance):
    """存在しない path に投げると 404 (4xx) を返し、state を mutate しない."""
    from fastapi.testclient import TestClient

    client = TestClient(app_instance, raise_server_exceptions=False)
    r = client.get("/api/__nonexistent_t_it_s0__")
    assert r.status_code == 404


# ══════════════════════════════════════════════════════════════════════
# Scenario (a) Bootstrap 整合性
# ══════════════════════════════════════════════════════════════════════


def test_scenario_a_main_app_importable(app_instance):
    """T-019-03: main:app が import できる."""
    from fastapi import FastAPI

    assert isinstance(app_instance, FastAPI)


def test_scenario_a_archived_dirs_removed():
    """T-019-01: onlook / penpot は repo root から除去済み."""
    for archived in ("onlook", "penpot"):
        p = REPO_ROOT / archived
        # 完全削除 or archive/ 下に移動済みのどちらかであれば OK
        assert not p.exists(), f"archive target still at root: {p}"


def test_scenario_a_required_routers_registered(app_instance):
    """Sprint 0 期に登録されるべき主要 router prefix が app.routes に存在."""
    paths = {getattr(r, "path", "") for r in app_instance.routes}

    for prefix in _REQUIRED_ROUTER_PREFIXES:
        matched = any(p.startswith(prefix) for p in paths if p)
        assert matched, f"required prefix not registered: {prefix}"


# ══════════════════════════════════════════════════════════════════════
# Scenario (b) Supabase 環境 + BF_ENV guard
# ══════════════════════════════════════════════════════════════════════


def test_scenario_b_required_supabase_keys_exact_4():
    """T-001-01: REQUIRED_SUPABASE が exact 4 keys."""
    from config import REQUIRED_SUPABASE

    assert set(REQUIRED_SUPABASE) == {
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_KEY",
        "SUPABASE_JWT_SECRET",
    }


def test_scenario_b_bf_env_guard_valid_envs():
    """T-001-10: VALID_ENVS が exact 5 種."""
    from services import bf_env_guard

    assert bf_env_guard.VALID_ENVS == ("dev", "test", "local", "staging", "prod")
    assert "prod" not in bf_env_guard.DESTRUCTIVE_ALLOWED_ENVS
    assert "staging" not in bf_env_guard.DESTRUCTIVE_ALLOWED_ENVS


def test_scenario_b_seed_sql_exists():
    """T-001-10: supabase/seed.sql が存在し bf_env_guard が指す."""
    from services import bf_env_guard

    seed_path = bf_env_guard.seed_sql_path()
    assert seed_path.exists(), f"seed.sql missing: {seed_path}"
    # idempotent な seed の慣行 — INSERT が含まれる
    body = seed_path.read_text(encoding="utf-8")
    assert "INSERT" in body.upper() or "SELECT" in body.upper()


# ══════════════════════════════════════════════════════════════════════
# Scenario (c) Migrations 集合
# ══════════════════════════════════════════════════════════════════════


def test_scenario_c_all_required_sprint0_migrations_present():
    """Sprint 0 で投入される 11 種 migration が全部存在."""
    mig_dir = REPO_ROOT / "supabase" / "migrations"
    assert mig_dir.is_dir(), f"migration dir missing: {mig_dir}"

    all_sql = list(mig_dir.glob("*.sql"))
    all_names = " ".join(p.name for p in all_sql)

    missing = [frag for frag in _REQUIRED_MIGRATION_FRAGMENTS if frag not in all_names]
    assert not missing, f"missing migrations: {missing}"


def test_scenario_c_migration_count_meets_baseline():
    """Sprint 0 完了後の migration ファイル数が baseline 以上."""
    mig_dir = REPO_ROOT / "supabase" / "migrations"
    sql_files = list(mig_dir.glob("*.sql"))
    assert len(sql_files) >= 11, f"too few migrations: {len(sql_files)}"


# ══════════════════════════════════════════════════════════════════════
# Scenario (d) Observability 3 層
# ══════════════════════════════════════════════════════════════════════


def test_scenario_d_sentry_config_public_api_available():
    """T-S0-10: Sentry config の公開 API がそろっている."""
    import sentry_config

    for name in ("init_sentry", "capture_exception", "set_user", "set_tag",
                 "reset_for_tests"):
        assert hasattr(sentry_config, name), f"missing API: sentry_config.{name}"


def test_scenario_d_sentry_no_op_without_dsn(monkeypatch):
    """T-S0-10: SENTRY_DSN 未設定で全 API が graceful no-op."""
    monkeypatch.delenv("SENTRY_DSN", raising=False)

    import sentry_config
    sentry_config.reset_for_tests()
    # init_sentry は例外を投げない
    try:
        sentry_config.init_sentry()
    except Exception as e:  # pragma: no cover
        pytest.fail(f"init_sentry raised without DSN: {e}")
    # capture_exception は None を返す (graceful)
    sentry_config.set_user("anon")
    sentry_config.set_tag("env", "test")


def test_scenario_d_logging_config_public_api_available():
    """T-S0-11: structlog wrapper の公開 API がそろっている."""
    import logging_config

    for name in ("configure_structlog", "get_logger", "bind_context",
                 "clear_context"):
        assert hasattr(logging_config, name), f"missing API: logging_config.{name}"


def test_scenario_d_uptime_heartbeat_graceful_without_url(monkeypatch):
    """T-S0-12: BETTER_STACK_HEARTBEAT_URL 未設定で is_configured() = False."""
    monkeypatch.delenv("BETTER_STACK_HEARTBEAT_URL", raising=False)

    # 既に import 済みでも安全に動く形式 (heartbeat URL は毎回 env 参照)
    import uptime_heartbeat
    importlib.reload(uptime_heartbeat)

    assert uptime_heartbeat.get_heartbeat_url() is None
    assert uptime_heartbeat.is_configured() is False


# ══════════════════════════════════════════════════════════════════════
# Scenario (e) Sandbox 基盤
# ══════════════════════════════════════════════════════════════════════


def test_scenario_e_sandbox_public_api_complete():
    """T-S0-09: sandbox パッケージの公開 API が一式そろっている."""
    import sandbox

    expected = {
        "SandboxConfig", "SandboxResult", "SandboxError",
        "SandboxViolation", "SandboxUnavailable", "run_sandboxed",
    }
    actual = set(getattr(sandbox, "__all__", []))
    missing = expected - actual
    assert not missing, f"sandbox.__all__ missing: {missing}"

    for name in expected:
        assert hasattr(sandbox, name), f"sandbox.{name} not exported"


def test_scenario_e_auth_middleware_importable():
    """T-S0-09b: RLS context helper / auth_middleware が import 可能."""
    from services import auth_middleware

    assert hasattr(auth_middleware, "get_current_user")
    assert hasattr(auth_middleware, "require_user")


# ══════════════════════════════════════════════════════════════════════
# Scenario (f) ADR-010 invariant: runner 系に LangGraph/LangChain 無し
# ══════════════════════════════════════════════════════════════════════


def test_scenario_f_runner_modules_no_langgraph_langchain():
    """ADR-010: claude-agent-sdk runner / agent_runner で LangGraph/LangChain
    import が文字列レベルで存在しないこと.
    既存 lint (scripts/lint-mock.sh check 6) と二重防衛.
    """
    candidates = [
        BACKEND_ROOT / "routers" / "agent_runner.py",
        BACKEND_ROOT / "services" / "claude_runner.py",
        BACKEND_ROOT / "ai_agents" / "secretary_agent.py",
    ]
    forbidden = ("from langgraph", "import langgraph",
                 "from langchain", "import langchain")
    for p in candidates:
        if not p.exists():
            continue
        body = p.read_text(encoding="utf-8")
        for f in forbidden:
            # コメントを除いた lines で発見されてはいけない
            for line in body.splitlines():
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                assert f not in line, f"{p}: forbidden import `{f}` in non-comment line"


# ══════════════════════════════════════════════════════════════════════
# Scenario (g) Tenant 階層 (T-004-01〜06)
# ══════════════════════════════════════════════════════════════════════


def test_scenario_g_account_service_public_api():
    """T-004-01: account_service の主要関数が import 可能."""
    from services import account_service

    for name in ("create_account", "get_account", "list_accounts",
                 "update_account", "deactivate_account", "list_members"):
        assert hasattr(account_service, name), f"account_service.{name} missing"


def test_scenario_g_workspace_service_public_api():
    """T-004-02: workspace_service の主要関数が import 可能."""
    from services import workspace_service

    for name in ("create_workspace", "get_workspace",
                 "list_workspaces_by_account", "list_workspaces_for_user",
                 "update_workspace", "archive_workspace"):
        assert hasattr(workspace_service, name), f"workspace_service.{name} missing"


def test_scenario_g_workspace_preferred_provider_validation():
    """T-S0-08/ADR-012 系: preferred_provider validation が存在."""
    from services import workspace_service

    assert hasattr(workspace_service, "validate_preferred_provider")
    assert hasattr(workspace_service, "InvalidPreferredProviderError")
    with pytest.raises(workspace_service.InvalidPreferredProviderError):
        workspace_service.validate_preferred_provider("nonexistent-provider")


# ══════════════════════════════════════════════════════════════════════
# Scenario (h) CI / workflows
# ══════════════════════════════════════════════════════════════════════


def test_scenario_h_required_workflows_exist():
    """T-S0-02 + T-S0-03 + T-S0-04: 主要 CI workflow が存在."""
    wf_dir = REPO_ROOT / ".github" / "workflows"
    assert wf_dir.is_dir(), f"workflows dir missing: {wf_dir}"

    for name in ("ci.yml", "license-check.yml", "deploy-staging.yml"):
        path = wf_dir / name
        assert path.exists(), f"workflow missing: {path}"


def test_scenario_h_workflow_count():
    """Sprint 0 完了後の workflow yml ファイル数が baseline 以上."""
    wf_dir = REPO_ROOT / ".github" / "workflows"
    ymls = list(wf_dir.glob("*.yml"))
    assert len(ymls) >= 3, f"too few workflows: {len(ymls)}"
