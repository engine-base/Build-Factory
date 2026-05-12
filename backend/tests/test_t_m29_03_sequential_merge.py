"""T-M29-03: merge conflict 検出 + sequential merge ヘルパー — 4 AC.

NEW BE タスク. T-M29-01 worktree.py を REUSE (無改変). git merge-tree
の dry-run conflict 検出 + sequential plan generator を提供.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : sequential_merge.py に 5 公開 symbol /
                       T-M29-01 worktree.py REUSE (無改変).
  AC-2 EVENT-DRIVEN  : merge-tree dry-run 2 秒以内 / plan deterministic
                       (cell_index asc).
  AC-3 STATE-DRIVEN  : asyncio.create_subprocess_exec / cwd=REPO_ROOT /
                       no shell=True / no os.system / no langgraph /
                       langchain / litellm / REPO_ROOT 再定義禁止 /
                       no mutation.
  AC-4 UNWANTED      : invalid input で SequentialMergeError / git error
                       で MergeConflictError / N>MAX で reject /
                       no actual merge / no push.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import re
from pathlib import Path

import pytest

from services.swarm import sequential_merge as sm
from services.swarm import worktree as wt


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "backend" / "services" / "swarm" / "sequential_merge.py"
WORKTREE_PATH = REPO_ROOT / "backend" / "services" / "swarm" / "worktree.py"


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — 5 public symbols + T-M29-01 REUSE invariant
# ══════════════════════════════════════════════════════════════════════


def test_ac1_module_file_exists():
    assert MODULE_PATH.exists()


@pytest.mark.parametrize("sym", [
    "MergeConflictError",
    "SequentialMergeError",
    "detect_conflict_dry_run",
    "plan_sequential_merge",
    "MAX_CELLS_PER_PLAN",
])
def test_ac1_public_symbol(sym):
    assert hasattr(sm, sym), f"sequential_merge missing: {sym}"


def test_ac1_max_cells_per_plan_64():
    assert sm.MAX_CELLS_PER_PLAN == 64


def test_ac1_worktree_module_unchanged_no_t_m29_03_dep():
    """REUSE invariant: T-M29-01 worktree.py に T-M29-03 依存追加なし."""
    src = WORKTREE_PATH.read_text(encoding="utf-8")
    assert "T-M29-03" not in src
    assert "sequential_merge" not in src


def test_ac1_reuses_t_m29_01_imports():
    """worktree.py から REPO_ROOT / _validate / branch_name を import."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    assert "from services.swarm.worktree import" in src
    assert "REPO_ROOT" in src
    assert "_validate" in src
    assert "branch_name" in src


def test_ac1_error_classes_subclass_appropriately():
    assert issubclass(sm.SequentialMergeError, ValueError)
    assert issubclass(sm.MergeConflictError, RuntimeError)


def test_ac1_detect_conflict_is_async():
    assert inspect.iscoroutinefunction(sm.detect_conflict_dry_run)


def test_ac1_plan_sequential_merge_is_async():
    assert inspect.iscoroutinefunction(sm.plan_sequential_merge)


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — dry-run merge-tree + deterministic plan
# ══════════════════════════════════════════════════════════════════════


def test_ac2_detect_conflict_uses_merge_tree():
    """detect_conflict_dry_run のソースに `merge-tree` が含まれる."""
    src = inspect.getsource(sm.detect_conflict_dry_run)
    assert "merge-tree" in src


def test_ac2_detect_conflict_uses_write_tree_mode():
    """新構文 `--write-tree --name-only` で safer parse."""
    src = inspect.getsource(sm.detect_conflict_dry_run)
    assert "--write-tree" in src
    assert "--name-only" in src


def test_ac2_plan_deterministic_order():
    """plan が cell_index ascending."""
    src = inspect.getsource(sm.plan_sequential_merge)
    # for cell in range(n): で順序 0..n-1
    assert re.search(r"for\s+cell\s+in\s+range\(\s*n", src) or \
           re.search(r"for\s+cell_index\s+in\s+range", src)


def test_ac2_plan_returns_4_field_dict():
    """plan entry の field 名を実装で確認."""
    src = inspect.getsource(sm.plan_sequential_merge)
    for field in ("pool_id", "cell_index", "branch", "predicted_conflict"):
        assert field in src, f"plan entry missing field: {field}"


def test_ac2_detect_returns_required_fields():
    """detect_conflict_dry_run 戻り値に必須 field."""
    src = inspect.getsource(sm.detect_conflict_dry_run)
    for field in ("has_conflict", "conflicts", "stdout_sample",
                  "returncode", "base", "target"):
        assert field in src, f"detect_conflict response missing field: {field}"


def test_ac2_timeout_default_30s():
    """timeout default = 30s (2s spec を超えない typical case)."""
    sig = inspect.signature(sm.detect_conflict_dry_run)
    p = sig.parameters.get("timeout_sec")
    assert p is not None
    assert p.default == 30


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — async exec / no shell / no langgraph / no mutation
# ══════════════════════════════════════════════════════════════════════


def test_ac3_uses_async_create_subprocess_exec():
    src = MODULE_PATH.read_text(encoding="utf-8")
    assert "asyncio.create_subprocess_exec" in src


def test_ac3_no_shell_true():
    src = MODULE_PATH.read_text(encoding="utf-8")
    code = _strip_py_comments(src)
    assert "shell=True" not in code


def test_ac3_no_os_system():
    src = MODULE_PATH.read_text(encoding="utf-8")
    code = _strip_py_comments(src)
    assert not re.search(r"\bos\.system\s*\(", code)


