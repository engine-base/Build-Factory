"""T-003-04: スキル context 注入 (CLAUDE.md ルール準拠) — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : context 注入 service + endpoint が F-003 で公開
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit_logs に skills.context.injected emit
  AC-4 UNWANTED      : invalid input / 不明 skill / 空 actor は 4xx + structured
                       かつ persistent state mutate しない
"""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.skill_context_injector import (
    SkillContextError,
    SkillMdNotFoundError,
    inject_context,
    load_claude_rules,
    load_skill_md,
)


# ──────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def _tmp_skill(tmp_path: Path):
    """tmp_path 配下に SKILL.md を置く + CLAUDE.md を生成."""
    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    skill_dir = skills_root / "test-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\ndescription: テスト用スキル\n---\n# Test Skill\n本文です。",
        encoding="utf-8",
    )

    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(
        "# Build-Factory CLAUDE.md\n\n"
        "## 1. 概要\nfoo\n\n"
        "## 5. 絶対ルール (お作法)\n\n"
        "### 5.1 アイコン\nLucide のみ\n\n"
        "### 5.4 セキュリティ\n本番 DROP 禁止\n\n"
        "## 6. 次のセクション\nbar\n",
        encoding="utf-8",
    )
    return {"skills_root": skills_root, "claude_md": claude_md, "skill_dir": skill_dir}


@pytest.fixture(autouse=True)
def _capture_audit(monkeypatch):
    captured: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({
            "event_type": event_type, "user_id": user_id, "detail": detail or {},
        })
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)
    yield captured


@pytest.fixture
def _patch_paths(monkeypatch, _tmp_skill):
    """skill_context_injector のパスを tmp に向ける."""
    import services.skill_context_injector as inj
    monkeypatch.setattr(inj, "SKILL_STORE", _tmp_skill["skills_root"])
    monkeypatch.setattr(inj, "CLAUDE_MD", _tmp_skill["claude_md"])
    yield


# ──────────────────────────────────────────────────────────────────────────
# Service 単体テスト
# ──────────────────────────────────────────────────────────────────────────


def test_load_claude_rules_extracts_section_5(_tmp_skill):
    text = load_claude_rules(_tmp_skill["claude_md"])
    assert "## 5. 絶対ルール" in text
    # 次の "## 6." までを切り出している
    assert "## 6." not in text
    assert "Lucide のみ" in text
    assert "本番 DROP 禁止" in text


def test_load_claude_rules_missing_returns_empty(tmp_path):
    nonexistent = tmp_path / "nope.md"
    assert load_claude_rules(nonexistent) == ""


def test_load_skill_md_reads_file(_tmp_skill):
    text = load_skill_md("test-skill", store=_tmp_skill["skills_root"])
    assert "Test Skill" in text
    assert "テスト用スキル" in text


def test_load_skill_md_missing_raises(_tmp_skill):
    with pytest.raises(SkillMdNotFoundError):
        load_skill_md("nonexistent", store=_tmp_skill["skills_root"])


def test_load_skill_md_empty_name_raises():
    with pytest.raises(SkillContextError):
        load_skill_md("   ")


def test_inject_context_basic(_tmp_skill, _patch_paths):
    result = asyncio.run(inject_context("test-skill"))
    assert result["skill_name"] == "test-skill"
    assert result["rendered_size"] > 0
    assert any(s["title"].startswith("CLAUDE.md") for s in result["sections"])
    assert any("test-skill" in s["title"] for s in result["sections"])
    assert "ABSOLUTE RULES" in result["rendered"]
    assert "SKILL DEFINITION" in result["rendered"]


def test_inject_context_with_persona_chain(_tmp_skill, _patch_paths):
    async def fake_resolver(eid: int):
        return {
            "employee_id": eid,
            "chain_depth": 2,
            "chain": [],
            "merged_guideline": "# secretary\n松本基準\n\n# devon\n実装最小",
        }

    result = asyncio.run(inject_context(
        "test-skill",
        employee_id=3,
        guideline_resolver=fake_resolver,
        include_constitution=False,
    ))
    assert "INHERITED PERSONA GUIDELINE" in result["rendered"]
    assert "松本基準" in result["rendered"]


def test_inject_context_with_constitution(_tmp_skill, _patch_paths):
    async def fake_const():
        return "Constitution: 松本の判断基準 v1"

    result = asyncio.run(inject_context(
        "test-skill",
        include_constitution=True,
        constitution_loader=fake_const,
    ))
    assert "CONSTITUTION" in result["rendered"]
    assert "松本の判断基準 v1" in result["rendered"]


def test_inject_context_missing_skill_md(_tmp_skill, _patch_paths):
    with pytest.raises(SkillMdNotFoundError):
        asyncio.run(inject_context("missing"))


def test_inject_context_invalid_employee_id(_tmp_skill, _patch_paths):
    with pytest.raises(SkillContextError):
        asyncio.run(inject_context("test-skill", employee_id=0))


