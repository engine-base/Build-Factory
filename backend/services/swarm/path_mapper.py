"""T-M29-02: worktree path → session マッピング.

T-M29-01 worktree.py の正引き helper (pool_id, cell_index → path) に対する
逆引き module. file path から (pool_id, cell_index, relative) を抽出し、
さらに該当 session 行を引く graceful lookup を提供する.

設計境界:
  - T-M29-01 worktree.py は REUSE のみ (無改変).
  - parse_worktree_path / is_worktree_path は pure / I/O なし.
  - find_session_for_path は LRU cache (size=256) で O(1) lookup.
  - 既存 G15 invariant: REPO_ROOT / WORKTREES_BASE を再定義しない.

公開 API:
  - WORKTREE_PATH_PATTERN: re.Pattern (compiled)
  - parse_worktree_path(path) -> Optional[dict]
  - is_worktree_path(path) -> bool
  - find_session_for_path(path) -> Optional[dict]
  - InvalidPathError (caller が 4xx 化)

AC マッピング:
  AC-1 UBIQUITOUS: 5 公開 symbol + T-M29-01 REUSE invariant.
  AC-2 EVENT-DRIVEN: parse が dict / None を返す / find も None gracefully.
  AC-3 STATE-DRIVEN: pure parsing / no langgraph/langchain/litellm /
                     REPO_ROOT 再定義しない / LRU cache.
  AC-4 UNWANTED: empty/non-string/over 4096 で InvalidPathError /
                  find は non-worktree で None / pool_id <= 0 で reject.
"""
from __future__ import annotations

import functools
import re
from pathlib import Path
from typing import Any, Optional

# T-M29-01 REUSE: 定数を再定義しない (G15 single-source invariant).
from services.swarm.worktree import (
    REPO_ROOT,
    WORKTREES_BASE,
    InvalidWorktreeArgs,
    _validate as _validate_pool_cell,
    branch_name as _branch_name,
    worktree_path as _worktree_path,
)

MAX_PATH_LEN = 4096


class InvalidPathError(ValueError):
    """invalid input (caller が 4xx 化). T-M29-01 InvalidWorktreeArgs と
    similar 役割だが、 path レベルの validation 専用."""


# ──────────────────────────────────────────────────────────────────────
# Regex: .worktrees/swarm_{pool}/cell_{i}[/rest]
#
# - pool_id : 正の整数 (1 以上)
# - cell_index: 0 以上の整数
# - rest    : 任意 (optional)
# ──────────────────────────────────────────────────────────────────────

WORKTREE_PATH_PATTERN: re.Pattern = re.compile(
    r"(?:^|/)\.worktrees/swarm_(?P<pool_id>\d+)/cell_(?P<cell_index>\d+)"
    r"(?:/(?P<relative>.*))?$"
)


# ──────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────


def _validate_path(path: Any) -> str:
    if path is None:
        raise InvalidPathError("path must not be None")
    if not isinstance(path, (str, Path)):
        raise InvalidPathError(
            f"path must be str or Path, got {type(path).__name__}"
        )
    s = str(path)
    if not s.strip():
        raise InvalidPathError("path must not be empty")
    if len(s) > MAX_PATH_LEN:
        raise InvalidPathError(
            f"path must be <= {MAX_PATH_LEN} chars, got {len(s)}"
        )
    return s


# ──────────────────────────────────────────────────────────────────────
# Public API: pure parsing (no I/O)
# ──────────────────────────────────────────────────────────────────────


def parse_worktree_path(path: Any) -> Optional[dict[str, Any]]:
    """worktree path を構成要素に分解する.

    Returns:
      {pool_id, cell_index, relative, worktree_root, branch}
      or None if path does NOT match the worktree pattern.

    Raises:
      InvalidPathError: path が empty / non-string / over MAX_PATH_LEN /
                        None の場合.
      InvalidWorktreeArgs: pool_id <= 0 / cell_index < 0 の場合
                          (T-M29-01 _validate semantics 再利用).
    """
    s = _validate_path(path)
    m = WORKTREE_PATH_PATTERN.search(s)
    if not m:
        return None
    pool_id = int(m.group("pool_id"))
    cell_index = int(m.group("cell_index"))
    # T-M29-01 _validate REUSE: pool_id <= 0 / cell_index < 0 を弾く
    _validate_pool_cell(pool_id, cell_index)
    relative = m.group("relative") or ""
    # worktree_root は実 path 構造を維持: matched 前部分 + matched部分
    matched_start = m.start()
    matched_end_of_pool_cell = (
        m.start() + len(f".worktrees/swarm_{pool_id}/cell_{cell_index}")
        + (1 if matched_start == 0 else 0)  # leading slash adjustment
    )
    # Robust: matched substring を再構築
    matched_root = s[:m.end()].rstrip("/")
    if relative:
        # remove trailing /<relative>
        rel_idx = matched_root.rfind("/" + relative)
        if rel_idx > 0:
            matched_root = matched_root[:rel_idx]
    return {
        "pool_id": pool_id,
        "cell_index": cell_index,
        "relative": relative,
        "worktree_root": matched_root,
        "branch": _branch_name(pool_id, cell_index),
    }


def is_worktree_path(path: Any) -> bool:
    """path が .worktrees/swarm_X/cell_Y 配下か (pure / no I/O).

    None / empty / type error は False を返す (raise しない).
    """
    try:
        s = _validate_path(path)
    except InvalidPathError:
        return False
    try:
        parsed = parse_worktree_path(s)
    except InvalidWorktreeArgs:
        return False
    return parsed is not None


# ──────────────────────────────────────────────────────────────────────
# Public API: session lookup (LRU cached)
# ──────────────────────────────────────────────────────────────────────


@functools.lru_cache(maxsize=256)
def _cached_lookup_key(worktree_root: str) -> Optional[str]:
    """worktree_root → session_id の lookup key cache.

    Phase 1: 実 DB 接続なしで動く graceful lookup. 接続失敗 / table 不在
    で None を返す.
    """
    try:
        # Lazy import: tests で session DB なしでも import 自体は通す.
        from integrations.claude_agent_runner import InMemorySessionStore  # noqa: F401
        # Phase 1: 実 store lookup は別 issue. ここでは marker 返却.
        return f"lookup:{worktree_root}"
    except Exception:  # noqa: BLE001 — graceful fallback
        return None


def find_session_for_path(path: Any) -> Optional[dict[str, Any]]:
    """path から該当 session 情報を返す (no exception on miss).

    返す dict は {worktree_root, pool_id, cell_index, branch,
                  session_lookup_key}.
    """
    try:
        parsed = parse_worktree_path(path)
    except (InvalidPathError, InvalidWorktreeArgs):
        return None
    if parsed is None:
        return None
    key = _cached_lookup_key(parsed["worktree_root"])
    return {
        **parsed,
        "session_lookup_key": key,
    }


def reset_cache_for_test() -> None:
    """test cleanup 用 (production では呼ばない)."""
    _cached_lookup_key.cache_clear()
