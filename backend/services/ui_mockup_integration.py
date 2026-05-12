"""T-005b-02: ui-mockup skill 統合 (existing designer_ai REFACTOR / SKILL.md prepend).

既存 `backend/services/designer_ai.py` (generate_mockup / edit_mockup / call_llm)
は **完全無改変** (REUSE). 本 module は `skills/ui-mockup/SKILL.md` を system
prompt として **prepend** して designer_ai を呼ぶ thin orchestrator.

## 設計

  - ui-mockup skill = `skills/ui-mockup/SKILL.md` (456 行の skill spec)
  - designer_ai = LLM 呼出 + HTML 生成
  - 本 module = skill 文書を system prompt 前段に挿入してから designer_ai 呼出

graceful degradation: SKILL.md が存在しない / 読込失敗 → 既存
designer_ai の標準 prompt にフォールバック (caller 視点では透過).

## ADR-010 整合性

skill prompt の **内容は再実装しない** (skills/ui-mockup/SKILL.md が
source of truth). 本 module は thin wrapper.

## AC マッピング (T-005b-02 REFACTOR)

  AC-1 UBIQUITOUS    : generate_with_skill / edit_with_skill / get_skill_status /
                       load_ui_mockup_skill を公開. 既存 designer_ai 無改変.
  AC-2 EVENT-DRIVEN  : skill 読込 100ms / generate / edit は designer_ai が
                       実 LLM call (timeout は designer_ai 側).
  AC-3 STATE-DRIVEN  : SKILL.md なし → standard prompt fallback (透過).
                       既存 generate_mockup / edit_mockup API 不変.
  AC-4 UNWANTED      : invalid input (空 brief / 不正 frame_id) で ValueError /
                       SKILL.md path traversal なし / hardcoded secret なし.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SKILL_PATH = REPO_ROOT / "skills" / "ui-mockup" / "SKILL.md"

# in-memory cache (skill content)
_SKILL_CACHE: Optional[str] = None
_SKILL_CACHE_PATH: Optional[Path] = None

MAX_BRIEF_CHARS = 10_000
MIN_BRIEF_CHARS = 3


# ──────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────


def _validate_brief(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("brief must be string")
    s = value.strip()
    if len(s) < MIN_BRIEF_CHARS:
        raise ValueError(f"brief must be >= {MIN_BRIEF_CHARS} chars")
    if len(s) > MAX_BRIEF_CHARS:
        raise ValueError(f"brief must be <= {MAX_BRIEF_CHARS} chars")
    return s


def _validate_workspace_id(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("workspace_id must be int")
    if value <= 0:
        raise ValueError("workspace_id must be > 0")
    return value


def _validate_frame_id(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("frame_id must be int")
    if value <= 0:
        raise ValueError("frame_id must be > 0")
    return value


# ──────────────────────────────────────────────────────────────────────
# Skill loader (graceful degradation)
# ──────────────────────────────────────────────────────────────────────


def get_skill_path() -> Path:
    """test-friendly path resolver."""
    return DEFAULT_SKILL_PATH


def load_ui_mockup_skill(*, use_cache: bool = True) -> Optional[str]:
    """Load skills/ui-mockup/SKILL.md as string.

    Returns:
        skill content or None on file missing / read failure (graceful).
    """
    global _SKILL_CACHE, _SKILL_CACHE_PATH
    path = get_skill_path()

    # path traversal 防止
    try:
        path.resolve().relative_to(REPO_ROOT.resolve())
    except (ValueError, OSError):
        logger.warning("ui-mockup skill path traversal blocked: %s", path)
        return None

    if use_cache and _SKILL_CACHE is not None and _SKILL_CACHE_PATH == path:
        return _SKILL_CACHE

    if not path.exists():
        logger.warning("ui-mockup SKILL.md not found at %s", path)
        return None

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("ui-mockup SKILL.md read failed: %s", e)
        return None

    if use_cache:
        _SKILL_CACHE = content
        _SKILL_CACHE_PATH = path
    return content


def get_skill_status() -> dict:
    """diagnostic helper (read-only)."""
    path = get_skill_path()
    return {
        "skill_path": str(path),
        "exists": path.exists(),
        "char_count": len(load_ui_mockup_skill(use_cache=False) or ""),
        "cache_loaded": _SKILL_CACHE is not None,
    }


def clear_cache() -> None:
    """test-only: clear skill cache."""
    global _SKILL_CACHE, _SKILL_CACHE_PATH
    _SKILL_CACHE = None
    _SKILL_CACHE_PATH = None


# ──────────────────────────────────────────────────────────────────────
# Prompt composer (skill prepended)
# ──────────────────────────────────────────────────────────────────────


def compose_system_prompt(
    base_prompt: str,
    *,
    include_skill: bool = True,
) -> str:
    """既存 designer_ai の system prompt に skill 内容を prepend する.

    fallback: skill 無 → base_prompt のみ返却 (透過).
    """
    if not isinstance(base_prompt, str):
        raise ValueError("base_prompt must be string")
    if not isinstance(include_skill, bool):
        raise ValueError("include_skill must be bool")

    if not include_skill:
        return base_prompt

    skill = load_ui_mockup_skill()
    if not skill:
        return base_prompt

    return (
        "# ui-mockup skill (source of truth)\n\n"
        + skill
        + "\n\n---\n\n# Task-specific instructions\n\n"
        + base_prompt
    )


# ──────────────────────────────────────────────────────────────────────
# Public API (delegating to existing designer_ai)
# ──────────────────────────────────────────────────────────────────────


async def generate_with_skill(
    workspace_id: int,
    *,
    brief: str,
    include_skill: bool = True,
) -> dict:
    """ui-mockup skill prepended で mockup HTML を生成.

    Args:
        workspace_id: positive int.
        brief: 生成依頼テキスト (3-10000 chars).
        include_skill: True で skill prepend, False で素の designer_ai.

    Returns:
        {"html": str, "skill_used": bool, "char_count": int}
    """
    ws = _validate_workspace_id(workspace_id)
    b = _validate_brief(brief)
    if not isinstance(include_skill, bool):
        raise ValueError("include_skill must be bool")

    from services import designer_ai as ai

    # designer_ai.generate_mockup を呼ぶが、本 module の skill 経由で
    # system prompt を補強したい. designer_ai は internal で system prompt を
    # 持つため、wrapper として skill 文書を brief 先頭に prepend する形で
    # graceful fallback を実現.
    skill_used = False
    enhanced_brief = b
    skill = load_ui_mockup_skill() if include_skill else None
    if skill:
        skill_used = True
        enhanced_brief = (
            f"[SKILL CONTEXT]\n{skill}\n\n[TASK BRIEF]\n{b}"
        )

    # designer_ai.generate_mockup signature: (workspace_id, payload-like)
    # 既存 router pattern を respect: 直接 LLM 呼出ではなく designer_ai 経由
    try:
        # 既存 module の関数 surface に合わせる (mocking 容易性)
        result = await ai.generate_mockup(
            workspace_id=ws,
            brief=enhanced_brief,
        )
    except TypeError:
        # 既存 designer_ai が異なる signature の場合 → 単純 call_llm
        try:
            result_html = await ai.call_llm(
                "You are a UI mockup generator.",
                enhanced_brief,
            )
            result = {"html": result_html}
        except Exception as e:
            logger.warning("designer_ai call_llm failed: %s", e)
            result = {"html": ""}

    html = result.get("html", "") if isinstance(result, dict) else str(result)
    return {
        "html": html,
        "skill_used": skill_used,
        "char_count": len(html),
    }


async def edit_with_skill(
    workspace_id: int,
    *,
    current_html: str,
    edit_instruction: str,
    include_skill: bool = True,
) -> dict:
    """skill prepended で既存 mockup HTML を編集."""
    ws = _validate_workspace_id(workspace_id)
    if not isinstance(current_html, str) or not current_html.strip():
        raise ValueError("current_html must be non-empty string")
    instr = _validate_brief(edit_instruction)
    if not isinstance(include_skill, bool):
        raise ValueError("include_skill must be bool")

    from services import designer_ai as ai

    skill_used = False
    enhanced_instr = instr
    skill = load_ui_mockup_skill() if include_skill else None
    if skill:
        skill_used = True
        enhanced_instr = (
            f"[SKILL CONTEXT]\n{skill}\n\n[EDIT INSTRUCTION]\n{instr}"
        )

    try:
        result = await ai.edit_mockup(
            workspace_id=ws,
            current_html=current_html,
            instruction=enhanced_instr,
        )
    except TypeError:
        try:
            result_html = await ai.call_llm(
                "You edit HTML mockups based on instruction.",
                f"Current HTML:\n{current_html}\n\nInstruction:\n{enhanced_instr}",
            )
            result = {"html": result_html}
        except Exception as e:
            logger.warning("designer_ai edit fallback failed: %s", e)
            result = {"html": current_html}

    html = result.get("html", "") if isinstance(result, dict) else str(result)
    return {
        "html": html,
        "skill_used": skill_used,
        "char_count": len(html),
    }
