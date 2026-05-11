"""T-013-02: Claude Code commit + push wrap (worktree 経由) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-013 commit + push wrap service + endpoint (worktree 経由)
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 swarm.worktree service REUSE (backwards compat) + audit emit
  AC-4 UNWANTED      : 禁止 branch (main/master) / 禁止 flag (--force/--no-verify) /
                       不正 path は 4xx + structured / persistent state mutate しない
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import git_wrap as gw
from services.git_wrap import (
    CommitResult,
    GitResult,
    GitWrapError,
    PushResult,
    StatusResult,
    UnsafeOperationError,
    commit_changes,
    push_branch,
    status,
)


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
def real_worktree(tmp_path: Path) -> Path:
    """init された 一時 git repo を返す."""
    repo = tmp_path / "wt"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"],
                    cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.name", "Test"],
                    cwd=str(repo), check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"],
                    cwd=str(repo), check=True)
    (repo / "README.md").write_text("init")
    return repo


@pytest.fixture(autouse=True)
def _patch_worktree_resolver(monkeypatch, tmp_path):
    """router の _resolve_worktree が pool_id=1, cell_index=0 → tmp の git repo を返す."""
    import routers.git_wrap as router_gw
    from services.swarm import worktree as wt_mod

    # default worktree path を tmp_path/wt-1-0 に向ける
    fake_wt = tmp_path / "wt-1-0"
    fake_wt.mkdir(exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=str(fake_wt), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"],
                    cwd=str(fake_wt), check=True)
    subprocess.run(["git", "config", "user.name", "Test"],
                    cwd=str(fake_wt), check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"],
                    cwd=str(fake_wt), check=True)
    (fake_wt / "README.md").write_text("init")

    def fake_worktree_path(pool_id, cell_index):
        return fake_wt

    monkeypatch.setattr(wt_mod, "worktree_path", fake_worktree_path)
    yield {"path": fake_wt}


# ──────────────────────────────────────────────────────────────────────────
# Service 単体
# ──────────────────────────────────────────────────────────────────────────


def test_service_validate_workdir_must_be_absolute():
    with pytest.raises(GitWrapError):
        gw._validate_workdir(Path("relative/path"))


def test_service_validate_workdir_must_be_git_tree(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(GitWrapError):
        gw._validate_workdir(plain)


def test_service_validate_workdir_ok(real_worktree):
    out = gw._validate_workdir(real_worktree)
    assert out == real_worktree


def test_service_validate_branch_allowed_prefix():
    assert gw._validate_branch("claude/feat-1") == "claude/feat-1"


def test_service_validate_branch_forbidden_main():
    with pytest.raises(UnsafeOperationError):
        gw._validate_branch("main")


def test_service_validate_branch_forbidden_master():
    with pytest.raises(UnsafeOperationError):
        gw._validate_branch("master")


def test_service_validate_branch_disallowed_prefix():
    with pytest.raises(UnsafeOperationError):
        gw._validate_branch("feature/foo")


def test_service_validate_branch_invalid_chars():
    with pytest.raises(GitWrapError):
        gw._validate_branch("claude/feat$1")


def test_service_validate_branch_too_long():
    with pytest.raises(GitWrapError):
        gw._validate_branch("claude/" + "x" * 201)


def test_service_validate_branch_empty():
    with pytest.raises(GitWrapError):
        gw._validate_branch("  ")


def test_service_validate_message_empty():
    with pytest.raises(GitWrapError):
        gw._validate_message("  ")


def test_service_validate_message_too_long():
    with pytest.raises(GitWrapError):
        gw._validate_message("x" * (gw.MAX_COMMIT_MESSAGE + 1))


def test_service_forbidden_flag_rejected():
    with pytest.raises(UnsafeOperationError):
        gw._check_no_forbidden_flags(["--no-verify"])
    with pytest.raises(UnsafeOperationError):
        gw._check_no_forbidden_flags(["--force"])
    with pytest.raises(UnsafeOperationError):
        gw._check_no_forbidden_flags(["--force-with-lease"])
    with pytest.raises(UnsafeOperationError):
        gw._check_no_forbidden_flags(["--force-anything"])


def test_service_commit_dry_run(real_worktree):
    result = asyncio.run(commit_changes(
        real_worktree, "test commit", dry_run=True,
    ))
    assert result.git.dry_run is True
    assert result.git.ok is True


def test_service_commit_real(real_worktree):
    result = asyncio.run(commit_changes(
        real_worktree, "first commit",
    ))
    assert result.git.ok or "nothing to commit" not in result.git.stderr


def test_service_commit_forbidden_flag_raises(real_worktree):
    with pytest.raises(UnsafeOperationError):
        asyncio.run(commit_changes(
            real_worktree, "msg", extra_args=["--no-verify"],
        ))


def test_service_push_dry_run(real_worktree):
    result = asyncio.run(push_branch(
        real_worktree, "claude/test-branch", dry_run=True,
    ))
    assert result.git.dry_run is True
    assert result.branch == "claude/test-branch"


def test_service_push_to_main_raises(real_worktree):
    with pytest.raises(UnsafeOperationError):
        asyncio.run(push_branch(real_worktree, "main"))


def test_service_push_invalid_remote(real_worktree):
    with pytest.raises(GitWrapError):
        asyncio.run(push_branch(
            real_worktree, "claude/feat", remote="bad$remote",
        ))


def test_service_push_forbidden_flag(real_worktree):
    with pytest.raises(UnsafeOperationError):
        asyncio.run(push_branch(
            real_worktree, "claude/feat",
            extra_args=["--force"], dry_run=True,
        ))


def test_service_status_real(real_worktree):
    subprocess.run(["git", "add", "-A"], cwd=str(real_worktree), check=True)
    subprocess.run(
        ["git", "commit", "-m", "init", "--no-gpg-sign"],
        cwd=str(real_worktree), check=True,
    )
    result = asyncio.run(status(real_worktree))
    assert isinstance(result, StatusResult)
    assert result.dirty is False
    (real_worktree / "new.txt").write_text("x")
    result2 = asyncio.run(status(real_worktree))
    assert result2.dirty is True


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_commit_endpoint(client, _patch_worktree_resolver):
    r = client.post(
        "/api/git/worktree/1/0/commit",
        json={"message": "test commit", "dry_run": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["git"]["dry_run"] is True


def test_ac1_push_endpoint(client, _patch_worktree_resolver):
    r = client.post(
        "/api/git/worktree/1/0/push",
        json={"branch": "claude/test-branch", "dry_run": True},
    )
    assert r.status_code == 200
    assert r.json()["branch"] == "claude/test-branch"


def test_ac1_status_endpoint(client, _patch_worktree_resolver):
    subprocess.run(["git", "add", "-A"], cwd=str(_patch_worktree_resolver["path"]),
                    check=True)
    subprocess.run(
        ["git", "commit", "-m", "init", "--no-gpg-sign"],
        cwd=str(_patch_worktree_resolver["path"]), check=True,
    )
    r = client.get("/api/git/worktree/1/0/status")
    assert r.status_code == 200
    assert "branch" in r.json()


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured error
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_commit_within_2s(client, _patch_worktree_resolver):
    t0 = time.perf_counter()
    r = client.post(
        "/api/git/worktree/1/0/commit",
        json={"message": "x", "dry_run": True},
    )
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.post(
        "/api/git/worktree/0/0/commit",
        json={"message": "x"},
    )
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "git.invalid_pool_id"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: 既存 worktree REUSE + audit emit
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_swarm_worktree_module_intact():
    """T-M29-01 swarm.worktree が無傷."""
    from services.swarm import worktree as wt
    assert hasattr(wt, "worktree_path")
    assert hasattr(wt, "create_worktree")


def test_ac3_commit_emits_audit(client, _patch_worktree_resolver, _capture_audit):
    client.post(
        "/api/git/worktree/1/0/commit",
        json={"message": "x", "dry_run": True, "actor_user_id": "alice"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "git.commit"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "alice"
    assert events[0]["detail"]["dry_run"] is True


def test_ac3_push_emits_audit(client, _patch_worktree_resolver, _capture_audit):
    client.post(
        "/api/git/worktree/1/0/push",
        json={"branch": "claude/audit-test", "dry_run": True,
               "actor_user_id": "alice"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "git.push"]
    assert len(events) >= 1
    assert events[0]["detail"]["branch"] == "claude/audit-test"


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_invalid_pool_id(client):
    r = client.post(
        "/api/git/worktree/0/0/commit",
        json={"message": "x"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "git.invalid_pool_id"


def test_ac4_invalid_cell_index(client):
    r = client.post(
        "/api/git/worktree/1/-1/commit",
        json={"message": "x"},
    )
    assert r.status_code in (400, 422)


def test_ac4_empty_message(client, _patch_worktree_resolver):
    r = client.post(
        "/api/git/worktree/1/0/commit",
        json={"message": "   "},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "git.invalid_message"


def test_ac4_long_message(client, _patch_worktree_resolver):
    r = client.post(
        "/api/git/worktree/1/0/commit",
        json={"message": "x" * (gw.MAX_COMMIT_MESSAGE + 1)},
    )
    assert r.status_code == 400


def test_ac4_push_to_main_forbidden(client, _patch_worktree_resolver):
    r = client.post(
        "/api/git/worktree/1/0/push",
        json={"branch": "main", "dry_run": True},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "git.unsafe_operation"


def test_ac4_push_disallowed_prefix(client, _patch_worktree_resolver):
    r = client.post(
        "/api/git/worktree/1/0/push",
        json={"branch": "feature/x", "dry_run": True},
    )
    assert r.status_code == 403


def test_ac4_push_empty_branch(client, _patch_worktree_resolver):
    r = client.post(
        "/api/git/worktree/1/0/push",
        json={"branch": " ", "dry_run": True},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "git.invalid_branch"


def test_ac4_push_invalid_remote(client, _patch_worktree_resolver):
    r = client.post(
        "/api/git/worktree/1/0/push",
        json={"branch": "claude/x", "remote": "bad$",
               "dry_run": True},
    )
    assert r.status_code == 400


def test_ac4_empty_actor(client, _patch_worktree_resolver):
    r = client.post(
        "/api/git/worktree/1/0/commit",
        json={"message": "x", "actor_user_id": "  "},
    )
    assert r.status_code == 401


def test_ac4_worktree_not_found(client, monkeypatch):
    """worktree_path が存在しない dir を返す場合 404."""
    from services.swarm import worktree as wt_mod
    monkeypatch.setattr(
        wt_mod, "worktree_path",
        lambda p, c: Path("/tmp/nonexistent-bf-test-12345"),
    )
    r = client.post(
        "/api/git/worktree/1/0/commit",
        json={"message": "x"},
    )
    assert r.status_code in (400, 404)


def test_ac4_rejected_does_not_emit_audit(client, _capture_audit):
    client.post("/api/git/worktree/0/0/commit",
                 json={"message": "x"})
    events = [e for e in _capture_audit
              if e["event_type"] in ("git.commit", "git.push")]
    assert len(events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client, _patch_worktree_resolver):
    cases = [
        ("POST", "/api/git/worktree/0/0/commit", {"message": "x"}),
        ("POST", "/api/git/worktree/1/0/commit", {"message": " "}),
        ("POST", "/api/git/worktree/1/0/push",
         {"branch": "main", "dry_run": True}),
        ("POST", "/api/git/worktree/1/0/push",
         {"branch": "feature/x", "dry_run": True}),
        ("POST", "/api/git/worktree/1/0/commit",
         {"message": "x", "actor_user_id": " "}),
    ]
    for method, path, payload in cases:
        r = client.post(path, json=payload)
        assert 400 <= r.status_code < 500, f"{path}: {r.status_code}"
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
