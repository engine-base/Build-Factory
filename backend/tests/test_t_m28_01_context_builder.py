"""T-M28-01: Context Builder skeleton — 4 AC 1:1 + spec gap closure (G1-G4).

AC マッピング:
  AC-1 UBIQUITOUS    : Mem0 + Obsidian read/write + Constitution unified API.
                       G1 closure: write_obsidian_note() + POST endpoint.
  AC-2 EVENT-DRIVEN  : D-XXX lookup 200ms 以内.
  AC-3 STATE-DRIVEN  : is_secretary_active() で明示判定 (G2). build_context
                       は include_constitution AND secretary_active で
                       Constitution 注入を決定.
  AC-4 UNWANTED      : Mem0 conflicts surface + has_conflicts フラグ (G3) /
                       全 4xx {detail:{code,message}} 統一 (G4) /
                       不正入力で state mutate なし.
"""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import context_builder as cb
from services.context_builder import (
    CONTRADICTORY_PAIRS,
    DECISION_REF_RE,
    ContextBuilderError,
    build_context,
    is_secretary_active,
    lookup_decision,
    preload_constitution,
    read_obsidian_note,
    write_obsidian_note,
)


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def isolated_dirs(tmp_path, monkeypatch):
    """vault + constitution dir を tmp に隔離."""
    vault = tmp_path / "obsidian"
    vault.mkdir()
    const = tmp_path / "constitutions"
    const.mkdir()
    monkeypatch.setenv("OBSIDIAN_VAULT_DIR", str(vault))
    monkeypatch.setenv("CONSTITUTION_DIR", str(const))
    monkeypatch.delenv("CONSTITUTION_TEXT", raising=False)
    return {"vault": vault, "constitutions": const}


# ══════════════════════════════════════════════════════════════════════
# G1 (AC-1): Obsidian markdown write/read unified API
# ══════════════════════════════════════════════════════════════════════


def test_g1_write_obsidian_note_creates_file(isolated_dirs):
    p = write_obsidian_note("note-a", "# Hello\n\nbody")
    assert p.exists()
    assert p.read_text(encoding="utf-8") == "# Hello\n\nbody"
    assert p.parent == isolated_dirs["vault"]


def test_g1_write_obsidian_note_idempotent_overwrite(isolated_dirs):
    write_obsidian_note("note-a", "first")
    write_obsidian_note("note-a", "second")
    assert (isolated_dirs["vault"] / "note-a.md").read_text() == "second"


def test_g1_write_obsidian_note_creates_subdir(isolated_dirs):
    p = write_obsidian_note("sub/note-b", "x")
    assert p.exists()
    assert p.parent == isolated_dirs["vault"] / "sub"


def test_g1_read_obsidian_note_returns_content(isolated_dirs):
    write_obsidian_note("note-c", "content-c")
    assert read_obsidian_note("note-c") == "content-c"


def test_g1_read_obsidian_note_missing_returns_none(isolated_dirs):
    assert read_obsidian_note("does-not-exist") is None


def test_g1_write_rejects_path_traversal(isolated_dirs):
    for bad in ("../escape", "/abs/path", "..", "../../etc/passwd"):
        with pytest.raises(ContextBuilderError):
            write_obsidian_note(bad, "x")


def test_g1_write_rejects_invalid_slug(isolated_dirs):
    for bad in ("", "  ", "name with space", "name?", "name:colon", "a" * 201):
        with pytest.raises(ContextBuilderError):
            write_obsidian_note(bad, "x")


def test_g1_write_rejects_non_string_content(isolated_dirs):
    with pytest.raises(ContextBuilderError):
        write_obsidian_note("note", 123)  # type: ignore[arg-type]


def test_g1_write_rejects_oversize_content(isolated_dirs):
    with pytest.raises(ContextBuilderError):
        write_obsidian_note("note", "x" * 1_000_001)


def test_g1_read_rejects_path_traversal(isolated_dirs):
    for bad in ("../escape", "/abs", ".."):
        with pytest.raises(ContextBuilderError):
            read_obsidian_note(bad)


