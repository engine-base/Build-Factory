"""T-003-01: BMAD persona prompt loader (10 メンバー、md ファイルから読込).

CLAUDE.md §3 で定義された Build-Factory 用 10 ペルソナの system prompt を
`data/personas/bmad/*.md` から読み出す graceful loader.

## 設計

- single source of truth: `data/personas/bmad/{persona_key}.md`
- DB seed (`ai_personas` table) は cache 的に使う (Phase 1)
- T-M27-03 (handoff_service) が本 loader 経由で persona prompt を取得し、
  claude-agent-sdk Subagent (Task tool) に渡す設計

## Graceful degradation

ファイルが存在しない / 読込失敗 → None を返し caller で DB seed の
`personality` カラム等を使う fallback. ImportError / OSError は warning ログ
のみで raise しない.

## AC マッピング

  AC-1 UBIQUITOUS    : load_persona_prompt / list_personas / VALID_PERSONA_KEYS
                       を公開. data/personas/bmad/ から読み出す.
  AC-2 EVENT-DRIVEN  : load_persona_prompt(key) は 100ms 以内に str | None 返却.
                       cache hit は 1ms 以内.
  AC-3 STATE-DRIVEN  : ファイル無 / 読込失敗で None (graceful) /
                       既存 ai_employee_store / delegation_service / secretary_chat
                       は無改変 (REUSE).
  AC-4 UNWANTED      : invalid persona_key (空 / 非 str / VALID 外) で ValueError /
                       md ファイル外を読みに行かない (path traversal 防止).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Constants (CLAUDE.md §3 と整合)
# ──────────────────────────────────────────────────────────────────────

VALID_PERSONA_KEYS = (
    "mary",      # Business Analyst
    "preston",   # Project Manager
    "winston",   # Architect
    "sally",     # Product Owner
    "devon",     # Developer
    "quinn",     # QA Engineer
    "reviewer",  # Code Reviewer
    "brand",     # Brand Designer
    "mockup",    # UI Mockup
    "logan",     # Knowledge Curator
)

REQUIRED_SECTIONS = (
    "## Role",
    "## Personality",
    "## Tone Style",
    "## Catchphrase",
    "## Specialty",
    "## Constraints",
    "## Handoff",
)

# Repo root から見たディレクトリ (test / runtime 両対応)
_DEFAULT_PERSONAS_DIR = Path(__file__).resolve().parents[2] / "data" / "personas" / "bmad"

# persona_key 形式 (alnum + - _ のみ, path traversal 防止)
_PERSONA_KEY_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

# in-memory cache
_PROMPT_CACHE: dict[str, str] = {}


# ──────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────


def _validate_persona_key(key: object) -> str:
    if not isinstance(key, str) or not key.strip():
        raise ValueError("persona_key must be non-empty string")
    s = key.strip()
    if not _PERSONA_KEY_PATTERN.match(s):
        raise ValueError(
            f"persona_key must match {_PERSONA_KEY_PATTERN.pattern!r}, got {s!r}"
        )
    if s not in VALID_PERSONA_KEYS:
        raise ValueError(
            f"persona_key must be one of {VALID_PERSONA_KEYS}, got {s!r}"
        )
    return s


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


def get_personas_dir() -> Path:
    """Return the personas directory (overridable for tests)."""
    return _DEFAULT_PERSONAS_DIR


def list_personas() -> list[dict]:
    """List all 10 valid personas with availability flag.

    Returns:
        list of {"persona_key": str, "available": bool, "path": str}.
    """
    out: list[dict] = []
    base = get_personas_dir()
    for key in VALID_PERSONA_KEYS:
        path = base / f"{key}.md"
        out.append({
            "persona_key": key,
            "available": path.exists(),
            "path": str(path),
        })
    return out


def load_persona_prompt(persona_key: str, *, use_cache: bool = True) -> Optional[str]:
    """Load persona system prompt md from disk.

    Args:
        persona_key: one of VALID_PERSONA_KEYS.
        use_cache: True で in-memory cache を使用.

    Returns:
        Markdown content as str, or None on file-not-found / read failure.

    Raises:
        ValueError: invalid persona_key (caller bug).
    """
    key = _validate_persona_key(persona_key)
    if not isinstance(use_cache, bool):
        raise ValueError("use_cache must be bool")

    if use_cache and key in _PROMPT_CACHE:
        return _PROMPT_CACHE[key]

    path = get_personas_dir() / f"{key}.md"
    # path traversal 防止: 最終 path が base dir 配下
    try:
        path.resolve().relative_to(get_personas_dir().resolve())
    except (ValueError, OSError):  # pragma: no cover (defensive)
        logger.warning("persona path traversal detected: %s", path)
        return None

    if not path.exists():
        logger.debug("persona prompt file missing: %s", path)
        return None

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("persona prompt read failed: %s -- %s", path, e)
        return None

    if use_cache:
        _PROMPT_CACHE[key] = content
    return content


def get_prompt_validation_status(persona_key: str) -> dict:
    """Check whether a persona prompt has all required sections (AC-1 verification).

    Returns:
        {
          "persona_key": str,
          "available": bool,
          "missing_sections": list[str],
          "char_count": int,
        }
    """
    key = _validate_persona_key(persona_key)
    content = load_persona_prompt(key)
    if content is None:
        return {
            "persona_key": key,
            "available": False,
            "missing_sections": list(REQUIRED_SECTIONS),
            "char_count": 0,
        }
    missing = [s for s in REQUIRED_SECTIONS if s not in content]
    return {
        "persona_key": key,
        "available": True,
        "missing_sections": missing,
        "char_count": len(content),
    }


def clear_cache() -> None:
    """Test-only: clear in-memory prompt cache."""
    global _PROMPT_CACHE
    _PROMPT_CACHE = {}
