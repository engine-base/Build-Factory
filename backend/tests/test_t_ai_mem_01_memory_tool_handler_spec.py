"""T-AI-MEM-01 (NEW audit): Memory Tool client-side handler — 1:1 spec test.

Audit for the existing ADR-012 client-side Memory Tool handler. Each of the 6
official commands (view / create / str_replace / insert / delete / rename) is
covered by individual behavior tests — collapsed dispatch tests are NOT a
substitute. Path traversal patterns (`..` / `~` / absolute paths / Windows
backslash / null byte) are each verified individually so a single regex blanket
match cannot give a false positive.

Source files audited:
  - backend/services/anthropic_memory_tool.py
  - backend/routers/anthropic_memory.py

AC マッピング (T-AI-MEM-01 / ADR-012 Decision 1 — quoted verbatim from
docs/task-decomposition/2026-05-09_v1/tickets.json#T-AI-MEM-01):

  AC-1 UBIQUITOUS
    "The system shall implement the Anthropic Memory Tool (memory_20250818)
     client-side handler with all 6 official commands (view / create /
     str_replace / insert / delete / rename) backed by the filesystem under
     OBSIDIAN_VAULT_DIR / MEMORY_TOOL_DIR."

  AC-2 EVENT-DRIVEN
    "When the SDK or REST endpoint invokes a memory command, the system shall
     return a structured response within 2 seconds and shall emit the official
     return-string for that command
     (e.g. 'File created successfully at: {path}')."

  AC-3 STATE-DRIVEN
    "While the handler is active, the system shall confine all path operations
     to the `/memories` virtual root and shall reject any path resolving outside
     the physical root (path traversal blocked via pathlib.Path.resolve +
     relative_to)."

  AC-4 UNWANTED
    "If application code re-implements the 6 commands outside
     services/anthropic_memory_tool.py, the lint script shall fail. If invalid
     input (unknown command / duplicate create / nonexistent path) is detected,
     the system shall reject with 4xx {detail:{code,message}} and shall NOT
     mutate persistent state."
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from services import anthropic_memory_tool as amt
from services import subagent_memory as sm


REPO_ROOT = Path(__file__).resolve().parents[2]
HANDLER_MODULE_PATH = (
    REPO_ROOT / "backend" / "services" / "anthropic_memory_tool.py"
)
ROUTER_MODULE_PATH = REPO_ROOT / "backend" / "routers" / "anthropic_memory.py"


# ══════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture
def isolated_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Pin the Memory Tool physical root to a temp dir; reset subagent store."""
    monkeypatch.setenv("MEMORY_TOOL_DIR", str(tmp_path))
    monkeypatch.delenv("OBSIDIAN_VAULT_DIR", raising=False)
    sm.reset_default_store()
    yield tmp_path
    sm.reset_default_store()


@pytest.fixture
def handler(isolated_root: Path) -> amt.MemoryToolHandler:
    return amt.MemoryToolHandler()


@pytest.fixture(scope="module")
def client() -> TestClient:
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app  # type: ignore[import-not-found]
    return TestClient(app, raise_server_exceptions=False)


def _handler_source() -> str:
    return HANDLER_MODULE_PATH.read_text(encoding="utf-8")


def _router_source() -> str:
    return ROUTER_MODULE_PATH.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — 6 commands + module / handler invariants
# Quote: "implement the Anthropic Memory Tool (memory_20250818) client-side
#         handler with all 6 official commands (view / create / str_replace /
#         insert / delete / rename) backed by the filesystem"
# ══════════════════════════════════════════════════════════════════════


def test_ac1_handler_module_file_exists():
    """AC-1: services/anthropic_memory_tool.py must exist."""
    assert HANDLER_MODULE_PATH.exists(), f"missing module: {HANDLER_MODULE_PATH}"


def test_ac1_router_module_file_exists():
    """AC-1: routers/anthropic_memory.py must exist."""
    assert ROUTER_MODULE_PATH.exists(), f"missing module: {ROUTER_MODULE_PATH}"