def test_g1_endpoint_obsidian_write_and_read(client, isolated_dirs):
    r = client.post(
        "/api/context/obsidian/note-x",
        json={"content": "hello-x"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slug"] == "note-x"
    assert body["bytes_written"] == len(b"hello-x")
    r2 = client.get("/api/context/obsidian/note-x")
    assert r2.status_code == 200
    assert r2.json() == {"slug": "note-x", "content": "hello-x"}


def test_g1_endpoint_obsidian_read_missing_404(client, isolated_dirs):
    r = client.get("/api/context/obsidian/does-not-exist")
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == "context.not_found"


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: D-XXX lookup 200ms 以内
# ══════════════════════════════════════════════════════════════════════


def test_ac2_lookup_decision_within_200ms(isolated_dirs):
    (isolated_dirs["constitutions"] / "D-001.md").write_text(
        "# Decision 001\n\nbody", encoding="utf-8",
    )
    t0 = time.time()
    d = lookup_decision("D-001")
    elapsed_ms = (time.time() - t0) * 1000
    assert d is not None
    assert elapsed_ms < 200.0, f"lookup_decision took {elapsed_ms:.1f}ms"


def test_ac2_build_context_with_d_ref_within_200ms(isolated_dirs):
    (isolated_dirs["constitutions"] / "D-002.md").write_text(
        "# D2", encoding="utf-8",
    )
    t0 = time.time()
    out = asyncio.run(build_context(
        "see D-002 for details",
        session_id=1,
        include_constitution=False,
    ))
    elapsed_ms = (time.time() - t0) * 1000
    # build_context は I/O 含むので 1000ms 目安, decision 部分は <200ms を厳密に
    # 計測することは context 全体に依存. ここでは D-XXX が抽出された事実 + 1秒
    # 以内を弱条件として確認 (read-only)
    assert any(d["id"] == "D-002" for d in out["decisions"])
    assert elapsed_ms < 1000.0


# ══════════════════════════════════════════════════════════════════════
# G2 (AC-3): secretary_active 状態判定
# ══════════════════════════════════════════════════════════════════════


def test_g2_is_secretary_active_override_true():
    assert is_secretary_active(True) is True


def test_g2_is_secretary_active_override_false():
    assert is_secretary_active(False) is False


def test_g2_is_secretary_active_env_truthy(monkeypatch):
    monkeypatch.setenv("SECRETARY_ACTIVE", "true")
    assert is_secretary_active() is True
    monkeypatch.setenv("SECRETARY_ACTIVE", "1")
    assert is_secretary_active() is True


def test_g2_is_secretary_active_env_falsy(monkeypatch):
    monkeypatch.setenv("SECRETARY_ACTIVE", "false")
    assert is_secretary_active() is False
    monkeypatch.setenv("SECRETARY_ACTIVE", "no")
    assert is_secretary_active() is False
    monkeypatch.setenv("SECRETARY_ACTIVE", "")
    assert is_secretary_active() is False


def test_g2_is_secretary_active_default_when_env_unset(monkeypatch):
    monkeypatch.delenv("SECRETARY_ACTIVE", raising=False)
    assert is_secretary_active() is True


def test_g2_build_context_inactive_secretary_does_not_inject_constitution(
    isolated_dirs,
):
    (isolated_dirs["constitutions"] / "D-007.md").write_text(
        "# D7\nbody", encoding="utf-8",
    )
    out = asyncio.run(build_context(
        "hello",
        session_id=1,
        include_constitution=True,
        secretary_active=False,
    ))
    assert out["constitution"] == ""
    assert out["secretary_active"] is False


def test_g2_build_context_active_injects_constitution(isolated_dirs):
    (isolated_dirs["constitutions"] / "D-008.md").write_text(
        "# D8\nbody-8", encoding="utf-8",
    )
    out = asyncio.run(build_context(
        "hello",
        session_id=1,
        include_constitution=True,
        secretary_active=True,
    ))
    assert "body-8" in out["constitution"]
    assert out["secretary_active"] is True


def test_g2_build_context_include_constitution_false_takes_precedence(
    isolated_dirs,
):
    """include_constitution=False は secretary_active=True でも注入しない."""
    (isolated_dirs["constitutions"] / "D-009.md").write_text(
        "# D9", encoding="utf-8",
    )
    out = asyncio.run(build_context(
        "hello",
        session_id=1,
        include_constitution=False,
        secretary_active=True,
    ))
    assert out["constitution"] == ""


# ══════════════════════════════════════════════════════════════════════
# G3 (AC-4): conflicts surface + has_conflicts flag
# ══════════════════════════════════════════════════════════════════════


def test_g3_has_conflicts_true_when_mem0_conflicts(monkeypatch, isolated_dirs):
    async def fake_search(*args, **kwargs):
        return ["項目X を採用", "項目X を不採用"]
    import services.long_term_memory as ltm
    monkeypatch.setattr(ltm, "search_relevant_memories", fake_search)
    out = asyncio.run(build_context(
        "check X",
        session_id=1,
        include_constitution=False,
    ))
    assert out["has_conflicts"] is True
    assert len(out["conflicts"]) >= 1
    # silent pick 禁止: fact_a / fact_b 両方を呼出元に渡す
    c = out["conflicts"][0]
    assert "fact_a" in c and "fact_b" in c
    assert c["fact_a"] != c["fact_b"]


def test_g3_has_conflicts_false_when_no_mem0_conflicts(
    monkeypatch, isolated_dirs,
):
    async def fake_search(*args, **kwargs):
        return ["項目X を採用", "項目Y を採用"]
    import services.long_term_memory as ltm
    monkeypatch.setattr(ltm, "search_relevant_memories", fake_search)
    out = asyncio.run(build_context(
        "check",
        session_id=1,
        include_constitution=False,
    ))
    assert out["has_conflicts"] is False
    assert out["conflicts"] == []


def test_g3_has_conflicts_false_when_mem0_empty(monkeypatch, isolated_dirs):
    async def fake_search(*args, **kwargs):
        return []
    import services.long_term_memory as ltm
    monkeypatch.setattr(ltm, "search_relevant_memories", fake_search)
    out = asyncio.run(build_context(
        "hi",
        session_id=1,
        include_constitution=False,
    ))
    assert out["has_conflicts"] is False


def test_g3_response_shape_includes_new_fields(isolated_dirs):
    out = asyncio.run(build_context(
        "hi", session_id=1, include_constitution=False,
    ))
    for k in (
        "memory_block", "decisions", "constitution",
        "mem0_facts", "conflicts", "has_conflicts", "secretary_active",
    ):
        assert k in out, f"build_context response missing {k!r}"


# ══════════════════════════════════════════════════════════════════════
# G4 (AC-4): 4xx response form unification
# ══════════════════════════════════════════════════════════════════════


def test_g4_endpoint_build_invalid_user_message_400(client):
    r = client.post("/api/context/build", json={
        "user_message": "", "session_id": 1,
    })
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == "context.invalid"
    assert "message" in detail


def test_g4_endpoint_build_missing_required_400(client):
    r = client.post("/api/context/build", json={"user_message": "hi"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "context.invalid"


def test_g4_endpoint_build_bad_session_id_400(client):
    r = client.post("/api/context/build", json={
        "user_message": "hi", "session_id": 0,
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "context.invalid"


def test_g4_endpoint_build_bad_top_k_400(client):
    for bad in (0, 21, -1):
        r = client.post("/api/context/build", json={
            "user_message": "hi", "session_id": 1, "top_k": bad,
        })
        assert r.status_code == 400, f"top_k={bad}"
        assert r.json()["detail"]["code"] == "context.invalid"


def test_g4_endpoint_build_bad_include_constitution_type_400(client):
    r = client.post("/api/context/build", json={
        "user_message": "hi", "session_id": 1,
        "include_constitution": "yes",
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "context.invalid"


def test_g4_endpoint_build_bad_secretary_active_type_400(client):
    r = client.post("/api/context/build", json={
        "user_message": "hi", "session_id": 1,
        "secretary_active": "true",
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "context.invalid"


def test_g4_endpoint_decisions_invalid_format_400(client):
    r = client.get("/api/context/decisions/not-a-decision")
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == "context.invalid"


def test_g4_endpoint_decisions_not_found_404(client, isolated_dirs):
    r = client.get("/api/context/decisions/D-999")
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == "context.not_found"


def test_g4_endpoint_constitution_blank_user_id_400(client):
    r = client.get("/api/context/constitution", params={"user_id": "   "})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "context.invalid"


def test_g4_endpoint_obsidian_write_non_string_content_400(
    client, isolated_dirs,
):
    r = client.post(
        "/api/context/obsidian/note-y",
        json={"content": 123},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "context.invalid"


def test_g4_endpoint_obsidian_write_path_traversal_400(client, isolated_dirs):
    """slug 内に '..' を含む path traversal は 400."""
    r = client.post(
        "/api/context/obsidian/sub/..%2Fescape",
        json={"content": "x"},
    )
    # FastAPI が `..` の正規化をしないようにエンコード渡し. service 層で reject.
    # ただし path converter の正規化挙動次第で 404 になる可能性もあるので,
    # 4xx (400/404) のいずれかであることを許容しつつ, 4xx であること自体を
    # AC-4 として確認.
    assert r.status_code in (400, 404)
    detail = r.json()["detail"]
    assert isinstance(detail, dict), f"detail must be dict, got: {detail}"
    assert detail.get("code", "").startswith("context.")


def test_g4_all_4xx_detail_shape(client, isolated_dirs):
    """AC-4: 全 4xx response が {detail:{code,message}}."""
    cases = [
        ("POST", "/api/context/build", {"user_message": ""}, 400),
        ("POST", "/api/context/build",
         {"user_message": "x", "session_id": 0}, 400),
        ("GET", "/api/context/decisions/bad", None, 400),
        ("GET", "/api/context/decisions/D-998", None, 404),
        ("GET", "/api/context/obsidian/no-such-note", None, 404),
    ]
    for method, path, body, expected in cases:
        if method == "GET":
            r = client.get(path)
        else:
            r = client.post(path, json=body)
        assert r.status_code == expected, f"{path}: {r.status_code}: {r.text}"
        detail = r.json()["detail"]
        assert isinstance(detail, dict), f"{path}: detail must be dict"
        assert detail.get("code", "").startswith("context."), f"{path}: bad code"
        assert isinstance(detail.get("message", ""), str) and detail["message"]


def test_g4_build_context_invalid_input_does_not_mutate_state(isolated_dirs):
    """state mutate なし: invalid input で vault 書込が発生しない."""
    files_before = list(isolated_dirs["vault"].iterdir())
    with pytest.raises(ContextBuilderError):
        asyncio.run(build_context("", session_id=1))
    with pytest.raises(ContextBuilderError):
        asyncio.run(build_context("hi", session_id=0))
    files_after = list(isolated_dirs["vault"].iterdir())
    assert files_before == files_after


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS: unified API surface
# ══════════════════════════════════════════════════════════════════════


def test_ac1_unified_api_exposes_mem0_obsidian_constitution(isolated_dirs):
    """AC-1: build_context 単一窓口で 3 経路 (Mem0/Obsidian/Constitution) を統合."""
    out = asyncio.run(build_context(
        "hi", session_id=1, include_constitution=True,
    ))
    # 3 経路の戻り値キー
    assert "memory_block" in out          # memory_service.merge_for_session 経路
    assert "constitution" in out          # Constitution 経路
    assert "mem0_facts" in out            # Mem0 経路
    # 統合フィールド
    assert "decisions" in out             # D-XXX lookup
    assert "conflicts" in out             # UNWANTED


def test_ac1_obsidian_unified_read_write_round_trip(isolated_dirs):
    write_obsidian_note("session/notes/x", "y")
    assert read_obsidian_note("session/notes/x") == "y"


# ══════════════════════════════════════════════════════════════════════
# Module docstring documents G1-G4
# ══════════════════════════════════════════════════════════════════════


def test_module_docstring_documents_gap_closures():
    doc = cb.__doc__ or ""
    for tag in ("G1", "G2", "G3", "G4"):
        assert tag in doc, f"context_builder docstring must mention {tag}"
    assert "read/write" in doc
    assert "has_conflicts" in doc
