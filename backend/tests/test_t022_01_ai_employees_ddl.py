"""T-022-01: ai_employees DDL 拡張確認 + BMAD 10 ペルソナ seed AC 検証.

AC マッピング:
  AC-1 UBIQUITOUS: T-001-03 ai_employees / ai_personas が F-022 要件カバー +
                   BMAD 10 ペルソナ seed 投入
  AC-3 STATE:     既存 row 上書きしない (ON CONFLICT DO NOTHING)
  AC-4 UNWANTED:  CHECK 制約は T-001-03 で定義済 (本 migration data only)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MIGS = ROOT / "supabase" / "migrations"
T001_03_MIG = MIGS / "20260512200000_ai_hierarchy_clone_tables.sql"
T022_01_MIG = MIGS / "20260512400000_bmad_personas_seed.sql"


@pytest.fixture(scope="module")
def t001_03_src() -> str:
    return T001_03_MIG.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def t022_01_src() -> str:
    return T022_01_MIG.read_text(encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: T-001-03 ai_employees + ai_personas が F-022 要件をカバー
# ──────────────────────────────────────────────────────────────────────────


def test_ai_employees_has_role_level_for_bmad_hierarchy(t001_03_src: str) -> None:
    """secretary / leader / member の 3 階層 (M-22 必須)."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+ai_employees\s*\((.+?)\);",
        t001_03_src, re.IGNORECASE | re.DOTALL,
    )
    assert m
    body = m.group(1)
    assert "CHECK (role_level IN" in body
    for v in ("secretary", "leader", "member"):
        assert f"'{v}'" in body


