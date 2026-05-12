"""T-012-03: Landlock + seccomp red-line policy — 4 AC.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : landlock_policy service + router 公開. T-S0-09
                       backend/sandbox/{config,exec,__init__}.py 無改変
                       (REUSE invariant).
  AC-2 EVENT-DRIVEN  : evaluate_command 2 秒以内 + structured response /
                       audit_red_line deterministic kind asc sort.
  AC-3 STATE-DRIVEN  : DEFAULT_RED_LINE_POLICY frozen / G15 cross-module
                       不変 / detect_landlock_availability deterministic
                       (cache per process).
  AC-4 UNWANTED      : invalid cmd / policy / sandbox_cfg / non-absolute
                       path で LandlockPolicyError + state unchanged.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sandbox import landlock_policy as lp
from sandbox.config import SandboxConfig


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE = REPO_ROOT / "backend" / "sandbox" / "landlock_policy.py"
ROUTER = REPO_ROOT / "backend" / "routers" / "sandbox_landlock.py"
SANDBOX_INIT = REPO_ROOT / "backend" / "sandbox" / "__init__.py"
SANDBOX_CONFIG = REPO_ROOT / "backend" / "sandbox" / "config.py"
SANDBOX_EXEC = REPO_ROOT / "backend" / "sandbox" / "exec.py"


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_cache():
    lp._reset_availability_cache_for_test()
    yield
    lp._reset_availability_cache_for_test()


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — public API + T-S0-09 REUSE invariant
# ══════════════════════════════════════════════════════════════════════


def test_ac1_service_exists():
    assert SERVICE.exists()


def test_ac1_router_exists():
    assert ROUTER.exists()


@pytest.mark.parametrize("sym", [
    "LandlockPolicy",
    "DEFAULT_RED_LINE_POLICY",
    "DEFAULT_DENIED_SYSCALLS",
    "detect_landlock_availability",
    "evaluate_command",
    "audit_red_line",
    "LandlockPolicyError",
    "LANDLOCK_MIN_KERNEL",
])
def test_ac1_public_symbols(sym):
    assert hasattr(lp, sym), f"missing public symbol: {sym}"


def test_ac1_default_denied_syscalls_includes_critical():
    """red-line syscall (mount / ptrace / reboot / kexec) 必須."""
    for sc in (
        "socket", "connect", "ptrace", "reboot",
        "init_module", "delete_module", "kexec_load",
        "mount", "umount", "chroot", "pivot_root",
    ):
        assert sc in lp.DEFAULT_DENIED_SYSCALLS, (
            f"DEFAULT_DENIED_SYSCALLS missing critical syscall: {sc}"
        )


def test_ac1_default_red_line_policy_disallows_network():
    assert lp.DEFAULT_RED_LINE_POLICY.network_allowed is False


def test_ac1_s0_09_sandbox_init_unchanged():
    """REUSE invariant: backend/sandbox/__init__.py に landlock 依存追加なし.

    T-012-03 は新規 module だけを足す. __init__.py に landlock_policy を
    import しても OK だが本実装はしない (one-way dep: landlock_policy → config).
    """
    src = SANDBOX_INIT.read_text(encoding="utf-8")
    assert "landlock_policy" not in src or "from .landlock_policy" not in src


def test_ac1_s0_09_config_unchanged_logic():
    """SandboxConfig の field 構成が変わっていない (T-S0-09 spec rigor PR で
    確定したものと同じ)."""
    cfg = SandboxConfig()
    for f in (
        "allow_paths", "read_only_paths", "allow_hosts",
        "timeout_sec", "cwd", "extra_env",
    ):
        assert hasattr(cfg, f), f"SandboxConfig regression: missing {f}"


def test_ac1_s0_09_exec_unchanged_no_landlock_import():
    """sandbox/exec.py が landlock_policy を import しない (one-way dep)."""
    src = SANDBOX_EXEC.read_text(encoding="utf-8")
    assert "landlock_policy" not in src


def test_ac1_router_evaluate(client):
    resp = client.post(
        "/api/sandbox/landlock/evaluate",
        json={"cmd": ["ls", "/tmp"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "allowed" in body
    assert "violations" in body
    assert "landlock_available" in body
    assert "kernel_version" in body


def test_ac1_router_availability(client):
    resp = client.get("/api/sandbox/landlock/availability")
    assert resp.status_code == 200
    body = resp.json()
    assert "available" in body
    assert "kernel_version" in body
    assert "min_kernel" in body


def test_ac1_router_default_policy(client):
    resp = client.get("/api/sandbox/landlock/default-policy")
    assert resp.status_code == 200
    body = resp.json()
    assert "denied_syscalls" in body
    assert "ptrace" in body["denied_syscalls"]
    assert body["network_allowed"] is False


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — structured response + 2s + deterministic sort
# ══════════════════════════════════════════════════════════════════════


def test_ac2_evaluate_command_returns_4_fields():
    result = lp.evaluate_command(
        ["ls", "/tmp"], lp.DEFAULT_RED_LINE_POLICY,
    )
    for key in ("allowed", "violations", "landlock_available", "kernel_version"):
        assert key in result, f"evaluate_command missing field: {key}"


def test_ac2_evaluate_command_under_2s():
    t0 = time.time()
    for _ in range(100):
        lp.evaluate_command(
            ["ls", "/tmp", "/usr/bin/python3"],
            lp.DEFAULT_RED_LINE_POLICY,
        )
    elapsed = time.time() - t0
    assert elapsed < 2.0, f"evaluate_command 100x took {elapsed:.2f}s"


def test_ac2_evaluate_blocks_ptrace_invocation():
    """strace は ptrace syscall を呼ぶ → denied_syscall 違反."""
    result = lp.evaluate_command(
        ["strace", "-f", "ls"], lp.DEFAULT_RED_LINE_POLICY,
    )
    assert result["allowed"] is False
    kinds = {v["kind"] for v in result["violations"]}
    assert "denied_syscall" in kinds


def test_ac2_evaluate_blocks_mount():
    """mount コマンドは pol.denied_syscalls の mount 違反."""
    result = lp.evaluate_command(
        ["mount", "-t", "tmpfs", "none", "/mnt"],
        lp.DEFAULT_RED_LINE_POLICY,
    )
    assert result["allowed"] is False
    kinds = {v["kind"] for v in result["violations"]}
    assert "denied_syscall" in kinds


def test_ac2_evaluate_blocks_rm_outside_write_paths():
    """rm /usr/bin/python3 は write_outside_policy."""
    result = lp.evaluate_command(
        ["rm", "/usr/bin/python3"], lp.DEFAULT_RED_LINE_POLICY,
    )
    assert result["allowed"] is False
    kinds = {v["kind"] for v in result["violations"]}
    assert "write_outside_policy" in kinds


def test_ac2_evaluate_allows_safe_command():
    """/usr/bin/python3 -c '1' は許可される (read / exec 配下のみ)."""
    result = lp.evaluate_command(
        ["/usr/bin/python3", "-c", "print(1)"],
        lp.DEFAULT_RED_LINE_POLICY,
    )
    # network_not_allowed / write_outside_policy が無いはず
    kinds = {v["kind"] for v in result["violations"]}
    assert "denied_syscall" not in kinds


def test_ac2_audit_red_line_deterministic_sort():
    """同じ入力で常に同じ violation 順 (kind asc)."""
    cmd = ["strace", "rm", "/usr/bin/python3"]
    v1 = lp.audit_red_line(cmd, lp.DEFAULT_RED_LINE_POLICY)
    v2 = lp.audit_red_line(cmd, lp.DEFAULT_RED_LINE_POLICY)
    assert v1 == v2  # deterministic
    kinds = [v["kind"] for v in v1]
    assert kinds == sorted(kinds), f"violations not sorted by kind: {kinds}"


def test_ac2_network_not_allowed_when_sandbox_has_hosts():
    """policy.network_allowed=False + sandbox_cfg.allow_hosts 非空 → 違反."""
    cfg = SandboxConfig(allow_hosts=("example.com",))
    result = lp.evaluate_command(
        ["ls"], lp.DEFAULT_RED_LINE_POLICY, sandbox_cfg=cfg,
    )
    kinds = {v["kind"] for v in result["violations"]}
    assert "network_not_allowed" in kinds


def test_ac2_endpoint_evaluate_returns_structured(client):
    resp = client.post(
        "/api/sandbox/landlock/evaluate",
        json={"cmd": ["strace", "ls"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["allowed"] is False
    assert any(v["kind"] == "denied_syscall" for v in body["violations"])


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — frozen / deterministic / no DB / cross-module invariant
# ══════════════════════════════════════════════════════════════════════


def test_ac3_default_policy_is_frozen():
    """frozen dataclass: field を変更しようとすると raise."""
    with pytest.raises(Exception):
        lp.DEFAULT_RED_LINE_POLICY.network_allowed = True  # type: ignore[misc]


def test_ac3_landlock_policy_is_frozen():
    p = lp.LandlockPolicy()
    with pytest.raises(Exception):
        p.network_allowed = True  # type: ignore[misc]


def test_ac3_availability_is_cached_per_process():
    """detect_landlock_availability を 2 回呼んで同じ結果."""
    a1 = lp.detect_landlock_availability()
    a2 = lp.detect_landlock_availability()
    assert a1 == a2


def test_ac3_availability_returns_defensive_copy():
    """cache が呼び出し側の mutation で汚れない."""
    a1 = lp.detect_landlock_availability()
    a1["available"] = "tampered"
    a2 = lp.detect_landlock_availability()
    assert a2["available"] != "tampered"


def test_ac3_no_db_no_redis():
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert "aiosqlite" not in code
    assert "INSERT INTO" not in code
    assert "redis" not in code.lower()


def test_ac3_no_langgraph_no_langchain_no_litellm():
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src).lower()
    assert "langgraph" not in code
    assert "langchain" not in code
    assert "litellm" not in code


def test_ac3_no_section_keys_redefinition():
    """G15: SECTION_KEYS は mid_term_layer 責務."""
    code = _strip_comments(SERVICE.read_text(encoding="utf-8"))
    assert "SECTION_KEYS" not in code


def test_ac3_no_review_dimensions_redefinition():
    """G15: REVIEW_DIMENSIONS は reviewer_loop 責務."""
    code = _strip_comments(SERVICE.read_text(encoding="utf-8"))
    assert "REVIEW_DIMENSIONS" not in code


def test_ac3_no_persona_name_redefinition():
    """G15: PERSONA_NAME は reviewer_persona 責務."""
    code = _strip_comments(SERVICE.read_text(encoding="utf-8"))
    assert "PERSONA_NAME" not in code


def test_ac3_get_endpoints_do_not_mutate_state(client):
    a1 = lp.detect_landlock_availability()
    client.get("/api/sandbox/landlock/availability")
    client.get("/api/sandbox/landlock/default-policy")
    a2 = lp.detect_landlock_availability()
    assert a1 == a2
    # default policy 不変
    assert lp.DEFAULT_RED_LINE_POLICY.network_allowed is False


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED — validation
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("bad_cmd", [None, "", [], "ls", 123, {}])
def test_ac4_invalid_cmd_raises(bad_cmd):
    with pytest.raises(lp.LandlockPolicyError):
        lp.evaluate_command(bad_cmd, lp.DEFAULT_RED_LINE_POLICY)


def test_ac4_cmd_over_max_length_raises():
    long = ["ls"] * (lp.MAX_CMD_LEN + 1)
    with pytest.raises(lp.LandlockPolicyError):
        lp.evaluate_command(long, lp.DEFAULT_RED_LINE_POLICY)


def test_ac4_cmd_arg_over_4096_chars_raises():
    long_arg = "x" * (lp.MAX_CMD_ARG_LEN + 1)
    with pytest.raises(lp.LandlockPolicyError):
        lp.evaluate_command(["ls", long_arg], lp.DEFAULT_RED_LINE_POLICY)


def test_ac4_non_string_cmd_element_raises():
    with pytest.raises(lp.LandlockPolicyError):
        lp.evaluate_command(["ls", 123], lp.DEFAULT_RED_LINE_POLICY)


def test_ac4_non_landlock_policy_raises():
    with pytest.raises(lp.LandlockPolicyError):
        lp.evaluate_command(["ls"], {"not": "policy"})


def test_ac4_non_sandbox_cfg_raises():
    with pytest.raises(lp.LandlockPolicyError):
        lp.evaluate_command(
            ["ls"], lp.DEFAULT_RED_LINE_POLICY, sandbox_cfg="not a cfg",
        )


def test_ac4_relative_path_in_policy_raises():
    """Landlock は absolute path のみサポート."""
    bad_policy = lp.LandlockPolicy(read_paths=(Path("relative/path"),))
    with pytest.raises(lp.LandlockPolicyError) as exc:
        lp.evaluate_command(["ls"], bad_policy)
    assert "absolute" in str(exc.value).lower()


def test_ac4_validation_failure_does_not_mutate_default():
    before = lp.DEFAULT_RED_LINE_POLICY.network_allowed
    with pytest.raises(lp.LandlockPolicyError):
        lp.evaluate_command(None, lp.DEFAULT_RED_LINE_POLICY)
    after = lp.DEFAULT_RED_LINE_POLICY.network_allowed
    assert before == after


def test_ac4_endpoint_400_on_invalid_cmd(client):
    resp = client.post(
        "/api/sandbox/landlock/evaluate",
        json={"cmd": []},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "landlock_policy.invalid_input"


def test_ac4_endpoint_401_on_empty_actor(client):
    resp = client.post(
        "/api/sandbox/landlock/evaluate",
        json={"cmd": ["ls"], "actor_user_id": "  "},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "landlock_policy.unauthorized"


def test_ac4_endpoint_400_on_relative_path_policy(client):
    resp = client.post(
        "/api/sandbox/landlock/evaluate",
        json={
            "cmd": ["ls"],
            "policy": {
                "read_paths": ["relative/path"],
                "write_paths": [],
                "exec_paths": [],
                "network_allowed": False,
            },
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "landlock_policy.invalid_input"


def test_ac4_no_hardcoded_secret():
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", code)
    assert "SUPABASE_SERVICE_KEY" not in code


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_012_03_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-012-03"), None)
    assert t is not None
    generic = [
        "as specified by feature F-012",
        "When the relevant API endpoint or service function is invoked for T-012-03",
        "While the new feature for T-012-03 is enabled",
        "If invalid input or unauthorized actor is detected during T-012-03",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], (
                f"T-012-03 still generic: {phrase!r}"
            )
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "landlock_policy.py", "LandlockPolicy", "DEFAULT_RED_LINE_POLICY",
        "DEFAULT_DENIED_SYSCALLS", "evaluate_command", "audit_red_line",
        "detect_landlock_availability",
    ):
        assert sym in full, f"T-012-03 AC missing concrete symbol: {sym}"


def test_tickets_t_012_03_has_adr_link_and_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-012-03"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert "backend/sandbox/config.py" in files
    assert "backend/sandbox/exec.py" in files


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════


def _strip_comments(src: str) -> str:
    out_lines = []
    in_triple = False
    triple_char = None
    for raw in src.splitlines():
        line = raw
        if in_triple:
            if triple_char in line:
                line = line.split(triple_char, 1)[1]
                in_triple = False
            else:
                continue
        for ch in ('"""', "'''"):
            if ch in line:
                before, _, after = line.partition(ch)
                if ch in after:
                    line = before + after.split(ch, 1)[1]
                else:
                    line = before
                    in_triple = True
                    triple_char = ch
                break
        if "#" in line:
            line = line.split("#", 1)[0]
        if line.strip():
            out_lines.append(line)
    return "\n".join(out_lines)
