"""T-009-03: 影響範囲 AI ハイライト サービス.

T-006-03 (impact_analyzer) の downstream task list に severity / suggested_action /
group-by-phase の metadata を付けて UI 用にハイライト表示するデータを生成する.

公開 API:
  - compute_highlights(report, *, tasks_meta=None) -> HighlightReport
  - HighlightedTask: severity / suggested_action / metadata
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


class ImpactHighlightError(RuntimeError):
    pass


# 重要度判定ルール
SEVERITY_RULES = {
    "high": "深 1 (直接依存) + dep_type='reports_to' or 'blocks'",
    "medium": "深 2-3 (間接依存) または dep_type='delegates_to'",
    "low": "深 4 以上 (遠い依存)",
}

# dep_type ごとの critical weight
CRITICAL_DEP_TYPES = {"reports_to", "blocks", "depends_on"}
SOFT_DEP_TYPES = {"delegates_to", "mentors", "collaborates_with"}


@dataclass
class HighlightedTask:
    task_id: int
    depth: int
    dep_type: str
    severity: str  # "high" / "medium" / "low"
    suggested_action: str  # "re-test" / "re-plan" / "notify"
    title: Optional[str] = None
    status: Optional[str] = None
    project_id: Optional[int] = None
    phase_id: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "depth": self.depth,
            "dep_type": self.dep_type,
            "severity": self.severity,
            "suggested_action": self.suggested_action,
            "title": self.title,
            "status": self.status,
            "project_id": self.project_id,
            "phase_id": self.phase_id,
        }


@dataclass
class HighlightReport:
    source_task_id: int
    total: int
    high_count: int
    medium_count: int
    low_count: int
    highlights: list[HighlightedTask] = field(default_factory=list)
    grouped_by_phase: dict = field(default_factory=dict)  # phase_id -> count
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "source_task_id": self.source_task_id,
            "total": self.total,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "low_count": self.low_count,
            "highlights": [h.to_dict() for h in self.highlights],
            "grouped_by_phase": {str(k): v for k, v in self.grouped_by_phase.items()},
            "warnings": self.warnings,
        }


# ──────────────────────────────────────────────────────────────────────────
# severity 判定
# ──────────────────────────────────────────────────────────────────────────


def _classify_severity(depth: int, dep_type: str) -> tuple[str, str]:
    """severity と suggested_action を判定."""
    dt = (dep_type or "").lower()
    if depth <= 1 and dt in CRITICAL_DEP_TYPES:
        return "high", "re-test-immediately"
    if depth <= 1:
        return "high", "re-test"
    if depth <= 3:
        if dt in CRITICAL_DEP_TYPES:
            return "medium", "re-plan"
        return "medium", "notify"
    return "low", "notify"


# ──────────────────────────────────────────────────────────────────────────
# 集約
# ──────────────────────────────────────────────────────────────────────────


def compute_highlights(
    report: dict,
    *,
    tasks_meta: Optional[dict[int, dict]] = None,
) -> HighlightReport:
    """impact report (T-006-03 の to_dict 結果) を highlight に変換する.

    tasks_meta: {task_id: {title, status, project_id, phase_id}} (Optional)
    """
    if not isinstance(report, dict):
        raise ImpactHighlightError("report must be a dict")
    source_task_id = report.get("task_id") or report.get("source_task_id")
    if not isinstance(source_task_id, int) or source_task_id <= 0:
        raise ImpactHighlightError(
            f"report.task_id must be a positive int, got {source_task_id!r}"
        )
    downstream = report.get("downstream") or []
    if not isinstance(downstream, list):
        raise ImpactHighlightError("report.downstream must be a list")

    meta = tasks_meta or {}
    highlights: list[HighlightedTask] = []
    high = medium = low = 0
    grouped_by_phase: dict[Optional[int], int] = {}

    for d in downstream:
        if not isinstance(d, dict):
            continue
        tid = d.get("task_id")
        if not isinstance(tid, int) or tid <= 0:
            continue
        depth = int(d.get("depth", 0) or 0)
        dep_type = d.get("dep_type") or "reports_to"
        severity, action = _classify_severity(depth, dep_type)
        if severity == "high":
            high += 1
        elif severity == "medium":
            medium += 1
        else:
            low += 1

        m = meta.get(tid) or {}
        task_meta_pid = m.get("project_id")
        task_meta_phase = m.get("phase_id")
        grouped_by_phase[task_meta_phase] = grouped_by_phase.get(task_meta_phase, 0) + 1

        highlights.append(HighlightedTask(
            task_id=tid,
            depth=depth,
            dep_type=dep_type,
            severity=severity,
            suggested_action=action,
            title=m.get("title"),
            status=m.get("status"),
            project_id=task_meta_pid,
            phase_id=task_meta_phase,
        ))

    # severity 順 (high → medium → low) でソート
    sev_order = {"high": 0, "medium": 1, "low": 2}
    highlights.sort(key=lambda h: (sev_order[h.severity], h.depth, h.task_id))

    return HighlightReport(
        source_task_id=source_task_id,
        total=len(highlights),
        high_count=high,
        medium_count=medium,
        low_count=low,
        highlights=highlights,
        grouped_by_phase=grouped_by_phase,
    )
