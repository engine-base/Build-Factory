"""T-005b-02: ui-mockup スキル統合 (existing designer_ai REFACTOR).

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : 6 public API / SKILL.md 存在 / 既存 designer_ai 無改変 (REUSE).
  AC-2 EVENT-DRIVEN  : skill load 100ms (cache hit 1ms) / generate_with_skill が
                       designer_ai 経由で生成 / dict 返却 {html, skill_used, char_count}.
  AC-3 STATE-DRIVEN  : SKILL.md なしで designer_ai default fallback / include_skill=False
                       で skip / path traversal 防止.
  AC-4 UNWANTED      : invalid brief (空/非str/<3/>10000) で ValueError /
                       invalid workspace_id / include_skill 非 bool で ValueError /
                       hardcoded secret なし.
"""
from __future__ import annotations

import asyncio
import json as _json
import re
import time
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE = REPO_ROOT / "backend" / "services" / "ui_mockup_integration.py"
SKILL = REPO_ROOT / "skills" / "ui-mockup" / "SKILL.md"
EXISTING_DESIGNER = REPO_ROOT / "backend" / "services" / "designer_ai.py"


@pytest.fixture(autouse=True)
def _clear_cache():
    from services import ui_mockup_integration as uim
    uim.clear_cache()
    yield
    uim.clear_cache()


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS
# ══════════════════════════════════════════════════════════════════════


def test_ac1_service_exists():
    assert SERVICE.exists()


def test_ac1_skill_file_exists():
    assert SKILL.exists()
    # 既存 skill が ~10K chars
    assert len(SKILL.read_text(encoding="utf-8")) > 1000


def test_ac1_public_api():
    from services import ui_mockup_integration as uim
    for sym in (
        "generate_with_skill", "edit_with_skill",
        "load_ui_mockup_skill", "compose_system_prompt",
        "get_skill_status", "clear_cache", "get_skill_path",
        "MAX_BRIEF_CHARS", "MIN_BRIEF_CHARS",
    ):
        assert hasattr(uim, sym), f"missing uim.{sym}"


def test_ac1_existing_designer_ai_unchanged():
    """designer_ai に ui_mockup_integration への依存を入れていない (REUSE)."""
    assert EXISTING_DESIGNER.exists()
    src = EXISTING_DESIGNER.read_text(encoding="utf-8")
    assert "from services.ui_mockup_integration" not in src
    assert "import services.ui_mockup_integration" not in src


def test_ac1_existing_designer_ai_has_required_symbols():
    """designer_ai が generate_mockup / edit_mockup / call_llm を提供."""
    from services import designer_ai as ai
    for sym in ("generate_mockup", "edit_mockup", "call_llm"):
        assert hasattr(ai, sym), f"existing designer_ai.{sym} missing"


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: skill load + generate
# ══════════════════════════════════════════════════════════════════════


def test_ac2_load_skill_returns_content():
    from services import ui_mockup_integration as uim
    content = uim.load_ui_mockup_skill()
    assert content is not None
    assert "ui-mockup" in content
    assert len(content) > 1000


def test_ac2_load_skill_within_100ms():
    from services import ui_mockup_integration as uim
    uim.clear_cache()
    t0 = time.time()
    uim.load_ui_mockup_skill(use_cache=False)
    elapsed = (time.time() - t0) * 1000
    assert elapsed < 100, f"skill load took {elapsed:.1f}ms"


def test_ac2_cache_hit_fast():
    from services import ui_mockup_integration as uim
    uim.load_ui_mockup_skill()  # warm cache
    t0 = time.time()
    uim.load_ui_mockup_skill()
    elapsed = (time.time() - t0) * 1000
    assert elapsed < 5, f"cache hit took {elapsed:.2f}ms"


def test_ac2_get_skill_status():
    from services import ui_mockup_integration as uim
    status = uim.get_skill_status()
    assert status["exists"] is True
    assert status["char_count"] > 1000
    assert "skill_path" in status


def test_ac2_compose_system_prompt_prepends_skill():
    from services import ui_mockup_integration as uim
    out = uim.compose_system_prompt(
        "Generate a login page.", include_skill=True,
    )
    # skill 文書が含まれる
    assert "ui-mockup skill" in out
    assert "Generate a login page" in out


def test_ac2_compose_system_prompt_no_skill_passthrough():
    from services import ui_mockup_integration as uim
    base = "Generate something."
    out = uim.compose_system_prompt(base, include_skill=False)
    # base と完全一致
    assert out == base


def test_ac2_generate_with_skill_returns_dict(monkeypatch):
    """generate_with_skill が designer_ai 経由で dict を返す."""
    from services import ui_mockup_integration as uim
    from services import designer_ai as ai

    async def fake_generate(**kwargs):
        return {"html": "<html>fake</html>"}

    monkeypatch.setattr(ai, "generate_mockup", fake_generate)

    result = asyncio.run(uim.generate_with_skill(
        1, brief="Generate a login page with two fields.",
    ))
    assert "html" in result
    assert "skill_used" in result
    assert "char_count" in result
    assert result["skill_used"] is True


