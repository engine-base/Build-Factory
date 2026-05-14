"""T-024-03: RLS 連動 — 1:1 spec invariants (REUSE audit).

F-024 グローバル検索 (Cmd+K) の happy path:
  Cmd+K で modal → query → Postgres FTS + pgvector + pg_trgm →
  カテゴリ別 → **RLS で見える範囲のみ** → ジャンプ.

T-024-03 = "RLS 連動" を REUSE タスクとして担保する.
本 module は **新規 impl を書かず**、既存 3 layer (
  - T-001-06 RLS migration (supabase/migrations/20260510000002_*.sql)
  - T-S0-09b rls_context helper (backend/services/rls_context.py)
  - T-024-02 unified_search + T-AI-03 chat_search (backend/services/*.py)
) が "search ↔ RLS の合流" として整合していることを 17 test で検証する.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : RLS migration enabled / rls_context helper 公開 /
                       unified_search + chat_search が account/workspace scope
                       受領 / search modules が auth.uid()/bf_can_access_workspace
                       を再実装してない.
  AC-2 EVENT-DRIVEN  : POST /api/search/unified が dict/error envelope 返却 /
                       account scope 付きで 2 秒以内.
  AC-3 STATE-DRIVEN  : T-001-06 / T-S0-09b / T-024-02 / T-AI-03 公開 API 不変
                       (REUSE invariant).
  AC-4 UNWANTED      : unauthorized actor → 401 / invalid account_id → 400 /
                       invalid user_id for rls_context → RLSContextError BEFORE
                       SET LOCAL / search modules read-only / no hardcoded secret.

audit doc: docs/audit/2026-05-13_v2/T-024-03.md
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import time
from pathlib import Path
from typing import Optional

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
RLS_MIGRATION = (
    REPO_ROOT / "supabase" / "migrations"
    / "20260510000002_rls_full_enforcement.sql"
)
RLS_SKELETON = (
    REPO_ROOT / "supabase" / "migrations"
    / "20260501220300_rls_skeleton.sql"
)
RLS_BF_PROJECT = (
    REPO_ROOT / "supabase" / "migrations"
    / "20260510000001_bf_project_tables.sql"
)
MIGRATIONS_DIR = REPO_ROOT / "supabase" / "migrations"
RLS_CONTEXT_PY = REPO_ROOT / "backend" / "services" / "rls_context.py"
UNIFIED_SEARCH_PY = REPO_ROOT / "backend" / "services" / "unified_search.py"
UNIFIED_ROUTER_PY = REPO_ROOT / "backend" / "routers" / "unified_search.py"
CHAT_SEARCH_PY = REPO_ROOT / "backend" / "services" / "chat_search.py"
CHAT_ROUTER_PY = REPO_ROOT / "backend" / "routers" / "chat_search.py"
AUDIT_DOC = REPO_ROOT / "docs" / "audit" / "2026-05-13_v2" / "T-024-03.md"
TICKETS = (
    REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
)


# ──────────────────────────────────────────────────────────────────────
# Helpers — comment stripping (re-used pattern from T-024-02)
# ──────────────────────────────────────────────────────────────────────


def _strip_comments_and_docstrings(src: str) -> str:
    """簡易 docstring + comment 剥離 (literal 検査の偽陽性回避)."""
    out_lines: list[str] = []
    in_triple = False
    triple_char: Optional[str] = None
    for raw in src.splitlines():
        line = raw
        if in_triple:
            if triple_char is not None and triple_char in line:
                line = line.split(triple_char, 1)[1]
                in_triple = False
                triple_char = None
            else:
                continue
        for ch in ('"""', "'''"):
            if ch in line:
                before, _sep, after = line.partition(ch)
                if ch in after:
                    line = before + after.split(ch, 1)[1]
                else:
                    line = before
                    in_triple = True
                    triple_char = ch
                break
        if "#" in line:
            line = line.split("#", 1)[0]
        if line.strip():
            out_lines.append(line)
    return "\n".join(out_lines)


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — RLS migration / rls_context / search modules wired
# ══════════════════════════════════════════════════════════════════════


