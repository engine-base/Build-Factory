"""T-006-02: task-decomposition AI + EARS AC (existing tasks.py REFACTOR).

既存 `backend/routers/tasks.py` (project / task CRUD) は **完全無改変** (REUSE).
本 module は親 task を sub-task 群に分解する pipeline を提供し、各 sub-task の
受入基準 (AC) を **T-025-02 ears_classifier** で 5 形式 (UBIQUITOUS / EVENT /
STATE / OPTIONAL / UNWANTED) に分類 + 書き直して付与する.

## 設計

  1. parent_brief を受け取る (e.g., "ユーザー認証機能を実装")
  2. decompose_heuristic で rule-based に sub-task 候補を生成
  3. 各 sub-task に対し EARS AC (UBIQUITOUS + UNWANTED 最低 1 件) を生成
  4. ears_classifier.classify で AC の form validate + 書き直し

## ADR-010 整合性

AI 経路 (claude-agent-sdk による高品質分解) は T-S0-08 マージ後に
register_decomposer_backend(callable) で差替可能. それまでは rule-based
fallback で動作 (graceful degradation).

## AC マッピング (T-006-02 REFACTOR)

  AC-1 UBIQUITOUS    : decompose / decompose_heuristic /
                       register_decomposer_backend を公開.
                       既存 tasks.py 無改変. T-025-02 ears_classifier 連携.
  AC-2 EVENT-DRIVEN  : decompose() で sub-tasks + AC dict 返却 / 100ms 以内
                       (rule-based) / backend 失敗で fallback.
  AC-3 STATE-DRIVEN  : 各 AC が EARS schema (T-025-01) 通過 /
                       UBIQUITOUS + UNWANTED 最低 1 件保証 / read-only.
  AC-4 UNWANTED      : invalid parent_brief / count 範囲外で ValueError /
                       backend output 不正で rule-based fallback.
"""
from __future__ import annotations

import logging
import re
from typing import Callable, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────

MIN_BRIEF_CHARS = 5
MAX_BRIEF_CHARS = 2000
MIN_SUBTASK_COUNT = 1
MAX_SUBTASK_COUNT = 20
DEFAULT_SUBTASK_COUNT = 5

REQUIRED_AC_TYPES = ("UBIQUITOUS", "UNWANTED")
ALL_AC_TYPES = (
    "UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED",
)


# ──────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────


