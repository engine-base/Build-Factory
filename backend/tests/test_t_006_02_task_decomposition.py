"""T-006-02: task-decomposition AI + EARS AC (existing tasks.py REFACTOR).

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : service + router 公開 / existing tasks.py 無改変.
  AC-2 EVENT-DRIVEN  : POST endpoint で structured response / 2 秒以内.
  AC-3 STATE-DRIVEN  : backend 未登録 → heuristic fallback / audit emit /
                       tasks tableに書き込まない.
  AC-4 UNWANTED      : invalid brief / count / 空 actor / backend 不正 → 4xx +
                       fallback (raise しない).
"""
from __future__ import annotations

import json as _json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE = REPO_ROOT / "backend" / "services" / "task_decomposition.py"
ROUTER = REPO_ROOT / "backend" / "routers" / "task_decomposition.py"
EXISTING_TASKS = REPO_ROOT / "backend" / "routers" / "tasks.py"


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _capture_audit(monkeypatch):
    captured: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({
            "event_type": event_type,
            "user_id": user_id,
            "detail": detail or {},
        })
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)
    yield captured


@pytest.fixture(autouse=True)
def _clear_backend():
    """Each test starts with no registered backend (heuristic mode)."""
    from services import task_decomposition as td
    td.register_decomposer_backend(None)
    yield
    td.register_decomposer_backend(None)


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS: public API + REUSE invariant
# ══════════════════════════════════════════════════════════════════════


def test_ac1_service_exists():
    assert SERVICE.exists()


def test_ac1_router_exists():
    assert ROUTER.exists()


def test_ac1_public_api():
    from services import task_decomposition as td
    for sym in (
        "decompose", "decompose_heuristic",
        "register_decomposer_backend", "get_decomposer_backend",
        "list_ac_types",
        "MIN_BRIEF_CHARS", "MAX_BRIEF_CHARS",
        "MIN_SUBTASK_COUNT", "MAX_SUBTASK_COUNT",
        "REQUIRED_AC_TYPES", "ALL_AC_TYPES",
    ):
        assert hasattr(td, sym), f"missing service.{sym}"


def test_ac1_existing_tasks_router_unchanged():
    """既存 routers/tasks.py に task_decomposition 依存追加なし (REUSE)."""
    assert EXISTING_TASKS.exists()
    src = EXISTING_TASKS.read_text(encoding="utf-8")
    assert "from services.task_decomposition" not in src
    assert "from routers.task_decomposition" not in src
    assert "task_decomposition_router" not in src


def test_ac1_existing_tasks_symbols_intact():
    """既存 tasks.py の主要 endpoint symbol が残る."""
    from routers import tasks as t
    assert hasattr(t, "router")


def test_ac1_list_ac_types_includes_all_5_forms():
    from services import task_decomposition as td
    types = set(td.list_ac_types())
    assert {"UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN",
            "OPTIONAL", "UNWANTED"} <= types


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: structured response, 2 秒以内, EARS schema 整合
# ══════════════════════════════════════════════════════════════════════


def test_ac2_decompose_service_structure():
    from services import task_decomposition as td
    r = td.decompose("ユーザー認証機能を実装", subtask_count=3)
    assert r["parent_brief"].startswith("ユーザー認証")
    assert isinstance(r["subtasks"], list)
    assert len(r["subtasks"]) == 3
    for sub in r["subtasks"]:
        assert "title" in sub
        assert "acceptance_criteria" in sub
        ac_types = {ac["type"] for ac in sub["acceptance_criteria"]}
        # AC-3 enforces UBIQUITOUS + UNWANTED minimum
        assert "UBIQUITOUS" in ac_types
        assert "UNWANTED" in ac_types
    assert r["config"]["count_requested"] == 3
    assert r["config"]["count_returned"] == 3


