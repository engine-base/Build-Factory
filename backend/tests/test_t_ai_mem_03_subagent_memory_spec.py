"""T-AI-MEM-03: Subagent Memory store — 4 AC 1:1 spec test (dedicated).

Audit doc: docs/audit/2026-05-13_v2/T-AI-MEM-03.md

このファイルは tickets.json#T-AI-MEM-03 の 4 EARS AC × 24 sub-clause を
1:1 で検証する dedicated 仕様テスト. 既存の test_adr_012_anthropic_memory_tool.py
は subagent_memory も扱うが mixed (Memory Tool 全体). 本 file は AC 1:1 のみに
集中して spec drift を機械的に検出する.

AC mapping:
  AC-1 UBIQUITOUS    : SubagentMemoryStore + 4 method (record_handoff /
                       preload_for / list_persona_files / clear_persona) +
                       MemoryToolHandler 委譲 + 2 scope (user / workspace_id).
  AC-2 EVENT-DRIVEN  : record_handoff は path 形式 /memories/subagent/<persona>/
                       handoff/<ts>-from-<source>.md を 2 秒以内で書き
                       preload_for で newest-first 取得.
  AC-3 STATE-DRIVEN  : 2 scope coexist + isolate / handoff_service.py 不変 +
                       no import cycle.
  AC-4 UNWANTED      : invalid persona / workspace_id / message → reject +
                       4xx {detail:{code,message}} via REST + state mutate なし.
"""
from __future__ import annotations

import inspect
import os
import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import anthropic_memory_tool as amt
from services import subagent_memory as sm


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


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
def store(isolated_root):
    return sm.SubagentMemoryStore()


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS: SubagentMemoryStore + 4 method + MemoryToolHandler 委譲 + 2 scope
# ══════════════════════════════════════════════════════════════════════


def test_ac1_class_exists_and_signature():
    """1.1: SubagentMemoryStore class 提供 (dataclass / handler 引数受容)."""
    assert hasattr(sm, "SubagentMemoryStore")
    cls = sm.SubagentMemoryStore
    assert inspect.isclass(cls)
    sig = inspect.signature(cls)
    assert "handler" in sig.parameters
    # default handler=None で生成可能
    obj = cls()
    assert isinstance(obj, sm.SubagentMemoryStore)


def test_ac1_record_handoff_signature(store):
    """1.2: record_handoff method 提供 + 必須 / オプション引数."""
    sig = inspect.signature(store.record_handoff)
    params = sig.parameters
    assert {"source", "target", "message"}.issubset(params.keys())
    for opt in ("context", "workspace_id", "session_id"):
        assert opt in params, f"optional kwarg {opt} 欠落"


def test_ac1_preload_for_signature(store):
    """1.3: preload_for method 提供 + workspace_id / limit kwarg."""
    sig = inspect.signature(store.preload_for)
    assert "target" in sig.parameters
    assert "workspace_id" in sig.parameters
    assert "limit" in sig.parameters


def test_ac1_list_persona_files_signature(store):
    """1.4: list_persona_files method 提供 (G2 dedicated test)."""
    sig = inspect.signature(store.list_persona_files)
    assert "persona" in sig.parameters
    assert "workspace_id" in sig.parameters
    assert "limit" in sig.parameters


def test_ac1_clear_persona_signature(store):
    """1.5: clear_persona method 提供."""
    sig = inspect.signature(store.clear_persona)
    assert "persona" in sig.parameters
    assert "workspace_id" in sig.parameters


def test_ac1_backed_by_memory_tool_handler(store):
    """1.6: backed by anthropic_memory_tool.MemoryToolHandler (G3 委譲 test)."""
    # default handler は MemoryToolHandler instance を生成
    h = store._h()
    assert isinstance(h, amt.MemoryToolHandler), (
        "SubagentMemoryStore must delegate to MemoryToolHandler "
        "(AC-1 'backed by anthropic_memory_tool.MemoryToolHandler')"
    )
    # 明示 inject も受け取る
    explicit = amt.MemoryToolHandler()
    s2 = sm.SubagentMemoryStore(handler=explicit)
    assert s2._h() is explicit
    # SUBAGENT_VIRTUAL_PREFIX が MEMORY_ROOT_PREFIX 配下にある
    assert sm.SUBAGENT_VIRTUAL_PREFIX.startswith(amt.MEMORY_ROOT_PREFIX)


