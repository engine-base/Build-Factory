"""T-003-03: parent guideline 継承 (AI 社員階層).

ai_employees + ai_personas + ai_hierarchies を読み、
parent → child のチェーンに沿って persona / guideline を継承する.

公開 API:
  - build_chain(employee_id, *, hierarchy_loader, persona_loader) -> list[PersonaSnapshot]
  - merge_guidelines(chain) -> str
  - resolve_guideline(employee_id, ...) -> dict[chain, merged_text]

`hierarchy_loader` / `persona_loader` を注入することで DB 接続なしでテスト可能.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Iterable, Optional

logger = logging.getLogger(__name__)


class GuidelineInheritanceError(RuntimeError):
    """guideline 解決エラー."""


class EmployeeNotFoundError(GuidelineInheritanceError):
    """employee_id が ai_employees に存在しない."""


class CycleDetectedError(GuidelineInheritanceError):
    """ai_hierarchies に循環があり root に到達できない."""


@dataclass
class PersonaSnapshot:
    """継承解決時の persona 情報スナップショット."""

    employee_id: int
    employee_key: str
    persona_key: Optional[str] = None
    persona_name: Optional[str] = None
    personality: Optional[str] = None
    tone_style: Optional[str] = None
    specialty: Optional[str] = None
    guideline_text: str = ""  # constitution / role rule (free text)
    depth: int = 0  # 0 = root


# 注入用 loader 型
HierarchyLoader = Callable[[int], Awaitable[Optional[int]]]   # child_id -> parent_id (or None)
PersonaLoader = Callable[[int], Awaitable[Optional[PersonaSnapshot]]]


MAX_DEPTH = 10


async def build_chain(
    employee_id: int,
    *,
    hierarchy_loader: HierarchyLoader,
    persona_loader: PersonaLoader,
    max_depth: int = MAX_DEPTH,
) -> list[PersonaSnapshot]:
    """employee_id から root まで遡って persona snapshot のリストを返す.

    Returns: [root, ..., leaf] の順序.
    """
    if employee_id <= 0:
        raise GuidelineInheritanceError(f"employee_id must be > 0, got {employee_id}")

    visited: set[int] = set()
    rev_chain: list[PersonaSnapshot] = []  # leaf -> root の順で集める
    current: Optional[int] = employee_id
    depth = 0

    while current is not None and depth < max_depth:
        if current in visited:
            raise CycleDetectedError(
                f"cycle detected in ai_hierarchies: revisited employee_id={current}"
            )
        visited.add(current)

        snap = await persona_loader(current)
        if snap is None:
            if depth == 0:
                raise EmployeeNotFoundError(f"employee_id={current} not found")
            # 中間 ancestor が存在しないのは hierarchy 不整合だがチェーンは打ち切る
            logger.warning("ancestor employee_id=%s not found, truncating chain", current)
            break
        snap.depth = depth
        rev_chain.append(snap)
        parent_id = await hierarchy_loader(current)
        current = parent_id
        depth += 1

    if depth >= max_depth and current is not None:
        raise CycleDetectedError(
            f"chain depth exceeds max_depth={max_depth} (possible cycle)"
        )

    # depth は leaf=0 / root=len-1 で記録されているので reverse して
    # snap.depth を root=0 に振り直す
    rev_chain.reverse()
    for i, snap in enumerate(rev_chain):
        snap.depth = i
    return rev_chain


def merge_guidelines(chain: Iterable[PersonaSnapshot]) -> str:
    """root → leaf 順で guideline を結合する.

    各 ancestor の guideline_text を改行で区切って 1 つの prompt にまとめる.
    """
    parts: list[str] = []
    for snap in chain:
        if not snap.guideline_text:
            continue
        header = f"# [depth={snap.depth}] {snap.employee_key}"
        if snap.persona_key:
            header += f" / {snap.persona_key}"
        parts.append(f"{header}\n{snap.guideline_text.strip()}")
    return "\n\n".join(parts).strip()


async def resolve_guideline(
    employee_id: int,
    *,
    hierarchy_loader: HierarchyLoader,
    persona_loader: PersonaLoader,
    max_depth: int = MAX_DEPTH,
) -> dict:
    """employee_id の継承された guideline を解決して返す."""
    chain = await build_chain(
        employee_id,
        hierarchy_loader=hierarchy_loader,
        persona_loader=persona_loader,
        max_depth=max_depth,
    )
    merged = merge_guidelines(chain)
    return {
        "employee_id": employee_id,
        "chain_depth": len(chain),
        "chain": [
            {
                "depth": s.depth,
                "employee_id": s.employee_id,
                "employee_key": s.employee_key,
                "persona_key": s.persona_key,
                "persona_name": s.persona_name,
                "tone_style": s.tone_style,
                "specialty": s.specialty,
            }
            for s in chain
        ],
        "merged_guideline": merged,
    }