def test_ac2_generate_without_skill(monkeypatch):
    from services import ui_mockup_integration as uim
    from services import designer_ai as ai

    captured_briefs = []

    async def fake_generate(**kwargs):
        captured_briefs.append(kwargs.get("brief", ""))
        return {"html": "<html>x</html>"}

    monkeypatch.setattr(ai, "generate_mockup", fake_generate)

    result = asyncio.run(uim.generate_with_skill(
        1, brief="Generate a login page with email and password.",
        include_skill=False,
    ))
    assert result["skill_used"] is False
    # brief は無加工
    assert "SKILL CONTEXT" not in captured_briefs[0]


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: graceful fallback + path traversal
# ══════════════════════════════════════════════════════════════════════


def test_ac3_skill_missing_returns_none(tmp_path, monkeypatch):
    """SKILL.md が無いと None (graceful)."""
    from services import ui_mockup_integration as uim
    monkeypatch.setattr(uim, "DEFAULT_SKILL_PATH", tmp_path / "missing.md")
    uim.clear_cache()
    result = uim.load_ui_mockup_skill()
    assert result is None


def test_ac3_compose_system_prompt_falls_back_when_skill_missing(tmp_path, monkeypatch):
    from services import ui_mockup_integration as uim
    monkeypatch.setattr(uim, "DEFAULT_SKILL_PATH", tmp_path / "missing.md")
    uim.clear_cache()
    base = "Original prompt for designer_ai."
    out = uim.compose_system_prompt(base, include_skill=True)
    # skill 無 → base のみ
    assert out == base


def test_ac3_path_traversal_prevention(tmp_path, monkeypatch):
    """REPO_ROOT 外への path 解決は load 拒否."""
    from services import ui_mockup_integration as uim
    # /etc/passwd など外部 path
    outside = Path("/etc/passwd")
    monkeypatch.setattr(uim, "DEFAULT_SKILL_PATH", outside)
    uim.clear_cache()
    result = uim.load_ui_mockup_skill()
    assert result is None


def test_ac3_module_does_not_write_to_audit_logs():
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert "emit_event" not in code
    assert "from services.memory_service" not in code


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
# AC-4 UNWANTED: invalid input
# ══════════════════════════════════════════════════════════════════════


def test_ac4_invalid_brief_raises():
    from services import ui_mockup_integration as uim
    for bad in ("", "  ", "ab", None, 123, [], "x" * 11000):
        with pytest.raises(ValueError):
            asyncio.run(uim.generate_with_skill(1, brief=bad))


def test_ac4_invalid_workspace_id_raises():
    from services import ui_mockup_integration as uim
    for bad in (0, -1, "1", None, 1.5, True):
        with pytest.raises(ValueError):
            asyncio.run(uim.generate_with_skill(bad, brief="valid brief here"))


def test_ac4_invalid_include_skill_raises():
    from services import ui_mockup_integration as uim
    for bad in ("yes", 1, 0, None):
        with pytest.raises(ValueError):
            asyncio.run(uim.generate_with_skill(
                1, brief="valid brief here", include_skill=bad,
            ))


def test_ac4_compose_invalid_base_raises():
    from services import ui_mockup_integration as uim
    for bad in (None, 123, [], {}):
        with pytest.raises(ValueError):
            uim.compose_system_prompt(bad)


def test_ac4_compose_invalid_include_skill_raises():
    from services import ui_mockup_integration as uim
    for bad in ("yes", 1, 0, None):
        with pytest.raises(ValueError):
            uim.compose_system_prompt("base", include_skill=bad)


def test_ac4_edit_with_skill_invalid_current_html_raises():
    from services import ui_mockup_integration as uim
    for bad in ("", "   ", None, 123):
        with pytest.raises(ValueError):
            asyncio.run(uim.edit_with_skill(
                1, current_html=bad, edit_instruction="change color",
            ))


def test_ac4_no_hardcoded_secrets():
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", code)
    assert "SUPABASE_SERVICE_KEY" not in code
    assert "Bearer " not in code
    assert "Authorization" not in code


def test_ac4_no_hardcoded_external_urls():
    src = SERVICE.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert "api.openai.com" not in code
    assert "api.anthropic.com" not in code


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_005b_02_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-005b-02"), None)
    assert t is not None
    generic = [
        "as specified by feature",
        "When the relevant API endpoint or service function is invoked for T-005b-02",
        "While refactoring for T-005b-02 is in progress",
        "If invalid input or unauthorized actor is detected during T-005b-02",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], f"T-005b-02 still generic: {phrase!r}"
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "ui_mockup_integration.py" in full
    assert "SKILL.md" in full
    assert "generate_with_skill" in full


def test_tickets_t_005b_02_has_adr_link():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-005b-02"), None)
    assert t.get("adr_link") is not None