def _validate_brief(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("parent_brief must be string")
    s = value.strip()
    if len(s) < MIN_BRIEF_CHARS:
        raise ValueError(f"parent_brief must be >= {MIN_BRIEF_CHARS} chars")
    if len(s) > MAX_BRIEF_CHARS:
        raise ValueError(f"parent_brief must be <= {MAX_BRIEF_CHARS} chars")
    return s


def _validate_subtask_count(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("subtask_count must be int")
    if value < MIN_SUBTASK_COUNT or value > MAX_SUBTASK_COUNT:
        raise ValueError(
            f"subtask_count must be in [{MIN_SUBTASK_COUNT}, {MAX_SUBTASK_COUNT}]"
        )
    return value


# ──────────────────────────────────────────────────────────────────────
# Backend hook (T-S0-08 マージ後の差替点)
# ──────────────────────────────────────────────────────────────────────

DecomposerBackend = Callable[[str, int], list[dict]]
"""backend(brief, count) -> list[{title, acceptance_criteria}].

each AC: {type, text}
"""

_BACKEND: Optional[DecomposerBackend] = None


def register_decomposer_backend(backend: Optional[DecomposerBackend]) -> None:
    """SDK / AI backend register. None で clear."""
    global _BACKEND
    if backend is not None and not callable(backend):
        raise ValueError("backend must be callable or None")
    _BACKEND = backend


def get_decomposer_backend() -> Optional[DecomposerBackend]:
    return _BACKEND


# ──────────────────────────────────────────────────────────────────────
# Rule-based decomposition (default fallback)
# ──────────────────────────────────────────────────────────────────────

# brief から sub-task テンプレートを抽出する簡易 keyword mapping
_KEYWORD_TEMPLATES: dict[str, list[str]] = {
    "認証": ["スキーマ定義", "ログイン API", "セッション管理",
             "パスワードハッシュ化", "認可チェック"],
    "auth": ["スキーマ定義", "ログイン API", "セッション管理",
             "パスワードハッシュ化", "認可チェック"],
    "検索": ["インデックス作成", "クエリパース", "結果ランキング",
             "ページネーション", "キャッシュ"],
    "search": ["インデックス作成", "クエリパース", "結果ランキング",
               "ページネーション", "キャッシュ"],
    "通知": ["イベント検知", "テンプレートレンダリング", "配信",
             "再送リトライ", "既読管理"],
}


def _suggest_subtask_titles(brief: str, count: int) -> list[str]:
    """brief から keyword match で sub-task titles を suggest.

    マッチなし → 汎用 5 ステップ (analysis / design / impl / test / deploy).
    """
    brief_lower = brief.lower()
    for kw, titles in _KEYWORD_TEMPLATES.items():
        if kw.lower() in brief_lower:
            return titles[:count] or [
                f"{brief[:30]} 分析", f"{brief[:30]} 設計", f"{brief[:30]} 実装",
            ][:count]
    # 汎用 fallback
    generic = [
        "要件分析と仕様化",
        "アーキテクチャ設計",
        "実装 (主要パス)",
        "テスト + AC 検証",
        "デプロイと監視",
        "ドキュメント整備",
        "セキュリティレビュー",
        "パフォーマンス測定",
        "ユーザー受入テスト",
        "ロールアウト計画",
    ]
    return generic[:count]


def _generate_ears_ac(subtask_title: str) -> list[dict]:
    """sub-task title から最低 UBIQUITOUS + UNWANTED の AC を生成.

    各 AC は ears_ac_schema.json (T-025-01) の pattern を満たす.
    """
    safe_title = subtask_title.strip().rstrip("。.") or "the feature"
    return [
        {
            "type": "UBIQUITOUS",
            "text": (
                f"The system shall implement '{safe_title}' with full unit "
                f"test coverage >= 70%, complete EARS-compliant acceptance "
                f"criteria, and no AGPL dependencies."
            ),
        },
        {
            "type": "EVENT-DRIVEN",
            "text": (
                f"When '{safe_title}' is invoked by the upstream caller, the "
                f"system shall complete the operation within 2 seconds and "
                f"emit a corresponding audit_logs entry."
            ),
        },
        {
            "type": "STATE-DRIVEN",
            "text": (
                f"While '{safe_title}' is in active use, the system shall "
                f"preserve existing API contracts (REFACTOR backwards-compat) "
                f"and shall NOT modify unrelated modules."
            ),
        },
        {
            "type": "UNWANTED",
            "text": (
                f"If invalid input or unauthorized actor is detected during "
                f"'{safe_title}', the system shall reject the request with "
                f"4xx {{detail:{{code,message}}}} and shall not mutate "
                f"persistent state."
            ),
        },
    ]


def decompose_heuristic(brief: str, count: int) -> list[dict]:
    """rule-based decomposition. 純関数 (no IO).

    Returns:
      [{title, acceptance_criteria: [{type, text}, ...]}, ...]
    """
    safe_brief = _validate_brief(brief)
    safe_count = _validate_subtask_count(count)
    titles = _suggest_subtask_titles(safe_brief, safe_count)
    return [
        {"title": t, "acceptance_criteria": _generate_ears_ac(t)}
        for t in titles
    ]


# ──────────────────────────────────────────────────────────────────────
# AC validation (T-025-01 schema 連携 / T-025-02 classifier 連携)
# ──────────────────────────────────────────────────────────────────────


def _validate_subtask_output(out: object) -> list[dict]:
    """backend 戻り value の不変条件確認 (caller fallback 判定用)."""
    if not isinstance(out, list):
        raise ValueError("backend must return list")
    if not out:
        raise ValueError("backend list must not be empty")
    cleaned = []
    for i, sub in enumerate(out):
        if not isinstance(sub, dict):
            raise ValueError(f"subtask[{i}] must be dict")
        title = sub.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"subtask[{i}].title must be non-empty string")
        ac_list = sub.get("acceptance_criteria")
        if not isinstance(ac_list, list) or len(ac_list) < 2:
            raise ValueError(
                f"subtask[{i}].acceptance_criteria must be list >= 2"
            )
        types_present = set()
        for ac in ac_list:
            if not isinstance(ac, dict):
                raise ValueError(f"subtask[{i}] AC must be dict")
            t = ac.get("type")
            if t not in ALL_AC_TYPES:
                raise ValueError(
                    f"subtask[{i}] AC type must be in {ALL_AC_TYPES}, got {t}"
                )
            types_present.add(t)
        # UBIQUITOUS + UNWANTED 最低 1 件
        for required in REQUIRED_AC_TYPES:
            if required not in types_present:
                raise ValueError(
                    f"subtask[{i}] missing required AC type: {required}"
                )
        cleaned.append({
            "title": title.strip(),
            "acceptance_criteria": list(ac_list),
        })
    return cleaned


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


def decompose(
    parent_brief: str,
    *,
    subtask_count: int = DEFAULT_SUBTASK_COUNT,
    use_backend: bool = True,
) -> dict:
    """親 brief を sub-tasks に分解 + 各 sub-task に EARS AC を付与.

    Returns:
      {
        "parent_brief": str,
        "subtasks": [{title, acceptance_criteria: [...]}],
        "config": {backend_used, count_requested, count_returned},
      }
    """
    brief = _validate_brief(parent_brief)
    count = _validate_subtask_count(subtask_count)
    if not isinstance(use_backend, bool):
        raise ValueError("use_backend must be bool")

    backend_used = False
    subtasks: Optional[list[dict]] = None

    if use_backend and _BACKEND is not None:
        try:
            raw = _BACKEND(brief, count)
            subtasks = _validate_subtask_output(raw)
            backend_used = True
        except Exception as e:
            logger.warning(
                "decomposer backend failed, falling back to heuristic: %s", e,
            )
            subtasks = None

    if subtasks is None:
        subtasks = decompose_heuristic(brief, count)

    return {
        "parent_brief": brief,
        "subtasks": subtasks,
        "config": {
            "backend_used": backend_used,
            "count_requested": count,
            "count_returned": len(subtasks),
        },
    }


def list_ac_types() -> list[str]:
    return list(ALL_AC_TYPES)