def test_inject_context_invalid_skill_name():
    with pytest.raises(SkillContextError):
        asyncio.run(inject_context("   "))


def test_inject_context_warnings_when_claude_md_missing(tmp_path, _tmp_skill, monkeypatch):
    """CLAUDE.md が存在しない場合 warnings に記録するが rendering 続行."""
    import services.skill_context_injector as inj
    monkeypatch.setattr(inj, "CLAUDE_MD", tmp_path / "nope.md")
    monkeypatch.setattr(inj, "SKILL_STORE", _tmp_skill["skills_root"])
    result = asyncio.run(inject_context("test-skill", include_claude_rules=True))
    assert "claude_rules_not_found" in result["warnings"]
    # SKILL.md section は残っている
    assert any("test-skill" in s["title"] for s in result["sections"])


def test_inject_context_persona_failure_recorded(_tmp_skill, _patch_paths):
    async def failing_resolver(eid: int):
        raise RuntimeError("DB unreachable")

    result = asyncio.run(inject_context(
        "test-skill", employee_id=5,
        guideline_resolver=failing_resolver,
        include_constitution=False,
    ))
    assert any(w.startswith("persona_chain_failed") for w in result["warnings"])


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint 公開
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_context_endpoint_exists(client, _tmp_skill, _patch_paths):
    r = client.post("/api/skills/test-skill/context", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["skill_name"] == "test-skill"
    assert "rendered" in body
    assert "sections" in body


def test_ac1_context_includes_claude_rules(client, _tmp_skill, _patch_paths):
    r = client.post("/api/skills/test-skill/context",
                     json={"include_constitution": False})
    body = r.json()
    assert "ABSOLUTE RULES" in body["rendered"]
    assert "Lucide のみ" in body["rendered"]


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured error
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_returns_within_2s(client, _tmp_skill, _patch_paths):
    t0 = time.perf_counter()
    r = client.post("/api/skills/test-skill/context", json={})
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_error_uses_detail_code_message(client, _tmp_skill, _patch_paths):
    r = client.post("/api/skills/missing-skill/context", json={})
    assert r.status_code == 404
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "skills.skill_md_not_found"
    assert "message" in body["detail"]


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: audit_logs emit
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_audit_emitted_on_success(client, _tmp_skill, _patch_paths, _capture_audit):
    client.post("/api/skills/test-skill/context",
                 json={"actor_user_id": "alice"})
    events = [e for e in _capture_audit if e["event_type"] == "skills.context.injected"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "alice"
    assert events[0]["detail"]["skill_name"] == "test-skill"
    assert events[0]["detail"]["rendered_size"] > 0
    assert events[0]["detail"]["section_count"] >= 2


def test_ac3_audit_detail_includes_employee_id(client, _tmp_skill, _patch_paths, _capture_audit):
    client.post("/api/skills/test-skill/context",
                 json={"actor_user_id": "bob", "employee_id": 7})
    events = [e for e in _capture_audit if e["event_type"] == "skills.context.injected"]
    assert events[-1]["detail"]["employee_id"] == 7


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_missing_skill_returns_404(client, _tmp_skill, _patch_paths):
    r = client.post("/api/skills/nope/context", json={})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "skills.skill_md_not_found"


def test_ac4_invalid_skill_name_rejected(client, _tmp_skill, _patch_paths):
    r = client.post("/api/skills/BAD!/context", json={})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "skills.invalid_skill_name"


def test_ac4_empty_actor_rejected(client, _tmp_skill, _patch_paths):
    r = client.post("/api/skills/test-skill/context",
                     json={"actor_user_id": "  "})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "skills.unauthorized"


def test_ac4_invalid_employee_id_rejected(client, _tmp_skill, _patch_paths):
    r = client.post("/api/skills/test-skill/context",
                     json={"employee_id": 0})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "skills.invalid_employee_id"


def test_ac4_no_audit_emitted_on_rejected(client, _tmp_skill, _patch_paths, _capture_audit):
    """AC-4 UNWANTED: rejected request では context.injected を emit しない."""
    client.post("/api/skills/nope/context", json={})
    client.post("/api/skills/test-skill/context", json={"actor_user_id": "   "})
    events = [e for e in _capture_audit if e["event_type"] == "skills.context.injected"]
    assert len(events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client, _tmp_skill, _patch_paths):
    cases = [
        ("POST", "/api/skills/BAD!/context", {}),
        ("POST", "/api/skills/test-skill/context", {"actor_user_id": "   "}),
        ("POST", "/api/skills/test-skill/context", {"employee_id": 0}),
        ("POST", "/api/skills/nope/context", {}),
    ]
    for method, path, payload in cases:
        r = client.post(path, json=payload)
        assert 400 <= r.status_code < 500, f"{path}: {r.status_code}"
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