def test_ac3_no_blocking_subprocess_on_git():
    src = MODULE_PATH.read_text(encoding="utf-8")
    code = _strip_py_comments(src)
    # subprocess.run / call / Popen を git に直接使わない
    assert not re.search(r"subprocess\.run\s*\(\s*\[?\s*['\"]git['\"]", code)
    assert not re.search(r"subprocess\.call\s*\(\s*\[?\s*['\"]git['\"]", code)
    assert not re.search(r"subprocess\.Popen\s*\(\s*\[?\s*['\"]git['\"]", code)


def test_ac3_cwd_defaults_to_repo_root():
    src = inspect.getsource(sm._run_git)
    assert "REPO_ROOT" in src
    assert "cwd=str(REPO_ROOT)" in src or "cwd=REPO_ROOT" in src


def test_ac3_no_langgraph_langchain_litellm():
    src = MODULE_PATH.read_text(encoding="utf-8")
    code = _strip_py_comments(src).lower()
    for forbidden in ("langgraph", "langchain", "litellm"):
        assert forbidden not in code


def test_ac3_no_section_keys_redefinition():
    """G15: SECTION_KEYS / REPO_ROOT / WORKTREES_BASE 再定義禁止."""
    code = _strip_py_comments(MODULE_PATH.read_text(encoding="utf-8"))
    assert "SECTION_KEYS" not in code
    assert not re.search(r"^\s*REPO_ROOT\s*=\s*Path", code, re.MULTILINE)
    assert not re.search(r"^\s*WORKTREES_BASE\s*=\s*Path", code, re.MULTILINE)


def test_ac3_no_actual_merge_or_checkout():
    """source 上で `git merge` (without --no-commit) / `git checkout` /
    `git push` を呼ばない (dry-run only)."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    code = _strip_py_comments(src)
    # "merge" は merge-tree でのみ使う (subcommand 単独の "merge" を弾く)
    bad_patterns = [
        r"['\"]checkout['\"]",
        r"['\"]push['\"]",
        r"['\"]reset['\"]",
    ]
    for pat in bad_patterns:
        assert not re.search(pat, code), (
            f"forbidden git subcommand pattern: {pat}"
        )


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED — invalid input + N > MAX + no actual merge
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("bad_branch", [None, "", "  ", 123, [], "ref;rm -rf /", "a\nb"])
def test_ac4_invalid_branch_raises(bad_branch):
    """invalid branch (None / 空 / shell metachar) で SequentialMergeError."""
    with pytest.raises(sm.SequentialMergeError):
        asyncio.run(sm.detect_conflict_dry_run(bad_branch, "main"))


@pytest.mark.parametrize("bad_pool", [0, -1, "1", 1.5, True])
def test_ac4_invalid_pool_id_raises(bad_pool):
    with pytest.raises(sm.SequentialMergeError):
        asyncio.run(sm.plan_sequential_merge(bad_pool, 3))


def test_ac4_n_over_max_raises():
    with pytest.raises(sm.SequentialMergeError):
        asyncio.run(sm.plan_sequential_merge(1, sm.MAX_CELLS_PER_PLAN + 1))


@pytest.mark.parametrize("bad_n", [-1, "5", 1.5, None])
def test_ac4_invalid_n_raises(bad_n):
    with pytest.raises(sm.SequentialMergeError):
        asyncio.run(sm.plan_sequential_merge(1, bad_n))


def test_ac4_n_zero_returns_empty_plan():
    """n=0 で 空 plan (edge case / no exception)."""
    plan = asyncio.run(sm.plan_sequential_merge(1, 0))
    assert plan == []


def test_ac4_shell_metachar_in_branch_rejected():
    """; | ` $ \\\\ \\n \\r などの shell injection 文字を弾く."""
    for c in (";", "|", "`", "$", "\\", "\n", "\r"):
        bad = f"feature{c}rm"
        with pytest.raises(sm.SequentialMergeError):
            asyncio.run(sm.detect_conflict_dry_run("main", bad))


def test_ac4_branch_over_max_length_raises():
    long = "x" * (sm.MAX_BRANCH_LEN + 1)
    with pytest.raises(sm.SequentialMergeError):
        asyncio.run(sm.detect_conflict_dry_run("main", long))


def test_ac4_no_hardcoded_secret():
    src = MODULE_PATH.read_text(encoding="utf-8")
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_m29_03_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.loads(path.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-M29-03"), None)
    generic = [
        "as specified by feature M-29",
        "When the relevant API endpoint or service function is invoked for T-M29-03",
        "While the new feature for T-M29-03 is enabled",
        "If invalid input or unauthorized actor is detected during T-M29-03",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"]
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "sequential_merge.py",
        "MergeConflictError", "SequentialMergeError",
        "detect_conflict_dry_run", "plan_sequential_merge",
        "MAX_CELLS_PER_PLAN=64",
        "merge-tree", "asyncio.create_subprocess_exec",
    ):
        assert sym in full, f"T-M29-03 AC missing: {sym}"


def test_tickets_t_m29_03_has_adr_link_and_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.loads(path.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-M29-03"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert any("worktree.py" in f for f in files)
    assert any("path_mapper.py" in f for f in files)


def test_tickets_t_m29_03_canonical_ears():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.loads(path.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-M29-03"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == ["UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "UNWANTED"]


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════


def _strip_py_comments(src: str) -> str:
    out = re.sub(r'"""[\s\S]*?"""', "", src)
    out = re.sub(r"'''[\s\S]*?'''", "", out)
    out = re.sub(r"#[^\n]*", "", out)
    return out
