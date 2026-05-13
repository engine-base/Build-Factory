"""ADR-012: Anthropic Context Editing config (clear_tool_uses / compact / clear_thinking).

claude-agent-sdk / anthropic-python の `client.beta.messages.create(...,
context_management=...)` に渡す config を生成するファクトリ.

公式仕様 (2026-05 現在):
  - clear_tool_uses_20250919  : 古い tool_result を自動 clear (re-callable な tool 用)
  - compact_20260112          : 会話全体を server-side 要約 (50K minimum)
  - clear_thinking_20251015   : extended thinking blocks を clear (必ず最初に配置)

Beta headers:
  - context-management-2025-06-27  (clear_tool_uses)
  - compact-2026-01-12             (compaction)

設計原則:
  - Memory tool (memory_20250818) の結果は `exclude_tools: ["memory"]` で保護.
  - 自前 trim / compaction logic は実装しない (ADR-010 / ADR-012 Decision 4).
  - 本 module は config 値を返すだけの pure factory (副作用なし, audit emit なし).

公開 API:
  - default_context_management_config()  -> dict
  - recommended_beta_headers()           -> list[str]
  - validate_config(cfg)                  -> dict   (caller 用 sanity check)
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)


# 公式 strategy type 値
STRATEGY_CLEAR_TOOL_USES = "clear_tool_uses_20250919"
STRATEGY_COMPACT = "compact_20260112"
STRATEGY_CLEAR_THINKING = "clear_thinking_20251015"

VALID_STRATEGY_TYPES = (
    STRATEGY_CLEAR_TOOL_USES,
    STRATEGY_COMPACT,
    STRATEGY_CLEAR_THINKING,
)

# Beta headers
BETA_HEADER_CONTEXT_MANAGEMENT = "context-management-2025-06-27"
BETA_HEADER_COMPACT = "compact-2026-01-12"

# Memory tool 結果は clearing から保護する (ADR-012 Decision 2)
PROTECTED_TOOLS = ("memory",)

# 既定 trigger 値 (公式 doc 推奨 + Build-Factory ¥0/月構成への配慮)
DEFAULT_CLEAR_TOOL_USES_TRIGGER_TOKENS = 30_000
DEFAULT_CLEAR_TOOL_USES_KEEP = 4
DEFAULT_CLEAR_TOOL_USES_CLEAR_AT_LEAST = 10_000

DEFAULT_COMPACT_TRIGGER_TOKENS = 180_000

DEFAULT_CLEAR_THINKING_TRIGGER_TOKENS = 50_000
DEFAULT_CLEAR_THINKING_KEEP = 2


class ContextEditingError(RuntimeError):
    """Context Editing config 入力 / 不変条件違反."""


def recommended_beta_headers() -> list[str]:
    """SDK 呼出時に付与すべき beta headers (順序意味なし)."""
    return [BETA_HEADER_CONTEXT_MANAGEMENT, BETA_HEADER_COMPACT]


def default_context_management_config(
    *,
    enable_clear_tool_uses: bool = True,
    enable_compact: bool = True,
    enable_clear_thinking: bool = False,
    clear_tool_uses_trigger: int = DEFAULT_CLEAR_TOOL_USES_TRIGGER_TOKENS,
    clear_tool_uses_keep: int = DEFAULT_CLEAR_TOOL_USES_KEEP,
    clear_tool_uses_clear_at_least: int = DEFAULT_CLEAR_TOOL_USES_CLEAR_AT_LEAST,
    compact_trigger: int = DEFAULT_COMPACT_TRIGGER_TOKENS,
    compact_instructions: Optional[str] = None,
    clear_thinking_trigger: int = DEFAULT_CLEAR_THINKING_TRIGGER_TOKENS,
    clear_thinking_keep: int = DEFAULT_CLEAR_THINKING_KEEP,
    extra_protected_tools: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Build-Factory 既定の context_management dict を返す.

    Memory tool (memory_20250818) は clearing 対象から exclude する.

    Returns:
      anthropic-python `messages.create(..., context_management=cfg)` に渡せる
      dict. caller は `betas=recommended_beta_headers()` も合わせて付与すること.
    """
    if compact_trigger < 50_000:
        raise ContextEditingError(
            "compact_20260112 trigger must be >= 50,000 tokens (公式 doc 制約)",
        )
    if clear_tool_uses_keep < 0:
        raise ContextEditingError("clear_tool_uses keep must be >= 0")
    if clear_tool_uses_trigger <= 0:
        raise ContextEditingError("clear_tool_uses trigger must be > 0")

    protected = list(PROTECTED_TOOLS)
    if extra_protected_tools:
        for t in extra_protected_tools:
            if not isinstance(t, str) or not t:
                raise ContextEditingError("extra_protected_tools must be list[str]")
            if t not in protected:
                protected.append(t)

    edits: list[dict[str, Any]] = []

    # clear_thinking_20251015 は必ず先頭 (公式 doc)
    if enable_clear_thinking:
        edits.append({
            "type": STRATEGY_CLEAR_THINKING,
            "trigger": {"type": "input_tokens", "value": clear_thinking_trigger},
            "keep": {"type": "thinking_uses", "value": clear_thinking_keep},
        })

    if enable_clear_tool_uses:
        clear_cfg: dict[str, Any] = {
            "type": STRATEGY_CLEAR_TOOL_USES,
            "trigger": {"type": "input_tokens", "value": clear_tool_uses_trigger},
            "keep": {"type": "tool_uses", "value": clear_tool_uses_keep},
            "clear_at_least": {
                "type": "input_tokens", "value": clear_tool_uses_clear_at_least,
            },
            "exclude_tools": list(protected),
        }
        edits.append(clear_cfg)

    if enable_compact:
        compact_cfg: dict[str, Any] = {
            "type": STRATEGY_COMPACT,
            "trigger": {"type": "input_tokens", "value": compact_trigger},
        }
        if compact_instructions:
            compact_cfg["instructions"] = compact_instructions
        edits.append(compact_cfg)

    return {"edits": edits}


