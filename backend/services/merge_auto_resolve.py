"""T-013-04 (Phase 1): merge conflict detection + human escalation.

F-013 error_path "merge conflict → AI 自動解決試行 → 失敗で人間エスカ" のうち、
**Phase 1 では中間の「AI 自動解決試行」は未実装** とし、`detect → escalate` の
2 段のみを正直に提供する.

## Phase 境界 (極めて重要 — spot-check で発覚した spec drift を防ぐ)

Phase 1 (本モジュール / this PR):
  - `detect_and_escalate(base, target)` のみ.
  - T-M29-03 `detect_conflict_dry_run` を REUSE.
  - status ∈ {"no_conflict", "escalate"} のみ.
  - **"resolved" status は Phase 1 では返らない** (まだ実装されていない).
  - conflicts が見つかれば即 escalate (= human review).

Phase 1.5 (deferred — 新規 task T-013-04b に分離予定):
  - LLM-driven 実 strategy 試行 (S-5 impact-analysis 連動).
  - git >= 2.40 `merge-tree --strategy=ours/theirs/...` 経由の真の自動解決.
  - `try_auto_resolve(base, target, strategies=[...])` を新規公開.
  - status ∈ {"no_conflict", "resolved", "escalate"}.

## 設計境界

- T-M29-03 (sequential_merge.py) は **REUSE のみ (無改変 import)**.
- 本 module は **read-only**: 実 merge / push / commit は一切実行しない.
- F-013 policy ``force_push: red line 自動停止`` を遵守 (force / push 文字列を含まない).
- LangGraph / LangChain / LiteLLM の import 禁止 (CLAUDE.md §3 禁則).

## 公開 API

- ``detect_and_escalate(base_branch, target_branch, *, timeout_sec=2)`` -> dict
- ``AutoResolveError`` (caller が 4xx 変換用)
- ``DEFAULT_TIMEOUT_SEC``: per-call timeout (≤ 2 秒)
- ``PHASE``: 文字列 "1" (Phase 識別子 — Phase 1.5 で "1.5" に拡張予定)

## EscalationResult shape

  {
    "status": "no_conflict" | "escalate",
    "phase": "1",
    "base": str,
    "target": str,
    "conflicts": list[str],          # escalate 時のみ非空
    "next_step": "none" | "human_review",
  }

## AC マッピング (Phase 1 honest version)

  AC-1 UBIQUITOUS    : 4 公開 symbol / T-M29-03 REUSE 無改変 / detect + escalate
                        の 2 段 / force-push 文字列なし / Phase 識別子明示.
  AC-2 EVENT-DRIVEN  : dict 返却 / 必須 keys / AutoResolveError raise /
                        per-call timeout ≤ 2 秒.
  AC-3 STATE-DRIVEN  : no shell=True / cwd 固定 (delegate 経由) / forbidden
                        AI stack import なし / no mutating git subcommand /
                        no REPO_ROOT redefinition.
  AC-4 UNWANTED      : invalid input で AutoResolveError / no DB mutation /
                        no fs write / no hardcoded secret.
"""
from __future__ import annotations

from typing import Any

# T-M29-03 REUSE (G15 single-source / 無改変).
from services.swarm.sequential_merge import (
    MergeConflictError,
    SequentialMergeError,
    detect_conflict_dry_run,
)


# Phase identifier. Phase 1.5 will set this to "1.5" alongside resolved-path impl.
PHASE = "1"

# AC-2: per-call timeout ≤ 2 秒 (要件文 "within 2 seconds").
DEFAULT_TIMEOUT_SEC = 2


class AutoResolveError(ValueError):
    """invalid input / git-level fatal (caller が 4xx 化).

    Wraps lower-level T-M29-03 SequentialMergeError / MergeConflictError so
    callers can catch a single exception type.
    """


async def detect_and_escalate(
    base_branch: str,
    target_branch: str,
    *,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    """F-013 error_path Phase 1: detect conflict → escalate to human.

    Phase 1 deliberately omits the "AI 自動解決試行" middle stage.
    Whenever conflicts exist, the function returns `status="escalate"` so the
    human reviewer is the next step. Phase 1.5 will introduce LLM-driven
    strategies via `try_auto_resolve()` in a follow-up task (T-013-04b).

    Args:
      base_branch: e.g. ``main``.
      target_branch: e.g. ``claude/feature-x``.
      timeout_sec: per-call timeout (>= 1, <= DEFAULT_TIMEOUT_SEC).

    Returns:
      EscalationResult dict (see module docstring for shape).

    Raises:
      AutoResolveError: invalid input / git-level fatal.
    """
    try:
        result = await detect_conflict_dry_run(
            base_branch, target_branch, timeout_sec=timeout_sec,
        )
    except MergeConflictError as exc:
        # ref-not-found 等の git-level error.
        raise AutoResolveError(f"git error: {exc}") from exc
    except SequentialMergeError as exc:
        # invalid branch / shell metachar / over-length.
        raise AutoResolveError(f"invalid input: {exc}") from exc

    if not result["has_conflict"]:
        return {
            "status": "no_conflict",
            "phase": PHASE,
            "base": base_branch,
            "target": target_branch,
            "conflicts": [],
            "next_step": "none",
        }

    # Phase 1: conflicts present → escalate immediately (no middle stage).
    return {
        "status": "escalate",
        "phase": PHASE,
        "base": base_branch,
        "target": target_branch,
        "conflicts": list(result.get("conflicts", [])),
        "next_step": "human_review",
    }
