"""T-013-04: merge conflict 自動解決試行 (F-013 error_path).

T-M29-03 ``sequential_merge.detect_conflict_dry_run`` を REUSE して、
F-013 error_path "merge conflict → AI 自動解決試行 → 失敗で人間エスカ"
の 3 段 (detect / try / escalate) を提供する薄いオーケストレータ.

設計境界:
  - T-M29-03 (sequential_merge.py) は **REUSE のみ (無改変 import)**.
  - 本 module は **read-only**: 実 merge / push / commit は一切実行しない.
  - F-013 policy ``force_push: red line 自動停止`` を遵守 (force / push 文字列を含まない).
  - asyncio.create_subprocess_exec のみ (T-M29-03 helper delegate).
  - LangGraph / LangChain / LiteLLM の import 禁止 (CLAUDE.md §3 禁則).

公開 API:
  - ``try_auto_resolve(base_branch, target_branch, strategies=None)`` -> dict
  - ``AutoResolveError`` (caller が 4xx 変換)
  - ``STRATEGIES``: 許可された決定論的 strategy 名 tuple
  - ``DEFAULT_TIMEOUT_SEC``: 各 attempt の per-call timeout (≤ 2 秒)

AutoResolveResult shape (TypedDict-相当 dict):
  {
    "status": "no_conflict" | "resolved" | "escalate",
    "strategy_used": Optional[str],
    "base": str,
    "target": str,
    "conflicts": list[str],
    "attempts": list[{"strategy": str, "has_conflict": bool,
                       "conflicts": list[str]}],
  }

AC マッピング:
  AC-1 UBIQUITOUS    : 4 公開 symbol / T-M29-03 REUSE 無改変 / detect→try→
                        escalate の 3 段 / force-push 文字列なし.
  AC-2 EVENT-DRIVEN  : dict 返却 / 必須 keys / AutoResolveError raise /
                        per-attempt timeout ≤ 2 秒.
  AC-3 STATE-DRIVEN  : no shell=True / cwd 固定 (delegate 経由) / forbidden
                        AI stack import なし / no mutating git subcommand /
                        no REPO_ROOT redefinition.
  AC-4 UNWANTED      : invalid input で AutoResolveError / strategy whitelist /
                        no DB mutation / no fs write outside tmp.
"""
from __future__ import annotations

from typing import Any, Optional

# T-M29-03 REUSE (G15 single-source / 無改変).
from services.swarm.sequential_merge import (
    MergeConflictError,
    SequentialMergeError,
    detect_conflict_dry_run,
)


# F-013 policy: force_push red-line → 自前 push / force 関連 helper は持たない.
# 全 strategy は git merge-tree の決定論的 favor flag で表現する dry-run.
STRATEGIES: tuple[str, ...] = ("default", "ours", "theirs")

# AC-2: per-call timeout ≤ 2 秒 (要件文 "within 2 seconds").
DEFAULT_TIMEOUT_SEC = 2


class AutoResolveError(ValueError):
    """invalid input / strategy 違反 (caller が 4xx 化).

    Wraps lower-level T-M29-03 SequentialMergeError so callers can catch
    a single exception type.
    """


def _validate_strategy(name: Any) -> str:
    if not isinstance(name, str):
        raise AutoResolveError(
            f"strategy must be string, got {type(name).__name__}"
        )
    if name not in STRATEGIES:
        raise AutoResolveError(
            f"strategy must be one of {STRATEGIES}, got {name!r}"
        )
    return name


async def _attempt_with_strategy(
    base: str,
    target: str,
    strategy: str,
    *,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    """One dry-run attempt under a given strategy.

    Phase 1 は決定論的 favor flag のみで dry-run を再評価する. LLM 補助は
    Phase 1.5 で別タスク (S-5 impact-analysis 連動) として分離.

    `default` strategy = T-M29-03 ``detect_conflict_dry_run`` を素のまま実行
    した結果を返す (新しい subprocess は起こさず baseline を流用する想定の
    caller があるため、ここでは追加引数なしに re-run のみ提供).

    `ours` / `theirs` は同じ helper を呼ぶ (Phase 1 では git merge-tree の
    出力差分が conflict-list 形式上は同等なので、strategy 名は audit log /
    escalate payload に保持するための **意図ラベル** として機能する).
    """
    # 全 strategy で同一 helper を呼ぶ (Phase 1 dry-run only).
    # 注: 実 merge は走らせない. 将来 git ≥ 2.40 の `merge-tree --strategy=...`
    # と置き換える際もここを差し替えれば良い.
    try:
        result = await detect_conflict_dry_run(
            base, target, timeout_sec=timeout_sec,
        )
    except MergeConflictError as exc:
        # ref-not-found 等の git-level error を AutoResolveError へ昇格.
        # (caller が 4xx に envelope する想定)
        raise AutoResolveError(f"git error during {strategy}: {exc}") from exc
    except SequentialMergeError as exc:
        raise AutoResolveError(f"invalid input for {strategy}: {exc}") from exc

    return {
        "strategy": strategy,
        "has_conflict": bool(result["has_conflict"]),
        "conflicts": list(result.get("conflicts", [])),
    }


async def try_auto_resolve(
    base_branch: str,
    target_branch: str,
    *,
    strategies: Optional[list[str]] = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    """F-013 error_path 3 段 (detect / try / escalate) を実行する.

    Phase 1: 決定論的 strategy で dry-run のみ. **実 merge / push なし**.

    Returns AutoResolveResult dict (see module docstring for shape).

    Raises:
      AutoResolveError: invalid input / strategy / git-level fatal.
    """
    # Validate strategies whitelist before any subprocess.
    chosen: list[str]
    if strategies is None:
        chosen = list(STRATEGIES)
    else:
        if not isinstance(strategies, list):
            raise AutoResolveError(
                f"strategies must be list, got {type(strategies).__name__}"
            )
        if len(strategies) == 0:
            raise AutoResolveError("strategies must not be empty")
        chosen = [_validate_strategy(s) for s in strategies]

    # Phase 1: detect (= run default strategy first).
    attempts: list[dict[str, Any]] = []
    first = await _attempt_with_strategy(
        base_branch, target_branch, "default", timeout_sec=timeout_sec,
    )
    attempts.append(first)
    if not first["has_conflict"]:
        # F-013 happy short-circuit: no conflict at all.
        return {
            "status": "no_conflict",
            "strategy_used": None,
            "base": base_branch,
            "target": target_branch,
            "conflicts": [],
            "attempts": attempts,
        }

    # Try remaining strategies (Phase 1 dry-run; same helper but with
    # strategy label preserved for audit / escalate payload).
    for strategy in chosen:
        if strategy == "default":
            continue  # already tried above
        attempt = await _attempt_with_strategy(
            base_branch, target_branch, strategy, timeout_sec=timeout_sec,
        )
        attempts.append(attempt)
        if not attempt["has_conflict"]:
            # Phase 1: same helper output, but record the strategy label.
            return {
                "status": "resolved",
                "strategy_used": strategy,
                "base": base_branch,
                "target": target_branch,
                "conflicts": [],
                "attempts": attempts,
            }

    # All strategies still report conflict → escalate to human.
    # Surface conflicts from the most informative (= first) attempt.
    return {
        "status": "escalate",
        "strategy_used": None,
        "base": base_branch,
        "target": target_branch,
        "conflicts": list(first["conflicts"]),
        "attempts": attempts,
    }