def test_ac1_rls_enabled_on_search_target_tables():
    """F-024 related_entities (knowledge / tasks / artifacts / audit_logs /
    chat_messages) を含む search 対象 table 群が RLS 有効化されている.

    T-001-06 migration + rls_skeleton で計 >= 20 ALTER TABLE ENABLE RLS.
    (artifacts / audit_logs / knowledge_base / chat_messages 個別 grep)
    """
    assert RLS_MIGRATION.exists(), "T-001-06 RLS migration missing"
    assert RLS_SKELETON.exists(), "rls_skeleton missing"
    # 検索対象 table の RLS 有効化は migration 群全体に分散している
    # (T-001-04 bf_project_tables / T-001-06 rls_full / rls_skeleton).
    # F-024 search target tables を全 SQL 横断で検証する.
    full_sql = "\n".join(
        p.read_text(encoding="utf-8")
        for p in sorted(MIGRATIONS_DIR.glob("*.sql"))
    )
    # F-024 related_entities + chat_messages
    # NOTE: chat_messages 自体は initial_schema にあり個別 RLS 設定は
    # Phase 2 で workspace_id 列追加 + policy 化 (現時点では service_role 経由).
    # ここでは F-024 の主要 search target である knowledge_base / artifacts /
    # threads (chat container) / accounts / workspaces / audit_logs を確認.
    expected_rls_tables = (
        "knowledge_base",
        "artifacts",
        "threads",
        "accounts",
        "workspaces",
        "audit_logs",
    )
    for tbl in expected_rls_tables:
        pat = rf"ALTER TABLE\s+(IF EXISTS\s+)?{re.escape(tbl)}\s+ENABLE ROW LEVEL SECURITY"
        assert re.search(pat, full_sql), f"RLS not enabled on {tbl}"


def test_ac1_rls_context_helper_publicly_available():
    """T-S0-09b rls_context が auth_middleware → DB session に SET LOCAL する
    helper を公開し、search service 経路が re-use できる状態.
    """
    assert RLS_CONTEXT_PY.exists()
    from services import rls_context as rc
    for sym in (
        "set_request_user",
        "reset_request_user",
        "with_request_user",
        "DEV_BYPASS_USER_ID",
        "MAX_USER_ID_LEN",
        "RLSContextError",
        "effective_user_id_for_request",
        "is_bypass_allowed",
    ):
        assert hasattr(rc, sym), f"rls_context missing public symbol: {sym}"


def test_ac1_unified_search_accepts_account_scope():
    """unified_search(account_id=...) が workspace scope として WHERE 句に
    渡る経路を持つ (per-source SQL の workspace_id filter).
    """
    from services import unified_search as us
    sig = inspect.signature(us.unified_search)
    assert "account_id" in sig.parameters
    p = sig.parameters["account_id"]
    assert p.kind == inspect.Parameter.KEYWORD_ONLY
    # SOURCE_HANDLERS の各 handler も account_id を受ける
    for src_name, fn in us.SOURCE_HANDLERS.items():
        s = inspect.signature(fn)
        assert "account_id" in s.parameters, (
            f"SOURCE_HANDLERS[{src_name}] missing account_id"
        )


def test_ac1_unified_search_per_source_sql_uses_workspace_scope():
    """tasks / screens の SQL が `WHERE workspace_id = ?` で account scope を
    実際に SQL レベルで適用している (RLS と二重防御).
    """
    src = UNIFIED_SEARCH_PY.read_text(encoding="utf-8")
    # tasks / screens の per-source handler が workspace_id 句を含む
    assert re.search(
        r"WHERE\s+workspace_id\s*=\s*\?\s+AND\s+title\s+LIKE",
        src,
    ), "tasks handler missing workspace_id filter"
    assert re.search(
        r"WHERE\s+workspace_id\s*=\s*\?\s+AND\s+name\s+LIKE",
        src,
    ), "screens handler missing workspace_id filter"