def test_ac1_user_scope_path(store):
    """1.7: user scope (workspace_id=None) は /memories/subagent/<persona>."""
    out = store.record_handoff(
        "mary", "devon", "user-scope task", workspace_id=None,
    )
    assert out["path"].startswith("/memories/subagent/devon/handoff/")
    assert "/ws-" not in out["path"]
    assert out["workspace_id"] is None


def test_ac1_workspace_scope_path(store):
    """1.8: workspace_id 付きは /memories/subagent/ws-<id>/<persona>/."""
    out = store.record_handoff(
        "mary", "devon", "ws task", workspace_id=42,
    )
    assert out["path"].startswith("/memories/subagent/ws-42/devon/handoff/")
    assert out["workspace_id"] == 42


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: path format + 2 秒以内 + newest-first
# ══════════════════════════════════════════════════════════════════════


_USER_PATH_RE = re.compile(
    r"^/memories/subagent/(?P<persona>[A-Za-z0-9_\-]+)/handoff/"
    r"(?P<ts>\d+)(?:-\d+)?-from-(?P<source>[A-Za-z0-9_\-]+)\.md$"
)
_WS_PATH_RE = re.compile(
    r"^/memories/subagent/ws-(?P<ws>\d+)/(?P<persona>[A-Za-z0-9_\-]+)/handoff/"
    r"(?P<ts>\d+)(?:-\d+)?-from-(?P<source>[A-Za-z0-9_\-]+)\.md$"
)


def test_ac2_path_format_exact_regex(store):
    """2.1: path format 完全一致 (G5; 旧 test は startswith のみで弱かった)."""
    out = store.record_handoff("mary", "devon", "format check")
    m = _USER_PATH_RE.match(out["path"])
    assert m is not None, (
        f"path {out['path']!r} does not match spec format "
        f"/memories/subagent/<persona>/handoff/<ts>-from-<source>.md"
    )
    assert m.group("persona") == "devon"
    assert m.group("source") == "mary"
    assert int(m.group("ts")) > 0


def test_ac2_workspace_path_format_exact_regex(store):
    """2.4: workspace_id 付き path format 完全一致 (G5)."""
    out = store.record_handoff("mary", "devon", "format check", workspace_id=7)
    m = _WS_PATH_RE.match(out["path"])
    assert m is not None, (
        f"path {out['path']!r} does not match workspace spec format"
    )
    assert m.group("ws") == "7"
    assert m.group("persona") == "devon"
    assert m.group("source") == "mary"


def test_ac2_record_handoff_within_2sec(store):
    """2.2: record_handoff は 2 秒以内 (G6 timing test)."""
    t0 = time.perf_counter()
    out = store.record_handoff("mary", "devon", "timing check")
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0, f"record_handoff took {elapsed:.3f}s (spec: < 2s)"
    assert out["path"]


def test_ac2_preload_newest_first_dedicated(store):
    """2.3: preload_for は newest-first (1:1 dedicated)."""
    store.record_handoff("mary", "devon", "alpha")
    time.sleep(0.01)
    store.record_handoff("mary", "devon", "beta")
    time.sleep(0.01)
    store.record_handoff("mary", "devon", "gamma")
    snippets = store.preload_for("devon", limit=5)
    assert len(snippets) == 3
    # newest first: gamma > beta > alpha
    assert "gamma" in snippets[0]["content"]
    assert "beta" in snippets[1]["content"]
    assert "alpha" in snippets[2]["content"]


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: 2 scope coexist + handoff_service 不変 + no import cycle
# ══════════════════════════════════════════════════════════════════════


def test_ac3_two_scopes_coexist_isolated(store):
    """3.1: user scope + workspace scope が同時存在し isolate される."""
    store.record_handoff("mary", "devon", "user task")
    store.record_handoff("mary", "devon", "ws1 task", workspace_id=1)
    store.record_handoff("mary", "devon", "ws2 task", workspace_id=2)
    user_snips = store.preload_for("devon", workspace_id=None)
    ws1_snips = store.preload_for("devon", workspace_id=1)
    ws2_snips = store.preload_for("devon", workspace_id=2)
    assert len(user_snips) == 1 and "user task" in user_snips[0]["content"]
    assert len(ws1_snips) == 1 and "ws1 task" in ws1_snips[0]["content"]
    assert len(ws2_snips) == 1 and "ws2 task" in ws2_snips[0]["content"]


