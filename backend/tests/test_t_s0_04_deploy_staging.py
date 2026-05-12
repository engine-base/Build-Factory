"""T-S0-04: deploy-staging.yml (Vercel + Oracle Cloud / Phase 1) — 4 AC.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : 2 jobs (deploy-frontend / deploy-backend) +
                       workflow_dispatch + tag trigger 'staging-v*'.
  AC-2 EVENT-DRIVEN  : 30 分 timeout / summary 出力 / smoke GET /api/health.
  AC-3 STATE-DRIVEN  : secrets は ${{ secrets.* }} のみ / environment=staging /
                       ci.yml / license-check.yml 無改変.
  AC-4 UNWANTED      : hardcoded secret / main 自動 trigger / smoke skip 禁止.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy-staging.yml"
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
LICENSE_YML = REPO_ROOT / ".github" / "workflows" / "license-check.yml"


@pytest.fixture(scope="module")
def src() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS
# ══════════════════════════════════════════════════════════════════════


def test_ac1_workflow_exists():
    assert WORKFLOW.exists(), f"missing {WORKFLOW}"


def test_ac1_workflow_name(src):
    assert re.search(r"^name:\s*deploy-staging\s*$", src, re.MULTILINE)


def test_ac1_workflow_dispatch_trigger(src):
    """手動 trigger workflow_dispatch が定義されている."""
    assert "workflow_dispatch:" in src


def test_ac1_tag_trigger_staging_v(src):
    """staging-v* tag で auto trigger."""
    assert "tags:" in src
    assert "staging-v*" in src


def test_ac1_two_deploy_jobs(src):
    """deploy-frontend + deploy-backend jobs が定義されている."""
    assert re.search(r"^\s*deploy-frontend:\s*$", src, re.MULTILINE)
    assert re.search(r"^\s*deploy-backend:\s*$", src, re.MULTILINE)


def test_ac1_frontend_uses_vercel_cli(src):
    """frontend job が vercel CLI を使う."""
    assert "vercel@latest" in src or "vercel deploy" in src
    assert "vercel deploy" in src


def test_ac1_backend_uses_ssh_and_docker_compose(src):
    """backend job が ssh + docker compose を使う."""
    assert "ssh -i" in src
    assert "docker compose pull" in src
    assert "docker compose up" in src


def test_ac1_smoke_test_calls_health(src):
    """post-deploy smoke が /api/health を叩く."""
    assert "/api/health" in src


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN
# ══════════════════════════════════════════════════════════════════════


def test_ac2_timeout_within_30_minutes(src):
    """全 job が 30 分以内の timeout-minutes を持つ."""
    timeouts = re.findall(r"timeout-minutes:\s*(\d+)", src)
    assert timeouts, "no timeout-minutes declared"
    for t in timeouts:
        assert int(t) <= 30, f"job timeout {t} exceeds 30 min"


def test_ac2_summary_includes_sha_and_env(src):
    """GITHUB_STEP_SUMMARY に env + sha を出力."""
    assert "GITHUB_STEP_SUMMARY" in src
    assert "$GITHUB_SHA" in src
    assert "env: staging" in src or "env: $TARGET_ENVIRONMENT" in src


def test_ac2_smoke_retries_within_60_seconds(src):
    """smoke は 60 秒以内に判定 (12 retry × 5s = 60s)."""
    # `for i in 1 2 3 ... 12;` または `seq 1 12` のいずれか
    has_loop_12 = bool(
        re.search(r"for i in 1 2 3 4 5 6 7 8 9 10 11 12", src)
        or re.search(r"seq 1 12", src)
        or re.search(r"\{1\.\.12\}", src)
    )
    assert has_loop_12, "smoke must retry up to 12 times (60s/5s interval)"


def test_ac2_smoke_failure_exits_nonzero(src):
    """smoke timeout で exit 1."""
    assert "exit 1" in src


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN
# ══════════════════════════════════════════════════════════════════════


def test_ac3_environment_is_staging(src):
    """両 job の environment が 'staging'."""
    envs = re.findall(r"environment:\s*(\S+)", src)
    # フィルタ: input description 等の "environment:" は除外, job-level のみ
    job_envs = [e for e in envs if e in ("staging", "production")]
    assert job_envs, "no job-level environment declared"
    for e in job_envs:
        assert e == "staging", f"environment must be 'staging', got {e!r}"


def test_ac3_secrets_only_via_github_secrets(src):
    """secrets は ${{ secrets.X }} 経由のみ (hardcoded 禁止)."""
    # secrets reference があるべき
    assert "${{ secrets." in src
    # hardcoded secret pattern (AC-4 とも兼ねる) は無いこと
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)
    assert not re.search(r"AIza[0-9A-Za-z_-]{20,}", src)
    assert not re.search(r"eyJ[A-Za-z0-9_-]{30,}", src)


def test_ac3_does_not_trigger_on_main_push(src):
    """main / master への push では auto-deploy しない."""
    # push trigger は tags しかない
    push_block = re.search(r"push:\s*\n((?:\s+-?\s*\w+:.*\n)+)", src)
    if push_block:
        block = push_block.group(1)
        # branches が定義されていれば NG (tag-only deploy が安全)
        assert "branches:" not in block, "push trigger must be tag-only, not branch"


def test_ac3_ci_yml_unchanged_by_this_branch():
    """既存 ci.yml に deploy-staging への依存追加無し."""
    src = CI_YML.read_text(encoding="utf-8")
    assert "deploy-staging" not in src


def test_ac3_license_yml_unchanged_by_this_branch():
    src = LICENSE_YML.read_text(encoding="utf-8")
    assert "deploy-staging" not in src


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED
# ══════════════════════════════════════════════════════════════════════


def test_ac4_no_hardcoded_secret_patterns(src):
    forbidden = [
        (r"sk-ant-[A-Za-z0-9_-]{20,}", "Anthropic API key"),
        (r"sk-proj-[A-Za-z0-9_-]{20,}", "OpenAI project key"),
        (r"AIza[0-9A-Za-z_-]{20,}", "Google API key"),
        (r"eyJ[A-Za-z0-9_-]{30,}\.[A-Za-z0-9_-]{30,}\.[A-Za-z0-9_-]+", "JWT"),
    ]
    for pat, name in forbidden:
        assert not re.search(pat, src), f"hardcoded {name} detected"


def test_ac4_smoke_step_is_not_skipped(src):
    """smoke test step が `if: false` 等で skip されていない."""
    assert "smoke" in src.lower()
    # `if: false` か `continue-on-error: true` で smoke が無効化されていないこと
    smoke_section = src[src.lower().find("smoke test"):]
    assert "if: false" not in smoke_section[:500]
    assert "continue-on-error: true" not in smoke_section[:500]


def test_ac4_concurrency_prevents_overlap(src):
    """同時実行制限あり (deploy が overlap しない)."""
    assert "concurrency:" in src
    assert "deploy-staging" in src


def test_ac4_permissions_minimum(src):
    """permissions は最小限 (contents: read のみが基本)."""
    assert re.search(r"permissions:\s*\n\s+contents:\s*read", src)
    # 余計な write 権限が無いこと
    assert not re.search(r"id-token:\s*write", src)
    # NOTE: deployments: write 等を将来追加する場合は明示する


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_s0_04_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-04"), None)
    assert t is not None
    generic = [
        "as specified by feature META",
        "When the implementation step for T-S0-04 is triggered",
        "While the new feature for T-S0-04 is enabled",
        "If invalid input or unauthorized actor is detected during T-S0-04",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], (
                f"T-S0-04 still generic: {phrase!r}"
            )
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "deploy-staging.yml" in full
    assert "Vercel" in full
    assert "Oracle Cloud" in full or "ssh" in full
    assert "/api/health" in full


def test_tickets_t_s0_04_has_adr_link():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-04"), None)
    assert t.get("adr_link") is not None
    assert "TBD" not in str(t.get("existing_files", []))
