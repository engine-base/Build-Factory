"""T-008-03: phase gate 達成判定 + auto unlock サービス.

phase (フェーズ) の gate 達成条件を評価し、満たしていれば次の phase を unlock する.

Gate ルール (default):
  - min_completion_rate: 0.0..1.0  (task completed の割合)
  - required_artifact_types: list[str]  (必須 artifact type, 例: ["spec_doc", "design"])
  - required_reviewer_approvals: int    (必須 reviewer 承認数)
  - allow_partial: bool                 (True なら warn でも pass 扱い)

公開 API:
  - evaluate_gate(phase, tasks, *, rules, artifacts=None, approvals=0) -> GateEvaluation
  - auto_unlock_next(current, next_phase, *, complete_fn, start_fn) -> dict
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Iterable, Optional

logger = logging.getLogger(__name__)


class PhaseGateError(RuntimeError):
    pass


@dataclass
class GateRule:
    min_completion_rate: float = 1.0
    required_artifact_types: list[str] = field(default_factory=list)
    required_reviewer_approvals: int = 0
    allow_partial: bool = False

    def validate(self) -> None:
        if not (0.0 <= self.min_completion_rate <= 1.0):
            raise PhaseGateError(
                f"min_completion_rate must be 0.0..1.0, got {self.min_completion_rate}"
            )
        if self.required_reviewer_approvals < 0:
            raise PhaseGateError("required_reviewer_approvals must be >= 0")
        if not isinstance(self.required_artifact_types, list):
            raise PhaseGateError("required_artifact_types must be a list")


@dataclass
class GateCriterionResult:
    name: str
    expected: str
    actual: str
    status: str  # "pass" | "warn" | "fail"
    detail: str = ""


@dataclass
class GateEvaluation:
    phase_id: int
    overall: str  # "pass" | "warn" | "fail"
    completion_rate: float
    total_tasks: int
    completed_tasks: int
    blockers: list[str] = field(default_factory=list)
    criteria: list[GateCriterionResult] = field(default_factory=list)
    can_auto_unlock: bool = False

    def to_dict(self) -> dict:
        return {
            "phase_id": self.phase_id,
            "overall": self.overall,
            "completion_rate": round(self.completion_rate, 4),
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "blockers": list(self.blockers),
            "criteria": [
                {"name": c.name, "expected": c.expected, "actual": c.actual,
                 "status": c.status, "detail": c.detail}
                for c in self.criteria
            ],
            "can_auto_unlock": self.can_auto_unlock,
        }


def _completion_rate(tasks: list[dict]) -> tuple[float, int, int]:
    total = len(tasks)
    if total == 0:
        return 0.0, 0, 0
    done = sum(1 for t in tasks if (t.get("status") or "").lower() == "completed")
    return done / total, total, done


def evaluate_gate(
    phase: dict,
    tasks: list[dict],
    *,
    rules: Optional[GateRule] = None,
    artifacts: Optional[Iterable[dict]] = None,
    approvals: int = 0,
) -> GateEvaluation:
    """phase の gate 達成判定."""
    if not isinstance(phase, dict):
        raise PhaseGateError("phase must be a dict")
    phase_id = phase.get("id") or phase.get("phase_id")
    if not isinstance(phase_id, int) or phase_id <= 0:
        raise PhaseGateError(f"phase.id must be a positive int, got {phase_id!r}")
    if not isinstance(tasks, list):
        raise PhaseGateError("tasks must be a list")

    r = rules or GateRule()
    r.validate()

    rate, total, done = _completion_rate(tasks)
    criteria: list[GateCriterionResult] = []
    blockers: list[str] = []

    # 1. completion rate
    completion_status = "pass" if rate >= r.min_completion_rate else "fail"
    if completion_status == "fail":
        blockers.append(
            f"completion_rate {rate:.2%} < required {r.min_completion_rate:.2%}"
        )
    criteria.append(GateCriterionResult(
        name="completion_rate",
        expected=f">= {r.min_completion_rate:.2%}",
        actual=f"{rate:.2%}",
        status=completion_status,
        detail=f"{done}/{total} tasks completed",
    ))

    # 2. required artifact types
    if r.required_artifact_types:
        have_types = {
            (a.get("type") or "").lower() for a in (artifacts or [])
            if isinstance(a, dict)
        }
        missing = [
            t for t in r.required_artifact_types if t.lower() not in have_types
        ]
        artifact_status = "pass" if not missing else "fail"
        if missing:
            blockers.append(f"missing_artifacts: {missing}")
        criteria.append(GateCriterionResult(
            name="required_artifacts",
            expected=str(r.required_artifact_types),
            actual=str(sorted(have_types)),
            status=artifact_status,
            detail=f"missing: {missing}" if missing else "all present",
        ))

    # 3. reviewer approvals
    if r.required_reviewer_approvals > 0:
        approval_status = (
            "pass" if approvals >= r.required_reviewer_approvals else "fail"
        )
        if approval_status == "fail":
            blockers.append(
                f"approvals {approvals} < required {r.required_reviewer_approvals}"
            )
        criteria.append(GateCriterionResult(
            name="reviewer_approvals",
            expected=f">= {r.required_reviewer_approvals}",
            actual=str(approvals),
            status=approval_status,
        ))

    # overall 判定
    fail_count = sum(1 for c in criteria if c.status == "fail")
    if fail_count == 0:
        overall = "pass"
    elif r.allow_partial and fail_count == 1:
        overall = "warn"
    else:
        overall = "fail"

    return GateEvaluation(
        phase_id=phase_id,
        overall=overall,
        completion_rate=rate,
        total_tasks=total,
        completed_tasks=done,
        blockers=blockers,
        criteria=criteria,
        can_auto_unlock=(overall == "pass"),
    )


# ──────────────────────────────────────────────────────────────────────────
# Auto unlock 関連
# ──────────────────────────────────────────────────────────────────────────


CompleteFn = Callable[[int], Awaitable[dict]]
StartFn = Callable[[int], Awaitable[dict]]


async def auto_unlock_next(
    current_phase_id: int,
    next_phase_id: Optional[int],
    *,
    complete_fn: CompleteFn,
    start_fn: StartFn,
) -> dict:
    """現 phase を complete + 次 phase を start (atomic 順序実行).

    next_phase_id が None の場合は complete のみ.
    """
    if current_phase_id is None or current_phase_id <= 0:
        raise PhaseGateError("current_phase_id must be > 0")
    completed = await complete_fn(current_phase_id)
    started: Optional[dict] = None
    if next_phase_id is not None and next_phase_id > 0:
        if next_phase_id == current_phase_id:
            raise PhaseGateError(
                "next_phase_id must differ from current_phase_id"
            )
        started = await start_fn(next_phase_id)
    return {
        "completed": completed,
        "next_started": started,
    }