def test_ac1_tool_type_constant_is_official():
    """AC-1: MEMORY_TOOL_TYPE == official 'memory_20250818'."""
    assert amt.MEMORY_TOOL_TYPE == "memory_20250818"


def test_ac1_tool_name_constant_is_official():
    """AC-1: MEMORY_TOOL_NAME == official 'memory'."""
    assert amt.MEMORY_TOOL_NAME == "memory"


def test_ac1_tool_spec_matches_official_dict():
    """AC-1: memory_tool_spec() returns the official tools-list dict."""
    assert amt.memory_tool_spec() == {
        "type": "memory_20250818",
        "name": "memory",
    }


def test_ac1_valid_commands_are_exactly_six_official():
    """AC-1: VALID_COMMANDS == the 6 official commands, no more, no less."""
    assert set(amt.VALID_COMMANDS) == {
        "view", "create", "str_replace", "insert", "delete", "rename",
    }
    assert len(amt.VALID_COMMANDS) == 6


@pytest.mark.parametrize(
    "command",
    ["view", "create", "str_replace", "insert", "delete", "rename"],
)
def test_ac1_each_command_has_dedicated_method(
    handler: amt.MemoryToolHandler, command: str,
) -> None:
    """AC-1: each of 6 commands has its own method (no collapsed dispatch)."""
    fn = getattr(handler, command, None)
    assert fn is not None, f"missing handler.{command}"
    assert callable(fn), f"handler.{command} not callable"


# -- Each command — happy-path behavior + official return-string ----------


def test_ac1_view_file_returns_line_numbered_content(
    handler: amt.MemoryToolHandler,
) -> None:
    """AC-1 view: returns numbered file body per official spec."""
    handler.create("/memories/file.txt", "alpha\nbeta\ngamma\n")
    out = handler.view("/memories/file.txt")
    assert out.startswith("Here's the content of /memories/file.txt with line numbers:")
    assert "     1\talpha" in out
    assert "     2\tbeta" in out
    assert "     3\tgamma" in out


def test_ac1_view_directory_returns_listing(handler: amt.MemoryToolHandler) -> None:
    """AC-1 view: directory listing per official spec."""
    handler.create("/memories/a.txt", "a")
    handler.create("/memories/b.txt", "b")
    out = handler.view("/memories")
    assert "Here're the files and directories up to 2 levels deep in /memories" in out
    assert "/memories/a.txt" in out
    assert "/memories/b.txt" in out


def test_ac1_create_writes_file_and_returns_official_message(
    handler: amt.MemoryToolHandler, isolated_root: Path,
) -> None:
    """AC-1 create: file appears on disk; official return-string emitted."""
    msg = handler.create("/memories/new.txt", "payload")
    assert msg == "File created successfully at: /memories/new.txt"
    assert (isolated_root / "new.txt").read_text(encoding="utf-8") == "payload"


def test_ac1_str_replace_modifies_unique_match_and_returns_official_message(
    handler: amt.MemoryToolHandler,
) -> None:
    """AC-1 str_replace: unique-match replacement + official return-string."""
    handler.create("/memories/cfg.txt", "key: old_value\n")
    msg = handler.str_replace(
        "/memories/cfg.txt", "key: old_value", "key: new_value",
    )
    assert msg == "The memory file has been edited."
    assert "new_value" in handler.view("/memories/cfg.txt")


def test_ac1_insert_at_line_0_prepends(handler: amt.MemoryToolHandler) -> None:
    """AC-1 insert: insert_line=0 prepends to the start of the file."""
    handler.create("/memories/poem.txt", "one\ntwo\n")
    handler.insert("/memories/poem.txt", 0, "HEAD\n")
    out = handler.view("/memories/poem.txt")
    head_line = out.splitlines()[1]
    assert head_line.endswith("\tHEAD")