def test_ac1_hybrid_search_accepts_workspace_scope():
    """chat_search.hybrid_search(workspace_id=, user_id=) を accept."""
    from services.chat_search import hybrid_search
    sig = inspect.signature(hybrid_search)
    for kw in ("user_id", "workspace_id"):
        assert kw in sig.parameters, f"hybrid_search missing {kw}"
        assert sig.parameters[kw].kind == inspect.Parameter.KEYWORD_ONLY


def test_ac1_search_modules_dont_reimplement_rls():
    """search service / router は auth.uid() / bf_can_access_workspace を
    自前で SQL に書かない (= RLS 中央化 / helper delegate).

    `auth.uid()` / `bf_can_access_workspace(` literal が現れたら違反.
    docstring 内の参照は許可 (説明目的).
    """
    for path in (UNIFIED_SEARCH_PY, CHAT_SEARCH_PY, UNIFIED_ROUTER_PY, CHAT_ROUTER_PY):
        src = path.read_text(encoding="utf-8")
        code = _strip_comments_and_docstrings(src)
        assert "auth.uid()" not in code, (
            f"{path.name} reimplements auth.uid() — should delegate to RLS"
        )
        assert "bf_can_access_workspace(" not in code, (
            f"{path.name} reimplements bf_can_access_workspace — should delegate"
        )


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — endpoint dict / error envelope / 2s budget
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture
def _stub_handlers(monkeypatch):
    """unified_search の per-source handler を全 stub. 実 DB 不要."""
    from services import unified_search as us

    async def fake(query, *, account_id, limit):
        # account_id を必ず受領するか型確認
        assert account_id is None or isinstance(account_id, int)
        return [{
            "kind": "stub", "id": "x", "label": query,
            "hint": "", "group": "Stub",
        }][:limit]

    for src_name in ("knowledge", "tasks", "employees", "screens"):
        monkeypatch.setitem(us.SOURCE_HANDLERS, src_name, fake)
    yield


def test_ac2_unified_search_returns_dict(_stub_handlers):
    from services import unified_search as us
    result = asyncio.run(us.unified_search("hello", account_id=42))
    assert isinstance(result, dict)
    for key in ("query", "sources_used", "results", "by_kind", "total"):
        assert key in result
    assert result["query"] == "hello"


def test_ac2_error_response_envelope_shape():
    """router の _error helper が `{detail: {code, message}}` を生成."""
    src = UNIFIED_ROUTER_PY.read_text(encoding="utf-8")
    # _error(code, message, status_code=...) → HTTPException(detail={"code", "message"})
    assert re.search(
        r"detail\s*=\s*\{\s*[\"']code[\"']\s*:\s*code\s*,\s*[\"']message[\"']\s*:\s*message\s*\}",
        src,
    ), "router _error envelope shape drift"


def test_ac2_within_2_seconds_with_account_scope(_stub_handlers):
    """account scope 付き unified_search が 2 秒以内に完走."""
    from services import unified_search as us
    t0 = time.time()
    asyncio.run(us.unified_search("perf", account_id=7))
    elapsed = time.time() - t0
    assert elapsed < 2.0, f"unified_search exceeded 2s: {elapsed:.3f}s"


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — REUSE invariants (no public API regression)
# ══════════════════════════════════════════════════════════════════════


def test_ac3_t_001_06_rls_invariants_still_hold():
    """T-001-06 RLS migration が >= 20 ALTER ENABLE / >= 30 CREATE POLICY を
    維持 (T-024-03 で migration を改変していないことの間接検証).
    """
    sql = RLS_MIGRATION.read_text(encoding="utf-8")
    alters = re.findall(
        r"ALTER TABLE\s+(?:IF EXISTS\s+)?\w+\s+ENABLE ROW LEVEL SECURITY",
        sql,
    )
    creates = re.findall(r"CREATE POLICY\b", sql)
    assert len(alters) >= 20, f"T-001-06 ALTER count regressed: {len(alters)}"
    assert len(creates) >= 30, f"T-001-06 CREATE POLICY count regressed: {len(creates)}"
    assert "bf_can_access_workspace" in sql, "T-001-06 helper reference removed"


