"""ADR-012: Anthropic Memory Tool / Context Editing / Subagent Memory — 4 AC 全網羅.

AC マッピング (ADR-012 Decisions 1-3):
  AC-1 UBIQUITOUS    : 6 公式 commands (view/create/str_replace/insert/delete/rename)
                       + Context Editing default config + Subagent Memory unified.
  AC-2 EVENT-DRIVEN  : 各 command / config 取得は 2 秒以内.
  AC-3 STATE-DRIVEN  : path traversal blocked / Memory tool は exclude_tools で保護.
  AC-4 UNWANTED      : invalid input → MemoryToolError/ContextEditingError 経由 4xx
                       {detail:{code,message}}. state mutate なし.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import anthropic_context_editing as ce
from services import anthropic_memory_tool as amt
from services import subagent_memory as sm


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def isolated_root(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_TOOL_DIR", str(tmp_path))
    monkeypatch.delenv("OBSIDIAN_VAULT_DIR", raising=False)
    sm.reset_default_store()
    yield tmp_path
    sm.reset_default_store()


@pytest.fixture
def handler(isolated_root):
    return amt.MemoryToolHandler()


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS: Memory Tool 6 commands
# ══════════════════════════════════════════════════════════════════════


def test_ac1_tool_spec_matches_official():
    spec = amt.memory_tool_spec()
    assert spec == {"type": "memory_20250818", "name": "memory"}


def test_ac1_valid_commands_exactly_six():
    assert set(amt.VALID_COMMANDS) == {
        "view", "create", "str_replace", "insert", "delete", "rename",
    }


def test_ac1_create_and_view_round_trip(handler):
    handler.create("/memories/notes.txt", "hello\nworld\n")
    out = handler.view("/memories/notes.txt")
    assert "hello" in out
    assert "     1\thello" in out


def test_ac1_view_directory_listing(handler):
    handler.create("/memories/a.txt", "x")
    handler.create("/memories/b.txt", "y")
    out = handler.view("/memories")
    assert "Here're the files and directories" in out
    assert "/memories" in out


def test_ac1_str_replace(handler):
    handler.create("/memories/p.txt", "Favorite color: blue\n")
    msg = handler.str_replace(
        "/memories/p.txt",
        "Favorite color: blue",
        "Favorite color: green",
    )
    assert msg == "The memory file has been edited."
    assert "green" in handler.view("/memories/p.txt")


def test_ac1_insert_at_line(handler):
    handler.create("/memories/todo.txt", "a\nb\nc\n")
    handler.insert("/memories/todo.txt", 2, "INSERTED\n")
    out = handler.view("/memories/todo.txt")
    assert "INSERTED" in out


def test_ac1_delete_file(handler):
    handler.create("/memories/x.txt", "x")
    msg = handler.delete("/memories/x.txt")
    assert "Successfully deleted" in msg


def test_ac1_delete_directory_recursive(handler):
    handler.create("/memories/d/a.txt", "a")
    handler.create("/memories/d/b.txt", "b")
    msg = handler.delete("/memories/d")
    assert "Successfully deleted" in msg


def test_ac1_rename(handler):
    handler.create("/memories/draft.txt", "x")
    msg = handler.rename("/memories/draft.txt", "/memories/final.txt")
    assert "Successfully renamed" in msg
    assert handler.view("/memories/final.txt").endswith("\tx")


def test_ac1_dispatch_routes_command(handler):
    handler.dispatch("create", path="/memories/d.txt", file_text="z")
    out = handler.dispatch("view", path="/memories/d.txt")
    assert "z" in out


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: 2 sec timing
# ══════════════════════════════════════════════════════════════════════


def test_ac2_create_within_2sec(handler):
    t0 = time.time()
    handler.create("/memories/t.txt", "x" * 1000)
    assert (time.time() - t0) < 2.0


def test_ac2_view_within_2sec(handler):
    handler.create("/memories/t.txt", "x" * 1000)
    t0 = time.time()
    handler.view("/memories/t.txt")
    assert (time.time() - t0) < 2.0


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: path traversal blocked / `/memories` 配下のみ
# ══════════════════════════════════════════════════════════════════════


def test_ac3_path_must_start_with_memories(handler):
    with pytest.raises(amt.MemoryToolError):
        handler.view("/etc/passwd")
    with pytest.raises(amt.MemoryToolError):
        handler.create("/notmemories/x.txt", "x")


def test_ac3_path_traversal_blocked(handler, isolated_root):
    # 仮想 root 外への traversal
    with pytest.raises(amt.MemoryToolError):
        handler.view("/memories/../etc/passwd")
    # 物理 root 外への symlink 等は (環境依存) 検証スキップ. パターン文字列 reject 確認.
    with pytest.raises(amt.MemoryToolError):
        handler.create("/memories/../../escape.txt", "x")


def test_ac3_state_no_mutation_on_invalid_path(handler, isolated_root):
    files_before = list(isolated_root.rglob("*"))
    with pytest.raises(amt.MemoryToolError):
        handler.create("/etc/x.txt", "x")
    with pytest.raises(amt.MemoryToolError):
        handler.create("/memories/../escape.txt", "x")
    files_after = list(isolated_root.rglob("*"))
    assert files_before == files_after


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: official error strings + state preservation
# ══════════════════════════════════════════════════════════════════════


def test_ac4_view_missing_official_error(handler):
    with pytest.raises(amt.MemoryToolError, match="does not exist"):
        handler.view("/memories/missing.txt")


def test_ac4_create_duplicate_official_error(handler):
    handler.create("/memories/x.txt", "a")
    with pytest.raises(amt.MemoryToolError, match="already exists"):
        handler.create("/memories/x.txt", "b")


def test_ac4_str_replace_no_match(handler):
    handler.create("/memories/x.txt", "abc")
    with pytest.raises(amt.MemoryToolError, match="did not appear verbatim"):
        handler.str_replace("/memories/x.txt", "ZZ", "YY")


def test_ac4_str_replace_multiple_matches(handler):
    handler.create("/memories/x.txt", "X\nX\n")
    with pytest.raises(amt.MemoryToolError, match="Multiple occurrences"):
        handler.str_replace("/memories/x.txt", "X", "Y")


def test_ac4_insert_invalid_line(handler):
    handler.create("/memories/x.txt", "a\nb\n")
    with pytest.raises(amt.MemoryToolError, match="Invalid `insert_line`"):
        handler.insert("/memories/x.txt", 999, "z")


def test_ac4_rename_dest_exists(handler):
    handler.create("/memories/a.txt", "a")
    handler.create("/memories/b.txt", "b")
    with pytest.raises(amt.MemoryToolError, match="already exists"):
        handler.rename("/memories/a.txt", "/memories/b.txt")


def test_ac4_delete_missing(handler):
    with pytest.raises(amt.MemoryToolError, match="does not exist"):
        handler.delete("/memories/none.txt")


def test_ac4_dispatch_unknown_command(handler):
    with pytest.raises(amt.MemoryToolError, match="unknown command"):
        handler.dispatch("bogus", path="/memories/x")


# ══════════════════════════════════════════════════════════════════════
# Context Editing config
# ══════════════════════════════════════════════════════════════════════


def test_ce_default_config_has_memory_exempt():
    cfg = ce.default_context_management_config()
    edits = cfg["edits"]
    clear_edits = [e for e in edits if e["type"] == ce.STRATEGY_CLEAR_TOOL_USES]
    assert len(clear_edits) == 1
    assert "memory" in clear_edits[0]["exclude_tools"]


def test_ce_default_config_compact_strategy_present():
    cfg = ce.default_context_management_config()
    compact_edits = [e for e in cfg["edits"] if e["type"] == ce.STRATEGY_COMPACT]
    assert len(compact_edits) == 1
    assert compact_edits[0]["trigger"]["value"] >= 50_000


def test_ce_beta_headers():
    h = ce.recommended_beta_headers()
    assert "context-management-2025-06-27" in h
    assert "compact-2026-01-12" in h


def test_ce_compact_trigger_below_50k_rejected():
    with pytest.raises(ce.ContextEditingError):
        ce.default_context_management_config(compact_trigger=10_000)


def test_ce_clear_thinking_must_be_first():
    cfg = ce.default_context_management_config(enable_clear_thinking=True)
    assert cfg["edits"][0]["type"] == ce.STRATEGY_CLEAR_THINKING


def test_ce_validate_config_rejects_misordered_clear_thinking():
    bad = {"edits": [
        {"type": ce.STRATEGY_CLEAR_TOOL_USES,
         "trigger": {"type": "input_tokens", "value": 1000},
         "keep": {"type": "tool_uses", "value": 1}},
        {"type": ce.STRATEGY_CLEAR_THINKING,
         "trigger": {"type": "input_tokens", "value": 1000},
         "keep": {"type": "thinking_uses", "value": 1}},
    ]}
    with pytest.raises(ce.ContextEditingError):
        ce.validate_config(bad)


def test_ce_validate_config_rejects_unknown_strategy():
    bad = {"edits": [{"type": "unknown_x"}]}
    with pytest.raises(ce.ContextEditingError):
        ce.validate_config(bad)


def test_ce_env_override_disables(monkeypatch):
    monkeypatch.setenv("CONTEXT_MGMT_DISABLE", "1")
    assert ce.env_override_config() is None
    monkeypatch.setenv("CONTEXT_MGMT_DISABLE", "0")
    assert ce.env_override_config() is not None


def test_ce_extra_protected_tools_merged():
    cfg = ce.default_context_management_config(
        extra_protected_tools=["web_search", "memory"],
    )
    clear = next(e for e in cfg["edits"] if e["type"] == ce.STRATEGY_CLEAR_TOOL_USES)
    assert "web_search" in clear["exclude_tools"]
    assert "memory" in clear["exclude_tools"]
    # memory が重複しない
    assert clear["exclude_tools"].count("memory") == 1


# ══════════════════════════════════════════════════════════════════════
# Subagent Memory store
# ══════════════════════════════════════════════════════════════════════


def test_sm_record_handoff_writes_file(isolated_root):
    store = sm.SubagentMemoryStore()
    out = store.record_handoff(
        source="mary", target="devon", message="please implement X",
    )
    assert out["source"] == "mary"
    assert out["target"] == "devon"
    assert out["path"].startswith("/memories/subagent/devon/handoff/")
    assert out["size"] > 0


def test_sm_preload_for_returns_snippets(isolated_root):
    store = sm.SubagentMemoryStore()
    store.record_handoff("mary", "devon", "task A")
    store.record_handoff("mary", "devon", "task B")
    snippets = store.preload_for("devon", limit=5)
    assert len(snippets) == 2
    assert all("content" in s for s in snippets)


def test_sm_preload_newest_first(isolated_root):
    store = sm.SubagentMemoryStore()
    store.record_handoff("mary", "devon", "first")
    time.sleep(0.01)
    store.record_handoff("mary", "devon", "second")
    snippets = store.preload_for("devon", limit=5)
    # newest first
    assert "second" in snippets[0]["content"]


def test_sm_workspace_scope_isolation(isolated_root):
    store = sm.SubagentMemoryStore()
    store.record_handoff("mary", "devon", "ws1 task", workspace_id=1)
    store.record_handoff("mary", "devon", "ws2 task", workspace_id=2)
    s1 = store.preload_for("devon", workspace_id=1)
    s2 = store.preload_for("devon", workspace_id=2)
    assert len(s1) == 1 and "ws1 task" in s1[0]["content"]
    assert len(s2) == 1 and "ws2 task" in s2[0]["content"]


def test_sm_clear_persona(isolated_root):
    store = sm.SubagentMemoryStore()
    store.record_handoff("mary", "devon", "x")
    store.record_handoff("mary", "devon", "y")
    n = store.clear_persona("devon")
    assert n == 2
    assert store.preload_for("devon") == []


def test_sm_rejects_invalid_persona(isolated_root):
    store = sm.SubagentMemoryStore()
    for bad in ("", "  ", "name with space", "name/slash", "a" * 101):
        with pytest.raises(sm.SubagentMemoryError):
            store.record_handoff(bad, "devon", "x")


def test_sm_rejects_empty_message(isolated_root):
    store = sm.SubagentMemoryStore()
    with pytest.raises(sm.SubagentMemoryError):
        store.record_handoff("mary", "devon", "")


def test_sm_rejects_invalid_workspace_id(isolated_root):
    store = sm.SubagentMemoryStore()
    with pytest.raises(sm.SubagentMemoryError):
        store.record_handoff("mary", "devon", "x", workspace_id=0)
    with pytest.raises(sm.SubagentMemoryError):
        store.record_handoff("mary", "devon", "x", workspace_id="1")  # type: ignore[arg-type]


def test_sm_preload_empty_when_no_handoff(isolated_root):
    store = sm.SubagentMemoryStore()
    assert store.preload_for("devon") == []


def test_sm_clear_returns_zero_when_no_persona(isolated_root):
    store = sm.SubagentMemoryStore()
    assert store.clear_persona("devon") == 0


# ══════════════════════════════════════════════════════════════════════
# REST endpoint smoke (4xx form 統一 + happy path)
# ══════════════════════════════════════════════════════════════════════


def test_endpoint_tool_spec(client):
    r = client.get("/api/anthropic-memory/tool-spec")
    assert r.status_code == 200
    assert r.json() == {"type": "memory_20250818", "name": "memory"}


def test_endpoint_context_editing_default(client):
    r = client.get("/api/anthropic-memory/context-editing")
    assert r.status_code == 200
    body = r.json()
    assert "context_management" in body
    assert "betas" in body
    assert "context-management-2025-06-27" in body["betas"]


def test_endpoint_memory_command_create_view(client, isolated_root):
    r = client.post(
        "/api/anthropic-memory/create",
        json={"path": "/memories/notes.txt", "file_text": "hi"},
    )
    assert r.status_code == 200
    assert "created" in r.json()["result"]
    r2 = client.post(
        "/api/anthropic-memory/view",
        json={"path": "/memories/notes.txt"},
    )
    assert r2.status_code == 200
    assert "hi" in r2.json()["result"]


def test_endpoint_memory_unknown_command_400(client):
    r = client.post("/api/anthropic-memory/bogus", json={"path": "/memories/x"})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == "memory.invalid"


def test_endpoint_memory_invalid_json_400(client):
    r = client.post(
        "/api/anthropic-memory/view",
        content=b"not json",
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "memory.invalid"


def test_endpoint_memory_path_traversal_400(client, isolated_root):
    r = client.post(
        "/api/anthropic-memory/view",
        json={"path": "/memories/../escape"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "memory.invalid"


def test_endpoint_memory_view_missing_404(client, isolated_root):
    r = client.post(
        "/api/anthropic-memory/view",
        json={"path": "/memories/never-existed.txt"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "memory.not_found"


def test_endpoint_memory_create_duplicate_409(client, isolated_root):
    client.post(
        "/api/anthropic-memory/create",
        json={"path": "/memories/dup.txt", "file_text": "a"},
    )
    r = client.post(
        "/api/anthropic-memory/create",
        json={"path": "/memories/dup.txt", "file_text": "b"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "memory.conflict"


def test_endpoint_subagent_handoff_and_preload(client, isolated_root):
    r = client.post(
        "/api/anthropic-memory/subagent/handoff",
        json={"source": "mary", "target": "devon", "message": "implement Z"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "mary"
    assert body["target"] == "devon"

    r2 = client.get("/api/anthropic-memory/subagent/devon")
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["count"] == 1
    assert "implement Z" in body2["snippets"][0]["content"]


def test_endpoint_subagent_handoff_invalid_persona_400(client, isolated_root):
    r = client.post(
        "/api/anthropic-memory/subagent/handoff",
        json={"source": "", "target": "devon", "message": "x"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "memory.subagent.invalid"


def test_endpoint_subagent_preload_invalid_workspace_id_400(client, isolated_root):
    r = client.get(
        "/api/anthropic-memory/subagent/devon",
        params={"workspace_id": "abc"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "memory.invalid"


def test_endpoint_4xx_form_uniformity(client, isolated_root):
    """ADR-012 AC-4: 全 4xx response が {detail:{code,message}}."""
    cases = [
        ("POST", "/api/anthropic-memory/bogus", {"path": "/memories/x"}, 400),
        ("POST", "/api/anthropic-memory/view", {"path": "/etc/passwd"}, 400),
        ("POST", "/api/anthropic-memory/view",
         {"path": "/memories/never.txt"}, 404),
        ("POST", "/api/anthropic-memory/subagent/handoff",
         {"source": "", "target": "devon", "message": "x"}, 400),
    ]
    for _, path, body, expected in cases:
        r = client.post(path, json=body)
        assert r.status_code == expected, f"{path}: {r.status_code}: {r.text}"
        detail = r.json()["detail"]
        assert isinstance(detail, dict)
        assert detail.get("code", "").startswith("memory")
        assert isinstance(detail.get("message", ""), str) and detail["message"]


# ══════════════════════════════════════════════════════════════════════
# ADR-012 documentation invariants
# ══════════════════════════════════════════════════════════════════════


def test_adr_012_file_exists_and_documents_decisions():
    adr = (
        Path(__file__).resolve().parents[2]
        / "docs" / "decisions"
        / "ADR-012-anthropic-memory-tool-adoption.md"
    )
    assert adr.exists(), "ADR-012 must exist"
    text = adr.read_text(encoding="utf-8")
    for key in (
        "Memory Tool", "Context Editing", "Subagent Memory",
        "memory_20250818", "clear_tool_uses_20250919", "compact_20260112",
        "ADR-010",
    ):
        assert key in text, f"ADR-012 must mention {key}"


def test_module_docstrings_documents_adr_012():
    assert "ADR-012" in (amt.__doc__ or "")
    assert "ADR-012" in (ce.__doc__ or "")
    assert "ADR-012" in (sm.__doc__ or "")