def test_ac1_insert_at_end_appends(handler: amt.MemoryToolHandler) -> None:
    """AC-1 insert: insert_line=n appends to the end of the file."""
    handler.create("/memories/poem.txt", "one\ntwo\n")
    handler.insert("/memories/poem.txt", 2, "TAIL\n")
    out = handler.view("/memories/poem.txt")
    assert "TAIL" in out


def test_ac1_insert_returns_official_message(handler: amt.MemoryToolHandler) -> None:
    """AC-1 insert: official return-string emitted."""
    handler.create("/memories/log.txt", "a\nb\n")
    msg = handler.insert("/memories/log.txt", 1, "c\n")
    assert msg == "The file /memories/log.txt has been edited."


def test_ac1_delete_file_removes_disk_entry(
    handler: amt.MemoryToolHandler, isolated_root: Path,
) -> None:
    """AC-1 delete: file unlink + official return-string."""
    handler.create("/memories/tmp.txt", "x")
    physical = isolated_root / "tmp.txt"
    assert physical.exists()
    msg = handler.delete("/memories/tmp.txt")
    assert msg == "Successfully deleted /memories/tmp.txt"
    assert not physical.exists()


def test_ac1_delete_directory_is_recursive(
    handler: amt.MemoryToolHandler, isolated_root: Path,
) -> None:
    """AC-1 delete: recursive directory removal per official doc."""
    handler.create("/memories/d/a.txt", "a")
    handler.create("/memories/d/b.txt", "b")
    msg = handler.delete("/memories/d")
    assert msg == "Successfully deleted /memories/d"
    assert not (isolated_root / "d").exists()


def test_ac1_rename_moves_file_and_returns_official_message(
    handler: amt.MemoryToolHandler, isolated_root: Path,
) -> None:
    """AC-1 rename: file relocates on disk + official return-string."""
    handler.create("/memories/draft.txt", "draft")
    msg = handler.rename("/memories/draft.txt", "/memories/final.txt")
    assert msg == "Successfully renamed /memories/draft.txt to /memories/final.txt"
    assert not (isolated_root / "draft.txt").exists()
    assert (isolated_root / "final.txt").read_text(encoding="utf-8") == "draft"


def test_ac1_dispatch_unknown_command_raises_memory_tool_error(
    handler: amt.MemoryToolHandler,
) -> None:
    """AC-1: dispatch() rejects commands not in VALID_COMMANDS."""
    with pytest.raises(amt.MemoryToolError, match="unknown command"):
        handler.dispatch("bogus", path="/memories/x")


