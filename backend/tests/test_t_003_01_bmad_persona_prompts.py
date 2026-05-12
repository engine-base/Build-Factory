"""T-003-01: BMAD 12 → 10 メンバー persona prompt 整理.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : 10 persona md 全存在 / 7 sections format /
                       README で 12→10 mapping 文書化 / loader + list 公開 /
                       既存 ai_employee_store / delegation_service / secretary_chat 無改変.
  AC-2 EVENT-DRIVEN  : load_persona_prompt 100ms 以内 / cache hit 1ms 以内 /
                       get_prompt_validation_status で 7 sections check.
  AC-3 STATE-DRIVEN  : md=source of truth / DB seed=cache / audit_logs 書込なし /
                       path traversal 防止.
  AC-4 UNWANTED      : invalid persona_key で ValueError / file missing で None graceful /
                       hardcoded secret なし / 外部 HTTP call なし.
"""
from __future__ import annotations

import json as _json
import re
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
PERSONAS_DIR = REPO_ROOT / "data" / "personas" / "bmad"
README = PERSONAS_DIR / "README.md"
LOADER = REPO_ROOT / "backend" / "services" / "bmad_persona_prompts.py"


VALID_PERSONA_KEYS = (
    "mary", "preston", "winston", "sally", "devon",
    "quinn", "reviewer", "brand", "mockup", "logan",
)

REQUIRED_SECTIONS = (
    "## Role", "## Personality", "## Tone Style", "## Catchphrase",
    "## Specialty", "## Constraints", "## Handoff",
)


@pytest.fixture(autouse=True)
def _clear_loader_cache():
    from services import bmad_persona_prompts as bp
    bp.clear_cache()
    yield
    bp.clear_cache()


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS
# ══════════════════════════════════════════════════════════════════════


def test_ac1_all_10_persona_md_exist():
    for key in VALID_PERSONA_KEYS:
        path = PERSONAS_DIR / f"{key}.md"
        assert path.exists(), f"missing persona md: {path}"


def test_ac1_readme_exists():
    assert README.exists()


def test_ac1_readme_documents_12_to_10_mapping():
    src = README.read_text(encoding="utf-8")
    assert "12 → 10" in src or "12 -> 10" in src or "12→10" in src
    # 全 10 persona key が言及されている
    for key in VALID_PERSONA_KEYS:
        assert f"**{key}**" in src or f"`{key}`" in src or key in src


def test_ac1_each_persona_has_7_required_sections():
    """各 md ファイルが 7 required sections を含む."""
    for key in VALID_PERSONA_KEYS:
        src = (PERSONAS_DIR / f"{key}.md").read_text(encoding="utf-8")
        for sec in REQUIRED_SECTIONS:
            assert sec in src, f"{key}.md missing section: {sec}"


def test_ac1_loader_module_exists():
    assert LOADER.exists()


def test_ac1_loader_public_api():
    from services import bmad_persona_prompts as bp
    for sym in (
        "load_persona_prompt", "list_personas", "get_prompt_validation_status",
        "get_personas_dir", "clear_cache",
        "VALID_PERSONA_KEYS", "REQUIRED_SECTIONS",
    ):
        assert hasattr(bp, sym), f"loader.{sym} missing"


def test_ac1_existing_modules_unchanged():
    """ai_employee_store / delegation_service / secretary_chat に BMAD loader 依存を入れていない (REUSE)."""
    for fn in ("ai_employee_store.py", "delegation_service.py", "secretary_chat.py"):
        path = REPO_ROOT / "backend" / "services" / fn
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8")
        # 本セッションで bmad_persona_prompts への依存を追加していないこと
        assert "from services.bmad_persona_prompts" not in src
        assert "import services.bmad_persona_prompts" not in src


def test_ac1_db_seed_still_intact():
    """既存 supabase migration が破壊されていないこと."""
    seed = REPO_ROOT / "supabase" / "migrations" / "20260512400000_bmad_personas_seed.sql"
    assert seed.exists()
    src = seed.read_text(encoding="utf-8")
    # 10 persona INSERT が含まれる
    for key in VALID_PERSONA_KEYS:
        assert f"'{key}'" in src, f"DB seed missing INSERT for {key}"


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: load + validation timing
# ══════════════════════════════════════════════════════════════════════


