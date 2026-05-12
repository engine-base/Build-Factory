"""T-020-01: LiteLLM docker-compose 追加 (ADR-010 Layer 2b).

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : docker-compose.yml に litellm service / Layer 2b routes /
                       profiles: [litellm] で opt-in / main path から外す.
  AC-2 EVENT-DRIVEN  : healthcheck /health/liveliness / num_retries: 2 /
                       request_timeout: 60.
  AC-3 STATE-DRIVEN  : config read-only mount / env vars only / json_logs:true /
                       redact_user_api_key_info: true.
  AC-4 UNWANTED      : LITELLM_MASTER_KEY 必須 / hardcoded API key なし /
                       default profile に含まない.
"""
from __future__ import annotations

import json as _json
import re
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "docker-compose.yml"
LITELLM_CONFIG = REPO_ROOT / "monitoring" / "litellm-config.yaml"


@pytest.fixture(scope="module")
def compose_yaml():
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def litellm_yaml():
    return yaml.safe_load(LITELLM_CONFIG.read_text(encoding="utf-8"))


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS
# ══════════════════════════════════════════════════════════════════════


def test_ac1_compose_has_litellm_service(compose_yaml):
    assert "services" in compose_yaml
    assert "litellm" in compose_yaml["services"]


def test_ac1_litellm_uses_official_image(compose_yaml):
    svc = compose_yaml["services"]["litellm"]
    assert "image" in svc
    assert "berriai/litellm" in svc["image"]


def test_ac1_litellm_exposes_port_4000(compose_yaml):
    svc = compose_yaml["services"]["litellm"]
    ports = svc.get("ports", [])
    assert any("4000" in str(p) for p in ports)


def test_ac1_litellm_opt_in_via_profile(compose_yaml):
    """default で起動しない (profiles: [litellm] が必要)."""
    svc = compose_yaml["services"]["litellm"]
    profiles = svc.get("profiles", [])
    assert "litellm" in profiles


def test_ac1_litellm_config_exists():
    assert LITELLM_CONFIG.exists()


def test_ac1_model_list_has_required_routes(litellm_yaml):
    """ADR-010 Layer 2b の 4 用途 routes が定義済."""
    model_names = [m["model_name"] for m in litellm_yaml["model_list"]]
    # 安価バッチ
    assert "cheap-batch" in model_names or "gemini-flash" in model_names
    # 画像
    assert "image-gen" in model_names or "dalle-3" in model_names
    # 音声
    assert "whisper" in model_names
    # フォールバック
    assert "anthropic-fallback" in model_names


def test_ac1_main_path_not_through_litellm():
    """backend/main.py / claude-agent-sdk path に LiteLLM URL hardcode なし."""
    main_src = (REPO_ROOT / "backend" / "main.py").read_text(encoding="utf-8")
    # backend が LiteLLM proxy URL を hardcode していないこと
    assert "http://litellm:4000" not in main_src
    assert "http://localhost:4000" not in main_src


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: healthcheck + retry/timeout
# ══════════════════════════════════════════════════════════════════════


def test_ac2_healthcheck_uses_liveliness(compose_yaml):
    svc = compose_yaml["services"]["litellm"]
    hc = svc.get("healthcheck", {})
    test_cmd = " ".join(hc.get("test", []))
    assert "health/liveliness" in test_cmd or "/health" in test_cmd


def test_ac2_master_key_env_required(compose_yaml):
    svc = compose_yaml["services"]["litellm"]
    env = svc.get("environment", {})
    assert "LITELLM_MASTER_KEY" in env


def test_ac2_router_settings_retry_and_timeout(litellm_yaml):
    rs = litellm_yaml.get("router_settings", {})
    assert rs.get("num_retries") == 2
    assert rs.get("request_timeout") == 60


def test_ac2_fallbacks_configured(litellm_yaml):
    rs = litellm_yaml.get("router_settings", {})
    fb = rs.get("fallbacks", [])
    assert fb, "router_settings.fallbacks must be defined for Anthropic outage"


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: read-only mount + env only + json_logs + redact
# ══════════════════════════════════════════════════════════════════════


def test_ac3_config_mounted_read_only(compose_yaml):
    svc = compose_yaml["services"]["litellm"]
    vols = svc.get("volumes", [])
    config_vol = next((v for v in vols if "litellm-config" in v), None)
    assert config_vol is not None
    assert ":ro" in config_vol, "config must be read-only mounted"