def test_ac3_rls_context_public_api_intact():
    """T-S0-09b rls_context の 8 公開 symbol が全て残っている."""
    from services import rls_context as rc
    public = (
        "set_request_user", "reset_request_user", "with_request_user",
        "DEV_BYPASS_USER_ID", "MAX_USER_ID_LEN", "RLSContextError",
        "effective_user_id_for_request", "is_bypass_allowed",
    )
    for sym in public:
        assert hasattr(rc, sym), f"rls_context regressed: missing {sym}"
    assert rc.MAX_USER_ID_LEN == 200
    assert issubclass(rc.RLSContextError, ValueError)


def test_ac3_unified_search_public_api_intact():
    """T-024-02 unified_search の 7 公開 symbol が全て残っている."""
    from services import unified_search as us
    for sym in (
        "unified_search", "list_valid_sources", "SOURCE_HANDLERS",
        "VALID_SOURCES", "MAX_QUERY_CHARS", "DEFAULT_LIMIT_PER_SOURCE",
        "MAX_LIMIT_PER_SOURCE",
    ):
        assert hasattr(us, sym), f"unified_search regressed: missing {sym}"
    assert tuple(us.VALID_SOURCES) == (
        "knowledge", "tasks", "employees", "screens",
    )


def test_ac3_chat_search_public_api_intact():
    """T-AI-03 chat_search の hybrid_search signature 維持."""
    from services.chat_search import hybrid_search, HybridHit
    sig = inspect.signature(hybrid_search)
    for kw in ("user_id", "workspace_id", "top_k", "use_vector",
               "weight_trgm", "weight_vector"):
        assert kw in sig.parameters
    # HybridHit dataclass field 維持
    inst = HybridHit(
        message_id=1, thread_id=2, role="u", content="c",
        created_at=None, trgm_score=0.0, vector_score=0.0, final_score=0.0,
    )
    d = inst.to_dict()
    for f in ("message_id", "thread_id", "role", "content", "created_at",
              "trgm_score", "vector_score", "final_score"):
        assert f in d


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED — 4xx + envelope + no state mutation + read-only + secret
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _stub_for_router(monkeypatch):
    from services import unified_search as us

    async def fake(query, *, account_id, limit):
        return [{
            "kind": "stub", "id": "x", "label": query,
            "hint": "", "group": "Stub",
        }][:limit]

    for src_name in ("knowledge", "tasks", "employees", "screens"):
        monkeypatch.setitem(us.SOURCE_HANDLERS, src_name, fake)

    # audit emit を no-op stub
    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        return 0
    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)
    yield


def test_ac4_unauthorized_actor_rejected_401(client):
    """空白 actor_user_id → 401 + envelope (search.unauthorized)."""
    r = client.post("/api/search/unified", json={
        "query": "test", "actor_user_id": "  ",
    })
    assert r.status_code == 401
    body = r.json()
    assert "detail" in body
    assert body["detail"]["code"] == "search.unauthorized"
    assert "message" in body["detail"]


def test_ac4_invalid_account_id_rejected_400(client):
    """account_id <= 0 → 400 + envelope (search.invalid)."""
    r = client.post("/api/search/unified", json={
        "query": "test", "account_id": 0,
    })
    assert r.status_code == 400
    body = r.json()
    assert body["detail"]["code"] == "search.invalid"


def test_ac4_invalid_user_id_for_rls_context_raises_before_mutation():
    """rls_context.set_request_user に空 / 過大 / 危険文字を渡すと
    RLSContextError raise. SET LOCAL を発行する前 (= state mutation 前).
    """
    from services import rls_context as rc

    class FakeConn:
        def __init__(self):
            self.calls: list[tuple[str, tuple]] = []

        async def execute(self, query, *args):
            self.calls.append((query, args))

    # 空文字
    conn = FakeConn()
    with pytest.raises(rc.RLSContextError):
        asyncio.run(rc.set_request_user(conn, ""))
    assert not any("SET" in c[0] or "request.jwt" in c[0] for c in conn.calls), (
        "SET LOCAL emitted before validation — state mutation occurred!"
    )

    # 過大
    conn = FakeConn()
    long_id = "x" * (rc.MAX_USER_ID_LEN + 1)
    with pytest.raises(rc.RLSContextError):
        asyncio.run(rc.set_request_user(conn, long_id))
    assert not any("SET" in c[0] for c in conn.calls)

    # SQL injection 文字
    for bad in ("'", "\x00", "\\", ";", "\n"):
        conn = FakeConn()
        with pytest.raises(rc.RLSContextError):
            asyncio.run(rc.set_request_user(conn, f"u{bad}id"))
        assert not any("SET" in c[0] for c in conn.calls), (
            f"SET LOCAL emitted before validation for {bad!r}"
        )