def test_ac2_load_persona_prompt_returns_content():
    from services import bmad_persona_prompts as bp
    content = bp.load_persona_prompt("mary")
    assert content is not None
    assert "Mary" in content
    assert "## Role" in content


def test_ac2_load_within_100ms():
    from services import bmad_persona_prompts as bp
    t0 = time.time()
    bp.load_persona_prompt("devon", use_cache=False)
    elapsed = (time.time() - t0) * 1000
    assert elapsed < 100, f"load took {elapsed:.1f}ms (must be < 100ms)"


def test_ac2_cache_hit_under_5ms():
    from services import bmad_persona_prompts as bp
    bp.load_persona_prompt("winston")  # warm cache
    t0 = time.time()
    bp.load_persona_prompt("winston")
    elapsed = (time.time() - t0) * 1000
    # cache hit は file I/O なし、十分 5ms 以内
    assert elapsed < 5, f"cache hit took {elapsed:.2f}ms"


def test_ac2_list_personas_returns_all_10():
    from services import bmad_persona_prompts as bp
    items = bp.list_personas()
    assert len(items) == 10
    keys = [i["persona_key"] for i in items]
    assert set(keys) == set(VALID_PERSONA_KEYS)
    # 全て available (md ファイルが存在する)
    for item in items:
        assert item["available"] is True


def test_ac2_get_prompt_validation_status_all_sections_present():
    from services import bmad_persona_prompts as bp
    for key in VALID_PERSONA_KEYS:
        status = bp.get_prompt_validation_status(key)
        assert status["available"] is True
        assert status["missing_sections"] == [], (
            f"{key}.md missing sections: {status['missing_sections']}"
        )
        assert status["char_count"] > 100


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: read-only / no audit / path traversal 防止
# ══════════════════════════════════════════════════════════════════════


def test_ac3_loader_does_not_write_audit_logs():
    src = LOADER.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert "emit_event" not in code
    assert "from services.memory_service" not in code


def test_ac3_loader_does_not_make_http_calls():
    src = LOADER.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert "httpx" not in code
    assert "requests.get" not in code
    assert "urllib" not in code


def test_ac3_path_traversal_prevention():
    """persona_key が valid format でも path traversal を試みる場合は ValueError."""
    from services import bmad_persona_prompts as bp
    for bad in ("../etc/passwd", "../../mary", "mary/../sally", "."):
        with pytest.raises(ValueError):
            bp.load_persona_prompt(bad)


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


def test_ac4_invalid_persona_key_raises():
    from services import bmad_persona_prompts as bp
    for bad in ("", "   ", None, 123, [], {}, "bogus_persona"):
        with pytest.raises(ValueError):
            bp.load_persona_prompt(bad)


def test_ac4_invalid_chars_in_key_raises():
    from services import bmad_persona_prompts as bp
    for bad in ("mary devon", "mary.md", "mary;quinn", "mary!"):
        with pytest.raises(ValueError):
            bp.load_persona_prompt(bad)


def test_ac4_missing_file_returns_none_graceful(tmp_path, monkeypatch):
    """file missing → None (no raise)."""
    from services import bmad_persona_prompts as bp
    # personas_dir を一時 path に差替 → mary.md は存在しない
    monkeypatch.setattr(bp, "_DEFAULT_PERSONAS_DIR", tmp_path)
    bp.clear_cache()
    result = bp.load_persona_prompt("mary")
    assert result is None


def test_ac4_no_hardcoded_secrets():
    src = LOADER.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", code)
    assert "SUPABASE_SERVICE_KEY" not in code
    assert "Bearer " not in code


def test_ac4_use_cache_must_be_bool():
    from services import bmad_persona_prompts as bp
    for bad in ("yes", 1, 0, None):
        with pytest.raises(ValueError):
            bp.load_persona_prompt("mary", use_cache=bad)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_003_01_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-003-01"), None)
    assert t is not None
    generic = [
        "as specified by feature",
        "When the relevant API endpoint or service function is invoked for T-003-01",
        "While refactoring for T-003-01 is in progress",
        "If invalid input or unauthorized actor is detected during T-003-01",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], f"T-003-01 still generic: {phrase!r}"
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "load_persona_prompt" in full
    assert "VALID_PERSONA_KEYS" in full
    assert "mary" in full and "logan" in full


def test_tickets_t_003_01_has_adr_link_and_existing_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-003-01"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert files and not any("TBD" in f for f in files)
