"""T-011-04: 統合テスト指揮 AI (integration test conductor).

BMAD reviewer (quinn) workflow の最終ピース. 複数 target (task / feature) の
統合テストを deterministic topological 順序で実行し、 fail を T-011-02
reviewer_turn_counter に流して 4 連続失敗で escalation する.

設計境界 (NEW タスク, IMPLEMENTATION_PROTOCOL Step 4):
  - process-local dict のみ (no DB / no Redis).
  - 既存 reviewer_loop / reviewer_persona / reviewer_turn_counter は
    完全無改変 (REUSE invariant).
  - SECTION_KEYS / REVIEW_DIMENSIONS / PERSONA_NAME を再定義しない
    (G15 cross-module invariant).

## 公開 API

  - add_target(target_id, *, deps=(), actor_user_id=None) -> dict
  - record_result(target_id, status, *, output=None, actor_user_id=None) -> dict
  - run_pipeline(*, actor_user_id=None) -> dict
        {ran:int, pending:int, blocked:int, order:list[str]}
  - get_state(target_id) -> dict | None
  - get_summary() -> dict
        {total, pending, running, passed, failed, skipped, escalated}
  - reset(target_id) -> bool
  - reset_all_state() -> None       (test cleanup 用)
  - MAX_TARGETS = 500
  - MAX_TARGET_ID_LEN = 200
  - VALID_STATUSES = ('pending', 'running', 'pass', 'fail', 'skipped')
  - IntegrationTestConductorError   (router で 4xx に変換)

## ADR-010 整合

  - LangGraph / LangChain なし.
  - SDK auto 機能を再実装しない. 純粋 in-memory orchestration.

## fail → escalation 統合 (REUSE T-011-02)

  record_result(target_id, 'fail') が呼ばれた時点で
  reviewer_turn_counter.increment(target_id) を呼び、 escalate=True
  (count > 3) を target state に転記する.

## AC マッピング (T-011-04 NEW)

  AC-1 UBIQUITOUS    : 公開 12 symbol + router + REUSE invariant.
  AC-2 EVENT-DRIVEN  : run_pipeline 2 秒以内 / deterministic topological /
                       fail → reviewer_turn_counter.increment.
  AC-3 STATE-DRIVEN  : process-local dict / no DB / GET request mutate なし /
                       SECTION_KEYS / REVIEW_DIMENSIONS / PERSONA_NAME
                       再定義禁止.
  AC-4 UNWANTED      : invalid input / 不明 deps / cycle / overflow MAX_TARGETS
                       で IntegrationTestConductorError + state unchanged.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Iterable, Optional

from services import reviewer_turn_counter as rtc

logger = logging.getLogger(__name__)


class IntegrationTestConductorError(RuntimeError):
    """conductor の入力 / 不変条件違反 (router で 4xx に変換)."""


# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────

MAX_TARGETS = 500
MAX_TARGET_ID_LEN = 200
MAX_DEPS = 50              # 1 target 当たりの直接依存
MAX_OUTPUT_LEN = 10_000    # 1 result の output 文字列上限
MAX_ACTOR_USER_ID_LEN = 200

VALID_STATUSES: tuple[str, ...] = (
    "pending",
    "running",
    "pass",
    "fail",
    "skipped",
)


# ──────────────────────────────────────────────────────────────────────
# Process-local state
# ──────────────────────────────────────────────────────────────────────

_LOCK = threading.RLock()
_TARGETS: dict[str, dict[str, Any]] = {}


def reset_all_state() -> None:
    """test cleanup 用 (production code では呼ばない)."""
    with _LOCK:
        _TARGETS.clear()


# ──────────────────────────────────────────────────────────────────────
# Validation (AC-4 UNWANTED)
# ──────────────────────────────────────────────────────────────────────


def _validate_target_id(target_id: Any) -> str:
    if not isinstance(target_id, str):
        raise IntegrationTestConductorError("target_id must be string")
    s = target_id.strip()
    if not s:
        raise IntegrationTestConductorError("target_id must not be empty")
    if len(s) > MAX_TARGET_ID_LEN:
        raise IntegrationTestConductorError(
            f"target_id must be <= {MAX_TARGET_ID_LEN} chars"
        )
    return s


def _validate_status(status: Any) -> str:
    if not isinstance(status, str):
        raise IntegrationTestConductorError("status must be string")
    if status not in VALID_STATUSES:
        raise IntegrationTestConductorError(
            f"status must be one of {VALID_STATUSES}, got {status!r}"
        )
    return status


def _validate_deps(deps: Any) -> tuple[str, ...]:
    if deps is None:
        return ()
    if not isinstance(deps, (list, tuple)):
        raise IntegrationTestConductorError("deps must be list or tuple")
    if len(deps) > MAX_DEPS:
        raise IntegrationTestConductorError(
            f"deps count must be <= {MAX_DEPS}"
        )
    out: list[str] = []
    for d in deps:
        out.append(_validate_target_id(d))
    return tuple(out)


def _validate_output(output: Any) -> Optional[str]:
    if output is None:
        return None
    if not isinstance(output, str):
        raise IntegrationTestConductorError("output must be string or null")
    if len(output) > MAX_OUTPUT_LEN:
        raise IntegrationTestConductorError(
            f"output must be <= {MAX_OUTPUT_LEN} chars"
        )
    return output


def _validate_actor_user_id(actor_user_id: Optional[str]) -> Optional[str]:
    if actor_user_id is None:
        return None
    if not isinstance(actor_user_id, str):
        raise IntegrationTestConductorError(
            "actor_user_id must be string or null"
        )
    s = actor_user_id.strip()
    if not s:
        raise IntegrationTestConductorError(
            "actor_user_id must not be empty when provided"
        )
    if len(s) > MAX_ACTOR_USER_ID_LEN:
        raise IntegrationTestConductorError(
            f"actor_user_id must be <= {MAX_ACTOR_USER_ID_LEN} chars"
        )
    return s


# ──────────────────────────────────────────────────────────────────────
# Public API: write
# ──────────────────────────────────────────────────────────────────────


def add_target(
    target_id: str,
    *,
    deps: Optional[Iterable[str]] = None,
    actor_user_id: Optional[str] = None,
) -> dict[str, Any]:
    """target を登録する. 既に存在する target_id を再登録すると上書き.

    Returns:
      {target_id, status, deps:tuple[str], registered_at, ...}
    """
    tid = _validate_target_id(target_id)
    dep_tuple = _validate_deps(list(deps) if deps else None)
    _validate_actor_user_id(actor_user_id)

    with _LOCK:
        # AC-4 UNWANTED: 不明 deps を弾く
        for d in dep_tuple:
            if d not in _TARGETS and d != tid:
                raise IntegrationTestConductorError(
                    f"unknown dep: {d} (register it before adding {tid})"
                )
        # AC-4 UNWANTED: overflow MAX_TARGETS
        if tid not in _TARGETS and len(_TARGETS) >= MAX_TARGETS:
            raise IntegrationTestConductorError(
                f"target count would exceed MAX_TARGETS={MAX_TARGETS}"
            )
        # AC-4 UNWANTED: self loop は禁止
        if tid in dep_tuple:
            raise IntegrationTestConductorError(
                f"self-dependency: {tid}"
            )
        now = time.time()
        existing = _TARGETS.get(tid)
        _TARGETS[tid] = {
            "target_id": tid,
            "status": "pending",
            "deps": dep_tuple,
            "output": None,
            "registered_at": existing.get("registered_at", now) if existing else now,
            "updated_at": now,
            "escalated": False,
            "fail_count": 0,
        }
        # 既存 target を上書きしたが、ここまでで cycle 検出
        if _has_cycle():
            # rollback
            if existing is None:
                _TARGETS.pop(tid, None)
            else:
                _TARGETS[tid] = existing
            raise IntegrationTestConductorError(
                f"cycle detected: adding {tid} with deps {dep_tuple} forms a cycle"
            )
        return _serialize(_TARGETS[tid])


def record_result(
    target_id: str,
    status: str,
    *,
    output: Optional[str] = None,
    actor_user_id: Optional[str] = None,
) -> dict[str, Any]:
    """target の status を更新.

    status='fail' の場合 reviewer_turn_counter.increment を呼び、
    fail_count / escalated を更新する (T-011-02 連携 / AC-2).
    """
    tid = _validate_target_id(target_id)
    st = _validate_status(status)
    out = _validate_output(output)
    _validate_actor_user_id(actor_user_id)

    with _LOCK:
        if tid not in _TARGETS:
            raise IntegrationTestConductorError(
                f"target not found: {tid} (add_target first)"
            )
        entry = _TARGETS[tid]
        entry["status"] = st
        entry["output"] = out
        entry["updated_at"] = time.time()

        if st == "fail":
            # T-011-02 REUSE: 4 連続失敗で escalation
            try:
                rtc_state = rtc.increment(tid)
                entry["fail_count"] = rtc_state["count"]
                entry["escalated"] = rtc_state["escalate"]
            except rtc.ReviewerTurnCounterError as e:
                # turn counter 失敗は warn してそのまま継続 (silent drop しない)
                logger.warning(
                    "reviewer_turn_counter.increment failed for %s: %s",
                    tid, e,
                )
        return _serialize(entry)


def run_pipeline(
    *,
    actor_user_id: Optional[str] = None,
) -> dict[str, Any]:
    """topological 順序を計算し、 status='pending' の target を 'ready' 順に
    並べた order を返す (実行自体は呼び出し側に委ねる: conductor は
    deterministic 並びを提供する責務).

    Returns:
      {ran:0, pending:int, blocked:int, order:list[str]}

    実装ノート:
      conductor 自体は test 実行を行わない (sandbox / runner の責務).
      本 method は「次に走らせるべき target の deterministic 順」を返し、
      呼び出し側が record_result でフィードバックする contract.
    """
    _validate_actor_user_id(actor_user_id)

    with _LOCK:
        order = _topological_order()
        pending_ids = [
            tid for tid in order
            if _TARGETS[tid]["status"] in ("pending", "running")
        ]
        # blocked = pending かつ deps に fail / blocked がある
        blocked: list[str] = []
        for tid in pending_ids:
            for d in _TARGETS[tid]["deps"]:
                dep_status = _TARGETS[d]["status"] if d in _TARGETS else "pending"
                if dep_status in ("fail", "skipped"):
                    blocked.append(tid)
                    break
        return {
            "ran": 0,    # conductor は実行を行わない (sandbox 委譲)
            "pending": len(pending_ids),
            "blocked": len(blocked),
            "order": list(order),
        }


def reset(target_id: str) -> bool:
    """target を state から削除. 存在しなければ False."""
    tid = _validate_target_id(target_id)
    with _LOCK:
        return _TARGETS.pop(tid, None) is not None


# ──────────────────────────────────────────────────────────────────────
# Public API: read
# ──────────────────────────────────────────────────────────────────────


def get_state(target_id: str) -> Optional[dict[str, Any]]:
    tid = _validate_target_id(target_id)
    with _LOCK:
        entry = _TARGETS.get(tid)
        return _serialize(entry) if entry else None


def get_summary() -> dict[str, Any]:
    """全 target の status カウントを返す (read-only)."""
    with _LOCK:
        counts = {st: 0 for st in VALID_STATUSES}
        escalated = 0
        for entry in _TARGETS.values():
            counts[entry["status"]] = counts.get(entry["status"], 0) + 1
            if entry.get("escalated"):
                escalated += 1
        return {
            "total": len(_TARGETS),
            "pending": counts["pending"],
            "running": counts["running"],
            "passed": counts["pass"],
            "failed": counts["fail"],
            "skipped": counts["skipped"],
            "escalated": escalated,
        }


# ──────────────────────────────────────────────────────────────────────
# Internal: topological order + cycle detection
# ──────────────────────────────────────────────────────────────────────


def _topological_order() -> list[str]:
    """deterministic Kahn's algorithm. tie-breaker は target_id asc."""
    in_degree: dict[str, int] = {tid: 0 for tid in _TARGETS}
    for tid, entry in _TARGETS.items():
        for d in entry["deps"]:
            if d in in_degree:
                in_degree[tid] += 1
    ready = sorted([t for t, d in in_degree.items() if d == 0])
    out: list[str] = []
    while ready:
        cur = ready.pop(0)
        out.append(cur)
        # 自分に依存している target の in_degree を 1 減らす
        next_ready: list[str] = []
        for tid, entry in _TARGETS.items():
            if tid in out or tid in ready:
                continue
            if cur in entry["deps"]:
                in_degree[tid] -= 1
                if in_degree[tid] == 0:
                    next_ready.append(tid)
        ready.extend(sorted(next_ready))
        ready = sorted(set(ready) - set(out))
    return out


def _has_cycle() -> bool:
    """全 target を topological で並べたとき出力数が target 数と異なれば cycle."""
    ordered = _topological_order()
    return len(ordered) != len(_TARGETS)


def _serialize(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_id": entry["target_id"],
        "status": entry["status"],
        "deps": list(entry["deps"]),
        "output": entry.get("output"),
        "registered_at": entry["registered_at"],
        "updated_at": entry["updated_at"],
        "escalated": entry.get("escalated", False),
        "fail_count": entry.get("fail_count", 0),
    }
