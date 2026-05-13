"""T-M28-01: Context Builder の smoke test."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.context_builder import (
    build_context, lookup_decision, preload_constitution,
    DECISION_REF_RE, _detect_conflicts,
)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


# ──────────────────────────────────────────
# Decision lookup (EVENT AC)
# ──────────────────────────────────────────

def test_decision_ref_regex_matches_3to5_digits() -> None:
    assert DECISION_REF_RE.fullmatch("D-001")
    assert DECISION_REF_RE.fullmatch("D-1234")
    assert DECISION_REF_RE.fullmatch("D-99999")
    assert not DECISION_REF_RE.fullmatch("D-12")     # 2 桁は弾く
    assert not DECISION_REF_RE.fullmatch("D-")
    assert not DECISION_REF_RE.fullmatch("d-001")    # 大文字のみ


def test_lookup_decision_returns_none_for_invalid_format() -> None:
    assert lookup_decision("X-001") is None
    assert lookup_decision("D-12") is None


def test_lookup_decision_reads_md_when_exists(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CONSTITUTION_DIR", str(tmp_path))
    p = tmp_path / "D-042.md"
    p.write_text("# Test Decision 42\n\nThe quick brown fox.\n", encoding="utf-8")
    d = lookup_decision("D-042")
    assert d is not None
    assert d["id"] == "D-042"
    assert d["title"] == "Test Decision 42"
    assert "quick brown fox" in d["content"]


def test_lookup_decision_returns_none_when_file_absent(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CONSTITUTION_DIR", str(tmp_path))
    assert lookup_decision("D-999") is None


# ──────────────────────────────────────────
# Constitution preload (STATE AC)
# ──────────────────────────────────────────

def test_preload_constitution_returns_env_text(monkeypatch) -> None:
    monkeypatch.setenv("CONSTITUTION_TEXT", "MASATO IS THE BOSS")
    text = asyncio.run(preload_constitution())
    assert text == "MASATO IS THE BOSS"


def test_preload_constitution_concatenates_md_files(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("CONSTITUTION_TEXT", raising=False)
    monkeypatch.setenv("CONSTITUTION_DIR", str(tmp_path))
    (tmp_path / "D-001.md").write_text("# A\n\nPolicy A", encoding="utf-8")
    (tmp_path / "D-002.md").write_text("# B\n\nPolicy B", encoding="utf-8")
    text = asyncio.run(preload_constitution())
    assert "Policy A" in text
    assert "Policy B" in text


# ──────────────────────────────────────────
# Conflict detection (UNWANTED AC)
# ──────────────────────────────────────────

def test_detect_conflicts_finds_contradiction() -> None:
    facts = ["この案件は採用", "この案件は不採用"]
    conflicts = _detect_conflicts(facts)
    assert len(conflicts) >= 1
    assert "採用" in conflicts[0]["axis"]


def test_detect_conflicts_empty_for_consistent_facts() -> None:
    facts = ["顧客は田中商事", "金額は 50 万円"]
    conflicts = _detect_conflicts(facts)
    assert conflicts == []


# ──────────────────────────────────────────
# build_context (UBIQUITOUS AC)
# ──────────────────────────────────────────

def test_build_context_returns_unified_dict(monkeypatch) -> None:
    monkeypatch.delenv("CONSTITUTION_TEXT", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = asyncio.run(build_context(
        user_message="hi",
        session_id=1,
        user_id="masato",
        include_constitution=False,
    ))
    # 不確定 deps が無くても dict 構造は維持される
    for key in ("memory_block", "decisions", "constitution", "mem0_facts", "conflicts"):
        assert key in result


def test_build_context_extracts_decision_refs(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CONSTITUTION_DIR", str(tmp_path))
    (tmp_path / "D-100.md").write_text("# Decision 100\n\nrule X", encoding="utf-8")
    result = asyncio.run(build_context(
        user_message="D-100 についてどう思う?",
        session_id=1, user_id="masato",
        include_constitution=False,
    ))
    assert len(result["decisions"]) == 1
    assert result["decisions"][0]["id"] == "D-100"


# ──────────────────────────────────────────
# E2E: router
# ──────────────────────────────────────────

def test_context_decision_endpoint_404(client) -> None:
    r = client.get("/api/context/decisions/D-99999")
    assert r.status_code == 404


def test_context_decision_endpoint_400_bad_format(client) -> None:
    r = client.get("/api/context/decisions/X-001")
    assert r.status_code == 400


def test_context_build_endpoint_returns_unified_dict(client) -> None:
    r = client.post(
        "/api/context/build",
        json={
            "user_message": "hi",
            "session_id": 1,
            "user_id": "masato",
            "include_constitution": False,
        },
    )
    assert r.status_code == 200
    body = r.json()
    for key in ("memory_block", "decisions", "constitution", "mem0_facts", "conflicts"):
        assert key in body


# ─────────────────────────────────────────────────────────────────────────
# AC 全網羅 補完: AC-2 200ms / Obsidian / 全 fallback / endpoint cov
# ─────────────────────────────────────────────────────────────────────────


import sys
import time
import types
from typing import Any
from services import context_builder as cb


# ----------------- AC-1 UBIQUITOUS: Mem0 + Obsidian + Constitution unified -----


def test_build_context_includes_mem0_facts_in_unified_response(
    tmp_path, monkeypatch,
) -> None:
    """AC-1: Mem0 vector search の結果が mem0_facts に乗る."""
    fake_mod = types.ModuleType("services.long_term_memory")

    async def fake_search(*, user_id, query, limit=5):
        return ["customer is Acme Corp.", "budget 5M yen"]

    fake_mod.search_relevant_memories = fake_search
    sys.modules["services.long_term_memory"] = fake_mod
    monkeypatch.setenv("CONSTITUTION_DIR", str(tmp_path))
    try:
        result = asyncio.run(cb.build_context(
            user_message="この案件の予算は?",
            session_id=1, user_id="masato",
            include_constitution=False,
        ))
        assert "customer is Acme Corp." in result["mem0_facts"]
        assert "budget 5M yen" in result["mem0_facts"]
    finally:
        sys.modules.pop("services.long_term_memory", None)


def test_build_context_includes_obsidian_via_constitution_dir(tmp_path, monkeypatch) -> None:
    """AC-1 + AC-3: Obsidian/Constitution dir の Markdown が constitution に統合."""
    monkeypatch.setenv("CONSTITUTION_DIR", str(tmp_path))
    monkeypatch.delenv("CONSTITUTION_TEXT", raising=False)
    (tmp_path / "D-200.md").write_text("# Obsidian Policy\n\n簡潔に書く", encoding="utf-8")
    result = asyncio.run(cb.build_context(
        user_message="hi",
        session_id=1, user_id="masato",
        include_constitution=True,
    ))
    assert "簡潔に書く" in result["constitution"]


# ----------------- AC-2 EVENT: D-XXX lookup 200ms 制約 -------------------------


def test_lookup_decision_within_200ms(tmp_path, monkeypatch) -> None:
    """AC-2: D-XXX lookup は 200ms 以内 (read-only / no network)."""
    monkeypatch.setenv("CONSTITUTION_DIR", str(tmp_path))
    (tmp_path / "D-500.md").write_text("# Quick\n\n" + "x" * 10_000, encoding="utf-8")

    # 10 連続実行の最大時間が 200ms 以下
    max_dt = 0.0
    for _ in range(10):
        t0 = time.monotonic()
        d = cb.lookup_decision("D-500")
        dt = time.monotonic() - t0
        max_dt = max(max_dt, dt)
        assert d is not None
    assert max_dt < 0.2, f"slowest lookup={max_dt*1000:.1f}ms (limit 200ms)"


def test_build_context_d_ref_lookup_within_200ms(tmp_path, monkeypatch) -> None:
    """AC-2 inside build_context: D-XXX を含む input でも 200ms 以内.
    (mem0 / memory_service は全て stub で graceful skip)."""
    monkeypatch.setenv("CONSTITUTION_DIR", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CONSTITUTION_TEXT", raising=False)
    sys.modules.pop("services.long_term_memory", None)
    (tmp_path / "D-300.md").write_text("# Decision 300\n\nthe rule", encoding="utf-8")

    t0 = time.monotonic()
    result = asyncio.run(cb.build_context(
        user_message="D-300 の根拠を教えて",
        session_id=1, user_id="masato",
        include_constitution=False,
    ))
    dt = time.monotonic() - t0
    assert result["decisions"][0]["id"] == "D-300"
    assert dt < 0.2, f"build_context took {dt*1000:.1f}ms (limit 200ms)"


# ----------------- AC-3 STATE: Constitution preload paths --------------------


def test_preload_constitution_uses_repo_fallback_when_home_missing(
    tmp_path, monkeypatch,
) -> None:
    """env 未設定 + HOME 不在 → repo/data/constitutions/ に fallback."""
    monkeypatch.delenv("CONSTITUTION_TEXT", raising=False)
    monkeypatch.delenv("CONSTITUTION_DIR", raising=False)
    fake_home = tmp_path / "no-such-home"
    monkeypatch.setattr(cb.Path, "home", classmethod(lambda cls: fake_home))
    # repo path も差し替えて空 dir を作る
    repo_const = tmp_path / "repo" / "data" / "constitutions"
    repo_const.mkdir(parents=True)
    (repo_const / "D-001.md").write_text("# Repo Decision\n\nrepo body", encoding="utf-8")
    monkeypatch.setattr(cb, "_constitution_dir", lambda: repo_const)
    text = asyncio.run(cb.preload_constitution())
    assert "repo body" in text


def test_preload_constitution_returns_empty_when_dir_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("CONSTITUTION_TEXT", raising=False)
    monkeypatch.setenv("CONSTITUTION_DIR", str(tmp_path / "absent"))
    text = asyncio.run(cb.preload_constitution())
    assert text == ""


def test_preload_constitution_ignores_oserror_files(tmp_path, monkeypatch) -> None:
    """read 不能なファイルがあっても crash しない (他は読む)."""
    monkeypatch.delenv("CONSTITUTION_TEXT", raising=False)
    monkeypatch.setenv("CONSTITUTION_DIR", str(tmp_path))
    (tmp_path / "D-001.md").write_text("# OK\n\nOK body", encoding="utf-8")
    bad = tmp_path / "D-002.md"
    bad.write_text("x", encoding="utf-8")
    # read 時に OSError を投げる stub
    real_read = Path.read_text

    def _faulty_read(self, *a, **k):
        if self.name == "D-002.md":
            raise OSError("simulated read fail")
        return real_read(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", _faulty_read)
    text = asyncio.run(cb.preload_constitution())
    assert "OK body" in text  # D-001 は読めた


# ----------------- AC-4 UNWANTED: Mem0 conflict surface ----------------------


def test_build_context_surfaces_conflicts(tmp_path, monkeypatch) -> None:
    """AC-4 UNWANTED: Mem0 が矛盾を返すと conflicts に乗る (silent pick せず)."""
    fake_mod = types.ModuleType("services.long_term_memory")

    async def fake_search(*, user_id, query, limit=5):
        return ["この機能は採用", "この機能は不採用"]

    fake_mod.search_relevant_memories = fake_search
    sys.modules["services.long_term_memory"] = fake_mod
    monkeypatch.setenv("CONSTITUTION_DIR", str(tmp_path))
    try:
        result = asyncio.run(cb.build_context(
            user_message="採用判断は?",
            session_id=1, user_id="masato",
            include_constitution=False,
        ))
        assert len(result["conflicts"]) >= 1
        # 矛盾が surface している (= mem0_facts に両方残っている)
        assert "この機能は採用" in result["mem0_facts"]
        assert "この機能は不採用" in result["mem0_facts"]
    finally:
        sys.modules.pop("services.long_term_memory", None)


def test_detect_conflicts_multiple_pairs() -> None:
    """複数の対立軸 (採用/不採用 + OK/NG + approve/reject) を検出する."""
    facts = [
        "案件 A は採用",
        "案件 A は不採用",
        "テスト結果は OK",
        "テスト結果は NG",
    ]
    conflicts = cb._detect_conflicts(facts)
    axes = {c["axis"] for c in conflicts}
    assert any("採用" in ax for ax in axes)
    assert any("OK" in ax or "NG" in ax for ax in axes)


def test_detect_conflicts_handles_reverse_order() -> None:
    """neg → pos の順でも検出 (a に neg / b に pos)."""
    facts = ["この案件は不採用", "この案件は採用"]
    conflicts = cb._detect_conflicts(facts)
    assert len(conflicts) >= 1


# ----------------- lookup_decision: README 経路 --------------------------------


def test_lookup_decision_reads_subdir_readme_when_md_absent(tmp_path, monkeypatch) -> None:
    """D-XXX/README.md 形式 (1 D = 1 dir) も読める."""
    monkeypatch.setenv("CONSTITUTION_DIR", str(tmp_path))
    sub = tmp_path / "D-777"
    sub.mkdir()
    (sub / "README.md").write_text("# Subdir Decision\n\nsubdir body", encoding="utf-8")
    d = cb.lookup_decision("D-777")
    assert d is not None
    assert d["title"] == "Subdir Decision"
    assert "subdir body" in d["content"]


def test_lookup_decision_no_title_falls_back_to_id(tmp_path, monkeypatch) -> None:
    """先頭行が `# ` で始まらないなら title = decision_id."""
    monkeypatch.setenv("CONSTITUTION_DIR", str(tmp_path))
    (tmp_path / "D-888.md").write_text("body without title\n", encoding="utf-8")
    d = cb.lookup_decision("D-888")
    assert d is not None
    assert d["title"] == "D-888"


# ----------------- build_context graceful fallback paths ---------------------


def test_build_context_when_memory_service_raises(monkeypatch) -> None:
    """memory_service.merge_for_session が例外 → memory_block は空."""
    import services.memory_service as ms

    async def boom(**kw):
        raise RuntimeError("ms down")

    monkeypatch.setattr(ms, "merge_for_session", boom)
    monkeypatch.delenv("CONSTITUTION_TEXT", raising=False)
    sys.modules.pop("services.long_term_memory", None)
    result = asyncio.run(cb.build_context(
        user_message="hi", session_id=1, user_id="masato",
        include_constitution=False,
    ))
    assert result["memory_block"] == ""


def test_build_context_when_long_term_memory_module_missing(monkeypatch) -> None:
    """long_term_memory module が無くても crash しない (mem0_facts=[])."""
    sys.modules.pop("services.long_term_memory", None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CONSTITUTION_TEXT", raising=False)
    result = asyncio.run(cb.build_context(
        user_message="hi", session_id=1, user_id="masato",
        include_constitution=False,
    ))
    assert result["mem0_facts"] == []
    assert result["conflicts"] == []


# ----------------- Router endpoint cov 補完 -----------------------------------


def test_constitution_endpoint_returns_text(client, monkeypatch) -> None:
    monkeypatch.setenv("CONSTITUTION_TEXT", "secretary preload OK")
    r = client.get("/api/context/constitution")
    assert r.status_code == 200
    assert r.json()["constitution"] == "secretary preload OK"


def test_decisions_endpoint_returns_decision_when_found(
    client, tmp_path, monkeypatch,
) -> None:
    monkeypatch.setenv("CONSTITUTION_DIR", str(tmp_path))
    (tmp_path / "D-321.md").write_text("# Found\n\nbody", encoding="utf-8")
    r = client.get("/api/context/decisions/D-321")
    assert r.status_code == 200
    assert r.json()["id"] == "D-321"
    assert r.json()["title"] == "Found"


def test_build_endpoint_with_d_ref_lookup(client, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CONSTITUTION_DIR", str(tmp_path))
    (tmp_path / "D-654.md").write_text("# X\n\ny", encoding="utf-8")
    r = client.post("/api/context/build", json={
        "user_message": "D-654 ?",
        "session_id": 1, "user_id": "masato",
        "include_constitution": False,
    })
    assert r.status_code == 200
    body = r.json()
    assert any(d["id"] == "D-654" for d in body["decisions"])


def test_build_endpoint_validation_rejects_empty_message(client) -> None:
    """T-M28-01 G4: 全 4xx は {detail:{code,message}} 形式 (400)."""
    r = client.post("/api/context/build", json={
        "user_message": "", "session_id": 1, "user_id": "masato",
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "context.invalid"


def test_build_endpoint_validation_rejects_too_large_top_k(client) -> None:
    """T-M28-01 G4: 全 4xx は {detail:{code,message}} 形式 (400)."""
    r = client.post("/api/context/build", json={
        "user_message": "hi", "session_id": 1, "top_k": 99,
    })
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "context.invalid"
