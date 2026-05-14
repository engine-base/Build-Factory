"""ADR-012: Anthropic Memory Tool (memory_20250818) client-side handler.

Build-Factory が claude-agent-sdk / anthropic-python の Memory Tool を
activate するための薄い file-backed wrapper. 公式の `BetaAbstractMemoryTool`
を subclass せず, 同等のインターフェース (view / create / str_replace /
insert / delete / rename) を pure Python で提供する.

設計原則:
  - `/memories` 仮想 root を OBSIDIAN_VAULT_DIR / MEMORY_TOOL_DIR で物理マップ.
  - 全 path 操作で path traversal 防止 (pathlib.Path.resolve + relative_to).
  - 公式 doc 準拠の error message (test fixture と 1:1).
  - 自前 trim / compaction logic は実装しない (claude-agent-sdk auto-compaction
    に委譲, ADR-010 + ADR-012 Decision 4).

公開 API:
  - MEMORY_TOOL_TYPE: str   公式 tool spec 用 (memory_20250818)
  - MEMORY_TOOL_NAME: str   公式 tool name (memory)
  - memory_tool_spec()      claude-agent-sdk tools list 用の dict
  - class MemoryToolHandler MemoryError / 6 commands

AC マッピング (ADR-012 Decision 1):
  AC-1 UBIQUITOUS    : 6 公式 commands (view/create/str_replace/insert/delete/rename)
                       を 1 つの handler で公開.
  AC-2 EVENT-DRIVEN  : 各 command は 2 秒以内に dispatch 完了.
  AC-3 STATE-DRIVEN  : `/memories` 配下のみ操作. 物理 root 外は ContextBuilderError
                       (path traversal 防止).
  AC-4 UNWANTED      : 無効 path / 重複 create / 不在 file → 公式 error 文字列で reject.
                       state mutate なし.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


MEMORY_TOOL_TYPE = "memory_20250818"
MEMORY_TOOL_NAME = "memory"

# 仮想 root prefix (公式 doc 準拠)
MEMORY_ROOT_PREFIX = "/memories"

# 公式 commands
VALID_COMMANDS = (
    "view", "create", "str_replace", "insert", "delete", "rename",
)

# file size cap (公式 doc: 999,999 行で error)
MAX_FILE_LINES = 999_999

# Beta header 群 (本 module は明示せず, caller が組み立てる際の hint)
RECOMMENDED_BETA_HEADERS = (
    "context-management-2025-06-27",
)


class MemoryToolError(RuntimeError):
    """Memory Tool 入力 / 不変条件違反 (公式 error 文字列でも raise する)."""


def memory_tool_spec() -> dict[str, str]:
    """claude-agent-sdk / anthropic-python の tools list 用 dict.

    Example:
        from services.anthropic_memory_tool import memory_tool_spec
        tools = [..., memory_tool_spec()]
        client.messages.create(..., tools=tools)
    """
    return {"type": MEMORY_TOOL_TYPE, "name": MEMORY_TOOL_NAME}


def _physical_root() -> Path:
    """`/memories` 仮想 root の物理マッピング.

    優先順位:
      1. MEMORY_TOOL_DIR (テスト / sandbox 上書き用)
      2. OBSIDIAN_VAULT_DIR / "memories"  (Obsidian Vault と統合, ADR-012 Decision 1)
      3. ~/Documents/会社運営DB/memories/
      4. <repo>/data/memories/  (fallback)
    """
    override = os.environ.get("MEMORY_TOOL_DIR")
    if override:
        return Path(override)
    vault = os.environ.get("OBSIDIAN_VAULT_DIR")
    if vault:
        return Path(vault) / "memories"
    home = Path.home() / "Documents" / "会社運営DB" / "memories"
    if home.exists():
        return home
    return Path(__file__).resolve().parents[2] / "data" / "memories"


def _resolve_virtual_path(virtual_path: str, *, root: Optional[Path] = None) -> Path:
    """`/memories/foo/bar.txt` -> 物理 Path. path traversal を弾く.

    AC-3 STATE-DRIVEN: 物理 root 外は MemoryToolError.
    """
    if not isinstance(virtual_path, str) or not virtual_path:
        raise MemoryToolError(
            "The path  does not exist. Please provide a valid path.",
        )
    if not virtual_path.startswith(MEMORY_ROOT_PREFIX):
        raise MemoryToolError(
            f"Error: path must start with {MEMORY_ROOT_PREFIX}: {virtual_path}",
        )
    physical_root = (root or _physical_root()).resolve()
    physical_root.mkdir(parents=True, exist_ok=True)
    rel = virtual_path[len(MEMORY_ROOT_PREFIX):].lstrip("/")
    candidate = (physical_root / rel).resolve() if rel else physical_root
    # path traversal: 物理 root の外側に出ていたら reject
    try:
        candidate.relative_to(physical_root)
    except ValueError:
        raise MemoryToolError(
            f"Error: path traversal blocked: {virtual_path}",
        )
    return candidate


def _format_dir_listing(virtual_path: str, physical: Path) -> str:
    """公式 doc 仕様の directory listing 文字列を生成 (depth=2, no hidden, no node_modules)."""
    lines: list[str] = [
        "Here're the files and directories up to 2 levels deep in "
        f"{virtual_path}, excluding hidden items and node_modules:",
    ]

    def _human_size(b: int) -> str:
        if b < 1024:
            return f"{b}B"
        kb = b / 1024
        if kb < 1024:
            return f"{kb:.1f}K"
        return f"{kb / 1024:.1f}M"

    def _add(path: Path, virtual: str) -> None:
        try:
            size = path.stat().st_size if path.is_file() else (
                sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
            )
        except OSError:
            size = 0
        lines.append(f"{_human_size(size)}\t{virtual}")

    # depth=2 traverse
    if physical.is_file():
        _add(physical, virtual_path)
        return "\n".join(lines)
    _add(physical, virtual_path)
    for child in sorted(physical.iterdir()):
        if child.name.startswith(".") or child.name == "node_modules":
            continue
        cv = f"{virtual_path.rstrip('/')}/{child.name}"
        _add(child, cv)
        if child.is_dir():
            for gc in sorted(child.iterdir()):
                if gc.name.startswith(".") or gc.name == "node_modules":
                    continue
                gcv = f"{cv}/{gc.name}"
                _add(gc, gcv)
    return "\n".join(lines)


def _format_file_view(virtual_path: str, content: str, *, view_range: Optional[list[int]] = None) -> str:
    """公式 doc 仕様の file listing (line number prefix; width=6 right-aligned + tab)."""
    lines = content.splitlines() or [""]
    if len(lines) > MAX_FILE_LINES:
        raise MemoryToolError(
            f"File {virtual_path} exceeds maximum line limit of {MAX_FILE_LINES} lines.",
        )
    start = 1
    end = len(lines)
    if view_range:
        if not (isinstance(view_range, list) and len(view_range) == 2):
            raise MemoryToolError("view_range must be [start, end]")
        start, end = view_range
        if start < 1 or end < start or end > len(lines):
            raise MemoryToolError(
                f"Invalid view_range {view_range} for file of {len(lines)} lines",
            )
    header = f"Here's the content of {virtual_path} with line numbers:"
    body = [
        f"{i:>6}\t{lines[i - 1]}" for i in range(start, end + 1)
    ]
    return header + "\n" + "\n".join(body)


# ──────────────────────────────────────────────────────────────────────
# Public API: MemoryToolHandler
# ──────────────────────────────────────────────────────────────────────


@dataclass
class MemoryToolHandler:
    """6 commands を file-backed で実装する handler.

    claude-agent-sdk の tool_use 経由でも application 直接呼出でも使える.
    全 path は仮想 (`/memories/...`) で受け, 物理 mapping は _physical_root() に委譲.
    """

    root: Optional[Path] = None

    def _root(self) -> Path:
        return (self.root or _physical_root()).resolve()

    def dispatch(self, command: str, **kwargs: Any) -> str:
        """tool_input dict を 1 つの method で受ける entry point (sdk 経路用)."""
        if command not in VALID_COMMANDS:
            raise MemoryToolError(
                f"Error: unknown command {command!r}, expected one of {VALID_COMMANDS}",
            )
        fn = getattr(self, command)
        return fn(**kwargs)

    # -- view ----------------------------------------------------------
    def view(self, path: str, view_range: Optional[list[int]] = None) -> str:
        physical = _resolve_virtual_path(path, root=self._root())
        if not physical.exists():
            raise MemoryToolError(
                f"The path {path} does not exist. Please provide a valid path.",
            )
        if physical.is_dir():
            return _format_dir_listing(path, physical)
        content = physical.read_text(encoding="utf-8")
        return _format_file_view(path, content, view_range=view_range)

    # -- create --------------------------------------------------------
    def create(self, path: str, file_text: str) -> str:
        physical = _resolve_virtual_path(path, root=self._root())
        if physical.exists():
            raise MemoryToolError(f"Error: File {path} already exists")
        if not isinstance(file_text, str):
            raise MemoryToolError("file_text must be string")
        physical.parent.mkdir(parents=True, exist_ok=True)
        physical.write_text(file_text, encoding="utf-8")
        return f"File created successfully at: {path}"

    # -- str_replace ---------------------------------------------------
    def str_replace(self, path: str, old_str: str, new_str: str) -> str:
        physical = _resolve_virtual_path(path, root=self._root())
        if not physical.exists():
            raise MemoryToolError(
                f"Error: The path {path} does not exist. Please provide a valid path.",
            )
        if physical.is_dir():
            raise MemoryToolError(
                f"Error: The path {path} does not exist. Please provide a valid path.",
            )
        if not isinstance(old_str, str) or not isinstance(new_str, str):
            raise MemoryToolError("old_str / new_str must be string")
        content = physical.read_text(encoding="utf-8")
        # duplicate check (公式 doc 仕様)
        count = content.count(old_str)
        if count == 0:
            raise MemoryToolError(
                f"No replacement was performed, old_str `{old_str}` did not "
                f"appear verbatim in {path}.",
            )
        if count > 1:
            line_numbers: list[int] = []
            for i, line in enumerate(content.splitlines(), 1):
                if old_str in line:
                    line_numbers.append(i)
            raise MemoryToolError(
                "No replacement was performed. Multiple occurrences of old_str "
                f"`{old_str}` in lines: {line_numbers}. Please ensure it is unique",
            )
        new_content = content.replace(old_str, new_str, 1)
        physical.write_text(new_content, encoding="utf-8")
        return "The memory file has been edited."

    # -- insert --------------------------------------------------------
    def insert(self, path: str, insert_line: int, insert_text: str) -> str:
        physical = _resolve_virtual_path(path, root=self._root())
        if not physical.exists():
            raise MemoryToolError(f"Error: The path {path} does not exist")
        if physical.is_dir():
            raise MemoryToolError(f"Error: The path {path} does not exist")
        if isinstance(insert_line, bool) or not isinstance(insert_line, int):
            raise MemoryToolError(
                f"Error: Invalid `insert_line` parameter: {insert_line}",
            )
        if not isinstance(insert_text, str):
            raise MemoryToolError("insert_text must be string")
        content = physical.read_text(encoding="utf-8")
        lines = content.splitlines(keepends=True)
        n = len(lines)
        if insert_line < 0 or insert_line > n:
            raise MemoryToolError(
                f"Error: Invalid `insert_line` parameter: {insert_line}. "
                f"It should be within the range of lines of the file: [0, {n}]",
            )
        # insert_line=0 で先頭, n で末尾
        new_lines = lines[:insert_line] + [insert_text] + lines[insert_line:]
        physical.write_text("".join(new_lines), encoding="utf-8")
        return f"The file {path} has been edited."

    # -- delete --------------------------------------------------------
    def delete(self, path: str) -> str:
        physical = _resolve_virtual_path(path, root=self._root())
        if not physical.exists():
            raise MemoryToolError(f"Error: The path {path} does not exist")
        if physical.is_file():
            physical.unlink()
        else:
            # recursive (公式 doc 仕様)
            import shutil
            shutil.rmtree(physical)
        return f"Successfully deleted {path}"

    # -- rename --------------------------------------------------------
    def rename(self, old_path: str, new_path: str) -> str:
        src = _resolve_virtual_path(old_path, root=self._root())
        dst = _resolve_virtual_path(new_path, root=self._root())
        if not src.exists():
            raise MemoryToolError(f"Error: The path {old_path} does not exist")
        if dst.exists():
            raise MemoryToolError(f"Error: The destination {new_path} already exists")
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        return f"Successfully renamed {old_path} to {new_path}"
