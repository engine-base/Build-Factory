"""T-003-04: スキル context 注入 (CLAUDE.md ルール準拠).

スキル実行時に、Claude / AI 社員へ渡す system prompt を組み立てる.
セクション構成:
  1. CLAUDE.md §5 絶対ルール (お作法)
  2. SKILL.md 本文 (data/skills/<name>/SKILL.md)
  3. parent guideline 継承チェーン (T-003-03 連携、employee_id 指定時)
  4. (optional) Constitution (T-AI-04 連携)

公開 API:
  - load_claude_rules() -> str
  - load_skill_md(skill_name) -> str
  - inject_context(skill_name, *, employee_id=None, include_constitution=True,
                   guideline_resolver=None, constitution_loader=None) -> dict
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

# repo root を遡る (backend/services/ から 2 階層上)
REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
SKILL_STORE = REPO_ROOT / "data" / "skills"

# CLAUDE.md §5 セクション (絶対ルール) の見出し
CLAUDE_RULES_HEADING = "## 5. 絶対ルール"
CLAUDE_RULES_NEXT_HEADING_RE = re.compile(r"^## \d+\. ", re.MULTILINE)


class SkillContextError(RuntimeError):
    pass


class SkillMdNotFoundError(SkillContextError):
    pass


def load_claude_rules(claude_md_path: Optional[Path] = None) -> str:
    """CLAUDE.md §5 (絶対ルール) section だけを抽出する.

    存在しなければ空 string を返す (本番事故防止: skill 実行は止めない).
    """
    path = claude_md_path or CLAUDE_MD
    if not path.exists():
        logger.warning("CLAUDE.md not found at %s", path)
        return ""

    text = path.read_text(encoding="utf-8")
    idx = text.find(CLAUDE_RULES_HEADING)
    if idx < 0:
        return ""
    # 次の "## N. " 見出しまで切り出す
    tail = text[idx:]
    # 自分自身の見出しはスキップして次を探す
    m = CLAUDE_RULES_NEXT_HEADING_RE.search(tail, pos=len(CLAUDE_RULES_HEADING))
    if m:
        return tail[:m.start()].strip()
    return tail.strip()


def load_skill_md(skill_name: str, *, store: Optional[Path] = None) -> str:
    """data/skills/<name>/SKILL.md を読む."""
    if not skill_name or not skill_name.strip():
        raise SkillContextError("skill_name must not be empty")
    base = store or SKILL_STORE
    md = base / skill_name / "SKILL.md"
    if not md.exists():
        raise SkillMdNotFoundError(f"SKILL.md not found: {md}")
    return md.read_text(encoding="utf-8")


# 注入用 callable 型 (T-003-03 / T-AI-04 連携)
GuidelineResolver = Callable[[int], Awaitable[dict]]
ConstitutionLoader = Callable[[], Awaitable[str]]


async def inject_context(
    skill_name: str,
    *,
    employee_id: Optional[int] = None,
    include_constitution: bool = True,
    include_claude_rules: bool = True,
    guideline_resolver: Optional[GuidelineResolver] = None,
    constitution_loader: Optional[ConstitutionLoader] = None,
    claude_md_path: Optional[Path] = None,
    skill_store: Optional[Path] = None,
) -> dict:
    """skill_name に対する context block を組み立てる.

    Returns:
      {
        "skill_name": str,
        "sections": [{"title": str, "size": int, "source": str}, ...],
        "rendered": str,   # 全体を結合した system prompt
        "warnings": [str],
      }
    """
    if not skill_name or not skill_name.strip():
        raise SkillContextError("skill_name must not be empty")
    if employee_id is not None and employee_id <= 0:
        raise SkillContextError(f"employee_id must be > 0 when provided, got {employee_id}")

    sections: list[dict] = []
    parts: list[str] = []
    warnings: list[str] = []

    # 1. CLAUDE.md §5
    if include_claude_rules:
        rules = load_claude_rules(claude_md_path)
        if rules:
            sections.append({
                "title": "CLAUDE.md §5 (絶対ルール)",
                "size": len(rules),
                "source": "CLAUDE.md",
            })
            parts.append(f"## ABSOLUTE RULES (CLAUDE.md §5)\n\n{rules}")
        else:
            warnings.append("claude_rules_not_found")

    # 2. SKILL.md
    try:
        skill_md = load_skill_md(skill_name, store=skill_store)
        sections.append({
            "title": f"SKILL.md ({skill_name})",
            "size": len(skill_md),
            "source": f"data/skills/{skill_name}/SKILL.md",
        })
        parts.append(f"## SKILL DEFINITION ({skill_name})\n\n{skill_md}")
    except SkillMdNotFoundError as e:
        warnings.append(f"skill_md_not_found:{skill_name}")
        raise  # SKILL.md は必須 (router 側で 404 化)

    # 3. parent guideline 継承 (T-003-03)
    if employee_id is not None and guideline_resolver is not None:
        try:
            chain = await guideline_resolver(employee_id)
            merged = chain.get("merged_guideline") if isinstance(chain, dict) else ""
            if merged:
                sections.append({
                    "title": f"Persona chain (employee_id={employee_id})",
                    "size": len(merged),
                    "source": "ai_employees + ai_personas + ai_hierarchies",
                })
                parts.append(f"## INHERITED PERSONA GUIDELINE\n\n{merged}")
            else:
                warnings.append("persona_chain_empty")
        except Exception as e:
            warnings.append(f"persona_chain_failed:{e}")

    # 4. Constitution (T-AI-04, optional)
    if include_constitution and constitution_loader is not None:
        try:
            const_text = await constitution_loader()
            if const_text:
                sections.append({
                    "title": "Constitution (松本の判断基準)",
                    "size": len(const_text),
                    "source": "T-AI-04",
                })
                parts.append(f"## CONSTITUTION\n\n{const_text}")
            else:
                warnings.append("constitution_empty")
        except Exception as e:
            warnings.append(f"constitution_failed:{e}")

    rendered = "\n\n---\n\n".join(parts).strip()
    return {
        "skill_name": skill_name,
        "sections": sections,
        "rendered": rendered,
        "rendered_size": len(rendered),
        "warnings": warnings,
    }
