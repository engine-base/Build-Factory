"""T-001-09: 循環依存防止 trigger (recursive CTE) AC 検証.

DB 不要、 SQL 静的解析で trigger logic を検証.

AC マッピング:
  AC-1 UBIQUITOUS: bf_task_dependencies + ai_hierarchies の 2 graph に trigger
  AC-2 EVENT:     ERRCODE='check_violation' で caller 4xx 化可能
  AC-3 STATE:     既存 RLS / CHECK と直交 (BEFORE INSERT で trigger 起動)
  AC-4 UNWANTED:  cycle 形成 → reject + recursive CTE で reachability 計算
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MIG = ROOT / "supabase" / "migrations" / "20260512300000_cycle_prevention_triggers.sql"


@pytest.fixture(scope="module")
def src() -> str:
    return MIG.read_text(encoding="utf-8")


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: 2 graph に trigger 設置
# ──────────────────────────────────────────────────────────────────────────


def test_task_dep_cycle_function_exists(src: str) -> None:
    assert re.search(
        r"CREATE OR REPLACE FUNCTION\s+bf_prevent_task_dep_cycle\s*\(\s*\)",
        src, re.IGNORECASE,
    )


def test_ai_hierarchy_cycle_function_exists(src: str) -> None:
    assert re.search(
        r"CREATE OR REPLACE FUNCTION\s+bf_prevent_ai_hierarchy_cycle\s*\(\s*\)",
        src, re.IGNORECASE,
    )


def test_task_dep_trigger_attached(src: str) -> None:
    assert re.search(
        r"CREATE TRIGGER\s+trg_prevent_task_dep_cycle\s+BEFORE INSERT OR UPDATE ON bf_task_dependencies",
        src, re.IGNORECASE,
    )


def test_ai_hierarchy_trigger_attached(src: str) -> None:
    assert re.search(
        r"CREATE TRIGGER\s+trg_prevent_ai_hierarchy_cycle\s+BEFORE INSERT OR UPDATE ON ai_hierarchies",
        src, re.IGNORECASE,
    )


def test_both_triggers_use_for_each_row(src: str) -> None:
    """ROW-level trigger (not STATEMENT level)."""
    for name in ("trg_prevent_task_dep_cycle", "trg_prevent_ai_hierarchy_cycle"):
        assert re.search(
            rf"CREATE TRIGGER\s+{name}.*?FOR EACH ROW",
            src, re.IGNORECASE | re.DOTALL,
        )


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: recursive CTE で cycle 検出 + reject
# ──────────────────────────────────────────────────────────────────────────


def test_task_dep_function_uses_recursive_cte(src: str) -> None:
    """bf_prevent_task_dep_cycle 内に WITH RECURSIVE."""
    m = re.search(
        r"CREATE OR REPLACE FUNCTION\s+bf_prevent_task_dep_cycle.*?LANGUAGE plpgsql AS \$\$(.+?)\$\$",
        src, re.IGNORECASE | re.DOTALL,
    )
    assert m
    body = m.group(0)
    assert re.search(r"WITH RECURSIVE\s+reachable", body, re.IGNORECASE)


def test_ai_hierarchy_function_uses_recursive_cte(src: str) -> None:
    m = re.search(
        r"CREATE OR REPLACE FUNCTION\s+bf_prevent_ai_hierarchy_cycle.*?LANGUAGE plpgsql AS \$\$(.+?)\$\$",
        src, re.IGNORECASE | re.DOTALL,
    )
    assert m
    body = m.group(0)
    assert re.search(r"WITH RECURSIVE\s+reachable", body, re.IGNORECASE)


def test_both_functions_raise_check_violation(src: str) -> None:
    """caller が catch して 4xx 化できる ERRCODE."""
    funcs = re.findall(
        r"CREATE OR REPLACE FUNCTION\s+bf_prevent_\w+_cycle.*?\$\$\s*;",
        src, re.IGNORECASE | re.DOTALL,
    )
    assert len(funcs) >= 2
    for body in funcs:
        assert re.search(
            r"USING ERRCODE\s*=\s*'check_violation'", body, re.IGNORECASE,
        )


def test_both_functions_emit_cycle_detected_code(src: str) -> None:
    """RAISE EXCEPTION のメッセージに 'cycle_detected' を含める."""
    assert re.search(
        r"RAISE EXCEPTION\s+'cycle_detected:.*adding dep",
        src, re.IGNORECASE | re.DOTALL,
    )
    assert re.search(
        r"RAISE EXCEPTION\s+'cycle_detected:.*adding hierarchy",
        src, re.IGNORECASE | re.DOTALL,
    )


def test_task_dep_reachability_starts_from_depends_on(src: str) -> None:
    """recursive 起点: NEW.depends_on_task_id (新 edge の to-side)."""
    m = re.search(
        r"CREATE OR REPLACE FUNCTION\s+bf_prevent_task_dep_cycle.*?LANGUAGE plpgsql AS \$\$(.+?)\$\$",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(0)
    # 起点 SELECT に NEW.depends_on_task_id
    assert re.search(
        r"WHERE\s+task_id\s*=\s*NEW\.depends_on_task_id",
        body, re.IGNORECASE,
    )


def test_ai_hierarchy_reachability_starts_from_child(src: str) -> None:
    """ai_hierarchy: 起点 NEW.child_id."""
    m = re.search(
        r"CREATE OR REPLACE FUNCTION\s+bf_prevent_ai_hierarchy_cycle.*?LANGUAGE plpgsql AS \$\$(.+?)\$\$",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(0)
    assert re.search(
        r"WHERE\s+parent_id\s*=\s*NEW\.child_id",
        body, re.IGNORECASE,
    )


def test_ai_hierarchy_skips_null_parent(src: str) -> None:
    """parent_id NULL (root) は cycle 不可能 → RETURN NEW skip."""
    m = re.search(
        r"CREATE OR REPLACE FUNCTION\s+bf_prevent_ai_hierarchy_cycle.*?LANGUAGE plpgsql AS \$\$(.+?)\$\$",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(0)
    assert re.search(
        r"IF\s+NEW\.parent_id\s+IS\s+NULL\s+THEN\s+RETURN\s+NEW",
        body, re.IGNORECASE,
    )


# ──────────────────────────────────────────────────────────────────────────
# AC-1: 自己参照防止 (CHECK 制約と冗長化、 defense in depth)
# ──────────────────────────────────────────────────────────────────────────


def test_task_dep_function_rejects_self_loop(src: str) -> None:
    """task_id = depends_on_task_id (self loop) を CHECK と trigger 両方で reject."""
    m = re.search(
        r"CREATE OR REPLACE FUNCTION\s+bf_prevent_task_dep_cycle.*?LANGUAGE plpgsql AS \$\$(.+?)\$\$",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(0)
    assert re.search(
        r"NEW\.task_id\s*=\s*NEW\.depends_on_task_id",
        body, re.IGNORECASE,
    )
    assert re.search(
        r"task cannot depend on itself",
        body, re.IGNORECASE,
    )


def test_ai_hierarchy_function_rejects_self_parent(src: str) -> None:
    m = re.search(
        r"CREATE OR REPLACE FUNCTION\s+bf_prevent_ai_hierarchy_cycle.*?LANGUAGE plpgsql AS \$\$(.+?)\$\$",
        src, re.IGNORECASE | re.DOTALL,
    )
    body = m.group(0)
    assert re.search(
        r"NEW\.parent_id\s*=\s*NEW\.child_id",
        body, re.IGNORECASE,
    )


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE: idempotency + schema_versions
# ──────────────────────────────────────────────────────────────────────────


def test_both_triggers_idempotent(src: str) -> None:
    """DROP TRIGGER IF EXISTS で re-run safe."""
    for name in ("trg_prevent_task_dep_cycle", "trg_prevent_ai_hierarchy_cycle"):
        assert re.search(
            rf"DROP TRIGGER IF EXISTS\s+{name}\s+ON\s+\w+",
            src, re.IGNORECASE,
        ), f"{name}: DROP TRIGGER IF EXISTS missing"


def test_functions_use_create_or_replace(src: str) -> None:
    """CREATE OR REPLACE で関数 idempotent."""
    assert re.search(
        r"CREATE OR REPLACE FUNCTION\s+bf_prevent_task_dep_cycle",
        src, re.IGNORECASE,
    )
    assert re.search(
        r"CREATE OR REPLACE FUNCTION\s+bf_prevent_ai_hierarchy_cycle",
        src, re.IGNORECASE,
    )


def test_self_registers_to_schema_versions(src: str) -> None:
    assert "INSERT INTO schema_versions" in src
    assert "'20260512300000'" in src
    assert "T-001-09" in src
    assert "ON CONFLICT (version) DO NOTHING" in src


def test_functions_documented_with_comment(src: str) -> None:
    """COMMENT ON FUNCTION で目的を明示."""
    assert re.search(
        r"COMMENT ON FUNCTION\s+bf_prevent_task_dep_cycle",
        src, re.IGNORECASE,
    )
    assert re.search(
        r"COMMENT ON FUNCTION\s+bf_prevent_ai_hierarchy_cycle",
        src, re.IGNORECASE,
    )


def test_no_emoji_in_migration() -> None:
    """CLAUDE.md §5.1: 絵文字禁止."""
    text = MIG.read_text(encoding="utf-8")
    emoji_re = re.compile(
        r"[\U0001F000-\U0001FFFF\U00002600-\U000027BF\U0001F300-\U0001F9FF]"
    )
    assert not emoji_re.findall(text)


# ──────────────────────────────────────────────────────────────────────────
# Boundary: recursive CTE が UNION (重複排除) を使う (UNION ALL ではない)
# ──────────────────────────────────────────────────────────────────────────


def test_recursive_cte_uses_union_for_dedup(src: str) -> None:
    """UNION ALL ではなく UNION で訪問済 node の重複排除 → 無限ループ防止."""
    funcs = re.findall(
        r"WITH RECURSIVE\s+reachable.*?LIMIT 1",
        src, re.IGNORECASE | re.DOTALL,
    )
    assert len(funcs) >= 2
    for body in funcs:
        # UNION (重複排除) を使い、 UNION ALL ではない
        assert re.search(r"\bUNION\b", body, re.IGNORECASE)
        assert not re.search(r"\bUNION ALL\b", body, re.IGNORECASE), (
            "UNION ALL は無限ループの原因 → UNION (dedup) 推奨"
        )


def test_both_functions_use_limit_1_for_early_exit(src: str) -> None:
    """LIMIT 1 で cycle 検出時点で early exit (パフォーマンス)."""
    matches = re.findall(
        r"WHERE\s+node\s*=\s*NEW\.\w+\s+LIMIT 1",
        src, re.IGNORECASE,
    )
    assert len(matches) >= 2