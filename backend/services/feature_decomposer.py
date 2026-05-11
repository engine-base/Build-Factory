"""T-006-01: feature-decomposition AI (Devon).

機能 1 件を独立して開発できる task の単位に分解する.
本実装は **rule-based の heuristic 分解** (LLM 統合は将来 task-decomposition skill 連携).

分解規約 (Build-Factory 標準):
  1. 全 feature は最低 3 層 (BE / FE / TST) を生成
  2. DB を含む feature は DB ステップを先頭に
  3. 各 task は独立 (deps 明示)
  4. 各 task に EARS AC を 4 件自動付与 (UBIQUITOUS/EVENT/STATE/UNWANTED)

公開 API:
  - decompose_feature(feature) -> DecompositionResult
  - DecompositionResult(.tasks, .total, .warnings)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


class FeatureDecomposerError(RuntimeError):
    pass


@dataclass
class SubTask:
    task_id: str
    title: str
    layer: str  # DB / BE / FE / TST / OPS
    description: str = ""
    deps: list[str] = field(default_factory=list)
    estimated_hours: float = 1.0
    acceptance_criteria: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "layer": self.layer,
            "description": self.description,
            "deps": list(self.deps),
            "estimated_hours": self.estimated_hours,
            "acceptance_criteria": list(self.acceptance_criteria),
        }


@dataclass
class DecompositionResult:
    feature_id: str
    feature_title: str
    tasks: list[SubTask]
    total: int
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "feature_id": self.feature_id,
            "feature_title": self.feature_title,
            "total": self.total,
            "tasks": [t.to_dict() for t in self.tasks],
            "warnings": self.warnings,
        }


# ──────────────────────────────────────────────────────────────────────────
# Heuristic 分解
# ──────────────────────────────────────────────────────────────────────────


_DB_KEYWORDS = ("テーブル", "schema", "migration", "DB", "DDL", "RLS")
_FE_KEYWORDS = ("画面", "UI", "ボタン", "Next.js", "shadcn", "React", "Tailwind")
_INT_KEYWORDS = ("連携", "webhook", "Slack", "MCP", "OAuth", "外部 API")


def _build_ears_ac(feature_id: str, task_id: str, layer: str) -> list[dict]:
    """T-005-03 で確立した 4 AC を自動生成."""
    return [
        {"type": "UBIQUITOUS",
         "text": (
             f"The system shall implement {task_id} ({layer}) "
             f"as specified by feature {feature_id}."
         )},
        {"type": "EVENT-DRIVEN",
         "text": (
             f"When the relevant API endpoint or service function is invoked for {task_id}, "
             f"the system shall return a structured response "
             f"(success or {{detail: {{code, message}}}}) within 2 seconds."
         )},
        {"type": "STATE-DRIVEN",
         "text": (
             f"While the new feature for {task_id} is enabled, "
             f"the system shall apply Row Level Security and audit_logs "
             f"as per CLAUDE.md §5.3."
         )},
        {"type": "UNWANTED",
         "text": (
             f"If invalid input or unauthorized actor is detected during {task_id}, "
             f"the system shall reject the request with a 4xx response "
             f"carrying {{detail: {{code, message}}}} "
             f"and shall not mutate persistent state."
         )},
    ]


def _detect_layers(text: str) -> list[str]:
    """feature 説明文から必要な layer を推定."""
    layers: list[str] = []
    if any(k in text for k in _DB_KEYWORDS):
        layers.append("DB")
    # 常に BE / FE / TST は付ける
    if "BE" not in layers:
        layers.append("BE")
    if any(k in text for k in _FE_KEYWORDS) or "BE" in layers:
        layers.append("FE")
    if any(k in text for k in _INT_KEYWORDS):
        layers.append("OPS")
    layers.append("TST")
    # 重複除去 + 順序保持
    seen: set[str] = set()
    ordered: list[str] = []
    for l in layers:
        if l not in seen:
            ordered.append(l)
            seen.add(l)
    return ordered


def _layer_hours(layer: str) -> float:
    return {
        "DB": 1.5,
        "BE": 2.0,
        "FE": 2.0,
        "OPS": 1.0,
        "TST": 1.0,
    }.get(layer, 1.0)


def decompose_feature(
    feature: dict,
    *,
    title_max_len: int = 200,
    description_max_len: int = 4000,
) -> DecompositionResult:
    """feature dict を独立 task に分解する.

    feature = {
      "id": "F-006",                # 必須
      "title": "機能タイトル",       # 必須
      "description": "...",          # 任意
    }
    """
    if not isinstance(feature, dict):
        raise FeatureDecomposerError("feature must be a dict")
    feature_id = (feature.get("id") or "").strip()
    title = (feature.get("title") or "").strip()
    description = (feature.get("description") or "").strip()
    if not feature_id:
        raise FeatureDecomposerError("feature.id must not be empty")
    if not title:
        raise FeatureDecomposerError("feature.title must not be empty")
    if len(title) > title_max_len:
        raise FeatureDecomposerError(f"title must be <= {title_max_len} chars")
    if len(description) > description_max_len:
        raise FeatureDecomposerError(
            f"description must be <= {description_max_len} chars"
        )

    warnings: list[str] = []
    layers = _detect_layers(title + "\n" + description)
    if not description:
        warnings.append("description_empty")

    tasks: list[SubTask] = []
    prev_id: Optional[str] = None
    for i, layer in enumerate(layers, 1):
        task_id = f"{feature_id}-T{i:02d}-{layer}"
        deps: list[str] = []
        # 単純な直列依存 (前 layer が完了してから次)
        # ただし FE は BE 完了後、TST は他 layer 全て完了後
        if layer == "BE" and "DB" in [t.layer for t in tasks]:
            deps = [t.task_id for t in tasks if t.layer == "DB"]
        elif layer == "FE":
            deps = [t.task_id for t in tasks if t.layer == "BE"]
        elif layer == "OPS":
            deps = [t.task_id for t in tasks if t.layer == "BE"]
        elif layer == "TST":
            deps = [t.task_id for t in tasks]  # 全 layer 完了後
        sub = SubTask(
            task_id=task_id,
            title=f"{title} — {layer} 部分",
            layer=layer,
            description=description[:500] or f"{layer} 部分の実装",
            deps=deps,
            estimated_hours=_layer_hours(layer),
            acceptance_criteria=_build_ears_ac(feature_id, task_id, layer),
        )
        tasks.append(sub)
        prev_id = task_id

    if len(tasks) < 3:
        warnings.append("less_than_3_layers")

    return DecompositionResult(
        feature_id=feature_id,
        feature_title=title,
        tasks=tasks,
        total=len(tasks),
        warnings=warnings,
    )