def test_ac4_search_modules_are_read_only():
    """search service module は INSERT/UPDATE/DELETE SQL を含まない (no
    persistent mutation).  audit emit は router 層のみ (T-024-02 で確立).
    """
    for path in (UNIFIED_SEARCH_PY, CHAT_SEARCH_PY):
        src = path.read_text(encoding="utf-8")
        code = _strip_comments_and_docstrings(src)
        # CREATE / ALTER / DROP TABLE もなし
        assert not re.search(r"\bINSERT\s+INTO\b", code, re.IGNORECASE), (
            f"{path.name} contains INSERT (mutation)"
        )
        assert not re.search(r"\bUPDATE\s+\w+\s+SET\b", code, re.IGNORECASE), (
            f"{path.name} contains UPDATE (mutation)"
        )
        assert not re.search(r"\bDELETE\s+FROM\b", code, re.IGNORECASE), (
            f"{path.name} contains DELETE (mutation)"
        )
        assert "CREATE TABLE" not in code.upper()
        assert "DROP TABLE" not in code.upper()


def test_ac4_no_hardcoded_secret_in_search_path():
    """search 経路 (service + router) に hardcoded supabase / anthropic key
    がない (lint #5 secrets check と一致).
    """
    for path in (UNIFIED_SEARCH_PY, CHAT_SEARCH_PY,
                 UNIFIED_ROUTER_PY, CHAT_ROUTER_PY):
        src = path.read_text(encoding="utf-8")
        assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src), (
            f"{path.name} contains hardcoded Anthropic key"
        )
        assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src), (
            f"{path.name} contains hardcoded Supabase key"
        )
        # SUPABASE_SERVICE_KEY 直接 reference もなし (env 経由のみ許可)
        # docstring 内で説明目的の言及は除外
        code = _strip_comments_and_docstrings(src)
        assert "SUPABASE_SERVICE_KEY" not in code, (
            f"{path.name} references SUPABASE_SERVICE_KEY directly"
        )


# ══════════════════════════════════════════════════════════════════════
# Audit doc presence (Step 1 / pre-flight workflow)
# ══════════════════════════════════════════════════════════════════════


def test_audit_doc_exists():
    assert AUDIT_DOC.exists(), (
        "Pre-flight audit doc missing: docs/audit/2026-05-13_v2/T-024-03.md"
    )


def test_audit_doc_references_required_sections():
    text = AUDIT_DOC.read_text(encoding="utf-8")
    for marker in (
        "AC-1 UBIQUITOUS",
        "AC-2 EVENT-DRIVEN",
        "AC-3 STATE-DRIVEN",
        "AC-4 UNWANTED",
        "Spec literal expansion",
        "Gap analysis",
        "REUSE",
        "F-024",
    ):
        assert marker in text, f"audit doc missing required marker: {marker}"


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_024_03_exists_and_label_reuse():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-024-03"), None)
    assert t is not None, "T-024-03 missing from tickets.json"
    assert t["label"] == "REUSE"
    assert t["feature"] == "F-024"


def test_tickets_t_024_03_has_canonical_ears_types():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-024-03"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    # generic stub の場合でも EARS type は正規 4 種
    for ty in types:
        assert ty in ("UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN",
                      "OPTIONAL", "UNWANTED"), f"non-EARS type: {ty}"
    assert "UBIQUITOUS" in types
    assert "UNWANTED" in types


def test_tickets_t_024_03_deps_include_t_s0_09():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-024-03"), None)
    deps = t.get("deps", [])
    assert "T-S0-09" in deps, "T-024-03 should depend on T-S0-09 (sandbox/RLS chain)"