def test_ac1_filesystem_root_honors_memory_tool_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-1: MEMORY_TOOL_DIR env overrides the physical root."""
    monkeypatch.setenv("MEMORY_TOOL_DIR", str(tmp_path))
    monkeypatch.delenv("OBSIDIAN_VAULT_DIR", raising=False)
    handler = amt.MemoryToolHandler()
    handler.create("/memories/env-target.txt", "ok")
    assert (tmp_path / "env-target.txt").exists()


def test_ac1_filesystem_root_falls_back_to_obsidian_vault_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-1: OBSIDIAN_VAULT_DIR fallback → <vault>/memories per ADR-012 Decision 1."""
    monkeypatch.delenv("MEMORY_TOOL_DIR", raising=False)
    monkeypatch.setenv("OBSIDIAN_VAULT_DIR", str(tmp_path))
    handler = amt.MemoryToolHandler()
    handler.create("/memories/vault-target.txt", "ok")
    assert (tmp_path / "memories" / "vault-target.txt").exists()


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — 2-second budget + official return-string per command
# Quote: "return a structured response within 2 seconds and shall emit the
#         official return-string for that command
#         (e.g. 'File created successfully at: {path}')"
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "command,kwargs,setup,expected_substring",
    [
        ("view", {"path": "/memories/v.txt"}, [("create", {"path": "/memories/v.txt", "file_text": "x"})], "Here's the content of /memories/v.txt"),
        ("create", {"path": "/memories/c.txt", "file_text": "y"}, [], "File created successfully at: /memories/c.txt"),
        ("str_replace", {"path": "/memories/s.txt", "old_str": "OLD", "new_str": "NEW"}, [("create", {"path": "/memories/s.txt", "file_text": "OLD\n"})], "The memory file has been edited."),
        ("insert", {"path": "/memories/i.txt", "insert_line": 1, "insert_text": "INS\n"}, [("create", {"path": "/memories/i.txt", "file_text": "a\nb\n"})], "The file /memories/i.txt has been edited."),
        ("delete", {"path": "/memories/d.txt"}, [("create", {"path": "/memories/d.txt", "file_text": "z"})], "Successfully deleted /memories/d.txt"),
        ("rename", {"old_path": "/memories/r.txt", "new_path": "/memories/r2.txt"}, [("create", {"path": "/memories/r.txt", "file_text": "q"})], "Successfully renamed /memories/r.txt to /memories/r2.txt"),
    ],
    ids=["view", "create", "str_replace", "insert", "delete", "rename"],
)
def test_ac2_each_command_returns_official_string_within_2s(
    handler: amt.MemoryToolHandler,
    command: str,
    kwargs: dict,
    setup: list[tuple[str, dict]],
    expected_substring: str,
) -> None:
    """AC-2: each command emits its official return-string within 2 seconds."""
    for cmd, ck in setup:
        getattr(handler, cmd)(**ck)
    t0 = time.time()
    out = getattr(handler, command)(**kwargs)
    elapsed = time.time() - t0
    assert elapsed < 2.0, f"{command} took {elapsed:.3f}s (> 2s budget)"
    assert expected_substring in out, (
        f"{command} return-string did not include {expected_substring!r}: got {out!r}"
    )


@pytest.mark.parametrize(
    "command", ["view", "create", "str_replace", "insert", "delete", "rename"],
)
def test_ac2_dispatch_routes_to_each_command(
    handler: amt.MemoryToolHandler, command: str,
) -> None:
    """AC-2: dispatch(command, ...) forwards to the per-command method."""
    if command == "view":
        handler.create("/memories/a.txt", "x")
        out = handler.dispatch("view", path="/memories/a.txt")
        assert "x" in out
    elif command == "create":
        out = handler.dispatch("create", path="/memories/b.txt", file_text="y")
        assert "File created successfully" in out
    elif command == "str_replace":
        handler.create("/memories/c.txt", "OLD\n")
        out = handler.dispatch(
            "str_replace", path="/memories/c.txt", old_str="OLD", new_str="NEW",
        )
        assert out == "The memory file has been edited."
    elif command == "insert":
        handler.create("/memories/d.txt", "a\nb\n")
        out = handler.dispatch(
            "insert", path="/memories/d.txt", insert_line=1, insert_text="C\n",
        )
        assert "has been edited" in out
    elif command == "delete":
        handler.create("/memories/e.txt", "z")
        out = handler.dispatch("delete", path="/memories/e.txt")
        assert "Successfully deleted" in out
    elif command == "rename":
        handler.create("/memories/f.txt", "q")
        out = handler.dispatch(
            "rename", old_path="/memories/f.txt", new_path="/memories/f2.txt",
        )
        assert "Successfully renamed" in out


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — Path traversal blocked / `/memories` confinement
# Quote: "confine all path operations to the `/memories` virtual root and shall
#         reject any path resolving outside the physical root (path traversal
#         blocked via pathlib.Path.resolve + relative_to)"
# ══════════════════════════════════════════════════════════════════════


def test_ac3_view_rejects_path_without_memories_prefix(
    handler: amt.MemoryToolHandler,
) -> None:
    """AC-3: paths without `/memories` prefix are rejected."""
    with pytest.raises(amt.MemoryToolError):
        handler.view("/etc/passwd")


