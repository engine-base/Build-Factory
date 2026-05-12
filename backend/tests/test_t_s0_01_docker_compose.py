"""T-S0-01: docker-compose.yml 全サービス AC 検証.

DB を立てず YAML/Dockerfile を静的解析する.

AC マッピング:
  AC-1 UBIQUITOUS: 全サービス + healthcheck + depends_on
  AC-2 EVENT:     起動 log で audit (docker logs 経由、 本 task は infra)
  AC-3 STATE:     RLS は postgres init script 経由 (supabase/migrations/)
  AC-4 UNWANTED:  不正 ENV (空 POSTGRES_PASSWORD 等) で fail
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.yml"
BACKEND_DOCKERFILE = ROOT / "backend" / "Dockerfile"
FRONTEND_DOCKERFILE = ROOT / "frontend" / "Dockerfile"


@pytest.fixture(scope="module")
def compose_text() -> str:
    return COMPOSE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def compose() -> dict:
    """yaml lib 不要のため、 簡易 parse (key/value 抽出のみ static check)."""
    text = COMPOSE.read_text(encoding="utf-8")
    # full YAML parse は yaml/pyyaml に依存しないため簡易. 代わりに pattern match.
    return {"_text": text}


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: 全サービス + healthcheck + depends_on
# ──────────────────────────────────────────────────────────────────────────


def test_compose_file_exists() -> None:
    assert COMPOSE.exists(), "docker-compose.yml not at repo root"


def test_compose_has_4_required_services(compose_text: str) -> None:
    """postgres / redis / backend / frontend の 4 service が必須."""
    for svc in ("postgres", "redis", "backend", "frontend"):
        # `  <svc>:` で service block を識別 (top-level services の child)
        assert re.search(
            rf"^  {svc}:\s*$", compose_text, re.MULTILINE,
        ), f"service '{svc}' missing"


def test_compose_uses_supabase_postgres_image(compose_text: str) -> None:
    """Postgres は Supabase 互換 (pgvector / pg_trgm / pgsodium / pg_cron 同梱)."""
    assert "supabase/postgres" in compose_text


def test_compose_postgres_mounts_migrations(compose_text: str) -> None:
    """./supabase/migrations を /docker-entrypoint-initdb.d/ にマウント
    → 起動時に migration 自動実行 (AC-3 STATE: RLS 適用)."""
    assert "./supabase/migrations:/docker-entrypoint-initdb.d:ro" in compose_text


def test_compose_postgres_healthcheck(compose_text: str) -> None:
    """AC-1: postgres に pg_isready healthcheck."""
    assert "pg_isready" in compose_text


def test_compose_redis_healthcheck(compose_text: str) -> None:
    """AC-1: redis に PING healthcheck."""
    # redis-cli ping パターン
    assert re.search(r"redis-cli.*ping", compose_text, re.IGNORECASE)


def test_compose_backend_healthcheck_uses_api_health(compose_text: str) -> None:
    """AC-1: backend に /api/health の curl healthcheck."""
    assert "curl -f http://localhost:8001/api/health" in compose_text


def test_compose_backend_depends_on_postgres_and_redis(compose_text: str) -> None:
    """AC-1: backend は postgres + redis が healthy になってから起動."""
    # backend block 内に depends_on: postgres, redis (service_healthy)
    m = re.search(
        r"^  backend:\s*$(.*?)^  \w+:\s*$",
        compose_text, re.MULTILINE | re.DOTALL,
    )
    if not m:
        # 最後の service の場合は次の top-level セクションまで
        m = re.search(
            r"^  backend:\s*$(.*?)(^volumes:|^networks:|$)",
            compose_text, re.MULTILINE | re.DOTALL,
        )
    assert m
    body = m.group(1)
    assert "depends_on:" in body
    assert re.search(r"postgres:\s*\n\s*condition:\s*service_healthy", body)
    assert re.search(r"redis:\s*\n\s*condition:\s*service_healthy", body)


def test_compose_frontend_depends_on_backend(compose_text: str) -> None:
    """frontend は backend healthy で起動."""
    # frontend は最後の service の場合 `volumes:` までを取る
    m = re.search(
        r"^  frontend:\s*\n(.*?)(\n# |\nvolumes:|\nnetworks:|\Z)",
        compose_text, re.MULTILINE | re.DOTALL,
    )
    assert m
    body = m.group(1)
    assert "depends_on:" in body
    assert "backend:" in body
    assert "service_healthy" in body


def test_compose_uses_dedicated_network(compose_text: str) -> None:
    """サービス間通信用に dedicated network."""
    assert "networks:" in compose_text
    assert "bf-net" in compose_text


def test_compose_postgres_volume_persistent(compose_text: str) -> None:
    """volume mount で data 永続化."""
    assert "postgres_data:" in compose_text
    assert "/var/lib/postgresql/data" in compose_text


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE: env override + 設定の柔軟性
# ──────────────────────────────────────────────────────────────────────────


def test_compose_supports_env_override_for_ports(compose_text: str) -> None:
    """${VAR:-default} 形式で port を env 上書き可能."""
    assert re.search(r"\$\{POSTGRES_PORT:-54322\}", compose_text)
    assert re.search(r"\$\{BACKEND_PORT:-8001\}", compose_text)
    assert re.search(r"\$\{FRONTEND_PORT:-3000\}", compose_text)


def test_compose_supports_env_override_for_credentials(compose_text: str) -> None:
    """credentials も env 経由で上書き可能 (default は dev 用)."""
    assert "${POSTGRES_USER:-postgres}" in compose_text
    assert "${POSTGRES_PASSWORD:-postgres}" in compose_text


def test_compose_supports_anthropic_api_key_passthrough(compose_text: str) -> None:
    """ANTHROPIC_API_KEY を backend container に流す."""
    assert "ANTHROPIC_API_KEY:" in compose_text


def test_compose_supports_supabase_credentials_passthrough(compose_text: str) -> None:
    """SUPABASE_URL / SERVICE_KEY を backend に."""
    assert "SUPABASE_URL:" in compose_text
    assert "SUPABASE_SERVICE_KEY:" in compose_text


def test_compose_frontend_receives_next_public_api_base(compose_text: str) -> None:
    """frontend に NEXT_PUBLIC_API_BASE を渡す (browser → backend)."""
    assert "NEXT_PUBLIC_API_BASE" in compose_text


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 無効な設定の検出
# ──────────────────────────────────────────────────────────────────────────


def test_compose_no_secret_baked_in() -> None:
    """compose.yml に実 secret (sk-ant- / xoxb- / postgres real password 等) が
    リテラルで埋め込まれていないこと (CLAUDE.md §5.4 / lint-secrets と整合)."""
    text = COMPOSE.read_text(encoding="utf-8")
    forbidden_patterns = [
        r"sk-ant-[A-Za-z0-9_-]{20,}",     # Anthropic key
        r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}",
        r"xoxb-[A-Za-z0-9_-]{20,}",        # Slack bot
    ]
    for p in forbidden_patterns:
        assert not re.search(p, text), f"secret pattern leaked: {p}"


def test_compose_has_no_emoji() -> None:
    """CLAUDE.md §5.1: 絵文字禁止."""
    text = COMPOSE.read_text(encoding="utf-8")
    emoji_re = re.compile(
        r"[\U0001F000-\U0001FFFF\U00002600-\U000027BF\U0001F300-\U0001F9FF]"
    )
    found = emoji_re.findall(text)
    assert not found, f"emoji in compose: {found}"


def test_compose_postgres_password_has_default_for_dev(compose_text: str) -> None:
    """dev 用 POSTGRES_PASSWORD は default 'postgres' (production は env 必須)."""
    assert "POSTGRES_PASSWORD:-postgres" in compose_text


# ──────────────────────────────────────────────────────────────────────────
# Backend Dockerfile
# ──────────────────────────────────────────────────────────────────────────


def test_backend_dockerfile_exists() -> None:
    assert BACKEND_DOCKERFILE.exists()


def test_backend_dockerfile_uses_python_3_13_slim() -> None:
    text = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "FROM python:3.13-slim" in text


def test_backend_dockerfile_uses_multistage() -> None:
    """Multi-stage build (base / deps / runtime)."""
    text = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "FROM python:3.13-slim AS base" in text
    assert re.search(r"FROM base AS deps", text)
    assert re.search(r"FROM deps AS runtime", text)


def test_backend_dockerfile_uses_non_root_user() -> None:
    """USER bf で non-root 起動."""
    text = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "USER bf" in text
    assert "useradd" in text


def test_backend_dockerfile_includes_bubblewrap_for_sandbox() -> None:
    """T-S0-09 sandbox 用 bubblewrap が image に含まれる."""
    text = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "bubblewrap" in text


def test_backend_dockerfile_includes_git_for_worktree() -> None:
    """T-M29-01 git worktree 用 git が image に含まれる."""
    text = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(r"\bgit\b", text)


def test_backend_dockerfile_exposes_8001() -> None:
    text = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "EXPOSE 8001" in text


def test_backend_dockerfile_uses_uvicorn_for_cmd() -> None:
    text = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "uvicorn" in text and "main:app" in text


# ──────────────────────────────────────────────────────────────────────────
# Frontend Dockerfile
# ──────────────────────────────────────────────────────────────────────────


def test_frontend_dockerfile_exists() -> None:
    assert FRONTEND_DOCKERFILE.exists()


def test_frontend_dockerfile_uses_node_22_alpine() -> None:
    text = FRONTEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "FROM node:22-alpine" in text


def test_frontend_dockerfile_uses_multistage() -> None:
    text = FRONTEND_DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(r"FROM node:22-alpine AS deps", text)
    assert re.search(r"FROM node:22-alpine AS build", text)
    assert re.search(r"FROM node:22-alpine AS runtime", text)


def test_frontend_dockerfile_uses_legacy_peer_deps() -> None:
    """React 19 + 一部 lib の peer 警告を許容."""
    text = FRONTEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "--legacy-peer-deps" in text


def test_frontend_dockerfile_uses_non_root_user() -> None:
    text = FRONTEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "USER nextjs" in text


def test_frontend_dockerfile_exposes_3000() -> None:
    text = FRONTEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "EXPOSE 3000" in text


def test_frontend_dockerfile_uses_standalone_output() -> None:
    """Next.js standalone output で minimal runtime."""
    text = FRONTEND_DOCKERFILE.read_text(encoding="utf-8")
    assert ".next/standalone" in text
    assert "node" in text and "server.js" in text


def test_frontend_dockerfile_disables_telemetry() -> None:
    text = FRONTEND_DOCKERFILE.read_text(encoding="utf-8")
    assert "NEXT_TELEMETRY_DISABLED=1" in text


# ──────────────────────────────────────────────────────────────────────────
# Security boundary
# ──────────────────────────────────────────────────────────────────────────


def test_neither_dockerfile_uses_root_at_runtime() -> None:
    """両 Dockerfile が USER directive で non-root に切り替え."""
    for path in (BACKEND_DOCKERFILE, FRONTEND_DOCKERFILE):
        text = path.read_text(encoding="utf-8")
        assert "USER " in text, f"{path.name}: no USER directive (root のまま)"


def test_compose_uses_read_only_migration_mount() -> None:
    """migration mount は :ro で書き込み禁止."""
    text = COMPOSE.read_text(encoding="utf-8")
    assert "/docker-entrypoint-initdb.d:ro" in text


# ──────────────────────────────────────────────────────────────────────────
# tickets.json AC 具体化 (spec rigor)
# ──────────────────────────────────────────────────────────────────────────


def test_tickets_t_s0_01_ac_concretized() -> None:
    import json
    path = ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-01"), None)
    assert t is not None
    generic = [
        "as specified by feature META",
        "When the implementation step for T-S0-01 is triggered",
        "While the new feature for T-S0-01 is enabled",
        "If invalid input or unauthorized actor is detected during T-S0-01",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], (
                f"T-S0-01 still generic: {phrase!r}"
            )
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "docker-compose.yml" in full
    assert "postgres" in full and "redis" in full and "litellm" in full
    assert "depends_on" in full and "healthcheck" in full


def test_tickets_t_s0_01_has_adr_link_and_files() -> None:
    import json
    path = ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-01"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert "TBD" not in str(files)
    assert "docker-compose.yml" in files
    assert "backend/Dockerfile" in files
    assert "frontend/Dockerfile" in files


def test_compose_litellm_is_opt_in_profile() -> None:
    """T-S0-01 AC-3 / ADR-010: litellm は profile opt-in (常時起動しない)."""
    text = COMPOSE.read_text(encoding="utf-8")
    # litellm block 内に profiles: + - litellm
    m = re.search(r"\n  litellm:\s*\n((?:    .+\n)+)", text)
    assert m, "litellm service block not found"
    block = m.group(1)
    assert "profiles:" in block
    assert "- litellm" in block


def test_compose_litellm_uses_health_liveliness() -> None:
    """T-S0-01 AC-2: litellm healthcheck = /health/liveliness."""
    text = COMPOSE.read_text(encoding="utf-8")
    assert "/health/liveliness" in text


def test_compose_no_latest_image_tag() -> None:
    """T-S0-01 AC-4: :latest tag は禁止 (pinned tag のみ)."""
    text = COMPOSE.read_text(encoding="utf-8")
    latest_hits = re.findall(r"image:\s*\S+:latest\b", text)
    assert not latest_hits, f":latest image tag detected: {latest_hits}"


def test_compose_secrets_are_env_interpolation_only() -> None:
    """T-S0-01 AC-3: env block の secret keys は ${VAR:-...} 経由のみ.

    matching scope: 行頭 indent (6 spaces 以上) + KEY: で env block の declaration
    のみ拾う. 接続文字列 (DATABASE_URL: postgresql://...PASSWORD...) 内の
    substring は対象外.
    """
    text = COMPOSE.read_text(encoding="utf-8")
    for key in (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "SUPABASE_SERVICE_KEY",
        "POSTGRES_PASSWORD",
        "LITELLM_MASTER_KEY",
    ):
        # ^      KEY: value (env block declaration)
        for m in re.finditer(
            rf"^      {key}:\s*(\S+)", text, re.MULTILINE,
        ):
            val = m.group(1).strip()
            assert val.startswith("$") or val == "", (
                f"{key} env declaration must be ${{VAR}} interpolation, "
                f"got {val!r}"
            )