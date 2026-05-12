"""T-M29-02: worktree path → session マッピング — 4 AC.

NEW WK タスク. T-M29-01 worktree.py を REUSE (無改変) して
逆引き path_mapper.py を追加.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : path_mapper.py に 5 公開 symbol /
                       T-M29-01 worktree.py REUSE (無改変).
  AC-2 EVENT-DRIVEN  : parse_worktree_path dict / None / find_session_for_path
                       None graceful.
  AC-3 STATE-DRIVEN  : pure parsing / no I/O / no langgraph etc. /
                       REPO_ROOT 再定義しない / LRU cache.
  AC-4 UNWANTED      : empty/non-string/over 4096 で InvalidPathError /
                       find_session は non-worktree で None / pool_id<=0
                       で InvalidWorktreeArgs.
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest

from services.swarm import path_mapper as pm
from services.swarm import worktree as wt


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "backend" / "services" / "swarm" / "path_mapper.py"
WORKTREE_PATH = REPO_ROOT / "backend" / "services" / "swarm" / "worktree.py"


@pytest.fixture(autouse=True)
def _reset_cache():
    pm.reset_cache_for_test()
    yield
    pm.reset_cache_for_test()


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — 5 public symbols + T-M29-01 REUSE invariant
# ══════════════════════════════════════════════════════════════════════


def test_ac1_module_file_exists():
    assert MODULE_PATH.exists()


@pytest.mark.parametrize("sym", [
    "WORKTREE_PATH_PATTERN",
    "parse_worktree_path",
    "is_worktree_path",
    "find_session_for_path",
    "InvalidPathError",
])
def test_ac1_public_symbol_exists(sym):
    assert hasattr(pm, sym), f"path_mapper missing: {sym}"


def test_ac1_worktree_module_unchanged_no_t_m29_02_dep():
    """REUSE invariant: T-M29-01 worktree.py に T-M29-02 依存追加なし."""
    src = WORKTREE_PATH.read_text(encoding="utf-8")
    assert "T-M29-02" not in src
    assert "path_mapper" not in src


def test_ac1_path_mapper_reuses_worktree_constants():
    """G15: REPO_ROOT / WORKTREES_BASE を再定義しない (worktree.py から import)."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    code = _strip_py_comments(src)
    # 再定義の代入が無いこと: `REPO_ROOT =` `WORKTREES_BASE =` 禁止
    assert not re.search(r"^\s*REPO_ROOT\s*=\s*Path", code, re.MULTILINE), (
        "REPO_ROOT must NOT be redefined in path_mapper (G15 invariant)"
    )
    assert not re.search(r"^\s*WORKTREES_BASE\s*=\s*Path", code, re.MULTILINE), (
        "WORKTREES_BASE must NOT be redefined in path_mapper"
    )
    # T-M29-01 worktree.py から import している
    assert "from services.swarm.worktree import" in src


def test_ac1_invalid_path_error_is_value_error_subclass():
    """InvalidPathError は router で 4xx mapping できるよう ValueError 継承."""
    assert issubclass(pm.InvalidPathError, ValueError)


def test_ac1_pattern_is_compiled_regex():
    assert isinstance(pm.WORKTREE_PATH_PATTERN, re.Pattern)


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — parse / find return shape + None graceful
# ══════════════════════════════════════════════════════════════════════


def test_ac2_parse_returns_dict_for_valid_path():
    result = pm.parse_worktree_path(
        "/home/user/Build-Factory/.worktrees/swarm_42/cell_7/subdir/file.py"
    )
    assert result is not None
    assert result["pool_id"] == 42
    assert result["cell_index"] == 7
    assert result["relative"] == "subdir/file.py"
    assert result["worktree_root"].endswith(".worktrees/swarm_42/cell_7")
    assert result["branch"] == "swarm/42/cell-7"


def test_ac2_parse_returns_dict_for_worktree_root():
    """relative なし (worktree root 自体) でも parse 可."""
    result = pm.parse_worktree_path(
        "/repo/.worktrees/swarm_1/cell_0"
    )
    assert result is not None
    assert result["pool_id"] == 1
    assert result["cell_index"] == 0
    assert result["relative"] == ""


def test_ac2_parse_returns_none_for_non_worktree_path():
    """非 worktree path は None (exception ではない)."""
    for path in (
        "/etc/passwd",
        "/home/user/project/src/main.py",
        "backend/services/foo.py",
        "/repo/.git/index",
    ):
        result = pm.parse_worktree_path(path)
        assert result is None, f"expected None for {path}, got {result}"


def test_ac2_parse_handles_path_object():
    """pathlib.Path も受け入れる."""
    p = Path("/repo/.worktrees/swarm_5/cell_2/file.txt")
    result = pm.parse_worktree_path(p)
    assert result is not None
    assert result["pool_id"] == 5
    assert result["cell_index"] == 2


def test_ac2_is_worktree_path_bool():
    assert pm.is_worktree_path("/repo/.worktrees/swarm_1/cell_0/file.py") is True
    assert pm.is_worktree_path("/etc/passwd") is False
    assert pm.is_worktree_path("") is False
    assert pm.is_worktree_path(None) is False


def test_ac2_find_session_returns_dict_for_worktree():
    result = pm.find_session_for_path(
        "/repo/.worktrees/swarm_3/cell_1/file.py"
    )
    assert result is not None
    assert result["pool_id"] == 3
    assert result["cell_index"] == 1
    assert "session_lookup_key" in result