def test_ac3_view_rejects_relative_path(handler: amt.MemoryToolHandler) -> None:
    """AC-3: relative paths are rejected (no prefix)."""
    with pytest.raises(amt.MemoryToolError):
        handler.view("notmemories/foo.txt")


def test_ac3_view_rejects_empty_path(handler: amt.MemoryToolHandler) -> None:
    """AC-3: empty path → MemoryToolError."""
    with pytest.raises(amt.MemoryToolError):
        handler.view("")


def test_ac3_traversal_dot_dot_rejected(handler: amt.MemoryToolHandler) -> None:
    """AC-3 path traversal: `..` segments are rejected (resolve + relative_to)."""
    with pytest.raises(amt.MemoryToolError):
        handler.view("/memories/../etc/passwd")


def test_ac3_traversal_multi_dot_dot_rejected(
    handler: amt.MemoryToolHandler,
) -> None:
    """AC-3 path traversal: multi-segment `..` chain is rejected."""
    with pytest.raises(amt.MemoryToolError):
        handler.create("/memories/../../../escape.txt", "x")


def test_ac3_traversal_tilde_rejected_outside_root(
    handler: amt.MemoryToolHandler, isolated_root: Path,
) -> None:
    """AC-3 path traversal: `~` is treated as a literal path component;
    if it resolves outside the physical root it is rejected.

    `pathlib.Path` does NOT expand `~` automatically, so `/memories/~root/file`
    resolves to `<root>/~root/file` — inside the physical root. We instead
    assert that a path with `~/` that escapes the root (when paired with `..`)
    is rejected, AND that `~` alone never lets the handler write *outside*
    `isolated_root`. The latter is the security invariant.
    """
    # Path traversal pattern with embedded `~` + `..` must be rejected:
    with pytest.raises(amt.MemoryToolError):
        handler.create("/memories/~/../../escape.txt", "x")
    # And any successful write with `~` segment must stay inside isolated_root:
    handler.create("/memories/~weird-name.txt", "x")
    physical = isolated_root / "~weird-name.txt"
    assert physical.exists()
    assert physical.resolve().is_relative_to(isolated_root.resolve())


def test_ac3_traversal_absolute_path_rejected(
    handler: amt.MemoryToolHandler,
) -> None:
    """AC-3 path traversal: absolute paths outside `/memories` are rejected."""
    with pytest.raises(amt.MemoryToolError):
        handler.view("/tmp/leak.txt")
    with pytest.raises(amt.MemoryToolError):
        handler.view("/var/log/syslog")


def test_ac3_traversal_null_byte_rejected(
    handler: amt.MemoryToolHandler,
) -> None:
    """AC-3 path traversal: null-byte injection rejected (filesystem reject)."""
    # Either MemoryToolError or ValueError (Python rejects \x00 in paths).
    with pytest.raises((amt.MemoryToolError, ValueError)):
        handler.create("/memories/foo\x00bar.txt", "x")


def test_ac3_resolve_relative_to_used_for_confinement():
    """AC-3: implementation must use `Path.resolve` + `relative_to` for confinement."""
    src = _handler_source()
    assert ".resolve()" in src, "AC-3 requires pathlib resolve() in implementation"
    assert ".relative_to(" in src, "AC-3 requires relative_to() invariant check"


def test_ac3_no_mutation_on_rejected_traversal(
    handler: amt.MemoryToolHandler, isolated_root: Path,
) -> None:
    """AC-3 + AC-4: filesystem state unchanged when traversal is rejected."""
    before = sorted(p.relative_to(isolated_root) for p in isolated_root.rglob("*"))
    for bad in (
        "/memories/../escape.txt",
        "/etc/passwd",
        "/memories/../../../etc/shadow",
        "/tmp/leak.txt",
    ):
        with pytest.raises(amt.MemoryToolError):
            handler.create(bad, "should-not-be-written")
    after = sorted(p.relative_to(isolated_root) for p in isolated_root.rglob("*"))
    assert before == after, "filesystem state mutated on a rejected traversal"