def test_ac3_workspace_scope_isolation_basic(store):
    """3.2: workspace 間の漏れがない (positive case)."""
    store.record_handoff("mary", "devon", "alpha", workspace_id=1)
    store.record_handoff("mary", "devon", "beta", workspace_id=2)
    s1 = store.preload_for("devon", workspace_id=1)
    s2 = store.preload_for("devon", workspace_id=2)
    assert len(s1) == 1 and "alpha" in s1[0]["content"]
    assert len(s2) == 1 and "beta" in s2[0]["content"]
    # 双方向に漏れていない
    assert "beta" not in s1[0]["content"]
    assert "alpha" not in s2[0]["content"]


def test_ac3_no_leak_user_to_workspace_and_vice_versa(store):
    """3.3: user scope と workspace scope の双方向 leak negative (G7)."""
    store.record_handoff("mary", "devon", "user-only", workspace_id=None)
    store.record_handoff("mary", "devon", "ws1-only", workspace_id=1)
    user_snips = store.preload_for("devon", workspace_id=None)
    ws1_snips = store.preload_for("devon", workspace_id=1)
    # user → workspace に漏れない
    assert all("ws1-only" not in s["content"] for s in user_snips), (
        "user scope に workspace memory が漏れている"
    )
    # workspace → user に漏れない
    assert all("user-only" not in s["content"] for s in ws1_snips), (
        "workspace scope に user memory が漏れている"
    )


def test_ac3_handoff_service_module_unchanged():
    """3.4: handoff_service.py が無改変 (T-M30-03 G9 相当, G8)."""
    try:
        from services import handoff_service as hs
    except ImportError:
        pytest.skip("handoff_service 未存在 (Phase 1 で OK)")
    # subagent_memory が export している記号が handoff_service にも存在しない
    # (subagent_memory が handoff_service に副作用をかけていないことの証拠)
    sm_symbols = {n for n in dir(sm) if not n.startswith("_")}
    hs_symbols = {n for n in dir(hs) if not n.startswith("_")}
    overlap = sm_symbols & hs_symbols & {
        "SubagentMemoryStore", "SubagentMemoryError", "record_handoff",
        "preload_for", "list_persona_files", "clear_persona",
    }
    assert not overlap, (
        f"handoff_service が subagent_memory の symbol を export している: {overlap}"
    )


def test_ac3_no_import_cycle_with_handoff_service():
    """3.5: subagent_memory が handoff_service を import していない (G9)."""
    # source 文字列を直接 grep して import statement の不在を確認
    src_path = Path(sm.__file__)
    src_text = src_path.read_text(encoding="utf-8")
    forbidden_imports = [
        "from services.handoff_service",
        "from services import handoff_service",
        "import services.handoff_service",
    ]
    for line in src_text.splitlines():
        # 行頭が # でないコード行のみチェック
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        for fi in forbidden_imports:
            assert fi not in stripped, (
                f"subagent_memory が {fi!r} で handoff_service を import している "
                f"(AC-3 'no import cycle' 違反): {stripped!r}"
            )
    # NOTE: importlib.reload(sm) は SubagentMemoryError クラスを再定義し,
    # 同 process 内で先読み済の router (except SubagentMemoryError) が
    # 後続 REST 4xx を 500 化してしまうので意図的に避ける.
    # source 文字列の grep + 実 import (sm が既に import 済) で十分.


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: invalid input reject + 4xx {detail:{code,message}} + no state mutate
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("bad", [
    "name with space", "name/slash", "name\\back", "name?q", "name#hash",
])
def test_ac4_persona_non_alnum_rejected(store, bad):
    """4.1: persona 非 alnum を reject."""
    with pytest.raises(sm.SubagentMemoryError):
        store.record_handoff(bad, "devon", "x")


@pytest.mark.parametrize("bad", ["", "  ", "\n", "\t"])
def test_ac4_persona_empty_rejected(store, bad):
    """4.2: persona empty / 空白のみ を reject."""
    with pytest.raises(sm.SubagentMemoryError):
        store.record_handoff(bad, "devon", "x")


def test_ac4_persona_too_long_rejected(store):
    """4.3: persona > 100 chars を reject."""
    with pytest.raises(sm.SubagentMemoryError):
        store.record_handoff("a" * 101, "devon", "x")
    # boundary: 100 chars は OK
    store.record_handoff("a" * 100, "devon", "x")


@pytest.mark.parametrize("bad", [0, -1, -100])
def test_ac4_workspace_id_zero_or_negative_rejected(store, bad):
    """4.4: workspace_id <= 0 を reject."""
    with pytest.raises(sm.SubagentMemoryError):
        store.record_handoff("mary", "devon", "x", workspace_id=bad)