def test_ac2_find_session_returns_none_for_non_worktree():
    """non-worktree path で None (graceful)."""
    assert pm.find_session_for_path("/etc/passwd") is None
    assert pm.find_session_for_path("backend/main.py") is None


def test_ac2_find_session_does_not_raise_on_invalid_path():
    """invalid path (e.g. empty / None) で find_session_for_path は None."""
    assert pm.find_session_for_path("") is None
    assert pm.find_session_for_path(None) is None


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — pure / no I/O / no langgraph / LRU
# ══════════════════════════════════════════════════════════════════════


def test_ac3_parse_is_deterministic():
    """同じ入力で常に同じ output."""
    p = "/repo/.worktrees/swarm_99/cell_5/x/y.py"
    r1 = pm.parse_worktree_path(p)
    r2 = pm.parse_worktree_path(p)
    assert r1 == r2


def test_ac3_no_db_no_redis_in_pure_parsing():
    """parse / is_worktree_path は pure (no aiosqlite / no redis import).

    find_session_for_path は lazy import で graceful なので OK.
    """
    src = MODULE_PATH.read_text(encoding="utf-8")
    code = _strip_py_comments(src)
    # top-level (module-level) で aiosqlite / redis import なし
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import aiosqlite", "from aiosqlite",
                                 "import redis", "from redis")):
            raise AssertionError(
                f"top-level DB/cache import detected: {stripped}"
            )


def test_ac3_no_langgraph_langchain_litellm():
    src = MODULE_PATH.read_text(encoding="utf-8")
    code = _strip_py_comments(src).lower()
    for forbidden in ("langgraph", "langchain", "litellm"):
        assert forbidden not in code, f"forbidden {forbidden} in path_mapper"


def test_ac3_no_section_keys_redefinition():
    """G15: SECTION_KEYS は mid_term_layer 専管."""
    code = _strip_py_comments(MODULE_PATH.read_text(encoding="utf-8"))
    assert "SECTION_KEYS" not in code


def test_ac3_find_session_uses_lru_cache():
    """find_session 内部の lookup helper が functools.lru_cache を使う."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    assert "functools.lru_cache" in src or "@functools.lru_cache" in src
    # maxsize=256 が宣言されている
    assert "maxsize=256" in src


def test_ac3_repeated_lookup_uses_cache():
    """同 worktree_root の繰り返し lookup で _cached_lookup_key の cache_info()
    が hit する."""
    pm._cached_lookup_key.cache_clear()
    pm.find_session_for_path("/r/.worktrees/swarm_1/cell_0/a.py")
    pm.find_session_for_path("/r/.worktrees/swarm_1/cell_0/b.py")
    info = pm._cached_lookup_key.cache_info()
    # 同じ worktree_root なので 2 回目は hit
    assert info.hits >= 1, (
        f"expected cache hits >= 1, got {info}"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED — invalid input + pool_id validation
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("bad_path", [None, "", "  ", 123, [], {}])
def test_ac4_parse_invalid_input_raises(bad_path):
    with pytest.raises(pm.InvalidPathError):
        pm.parse_worktree_path(bad_path)


def test_ac4_parse_over_max_length_raises():
    long = "/r/" + "x" * (pm.MAX_PATH_LEN + 1)
    with pytest.raises(pm.InvalidPathError):
        pm.parse_worktree_path(long)


def test_ac4_parse_invalid_pool_id_zero_raises_via_worktree_validate():
    """pool_id=0 は T-M29-01 _validate で InvalidWorktreeArgs 発生 (REUSE)."""
    with pytest.raises(wt.InvalidWorktreeArgs):
        pm.parse_worktree_path("/r/.worktrees/swarm_0/cell_0/file.py")


def test_ac4_find_session_swallows_invalid_path():
    """find_session_for_path は invalid でも None (raise しない / graceful)."""
    # InvalidPathError ケース
    assert pm.find_session_for_path("") is None
    assert pm.find_session_for_path(None) is None
    # InvalidWorktreeArgs ケース (pool_id=0)
    assert pm.find_session_for_path(
        "/r/.worktrees/swarm_0/cell_0/file.py"
    ) is None


def test_ac4_invalid_path_error_is_distinct_from_invalid_worktree_args():
    """InvalidPathError と InvalidWorktreeArgs は別 class."""
    assert pm.InvalidPathError is not wt.InvalidWorktreeArgs
    # 両方 ValueError 継承
    assert issubclass(pm.InvalidPathError, ValueError)
    assert issubclass(wt.InvalidWorktreeArgs, ValueError)


def test_ac4_no_hardcoded_secret():
    src = MODULE_PATH.read_text(encoding="utf-8")
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_m29_02_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.loads(path.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-M29-02"), None)
    assert t is not None
    generic = [
        "as specified by feature M-29",
        "When the implementation step for T-M29-02 is triggered",
        "While the new feature for T-M29-02 is enabled",
        "If invalid input or unauthorized actor is detected during T-M29-02",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], (
                f"T-M29-02 still generic: {phrase!r}"
            )
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "path_mapper.py", "WORKTREE_PATH_PATTERN",
        "parse_worktree_path", "is_worktree_path",
        "find_session_for_path", "InvalidPathError",
        "lru_cache",
    ):
        assert sym in full, f"T-M29-02 AC missing: {sym}"


def test_tickets_t_m29_02_has_adr_link_and_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.loads(path.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-M29-02"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert any("worktree.py" in f for f in files)


def test_tickets_t_m29_02_canonical_ears_types():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.loads(path.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-M29-02"), None)
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