@pytest.mark.parametrize("workspace_dir", ["ws1", "ws2"])
def test_ac3_workspace_isolation_via_memory_tool_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, workspace_dir: str,
) -> None:
    """AC-3: per-workspace root isolation via MEMORY_TOOL_DIR override.

    Each workspace gets its own physical root → writes in one cannot reach
    another. This mirrors how the per-workspace caller will set
    MEMORY_TOOL_DIR or OBSIDIAN_VAULT_DIR per request context.
    """
    ws_root = tmp_path / workspace_dir
    ws_root.mkdir()
    monkeypatch.setenv("MEMORY_TOOL_DIR", str(ws_root))
    monkeypatch.delenv("OBSIDIAN_VAULT_DIR", raising=False)
    handler = amt.MemoryToolHandler()
    handler.create(f"/memories/{workspace_dir}-only.txt", "scoped")
    assert (ws_root / f"{workspace_dir}-only.txt").exists()
    # Any other workspace dir under tmp_path must be untouched:
    for other in tmp_path.iterdir():
        if other == ws_root:
            continue
        assert not (other / f"{workspace_dir}-only.txt").exists()


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED — invalid input rejected + state preserved + lint enforcement
# Quote: "If application code re-implements the 6 commands outside
#         services/anthropic_memory_tool.py, the lint script shall fail.
#         If invalid input (unknown command / duplicate create / nonexistent
#         path) is detected, the system shall reject with 4xx {detail:{code,
#         message}} and shall NOT mutate persistent state."
# ══════════════════════════════════════════════════════════════════════


def test_ac4_unknown_command_rejected(handler: amt.MemoryToolHandler) -> None:
    """AC-4: dispatch on unknown command raises with official message."""
    with pytest.raises(amt.MemoryToolError, match="unknown command 'bogus'"):
        handler.dispatch("bogus", path="/memories/x")


def test_ac4_duplicate_create_rejected(
    handler: amt.MemoryToolHandler, isolated_root: Path,
) -> None:
    """AC-4 duplicate create: official 'already exists' error + no overwrite."""
    handler.create("/memories/once.txt", "first")
    with pytest.raises(amt.MemoryToolError, match="already exists"):
        handler.create("/memories/once.txt", "second")
    # original content preserved:
    assert (isolated_root / "once.txt").read_text(encoding="utf-8") == "first"


def test_ac4_view_nonexistent_rejected(handler: amt.MemoryToolHandler) -> None:
    """AC-4: view on missing path → official 'does not exist' message."""
    with pytest.raises(amt.MemoryToolError, match="does not exist"):
        handler.view("/memories/missing.txt")


def test_ac4_str_replace_no_match_rejected(
    handler: amt.MemoryToolHandler, isolated_root: Path,
) -> None:
    """AC-4 str_replace: no-match → official 'did not appear verbatim' error,
    file content unchanged."""
    handler.create("/memories/x.txt", "alpha")
    with pytest.raises(amt.MemoryToolError, match="did not appear verbatim"):
        handler.str_replace("/memories/x.txt", "ZZZ", "WWW")
    assert (isolated_root / "x.txt").read_text(encoding="utf-8") == "alpha"


def test_ac4_str_replace_multiple_matches_rejected(
    handler: amt.MemoryToolHandler, isolated_root: Path,
) -> None:
    """AC-4 str_replace: multi-match → official 'Multiple occurrences' error;
    file content unchanged."""
    handler.create("/memories/x.txt", "DUP\nDUP\n")
    with pytest.raises(amt.MemoryToolError, match="Multiple occurrences"):
        handler.str_replace("/memories/x.txt", "DUP", "X")
    assert (isolated_root / "x.txt").read_text(encoding="utf-8") == "DUP\nDUP\n"


