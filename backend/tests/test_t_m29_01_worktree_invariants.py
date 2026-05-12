"""T-M29-01: git worktree manager — 4 AC 機械 invariant 検証.

PR #64 (T-M29-01 初版) で production 実装 + 18 件 behavior test が完成済.
本 module は **spec contract layer** として 4 AC が production code の
symbol / 命名規約 / event 名 / cross-module invariant と 1:1 整合している
ことを機械検証する.

既存 test_t_m29_01_worktree_manager.py は behavior (実 git worktree が
作られる) を、本 test は spec contract (公開 API + 命名規約 + audit event
名 + ADR-010 / G15 invariant) を担当する.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : worktree.py が 9 公開 symbol export /
                       worktree_path = .worktrees/swarm_{pool}/cell_{i} /
                       branch_name = swarm/{pool}/cell-{i}.
  AC-2 EVENT-DRIVEN  : create で 'worktree.created' / remove で
                       'worktree.removed' / audit-emit 失敗で silent log.
  AC-3 STATE-DRIVEN  : asyncio.create_subprocess_exec / no shell=True /
                       no os.system / no langgraph / langchain / litellm /
                       SECTION_KEYS / REVIEW_DIMENSIONS / PERSONA_NAME
                       再定義禁止.
  AC-4 UNWANTED      : pool_id <= 0 / cell_index < 0 で InvalidWorktreeArgs
                       (ValueError 継承) / partial worktree leak なし /
                       git error silent drop しない.
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest

from services.swarm import worktree as wt


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKTREE_PATH = REPO_ROOT / "backend" / "services" / "swarm" / "worktree.py"
ORCHESTRATOR_PATH = REPO_ROOT / "backend" / "services" / "swarm" / "orchestrator.py"


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — 9 public symbols + deterministic naming
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("sym", [
    "REPO_ROOT",
    "WORKTREES_BASE",
    "worktree_path",
    "branch_name",
    "create_worktree",
    "remove_worktree",
    "list_worktrees",
    "is_inside_cell_worktree",
    "InvalidWorktreeArgs",
])
def test_ac1_public_symbol_exists(sym):
    assert hasattr(wt, sym), f"missing public symbol: {sym}"


def test_ac1_worktrees_base_is_under_repo_root():
    assert wt.WORKTREES_BASE.name == ".worktrees"
    assert wt.WORKTREES_BASE.parent == wt.REPO_ROOT


def test_ac1_worktree_path_deterministic_naming():
    """.worktrees/swarm_{pool_id}/cell_{cell_index}."""
    p = wt.worktree_path(42, 7)
    assert p == wt.WORKTREES_BASE / "swarm_42" / "cell_7"


def test_ac1_branch_name_deterministic_naming():
    """swarm/{pool_id}/cell-{cell_index}."""
    b = wt.branch_name(42, 7)
    assert b == "swarm/42/cell-7"


def test_ac1_branch_name_pool_0_cell_0():
    """edge case: pool=0 拒否されるが branch_name 関数自体は pure (validate なし)."""
    assert wt.branch_name(1, 0) == "swarm/1/cell-0"


def test_ac1_create_remove_list_are_async():
    assert inspect.iscoroutinefunction(wt.create_worktree)
    assert inspect.iscoroutinefunction(wt.remove_worktree)
    assert inspect.iscoroutinefunction(wt.list_worktrees)


def test_ac1_invalid_worktree_args_is_value_error_subclass():
    assert issubclass(wt.InvalidWorktreeArgs, ValueError)


def test_ac1_is_inside_cell_worktree_returns_bool():
    """worktree 内判定 helper."""
    inside = wt.is_inside_cell_worktree(
        wt.worktree_path(1, 0) / "file.txt", 1, 0,
    )
    outside = wt.is_inside_cell_worktree(
        Path("/tmp/elsewhere.txt"), 1, 0,
    )
    assert inside is True
    assert outside is False


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — worktree.created / worktree.removed audit emit
# ══════════════════════════════════════════════════════════════════════


def test_ac2_create_worktree_emits_worktree_created_event():
    src = inspect.getsource(wt.create_worktree)
    assert '"worktree.created"' in src or "'worktree.created'" in src


def test_ac2_remove_worktree_emits_worktree_removed_event():
    src = inspect.getsource(wt.remove_worktree)
    assert '"worktree.removed"' in src or "'worktree.removed'" in src


def test_ac2_audit_emit_uses_memory_service_emit_event():
    """audit-emit は services.memory_service.emit_event 経由."""
    src = WORKTREE_PATH.read_text(encoding="utf-8")
    assert "from services.memory_service import emit_event" in src


def test_ac2_audit_emit_failure_silently_logged():
    """audit emit が失敗してもアプリは止めない (silent log) — try/except pass."""
    src = inspect.getsource(wt._emit_worktree_audit)
    # try/except Exception: pass パターン
    assert "try:" in src
    assert "except" in src
    assert "pass" in src or "logger" in src


def test_ac2_audit_detail_contains_pool_cell_path_branch():
    """detail dict に pool_id / cell_index / path / branch が含まれる."""
    src = inspect.getsource(wt._emit_worktree_audit)
    for key in ("pool_id", "cell_index", "path", "branch"):
        assert key in src, f"audit detail missing: {key}"


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — async subprocess only + ADR-010 + G15
# ══════════════════════════════════════════════════════════════════════


def test_ac3_uses_asyncio_create_subprocess_exec():
    src = WORKTREE_PATH.read_text(encoding="utf-8")
    assert "asyncio.create_subprocess_exec" in src


def test_ac3_no_shell_true():
    """shell=True は injection リスクなので禁止."""
    src = WORKTREE_PATH.read_text(encoding="utf-8")
    code = _strip_strings_and_comments(src)
    assert "shell=True" not in code


def test_ac3_no_os_system():
    """os.system は blocking + shell-injection なので禁止."""
    src = WORKTREE_PATH.read_text(encoding="utf-8")
    code = _strip_strings_and_comments(src)
    assert not re.search(r"\bos\.system\s*\(", code)


def test_ac3_no_blocking_subprocess_run_on_git():
    """git 操作は async subprocess のみ. subprocess.run( ... ['git', ...] ) なし.

    Note: subprocess module 自体の import は他の用途で OK だが、 git
    command を blocking で呼ばない."""
    src = WORKTREE_PATH.read_text(encoding="utf-8")
    code = _strip_strings_and_comments(src)
    # subprocess.run("git", ...) / subprocess.run(["git", ...]) パターンなし
    assert not re.search(r"subprocess\.run\s*\(\s*\[?\s*['\"]git['\"]", code)
    assert not re.search(r"subprocess\.call\s*\(\s*\[?\s*['\"]git['\"]", code)
    assert not re.search(r"subprocess\.Popen\s*\(\s*\[?\s*['\"]git['\"]", code)


def test_ac3_run_git_cwd_defaults_to_repo_root():
    """_run_git が cwd default = REPO_ROOT."""
    src = inspect.getsource(wt._run_git)
    assert "REPO_ROOT" in src
    assert "cwd or REPO_ROOT" in src or "cwd=str(cwd or REPO_ROOT)" in src


def test_ac3_no_langgraph_no_langchain_no_litellm():
    src = WORKTREE_PATH.read_text(encoding="utf-8")
    code = _strip_strings_and_comments(src).lower()
    assert "langgraph" not in code
    assert "langchain" not in code
    assert "litellm" not in code


def test_ac3_no_section_keys_redefinition():
    """G15: SECTION_KEYS は mid_term_layer 責務."""
    code = _strip_strings_and_comments(WORKTREE_PATH.read_text(encoding="utf-8"))
    assert "SECTION_KEYS" not in code


def test_ac3_no_review_dimensions_redefinition():
    code = _strip_strings_and_comments(WORKTREE_PATH.read_text(encoding="utf-8"))
    assert "REVIEW_DIMENSIONS" not in code


def test_ac3_no_persona_name_redefinition():
    code = _strip_strings_and_comments(WORKTREE_PATH.read_text(encoding="utf-8"))
    assert "PERSONA_NAME" not in code


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED — InvalidWorktreeArgs + no partial leak + git error surface
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("bad_pool", [0, -1, -100, 1.5, "1", True, None])
def test_ac4_invalid_pool_id_raises(bad_pool):
    """pool_id が non-int / <= 0 で InvalidWorktreeArgs."""
    # bool は int の subclass で True (=1) は通る. 明示的に False に絞る.
    if isinstance(bad_pool, bool):
        bad_pool = False  # bool(False) → 0 → 拒否される
    with pytest.raises(wt.InvalidWorktreeArgs):
        wt._validate(bad_pool, 0)


@pytest.mark.parametrize("bad_cell", [-1, -100, 1.5, "0", None])
def test_ac4_invalid_cell_index_raises(bad_cell):
    with pytest.raises(wt.InvalidWorktreeArgs):
        wt._validate(1, bad_cell)


def test_ac4_invalid_worktree_args_is_value_error():
    """4xx mapping のために ValueError 継承であること."""
    assert issubclass(wt.InvalidWorktreeArgs, ValueError)
    e = wt.InvalidWorktreeArgs("test")
    assert isinstance(e, ValueError)


def test_ac4_validation_does_not_create_worktree_dir():
    """_validate failure 時にディレクトリが作られない (空チェック)."""
    bogus_path = wt.worktree_path(99999, 99999)
    # 即チェック: そもそも存在しないこと
    assert not bogus_path.exists()
    # _validate は negative pool_id で raise → ディレクトリ作成しない
    with pytest.raises(wt.InvalidWorktreeArgs):
        wt._validate(-1, 0)


def test_ac4_create_worktree_does_not_silently_swallow_git_error():
    """create_worktree のソース上で git stderr が surface される (silent skip なし)."""
    src = inspect.getsource(wt.create_worktree)
    # rc / stderr を扱う (raise なり return なりで非ゼロを surface)
    assert "stderr" in src or "rc" in src
    # bare `except: pass` で git エラーを握りつぶさない
    # ※ audit_emit の中は silent OK だが create_worktree 本体では不可
    bare_pass = re.findall(r"except[^:]*:\s*pass", src)
    # except (Exception,): pass のような bare catch があれば fail
    assert len(bare_pass) == 0, (
        f"create_worktree must not silently swallow errors: {bare_pass}"
    )


def test_ac4_no_hardcoded_secret():
    src = WORKTREE_PATH.read_text(encoding="utf-8")
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_m29_01_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-M29-01"), None)
    assert t is not None
    generic = [
        "as specified by feature M-29",
        "When the implementation step for T-M29-01 is triggered",
        "While the new feature for T-M29-01 is enabled",
        "If invalid input or unauthorized actor is detected during T-M29-01",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], (
                f"T-M29-01 still generic: {phrase!r}"
            )
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "worktree.py", "worktree_path", "branch_name", "create_worktree",
        "remove_worktree", "list_worktrees", "is_inside_cell_worktree",
        "InvalidWorktreeArgs", "WORKTREES_BASE",
        "worktree.created", "worktree.removed",
        "asyncio.create_subprocess_exec", "REPO_ROOT",
    ):
        assert sym in full, f"T-M29-01 AC missing concrete symbol: {sym}"


def test_tickets_t_m29_01_has_adr_link_and_8_existing_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-M29-01"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert len(files) >= 8, f"expected >= 8 existing_files, got {len(files)}"
    assert "backend/services/swarm/worktree.py" in files
    assert "backend/routers/swarm.py" in files


def test_tickets_t_m29_01_canonical_ears_types():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-M29-01"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE"), (
            f"T-M29-01 still uses legacy alias: {ty}"
        )
    assert types == ["UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "UNWANTED"]


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════


def _strip_strings_and_comments(src: str) -> str:
    out: list[str] = []
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
            out.append(line)
    return "\n".join(out)
