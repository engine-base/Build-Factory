"""T-017-01: Langfuse self-host docker-compose — 4 AC 機械 invariant 検証.

NEW OPS タスク. docker compose CLI 不要で yaml を Python で parse + 検証.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : docker-compose.langfuse.yml が 4 service
                       (langfuse-web / langfuse-worker / langfuse-clickhouse /
                       langfuse-minio) 宣言 / main docker-compose.yml 無改変.
  AC-2 EVENT-DRIVEN  : yaml が有効 / depends_on chain / DATABASE_URL →
                       既存 postgres REUSE / CLICKHOUSE_URL → langfuse-clickhouse.
  AC-3 STATE-DRIVEN  : port 3001:3000 / 2 named volume / .env.langfuse.example
                       に 8 必須 ENV + placeholder のみ (real secret なし).
  AC-4 UNWANTED      : main compose service を override しない / image:latest
                       禁止 (pin) / real secret hardcode なし.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


REPO_ROOT = Path(__file__).resolve().parents[2]
MAIN_COMPOSE = REPO_ROOT / "docker-compose.yml"
LANGFUSE_COMPOSE = REPO_ROOT / "docker-compose.langfuse.yml"
ENV_EXAMPLE = REPO_ROOT / ".env.langfuse.example"


@pytest.fixture(scope="module")
def langfuse_compose():
    if yaml is None:
        pytest.skip("PyYAML not installed")
    return yaml.safe_load(LANGFUSE_COMPOSE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def main_compose():
    if yaml is None:
        pytest.skip("PyYAML not installed")
    return yaml.safe_load(MAIN_COMPOSE.read_text(encoding="utf-8"))


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — 4 services + main compose unchanged
# ══════════════════════════════════════════════════════════════════════


def test_ac1_langfuse_compose_file_exists():
    assert LANGFUSE_COMPOSE.exists()


def test_ac1_env_example_file_exists():
    assert ENV_EXAMPLE.exists()


def test_ac1_langfuse_compose_yaml_valid(langfuse_compose):
    assert isinstance(langfuse_compose, dict)
    assert "services" in langfuse_compose


@pytest.mark.parametrize("svc", [
    "langfuse-web",
    "langfuse-worker",
    "langfuse-clickhouse",
    "langfuse-minio",
])
def test_ac1_4_services_declared(svc, langfuse_compose):
    services = langfuse_compose.get("services", {})
    assert svc in services, f"missing service: {svc}"


def test_ac1_no_extra_services(langfuse_compose):
    """Langfuse compose は 4 service のみ. main compose を override しない."""
    services = set(langfuse_compose.get("services", {}).keys())
    expected = {"langfuse-web", "langfuse-worker", "langfuse-clickhouse", "langfuse-minio"}
    assert services == expected, (
        f"unexpected services: {services - expected}"
    )


def test_ac1_main_compose_does_not_reference_langfuse_yet(main_compose):
    """T-017-01 invariant: main docker-compose.yml に langfuse-* service なし
    (optional merge file 設計)."""
    main_services = main_compose.get("services", {})
    for s in main_services.keys():
        assert "langfuse" not in s.lower(), (
            f"main compose must NOT declare langfuse service: {s}"
        )


def test_ac1_langfuse_compose_has_2_volumes(langfuse_compose):
    volumes = langfuse_compose.get("volumes", {})
    assert "langfuse_clickhouse_data" in volumes
    assert "langfuse_minio_data" in volumes


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — depends_on chain + DB / CH URL REUSE
# ══════════════════════════════════════════════════════════════════════


def test_ac2_web_depends_on_worker_clickhouse_minio(langfuse_compose):
    web = langfuse_compose["services"]["langfuse-web"]
    deps = web.get("depends_on", [])
    if isinstance(deps, dict):
        deps = list(deps.keys())
    deps_set = set(deps)
    assert "langfuse-worker" in deps_set
    assert "langfuse-clickhouse" in deps_set
    assert "langfuse-minio" in deps_set


def test_ac2_worker_depends_on_clickhouse(langfuse_compose):
    worker = langfuse_compose["services"]["langfuse-worker"]
    deps = worker.get("depends_on", [])
    if isinstance(deps, dict):
        deps = list(deps.keys())
    assert "langfuse-clickhouse" in deps


def test_ac2_web_database_url_points_to_postgres(langfuse_compose):
    """T-S0-01 REUSE: 既存 supabase/postgres を REUSE (DB は二重起動しない)."""
    web = langfuse_compose["services"]["langfuse-web"]
    env = web.get("environment", {})
    db_url = env.get("DATABASE_URL", "")
    assert "postgres:5432" in db_url, (
        f"DATABASE_URL must point to existing postgres:5432, got: {db_url}"
    )


def test_ac2_worker_database_url_points_to_postgres(langfuse_compose):
    worker = langfuse_compose["services"]["langfuse-worker"]
    env = worker.get("environment", {})
    db_url = env.get("DATABASE_URL", "")
    assert "postgres:5432" in db_url


def test_ac2_clickhouse_url_points_to_langfuse_clickhouse(langfuse_compose):
    web = langfuse_compose["services"]["langfuse-web"]
    env = web.get("environment", {})
    ch_url = env.get("CLICKHOUSE_URL", "")
    assert "langfuse-clickhouse:8123" in ch_url, (
        f"CLICKHOUSE_URL must point to langfuse-clickhouse:8123, got: {ch_url}"
    )


def test_ac2_main_compose_has_postgres_service(main_compose):
    """T-S0-01 REUSE 前提: main compose に postgres が居る."""
    services = main_compose.get("services", {})
    assert "postgres" in services


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — port 3001:3000 / 2 volumes / 8 ENV in example
# ══════════════════════════════════════════════════════════════════════


def test_ac3_langfuse_web_port_3001_3000(langfuse_compose):
    """frontend default 3000 と衝突回避."""
    web = langfuse_compose["services"]["langfuse-web"]
    ports = web.get("ports", [])
    # "3001:3000" 形式 / {host: 3001, container: 3000} 形式の両方を許容
    found = False
    for p in ports:
        s = str(p)
        if "3001:3000" in s:
            found = True
            break
        if isinstance(p, dict):
            if (str(p.get("published")) == "3001"
                    and str(p.get("target")) == "3000"):
                found = True
                break
    assert found, f"langfuse-web must expose 3001:3000, got: {ports}"


def test_ac3_clickhouse_volume_mounted(langfuse_compose):
    ch = langfuse_compose["services"]["langfuse-clickhouse"]
    volumes = ch.get("volumes", [])
    found = any("langfuse_clickhouse_data" in str(v) for v in volumes)
    assert found, "langfuse-clickhouse must mount langfuse_clickhouse_data"


def test_ac3_minio_volume_mounted(langfuse_compose):
    minio = langfuse_compose["services"]["langfuse-minio"]
    volumes = minio.get("volumes", [])
    found = any("langfuse_minio_data" in str(v) for v in volumes)
    assert found, "langfuse-minio must mount langfuse_minio_data"


def test_ac3_env_example_has_8_required_keys():
    src = ENV_EXAMPLE.read_text(encoding="utf-8")
    required = (
        "NEXTAUTH_SECRET",
        "SALT",
        "ENCRYPTION_KEY",
        "TELEMETRY_ENABLED",
        "LANGFUSE_INIT_ORG_NAME",
        "LANGFUSE_INIT_USER_EMAIL",
        "LANGFUSE_INIT_PROJECT_PUBLIC_KEY",
        "LANGFUSE_INIT_PROJECT_SECRET_KEY",
    )
    for key in required:
        assert re.search(rf"^{key}=", src, re.MULTILINE), (
            f".env.langfuse.example missing key: {key}"
        )


def test_ac3_env_example_contains_only_placeholders():
    """real secret が書かれていないこと (placeholder のみ)."""
    src = ENV_EXAMPLE.read_text(encoding="utf-8")
    # sk-ant- / sk-lf-XXXX (real) / pk-lf-XXXX (real)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)
    # ENCRYPTION_KEY が all zeros placeholder
    assert "ENCRYPTION_KEY=0000000000" in src
    # placeholder marker が含まれる
    assert "change-me" in src or "placeholder" in src


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED — no override / no :latest / no real secret
# ══════════════════════════════════════════════════════════════════════


def test_ac4_no_override_of_main_compose_services(langfuse_compose, main_compose):
    """main compose service を langfuse compose で上書きしない."""
    main = set(main_compose.get("services", {}).keys())
    lf = set(langfuse_compose.get("services", {}).keys())
    overlap = main & lf
    assert not overlap, (
        f"docker-compose.langfuse.yml overrides main services: {overlap}"
    )


@pytest.mark.parametrize("svc", [
    "langfuse-web",
    "langfuse-worker",
    "langfuse-clickhouse",
    "langfuse-minio",
])
def test_ac4_no_latest_image_tag(svc, langfuse_compose):
    """image:latest 禁止. major version で pin / RELEASE-* で pin."""
    image = langfuse_compose["services"][svc].get("image", "")
    assert image, f"{svc} missing image"
    assert ":latest" not in image, (
        f"{svc} uses :latest (reproducibility violation): {image}"
    )
    assert ":" in image, (
        f"{svc} image must have explicit tag (not implicit latest): {image}"
    )


def test_ac4_langfuse_images_pinned_major_version(langfuse_compose):
    """specific images: langfuse:3 / langfuse-worker:3."""
    web = langfuse_compose["services"]["langfuse-web"]["image"]
    worker = langfuse_compose["services"]["langfuse-worker"]["image"]
    assert "langfuse/langfuse:3" in web
    assert "langfuse/langfuse-worker:3" in worker


def test_ac4_clickhouse_image_pinned(langfuse_compose):
    ch = langfuse_compose["services"]["langfuse-clickhouse"]["image"]
    # major 24 で pin
    assert "clickhouse/clickhouse-server:24" in ch


def test_ac4_minio_image_pinned_to_release(langfuse_compose):
    """MinIO は RELEASE-* で pin (date-suffix)."""
    minio = langfuse_compose["services"]["langfuse-minio"]["image"]
    assert "minio/minio:RELEASE" in minio


def test_ac4_no_real_secret_in_compose():
    src = LANGFUSE_COMPOSE.read_text(encoding="utf-8")
    # Anthropic / Supabase service key パターン
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)
    assert "SUPABASE_SERVICE_ROLE_KEY" not in src
    # ENCRYPTION_KEY default は all-zero placeholder (real は env override)
    # NEXTAUTH_SECRET default = "change-me-please"
    assert "change-me" in src.lower() or "${NEXTAUTH_SECRET:" in src


def test_ac4_main_compose_unchanged_no_t_017_01_dep():
    """T-S0-01 main compose に T-017-01 依存追加なし."""
    src = MAIN_COMPOSE.read_text(encoding="utf-8")
    assert "T-017-01" not in src
    assert "langfuse-" not in src


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_017_01_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-017-01"), None)
    assert t is not None
    generic = [
        "as specified by feature F-017",
        "When the implementation step for T-017-01 is triggered",
        "While the new feature for T-017-01 is enabled",
        "If invalid input or unauthorized actor is detected during T-017-01",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], (
                f"T-017-01 still generic: {phrase!r}"
            )
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "docker-compose.langfuse.yml",
        "langfuse-web", "langfuse-worker",
        "langfuse-clickhouse", "langfuse-minio",
        "DATABASE_URL", "CLICKHOUSE_URL",
        "3001:3000",
        "NEXTAUTH_SECRET", "ENCRYPTION_KEY",
        "TELEMETRY_ENABLED",
    ):
        assert sym in full, f"T-017-01 AC missing concrete symbol: {sym}"


def test_tickets_t_017_01_has_adr_link_and_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-017-01"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert "docker-compose.yml" in files
    assert any("observability" in f for f in files)


def test_tickets_t_017_01_canonical_ears_types():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-017-01"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == ["UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "UNWANTED"]