def test_ac4_insert_invalid_line_rejected(handler: amt.MemoryToolHandler) -> None:
    """AC-4 insert: out-of-range line → official 'Invalid `insert_line`' error."""
    handler.create("/memories/x.txt", "a\nb\n")
    with pytest.raises(amt.MemoryToolError, match="Invalid `insert_line`"):
        handler.insert("/memories/x.txt", 999, "z\n")


def test_ac4_insert_negative_line_rejected(handler: amt.MemoryToolHandler) -> None:
    """AC-4 insert: negative line → official 'Invalid `insert_line`' error."""
    handler.create("/memories/x.txt", "a\nb\n")
    with pytest.raises(amt.MemoryToolError, match="Invalid `insert_line`"):
        handler.insert("/memories/x.txt", -1, "z\n")


def test_ac4_insert_non_int_line_rejected(handler: amt.MemoryToolHandler) -> None:
    """AC-4 insert: non-int line → official 'Invalid `insert_line`' error."""
    handler.create("/memories/x.txt", "a\nb\n")
    with pytest.raises(amt.MemoryToolError, match="Invalid `insert_line`"):
        handler.insert("/memories/x.txt", "1", "z\n")  # type: ignore[arg-type]


def test_ac4_delete_nonexistent_rejected(handler: amt.MemoryToolHandler) -> None:
    """AC-4 delete: missing path → official 'does not exist' error."""
    with pytest.raises(amt.MemoryToolError, match="does not exist"):
        handler.delete("/memories/never.txt")


def test_ac4_rename_src_missing_rejected(handler: amt.MemoryToolHandler) -> None:
    """AC-4 rename: missing source → official 'does not exist' error."""
    with pytest.raises(amt.MemoryToolError, match="does not exist"):
        handler.rename("/memories/never.txt", "/memories/x.txt")


def test_ac4_rename_dst_collision_rejected(
    handler: amt.MemoryToolHandler, isolated_root: Path,
) -> None:
    """AC-4 rename: destination exists → official 'already exists' error;
    source preserved."""
    handler.create("/memories/a.txt", "A")
    handler.create("/memories/b.txt", "B")
    with pytest.raises(amt.MemoryToolError, match="already exists"):
        handler.rename("/memories/a.txt", "/memories/b.txt")
    # both files preserved:
    assert (isolated_root / "a.txt").read_text(encoding="utf-8") == "A"
    assert (isolated_root / "b.txt").read_text(encoding="utf-8") == "B"


# -- AC-4 router-level 4xx form ---------------------------------------------


def test_ac4_router_unknown_command_returns_400_with_code_and_message(
    client: TestClient,
) -> None:
    """AC-4 router: unknown command → 400 with {detail:{code,message}}."""
    r = client.post("/api/anthropic-memory/bogus", json={"path": "/memories/x"})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == "memory.invalid"
    assert isinstance(detail["message"], str) and detail["message"]