def test_ac3_api_keys_via_env_only(litellm_yaml):
    """litellm-config.yaml で api_key は os.environ/* 参照のみ (literal なし)."""
    for m in litellm_yaml["model_list"]:
        api_key = m["litellm_params"].get("api_key", "")
        # os.environ/XXX 形式のみ許可
        assert api_key.startswith("os.environ/"), (
            f"model {m['model_name']}: api_key must use os.environ/, got {api_key!r}"
        )


def test_ac3_json_logs_enabled(litellm_yaml):
    """T-S0-11 structlog 整合の json_logs:true."""
    gs = litellm_yaml.get("general_settings", {})
    assert gs.get("json_logs") is True


def test_ac3_redact_user_api_key_info(litellm_yaml):
    """PII 排除: redact_user_api_key_info:true."""
    ls = litellm_yaml.get("litellm_settings", {})
    assert ls.get("redact_user_api_key_info") is True


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: 認証必須 + hardcoded secret なし
# ══════════════════════════════════════════════════════════════════════


def test_ac4_no_hardcoded_api_keys_in_compose():
    src = COMPOSE.read_text(encoding="utf-8")
    # sk-ant-xxx / sk-proj-xxx (OpenAI) / AIza-xxx (Google) literal なし
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{30,}", src)
    assert not re.search(r"sk-proj-[A-Za-z0-9_-]{30,}", src)
    assert not re.search(r"AIza[A-Za-z0-9_-]{30,}", src)
    # JWT
    assert not re.search(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}", src)


def test_ac4_no_hardcoded_api_keys_in_litellm_config():
    src = LITELLM_CONFIG.read_text(encoding="utf-8")
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{30,}", src)
    assert not re.search(r"sk-proj-[A-Za-z0-9_-]{30,}", src)
    assert not re.search(r"AIza[A-Za-z0-9_-]{30,}", src)


def test_ac4_master_key_uses_env_substitution(compose_yaml):
    """master key は env var 経由のみ. literal は default 値 (dev only) のみ許容."""
    svc = compose_yaml["services"]["litellm"]
    master_key = svc["environment"]["LITELLM_MASTER_KEY"]
    # ${LITELLM_MASTER_KEY:-sk-bf-local-dev-only} のような env 形式
    assert master_key.startswith("${LITELLM_MASTER_KEY"), (
        f"LITELLM_MASTER_KEY must be ${{LITELLM_MASTER_KEY...}}, got {master_key}"
    )


def test_ac4_not_in_default_profile(compose_yaml):
    """litellm が default 起動に含まれない (profiles なしの service 列に含まれない)."""
    svc = compose_yaml["services"]["litellm"]
    profiles = svc.get("profiles", [])
    assert profiles, "litellm must have profiles (opt-in)"
    # postgres / redis / backend / frontend は profiles なし (default 起動)
    for s in ("postgres", "redis", "backend", "frontend"):
        if s in compose_yaml["services"]:
            assert not compose_yaml["services"][s].get("profiles"), (
                f"core service {s} must NOT have profiles"
            )


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_020_01_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-020-01"), None)
    assert t is not None
    generic = [
        "as specified by feature",
        "implementation step for T-020-01 is triggered",
        "shall record an audit entry capturing the action and timestamp",
        "shall apply Row Level Security and audit_logs as per CLAUDE.md",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], f"T-020-01 still generic: {phrase!r}"
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "litellm" in full.lower()
    assert "Layer 2b" in full
    assert "LITELLM_MASTER_KEY" in full


def test_tickets_t_020_01_has_adr_link_and_existing_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-020-01"), None)
    assert t.get("adr_link") is not None
    assert t.get("existing_files")


# ══════════════════════════════════════════════════════════════════════
# Existing services 不変保証 (REUSE)
# ══════════════════════════════════════════════════════════════════════


def test_existing_core_services_unchanged(compose_yaml):
    """既存 4 service (postgres/redis/backend/frontend) は今も存在."""
    services = compose_yaml["services"]
    for s in ("postgres", "redis", "backend", "frontend"):
        assert s in services, f"existing service {s} missing"


def test_litellm_does_not_block_default_compose():
    """profiles: [litellm] なので default compose up に影響しない."""
    cy = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    # default profile で起動される service 数
    default_services = [
        name for name, svc in cy["services"].items()
        if not svc.get("profiles")
    ]
    assert "litellm" not in default_services
    assert set(default_services) >= {"postgres", "redis", "backend", "frontend"}
