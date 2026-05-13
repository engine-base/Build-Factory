"""ADR-012: Subagent Memory store (handoff 引継ぎ知識保管).

T-M27-03 handoff (mary -> devon -> quinn) で persona ごとに persistent な
working memory を残し, 次の handoff target が pre-load できるようにする
薄い wrapper. 実体は anthropic_memory_tool.MemoryToolHandler に委譲し,
`/memories/subagent/<persona>/...` の virtual path で名前空間を分ける.

公式仕様 (2026-02 Claude Code v2.1.33):
  - Subagent Memory は user / project の 2 scope.
  - 本 module は user / workspace の 2 scope に拡張 (Build-Factory workspace_id 連携).

設計境界:
  - 既存 handoff_service.py は無改変. SubagentMemoryStore を import して
    handoff_service.register_handoff_backend の payload で受け渡しする使い方.
  - 自前 memory store 実装はしない (anthropic_memory_tool.MemoryToolHandler 経由).
  - audit emit は memory_service.emit_event の "subagent.memory.*" event_type 系.

公開 API:
  - SubagentMemoryError
  - SubagentMemoryStore
      .record_handoff(source, target, message, ...) -> str (memory file path)
      .preload_for(target, *, workspace_id=None) -> list[dict]
      .list_persona_files(persona, *, workspace_id=None) -> list[str]
      .clear_persona(persona, *, workspace_id=None) -> int
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from services.anthropic_memory_tool import (
    MEMORY_ROOT_PREFIX,
    MemoryToolError,
    MemoryToolHandler,
)

logger = logging.getLogger(__name__)


class SubagentMemoryError(RuntimeError):
    """Subagent memory 入力 / 不変条件違反 (router 層で 4xx に変換)."""


# scope prefix
SUBAGENT_VIRTUAL_PREFIX = f"{MEMORY_ROOT_PREFIX}/subagent"

# persona_key 検証 (handoff_service と整合)
PERSONA_KEY_RE = re.compile(r"^[A-Za-z0-9_\-]{1,100}$")

# audit events
EVENT_HANDOFF_RECORDED = "subagent.memory.handoff_recorded"
EVENT_PRELOADED = "subagent.memory.preloaded"
EVENT_CLEARED = "subagent.memory.cleared"


def _validate_persona(key: Any, *, field: str = "persona") -> str:
    if not isinstance(key, str) or not key.strip():
        raise SubagentMemoryError(f"{field} must not be empty")
    s = key.strip()
    if not PERSONA_KEY_RE.match(s):
        raise SubagentMemoryError(
            f"{field} must match {PERSONA_KEY_RE.pattern}",
        )
    return s


def _validate_workspace_id(workspace_id: Any) -> Optional[int]:
    if workspace_id is None:
        return None
    if isinstance(workspace_id, bool) or not isinstance(workspace_id, int):
        raise SubagentMemoryError("workspace_id must be int or null")
    if workspace_id <= 0:
        raise SubagentMemoryError("workspace_id must be > 0")
    return workspace_id


def _scope_prefix(persona: str, *, workspace_id: Optional[int]) -> str:
    """`/memories/subagent/<persona>/` または
    `/memories/subagent/ws-<id>/<persona>/` を返す."""
    if workspace_id is not None:
        return f"{SUBAGENT_VIRTUAL_PREFIX}/ws-{workspace_id}/{persona}"
    return f"{SUBAGENT_VIRTUAL_PREFIX}/{persona}"


@dataclass
class SubagentMemoryStore:
    """Subagent ごとの persistent memory store.

    handler: anthropic_memory_tool.MemoryToolHandler (None なら都度 default 生成).
    """

    handler: Optional[MemoryToolHandler] = field(default=None)

    def _h(self) -> MemoryToolHandler:
        return self.handler or MemoryToolHandler()

    # ──────────────────────────────────────────────────────────────────
    # Write: handoff recording
    # ──────────────────────────────────────────────────────────────────

    def record_handoff(
        self,
        source: str,
        target: str,
        message: str,
        *,
        context: Optional[dict[str, Any]] = None,
        workspace_id: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """handoff event を target persona の memory に記録.

        Returns:
          {"path": str, "source": str, "target": str, "size": int, "timestamp": float}
        """
        src = _validate_persona(source, field="source")
        tgt = _validate_persona(target, field="target")
        ws = _validate_workspace_id(workspace_id)
        if not isinstance(message, str) or not message.strip():
            raise SubagentMemoryError("message must not be empty")
        if context is not None and not isinstance(context, dict):
            raise SubagentMemoryError("context must be dict or null")
        if session_id is not None and not isinstance(session_id, str):
            raise SubagentMemoryError("session_id must be str or null")

        ts = time.time()
        # filename: handoff/<unix_ts>-from-<source>.md
        scope = _scope_prefix(tgt, workspace_id=ws)
        virtual_path = f"{scope}/handoff/{int(ts)}-from-{src}.md"

        body_lines = [
            f"# Handoff from {src} -> {tgt}",
            "",
            f"- timestamp: {ts}",
            f"- session_id: {session_id or 'n/a'}",
            f"- workspace_id: {ws or 'n/a'}",
            "",
            "## Message",
            "",
            message.strip(),
        ]
        if context:
            body_lines.extend([
                "",
                "## Context",
                "",
                "```json",
                json.dumps(context, ensure_ascii=False, indent=2),
                "```",
            ])
        content = "\n".join(body_lines) + "\n"

        handler = self._h()
        try:
            handler.create(virtual_path, content)
        except MemoryToolError as e:
            # 同 timestamp で衝突した場合 (テスト等), suffix を付け retry
            if "already exists" in str(e):
                virtual_path = (
                    f"{scope}/handoff/{int(ts)}-{int(ts * 1000) % 10000}-from-{src}.md"
                )
                handler.create(virtual_path, content)
            else:
                raise

        return {
            "path": virtual_path,
            "source": src,
            "target": tgt,
            "size": len(content.encode("utf-8")),
            "timestamp": ts,
            "workspace_id": ws,
        }

    # ──────────────────────────────────────────────────────────────────
    # Read: pre-load for target persona
    # ──────────────────────────────────────────────────────────────────

    def list_persona_files(
        self,
        persona: str,
        *,
        workspace_id: Optional[int] = None,
        limit: int = 20,
    ) -> list[str]:
        """target persona の memory file 一覧 (virtual paths, newest-first)."""
        p = _validate_persona(persona)
        ws = _validate_workspace_id(workspace_id)
        if isinstance(limit, bool) or not isinstance(limit, int) or not (1 <= limit <= 200):
            raise SubagentMemoryError("limit must be int in 1..200")
        scope = _scope_prefix(p, workspace_id=ws)
        handler = self._h()
        try:
            handler.view(scope)
        except MemoryToolError:
            return []
        # ファイルシステム横断で newest-first をかき集める
        from pathlib import Path
        from services.anthropic_memory_tool import _resolve_virtual_path
        try:
            physical = _resolve_virtual_path(scope, root=handler._root())
        except MemoryToolError:
            return []
        if not physical.exists() or not physical.is_dir():
            return []
        files: list[tuple[float, Path]] = []
        for p2 in physical.rglob("*.md"):
            if p2.is_file():
                files.append((p2.stat().st_mtime, p2))
        files.sort(reverse=True)
        out: list[str] = []
        root = handler._root()
        for _, fp in files[:limit]:
            rel = fp.resolve().relative_to(root)
            out.append(f"{MEMORY_ROOT_PREFIX}/{rel.as_posix()}")
        return out

    def preload_for(
        self,
        target: str,
        *,
        workspace_id: Optional[int] = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """target persona に渡す memory snippet 一覧 (newest-first)."""
        files = self.list_persona_files(
            target, workspace_id=workspace_id, limit=limit,
        )
        out: list[dict[str, Any]] = []
        handler = self._h()
        for vp in files:
            try:
                content = handler.view(vp)
            except MemoryToolError as e:
                logger.warning("subagent memory view failed %s: %s", vp, e)
                continue
            out.append({"path": vp, "content": content})
        return out

    # ──────────────────────────────────────────────────────────────────
    # Maintenance
    # ──────────────────────────────────────────────────────────────────

    def clear_persona(
        self,
        persona: str,
        *,
        workspace_id: Optional[int] = None,
    ) -> int:
        """persona の memory file を全削除. 削除件数を返す.

        scope dir 全体を delete recursive する.
        """
        p = _validate_persona(persona)
        ws = _validate_workspace_id(workspace_id)
        scope = _scope_prefix(p, workspace_id=ws)
        handler = self._h()
        # 件数 count
        files = self.list_persona_files(p, workspace_id=ws, limit=200)
        n = len(files)
        try:
            handler.delete(scope)
        except MemoryToolError as e:
            if "does not exist" in str(e):
                return 0
            raise
        return n


# ──────────────────────────────────────────────────────────────────────
# Default singleton (caller が任意で差替可)
# ──────────────────────────────────────────────────────────────────────

_DEFAULT_STORE: Optional[SubagentMemoryStore] = None


def get_default_store() -> SubagentMemoryStore:
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = SubagentMemoryStore()
    return _DEFAULT_STORE


def reset_default_store() -> None:
    """テスト用: default store を None に戻す."""
    global _DEFAULT_STORE
    _DEFAULT_STORE = None