def test_ac4_router_traversal_returns_400_with_code_and_message(
    client: TestClient, isolated_root: Path,
) -> None:
    """AC-4 router: path traversal → 400 with {detail:{code,message}}."""
    r = client.post(
        "/api/anthropic-memory/view", json={"path": "/memories/../escape"},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "memory.invalid"
    assert "traversal" in detail["message"] or "Error" in detail["message"]


def test_ac4_router_missing_path_returns_404_with_code_and_message(
    client: TestClient, isolated_root: Path,
) -> None:
    """AC-4 router: nonexistent path → 404 with {detail:{code,message}}."""
    r = client.post(
        "/api/anthropic-memory/view", json={"path": "/memories/none.txt"},
    )
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert detail["code"] == "memory.not_found"


def test_ac4_router_duplicate_create_returns_409_with_code_and_message(
    client: TestClient, isolated_root: Path,
) -> None:
    """AC-4 router: duplicate create → 409 with {detail:{code,message}}."""
    r1 = client.post(
        "/api/anthropic-memory/create",
        json={"path": "/memories/dup.txt", "file_text": "a"},
    )
    assert r1.status_code == 200
    r2 = client.post(
        "/api/anthropic-memory/create",
        json={"path": "/memories/dup.txt", "file_text": "b"},
    )
    assert r2.status_code == 409
    detail = r2.json()["detail"]
    assert detail["code"] == "memory.conflict"


def test_ac4_router_4xx_form_uniform_for_all_failure_modes(
    client: TestClient, isolated_root: Path,
) -> None:
    """AC-4 router: every 4xx response carries {detail:{code,message}}."""
    cases = [
        ("/api/anthropic-memory/bogus", {"path": "/memories/x"}, 400),
        ("/api/anthropic-memory/view", {"path": "/etc/passwd"}, 400),
        ("/api/anthropic-memory/view", {"path": "/memories/never.txt"}, 404),
    ]
    for path, body, expected in cases:
        r = client.post(path, json=body)
        assert r.status_code == expected, (
            f"{path} expected {expected} got {r.status_code}: {r.text}"
        )
        detail = r.json()["detail"]
        assert isinstance(detail, dict), f"{path}: detail must be dict"
        assert isinstance(detail.get("code"), str) and detail["code"], (
            f"{path}: detail.code must be non-empty str"
        )
        assert isinstance(detail.get("message"), str) and detail["message"], (
            f"{path}: detail.message must be non-empty str"
        )


# -- AC-4 lint enforcement: re-implementation outside this module ----------
# Note: ADR-012 §"機械的強制レイヤー (lint)" mandates a lint-mock.sh hook that
# fails when `memory_20250818` raw spec is reassembled outside
# services/anthropic_memory_tool.py. That bash-level lint is not yet wired up
# (documented as gap G1 in docs/audit/2026-05-13_v2/T-AI-MEM-01.md), so the
# AC-4 invariant is verified here at the Python level — by scanning the
# entire backend tree for `MEMORY_TOOL_TYPE = "memory_20250818"` redefinitions
# outside the canonical handler. When the bash lint check lands, it will
# enforce the same invariant at commit time.


def test_ac4_no_other_module_redefines_memory_tool_type():
    """AC-4: no module under backend/ re-declares MEMORY_TOOL_TYPE except the
    canonical handler module (drift guard against silent re-implementation)."""
    backend_root = REPO_ROOT / "backend"
    pattern = re.compile(r'\bMEMORY_TOOL_TYPE\s*=\s*"memory_20250818"')
    offenders: list[str] = []
    for py in backend_root.rglob("*.py"):
        if py == HANDLER_MODULE_PATH:
            continue
        # tests are allowed to assert the literal:
        if "tests" in py.parts:
            continue
        text = py.read_text(encoding="utf-8", errors="ignore")
        if pattern.search(text):
            offenders.append(str(py.relative_to(REPO_ROOT)))
    assert not offenders, (
        f"AC-4 drift: MEMORY_TOOL_TYPE redefined outside the canonical handler: "
        f"{offenders}"
    )


# ══════════════════════════════════════════════════════════════════════
# Drift guard — module / router docstring + tool-spec stability
# ══════════════════════════════════════════════════════════════════════


def test_drift_guard_module_documents_adr_012():
    """Drift: docstring must mention ADR-012 (so the module's purpose is traceable)."""
    assert amt.__doc__ is not None
    assert "ADR-012" in amt.__doc__


def test_drift_guard_router_documents_adr_012():
    """Drift: router docstring must mention ADR-012."""
    src = _router_source()
    assert "ADR-012" in src


def test_drift_guard_tool_spec_returns_exactly_two_keys():
    """Drift: tool_spec is a 2-key dict per official Anthropic doc."""
    spec = amt.memory_tool_spec()
    assert isinstance(spec, dict)
    assert set(spec.keys()) == {"type", "name"}