def test_ai_personas_has_required_persona_fields(t001_03_src: str) -> None:
    """F-022: personality / tone_style / catchphrase / specialty / handles 全完備."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+ai_personas\s*\((.+?)\);",
        t001_03_src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(1)
    for field in ("persona_name", "personality", "tone_style", "catchphrase",
                   "specialty", "handles", "avatar_lucide"):
        assert field in body, f"required field {field!r} missing"


def test_ai_employees_links_to_persona_via_persona_id(t001_03_src: str) -> None:
    """ai_employees.persona_id FK で個性付与."""
    assert "fk_ai_employees_persona" in t001_03_src
    # persona_id 列の定義
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+ai_employees\s*\((.+?)\);",
        t001_03_src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(1)
    assert "persona_id" in body


def test_ai_clones_opt_in_default_off_for_m22(t001_03_src: str) -> None:
    """M-22 必須: opt-in default OFF."""
    m = re.search(
        r"CREATE TABLE IF NOT EXISTS\s+ai_clones\s*\((.+?)\);",
        t001_03_src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(1)
    assert re.search(
        r"is_opted_in\s+BOOLEAN\s+NOT NULL\s+DEFAULT\s+FALSE",
        body, re.IGNORECASE,
    )


# ──────────────────────────────────────────────────────────────────────────
# AC-1: BMAD 10 ペルソナ seed
# ──────────────────────────────────────────────────────────────────────────


BMAD_CORE_PERSONAS = ("mary", "preston", "winston", "sally", "devon", "quinn", "reviewer")
PHASE_1_EXT_PERSONAS = ("brand", "mockup", "logan")
ALL_10_PERSONAS = BMAD_CORE_PERSONAS + PHASE_1_EXT_PERSONAS


@pytest.mark.parametrize("persona_key", ALL_10_PERSONAS)
def test_each_of_10_personas_seeded(t022_01_src: str, persona_key: str) -> None:
    """10 ペルソナそれぞれの persona_key が INSERT 文に含まれる."""
    assert re.search(
        rf"^\s*\('{persona_key}',", t022_01_src, re.IGNORECASE | re.MULTILINE,
    ), f"persona_key {persona_key!r} not in seed"


def test_seed_has_exactly_10_personas(t022_01_src: str) -> None:
    """INSERT VALUES 行が 10 件 (CLAUDE.md §3 BMAD 10 ペルソナ)."""
    # `    ('persona_key',` の行をカウント
    rows = re.findall(
        r"^\s*\('([a-z_]+)',\s*'[A-Za-z]",
        t022_01_src, re.MULTILINE,
    )
    assert len(rows) == 10, f"expected 10 personas, got {len(rows)}: {rows}"
    assert set(rows) == set(ALL_10_PERSONAS)


def test_bmad_core_personas_marked_in_metadata(t022_01_src: str) -> None:
    """7 core ペルソナの metadata に bmad_core:true."""
    # mary / preston / winston / sally / devon / quinn / reviewer 各行に bmad_core
    bmad_core_count = len(re.findall(
        r'"bmad_core":\s*true', t022_01_src,
    ))
    assert bmad_core_count == 7, f"expected 7 bmad_core:true, got {bmad_core_count}"


def test_phase_1_extension_personas_marked_in_metadata(t022_01_src: str) -> None:
    """3 phase 1 拡張ペルソナの metadata に bmad_core:false + phase:1."""
    phase_1_count = len(re.findall(
        r'"phase":\s*1', t022_01_src,
    ))
    assert phase_1_count == 3


def test_seeded_personas_use_lucide_icons_only(t022_01_src: str) -> None:
    """CLAUDE.md §5.1: avatar は lucide icon name のみ. emoji 0."""
    # avatar_lucide 列の値部分を抽出
    matches = re.findall(
        r"^\s*\('[a-z_]+',[^)]+?'([a-z][a-z0-9-]+)',",
        t022_01_src, re.MULTILINE,
    )
    # avatar_lucide は kebab-case の lucide icon name
    for avatar in matches:
        assert "-" in avatar or avatar.isalpha(), f"avatar {avatar!r} looks suspicious"
    # 絵文字なし
    emoji_re = re.compile(
        r"[\U0001F000-\U0001FFFF\U00002600-\U000027BF\U0001F300-\U0001F9FF]"
    )
    text = T022_01_MIG.read_text(encoding="utf-8")
    found = emoji_re.findall(text)
    assert not found, f"emoji in seed: {found}"


def test_each_persona_has_specialty_field(t022_01_src: str) -> None:
    """全 10 ペルソナに specialty (担当領域) が記述されている."""
    # INSERT VALUES の各タプルが 9 文字列 column を持つ
    rows = re.findall(
        r"\('([a-z_]+)',\s*'([^']+)',\s*'([^']+)',\s*'([^']+)',\s*'([^']+)',\s*'([^']+)',\s*'([^']+)',\s*'([^']+)',",
        t022_01_src,
    )
    assert len(rows) == 10
    for row in rows:
        # row[5] = specialty
        assert row[5].strip(), f"persona {row[0]}: empty specialty"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE: idempotency + backward compat
# ──────────────────────────────────────────────────────────────────────────


def test_seed_uses_on_conflict_do_nothing(t022_01_src: str) -> None:
    """既存 row を上書きしない."""
    assert re.search(
        r"ON CONFLICT\s*\(\s*persona_key\s*\)\s+DO NOTHING",
        t022_01_src, re.IGNORECASE,
    )


def test_seed_self_registers_to_schema_versions(t022_01_src: str) -> None:
    assert "INSERT INTO schema_versions" in t022_01_src
    assert "'20260512400000'" in t022_01_src
    assert "T-022-01" in t022_01_src
    assert "ON CONFLICT (version) DO NOTHING" in t022_01_src


def test_seed_documents_table_purpose(t022_01_src: str) -> None:
    """COMMENT ON TABLE で T-022-01 の役割を明示."""
    assert re.search(
        r"COMMENT ON TABLE\s+ai_personas",
        t022_01_src, re.IGNORECASE,
    )
    assert "T-022-01" in t022_01_src
    assert "BMAD 10" in t022_01_src


# ──────────────────────────────────────────────────────────────────────────
# F-022 整合性 boundary
# ──────────────────────────────────────────────────────────────────────────


def test_persona_keys_match_claude_md_spec(t022_01_src: str) -> None:
    """CLAUDE.md §3 列挙 7 + Phase 1 拡張 3 = 10 と一致."""
    rows = re.findall(
        r"^\s*\('([a-z_]+)',",
        t022_01_src, re.MULTILINE,
    )
    expected = set(ALL_10_PERSONAS)
    actual = set(rows[:10])  # schema_versions INSERT 等の他行を排除
    assert actual == expected, f"diff: missing={expected - actual}, extra={actual - expected}"


def test_no_secretary_in_seed(t022_01_src: str) -> None:
    """secretary は ~/.claude/skills/secretary/ で別管理 (seed しない)."""
    # `('secretary',` の INSERT 行が無いこと (comment 内の言及は OK)
    assert not re.search(
        r"^\s*\('secretary',", t022_01_src, re.MULTILINE,
    ), "secretary should not be in seed (managed separately)"


def test_seed_personality_traits_unique_per_persona(t022_01_src: str) -> None:
    """10 ペルソナの personality は全て異なる (個性の重複なし)."""
    personalities = re.findall(
        r"^\s*\('[a-z_]+',\s*'[^']+',\s*'([^']+)',",
        t022_01_src, re.MULTILINE,
    )
    assert len(personalities) == 10
    assert len(set(personalities)) == 10, "personality は重複してはならない"