def validate_config(cfg: Any) -> dict[str, Any]:
    """caller 渡しの config dict を sanity check し dict を返す.

    Raises ContextEditingError on invalid input.
    """
    if not isinstance(cfg, dict):
        raise ContextEditingError("context_management config must be dict")
    edits = cfg.get("edits")
    if not isinstance(edits, list):
        raise ContextEditingError("config.edits must be list")
    seen_thinking_at = -1
    for i, edit in enumerate(edits):
        if not isinstance(edit, dict):
            raise ContextEditingError(f"edits[{i}] must be dict")
        t = edit.get("type")
        if t not in VALID_STRATEGY_TYPES:
            raise ContextEditingError(
                f"edits[{i}].type must be one of {VALID_STRATEGY_TYPES}, got {t!r}",
            )
        if t == STRATEGY_CLEAR_THINKING:
            seen_thinking_at = i
        if t == STRATEGY_COMPACT:
            trig = edit.get("trigger", {})
            if not isinstance(trig, dict) or trig.get("value", 0) < 50_000:
                raise ContextEditingError(
                    "compact_20260112 trigger must be >= 50,000 tokens",
                )
        trig = edit.get("trigger")
        if not isinstance(trig, dict):
            raise ContextEditingError(f"edits[{i}].trigger must be dict")
        if trig.get("type") not in ("input_tokens",):
            raise ContextEditingError(
                f"edits[{i}].trigger.type must be 'input_tokens'",
            )
        if not isinstance(trig.get("value"), int) or trig["value"] <= 0:
            raise ContextEditingError(
                f"edits[{i}].trigger.value must be int > 0",
            )
    # clear_thinking が他より後ろにあったら警告 (公式 doc: 必ず先頭)
    if seen_thinking_at > 0:
        raise ContextEditingError(
            f"{STRATEGY_CLEAR_THINKING} must be placed first in edits (公式制約)",
        )
    return cfg


def env_override_config() -> Optional[dict[str, Any]]:
    """env CONTEXT_MGMT_DISABLE が truthy なら None を返し caller に skip 指示.

    Phase 1 で SDK 未接続時に config 適用を一時停止する用途.
    """
    raw = os.environ.get("CONTEXT_MGMT_DISABLE", "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return None
    return default_context_management_config()