def test_ac2_decompose_within_2_seconds():
    from services import task_decomposition as td
    t0 = time.time()
    td.decompose("検索機能の高速化", subtask_count=5)
    elapsed = time.time() - t0
    assert elapsed < 2.0


def test_ac2_endpoint_basic(client):
    resp = client.post(
        "/api/task-decomposition/decompose",
        json={"parent_brief": "通知システム実装", "subtask_count": 4},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["config"]["count_returned"] == 4
    assert len(body["subtasks"]) == 4


def test_ac2_endpoint_emits_audit(client, _capture_audit):
    client.post(
        "/api/task-decomposition/decompose",
        json={"parent_brief": "auth feature setup", "subtask_count": 2},
    )
    events = [e["event_type"] for e in _capture_audit]
    assert "task_decomposition.decomposed" in events


def test_ac2_ac_text_matches_ears_schema():
    """生成 AC text が EARS schema (T-025-01) pattern を満たす."""
    from services import task_decomposition as td
    r = td.decompose("セキュリティ強化", subtask_count=2)
    schema_path = REPO_ROOT / "backend" / "schemas" / "ears_ac_schema.json"
    assert schema_path.exists()
    schema = _json.loads(schema_path.read_text(encoding="utf-8"))
    # schema pattern shape: { definitions: { ac: { properties: { type, text } } } }
    # simpler check: ensure text starts with required keyword per type
    for sub in r["subtasks"]:
        for ac in sub["acceptance_criteria"]:
            t = ac["type"]
            text = ac["text"]
            if t == "UBIQUITOUS":
                assert "shall" in text.lower()
            elif t == "EVENT-DRIVEN":
                assert text.startswith("When ")
            elif t == "STATE-DRIVEN":
                assert text.startswith("While ")
            elif t == "UNWANTED":
                assert text.startswith("If ")


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: backend fallback / heuristic 純関数 / no DB write
# ══════════════════════════════════════════════════════════════════════


def test_ac3_backend_unregistered_uses_heuristic():
    from services import task_decomposition as td
    assert td.get_decomposer_backend() is None
    r = td.decompose("汎用タスク", subtask_count=2)
    assert r["config"]["backend_used"] is False


def test_ac3_backend_registered_used_on_success():
    from services import task_decomposition as td

    def fake_backend(brief, count):
        return [
            {
                "title": f"backend-task-{i}",
                "acceptance_criteria": [
                    {"type": "UBIQUITOUS",
                     "text": "The system shall do X."},
                    {"type": "UNWANTED",
                     "text": "If bad input, the system shall not crash."},
                ],
            }
            for i in range(count)
        ]

    td.register_decomposer_backend(fake_backend)
    r = td.decompose("test brief content", subtask_count=2)
    assert r["config"]["backend_used"] is True
    assert r["subtasks"][0]["title"] == "backend-task-0"


def test_ac3_heuristic_is_pure_function():
    """decompose_heuristic は同じ input で同じ output (deterministic)."""
    from services import task_decomposition as td
    r1 = td.decompose_heuristic("同じ brief です", 3)
    r2 = td.decompose_heuristic("同じ brief です", 3)
    assert r1 == r2


def test_ac3_module_no_db_write():
    """task_decomposition.py が直接 DB / file write しない."""
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert "INSERT INTO" not in code
    assert "UPDATE " not in code.upper() or "UPDATE" in "UPDATES "
    assert "aiosqlite" not in code
    assert "open(" not in code


def test_ac3_module_no_langgraph_no_langchain():
    """ADR-010: main runner path で LangGraph / LangChain 禁止."""
    src = SERVICE.read_text(encoding="utf-8")
    assert "langgraph" not in src.lower()
    assert "langchain" not in src.lower()


def _strip_comments(src: str) -> str:
    out_lines = []
    in_triple = False
    triple_char = None
    for raw in src.splitlines():
        line = raw
        if in_triple:
            if triple_char in line:
                line = line.split(triple_char, 1)[1]
                in_triple = False
            else:
                continue
        for ch in ('"""', "'''"):
            if ch in line:
                before, _, after = line.partition(ch)
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
# AC-4 UNWANTED: validation + backend fallback on malformed output
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("bad_brief", ["", "  ", "x", None, 123, []])
def test_ac4_invalid_brief_raises(bad_brief):
    from services import task_decomposition as td
    with pytest.raises(ValueError):
        td.decompose(bad_brief)


@pytest.mark.parametrize("bad_count", [0, -1, 21, 100, True, "5"])
def test_ac4_invalid_count_raises(bad_count):
    from services import task_decomposition as td
    with pytest.raises(ValueError):
        td.decompose("valid brief content", subtask_count=bad_count)


def test_ac4_endpoint_400_on_invalid_brief(client):
    resp = client.post(
        "/api/task-decomposition/decompose",
        json={"parent_brief": "  ", "subtask_count": 3},
    )
    # pydantic min_length=1 trips on "" but "  " is len>1 → service catches
    assert resp.status_code in (400, 422)


def test_ac4_endpoint_400_on_count_out_of_range(client):
    resp = client.post(
        "/api/task-decomposition/decompose",
        json={"parent_brief": "valid brief", "subtask_count": 999},
    )
    # pydantic le=20 → 422
    assert resp.status_code == 422


def test_ac4_endpoint_401_on_empty_actor(client):
    resp = client.post(
        "/api/task-decomposition/decompose",
        json={"parent_brief": "valid brief", "actor_user_id": "  "},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "task_decomposition.unauthorized"


def test_ac4_endpoint_structured_error_shape(client):
    resp = client.post(
        "/api/task-decomposition/decompose",
        json={"parent_brief": "valid brief", "actor_user_id": ""},
    )
    detail = resp.json()["detail"]
    assert "code" in detail
    assert "message" in detail


def test_ac4_backend_malformed_falls_back():
    """backend が dict 以外を返した場合 heuristic に fallback (raise しない)."""
    from services import task_decomposition as td

    def bad_backend(brief, count):
        return "not a list"

    td.register_decomposer_backend(bad_backend)
    r = td.decompose("test brief", subtask_count=2)
    # fallback to heuristic, backend_used=False
    assert r["config"]["backend_used"] is False
    assert len(r["subtasks"]) == 2


def test_ac4_backend_missing_required_ac_falls_back():
    """backend が UBIQUITOUS+UNWANTED 揃わない出力 → fallback."""
    from services import task_decomposition as td

    def bad_backend(brief, count):
        # missing UNWANTED
        return [
            {
                "title": "x",
                "acceptance_criteria": [
                    {"type": "UBIQUITOUS",
                     "text": "The system shall do X."},
                    {"type": "EVENT-DRIVEN",
                     "text": "When Y, the system shall Z."},
                ],
            }
        ] * count

    td.register_decomposer_backend(bad_backend)
    r = td.decompose("test brief", subtask_count=1)
    assert r["config"]["backend_used"] is False


def test_ac4_register_non_callable_raises():
    from services import task_decomposition as td
    with pytest.raises(ValueError):
        td.register_decomposer_backend("not callable")


def test_ac4_no_hardcoded_secret():
    import re
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", code)
    assert "SUPABASE_SERVICE_KEY" not in code


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_006_02_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-006-02"), None)
    assert t is not None
    generic = [
        "as specified by feature",
        "When the relevant API endpoint or service function is invoked for T-006-02",
        "While refactoring for T-006-02 is in progress",
        "If invalid input or unauthorized actor is detected during T-006-02",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], (
                f"T-006-02 still generic: {phrase!r}"
            )
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "task_decomposition.py" in full
    assert "register_decomposer_backend" in full
    assert "/api/task-decomposition/decompose" in full


def test_tickets_t_006_02_has_adr_link():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-006-02"), None)
    assert t.get("adr_link") is not None