@pytest.mark.parametrize("bad", [True, False, "1", 1.0, [1], {"id": 1}])
def test_ac4_workspace_id_wrong_type_rejected(store, bad):
    """4.5: workspace_id non-int (bool / str / float / list / dict) を reject."""
    with pytest.raises(sm.SubagentMemoryError):
        store.record_handoff("mary", "devon", "x", workspace_id=bad)


@pytest.mark.parametrize("bad", ["", "   ", "\t", "\n"])
def test_ac4_empty_message_rejected(store, bad):
    """4.6: message empty / 空白のみ を reject."""
    with pytest.raises(sm.SubagentMemoryError):
        store.record_handoff("mary", "devon", bad)


# AC-4.7: REST 4xx {detail:{code,message}} (G10)


def _post_subagent_handoff(client, body: dict):
    return client.post("/api/anthropic-memory/subagent/handoff", json=body)


def test_ac4_rest_endpoint_returns_4xx_structured_invalid_persona(client, isolated_root):
    """4.7a: invalid persona → 400 + {detail:{code,message}}."""
    r = _post_subagent_handoff(client, {
        "source": "name with space", "target": "devon", "message": "x",
    })
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert "code" in detail and "message" in detail
    assert detail["code"] == "memory.subagent.invalid"


def test_ac4_rest_endpoint_returns_4xx_structured_empty_message(client, isolated_root):
    """4.7b: empty message → 400 + {detail:{code,message}}."""
    r = _post_subagent_handoff(client, {
        "source": "mary", "target": "devon", "message": "",
    })
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "memory.subagent.invalid"


def test_ac4_rest_endpoint_returns_4xx_structured_invalid_workspace(client, isolated_root):
    """4.7c: invalid workspace_id → 400 + {detail:{code,message}}."""
    r = _post_subagent_handoff(client, {
        "source": "mary", "target": "devon", "message": "x", "workspace_id": 0,
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "memory.subagent.invalid"


def test_ac4_rest_endpoint_returns_4xx_structured_non_json(client, isolated_root):
    """4.7d: non-JSON body → 400 + {detail:{code,message}}."""
    r = client.post(
        "/api/anthropic-memory/subagent/handoff",
        content=b"not json",
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert "code" in detail and "message" in detail


# AC-4.8: state mutate なし (G11)


@pytest.mark.parametrize("bad_payload", [
    {"source": "name with space", "target": "devon", "message": "x"},
    {"source": "mary", "target": "devon", "message": ""},
    {"source": "mary", "target": "devon", "message": "x", "workspace_id": 0},
    {"source": "mary", "target": "name/slash", "message": "x"},
])
def test_ac4_invalid_input_does_not_mutate_store(store, bad_payload):
    """4.8: invalid input で persistent state mutate なし (G11)."""
    # 事前 file 数 (devon scope)
    before_user = store.list_persona_files("devon", workspace_id=None, limit=200)
    before_ws = store.list_persona_files("devon", workspace_id=1, limit=200)
    # invalid 呼出
    with pytest.raises(sm.SubagentMemoryError):
        store.record_handoff(**bad_payload)
    after_user = store.list_persona_files("devon", workspace_id=None, limit=200)
    after_ws = store.list_persona_files("devon", workspace_id=1, limit=200)
    assert before_user == after_user, (
        f"invalid input {bad_payload!r} で user scope に file 増えた "
        f"(before={before_user}, after={after_user})"
    )
    assert before_ws == after_ws, (
        f"invalid input {bad_payload!r} で workspace scope に file 増えた "
        f"(before={before_ws}, after={after_ws})"
    )


# ══════════════════════════════════════════════════════════════════════
# Audit doc traceability
# ══════════════════════════════════════════════════════════════════════


def test_audit_doc_exists_and_links_to_this_file():
    """audit doc が存在し本 test file を 1:1 で参照していること."""
    from pathlib import Path
    repo = Path(__file__).resolve().parents[2]
    audit_path = repo / "docs" / "audit" / "2026-05-13_v2" / "T-AI-MEM-03.md"
    assert audit_path.exists(), (
        f"audit doc 未存在: {audit_path} "
        "(pre-flight workflow Step 1 違反)"
    )
    text = audit_path.read_text(encoding="utf-8")
    assert "T-AI-MEM-03" in text
    assert "test_t_ai_mem_03_subagent_memory_spec.py" in text or \
           "test_ac1_class_exists_and_signature" in text
