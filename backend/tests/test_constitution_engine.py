"""T-AI-04: Constitution 自動注入エンジン — 5 AC 全網羅."""
from __future__ import annotations

import asyncio
import sys
import types
from typing import Any

import pytest

from services import constitution_engine as ce
from services.constitution_engine import (
    Constitution, ConstitutionError, CorruptConstitution, MissingConstitution,
    NON_SECRETARY_SECTIONS, SECTION_KEYS,
    get_active_constitution, invalidate_cache, inject_for_session,
    merge_constitutions, assert_constitution_available,
)


# ──────────────────────────────────────────────────────────────────────────
# Helpers / fixtures
# ──────────────────────────────────────────────────────────────────────────


_DEFAULT_PRINCIPLES = {
    "section_1_mission": "Build-Factory mission",
    "section_2_values": ["シンプル", "速く", "妥協しない"],
    "section_3_methods": ["EARS で AC を書く"],
    "section_4_red_lines": ["DROP TABLE 禁止", "鍵 commit 禁止"],
    "section_5_examples": ["D-001"],
}


class _Cur:
    def __init__(self, rows): self._rows = rows
    async def fetchall(self): return self._rows
    async def fetchone(self): return self._rows[0] if self._rows else None


class _Conn:
    Row = dict

    def __init__(self, *, global_rows=None, ws_rows=None,
                  raise_on_global=False, raise_on_ws=False):
        self._global = global_rows or []
        self._ws = ws_rows or []
        self._raise_global = raise_on_global
        self._raise_ws = raise_on_ws
        self.row_factory = None

    async def execute(self, sql, args=()):
        s = sql.lower()
        if "project_id is null" in s:
            if self._raise_global:
                raise RuntimeError("db down global")
            return _Cur(rows=self._global)
        if "project_id = ?" in s:
            if self._raise_ws:
                raise RuntimeError("db down ws")
            return _Cur(rows=self._ws)
        return _Cur(rows=[])

    async def commit(self): return None
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return None


def _patch_ce_db(monkeypatch, **kw):
    fake_mod = types.SimpleNamespace(connect=lambda _p: _Conn(**kw), Row=dict)
    monkeypatch.setattr(ce, "_db", lambda: fake_mod)
    monkeypatch.setattr(ce, "_db_path", lambda: ":memory:")


def _make_principles_row(version: int = 1, *, principles=None, authored_by="masato"):
    import json as _json
    return {
        "id": 1, "version": version, "authored_by": authored_by,
        "principles": _json.dumps(principles or _DEFAULT_PRINCIPLES, ensure_ascii=False),
    }


@pytest.fixture(autouse=True)
def _reset_cache():
    """全 test の前後で cache 初期化."""
    ce._cache.clear()
    yield
    ce._cache.clear()


# ──────────────────────────────────────────────────────────────────────────
# AC-UBIQUITOUS: 最新 Constitution を inject (cached prefix)
# ──────────────────────────────────────────────────────────────────────────


def test_get_active_constitution_loads_from_db(monkeypatch) -> None:
    _patch_ce_db(monkeypatch, global_rows=[_make_principles_row(version=3)])
    c = asyncio.run(get_active_constitution())
    assert c.version == 3
    assert c.principles["section_2_values"] == ["シンプル", "速く", "妥協しない"]


def test_get_active_constitution_caches_subsequent_calls(monkeypatch) -> None:
    """AC-UBIQUITOUS: cache hit で DB hit が増えない (prompt cache prefix 用)."""
    call_count = {"n": 0}

    class _CountingConn(_Conn):
        async def execute(self, sql, args=()):
            call_count["n"] += 1
            return await super().execute(sql, args)

    fake_mod = types.SimpleNamespace(
        connect=lambda _p: _CountingConn(global_rows=[_make_principles_row()]),
        Row=dict,
    )
    monkeypatch.setattr(ce, "_db", lambda: fake_mod)
    monkeypatch.setattr(ce, "_db_path", lambda: ":memory:")

    asyncio.run(get_active_constitution())
    asyncio.run(get_active_constitution())
    asyncio.run(get_active_constitution())
    assert call_count["n"] == 1  # 1 回だけ DB を読んで以降は cache


def test_inject_includes_version_marker_in_prompt(monkeypatch) -> None:
    _patch_ce_db(monkeypatch, global_rows=[_make_principles_row(version=7)])
    text = asyncio.run(inject_for_session(role="default"))
    assert "Constitution v7" in text


# ──────────────────────────────────────────────────────────────────────────
# AC-EVENT: invalidate_cache
# ──────────────────────────────────────────────────────────────────────────


def test_invalidate_cache_causes_fresh_db_read(monkeypatch) -> None:
    call_count = {"n": 0}

    class _CountingConn(_Conn):
        async def execute(self, sql, args=()):
            call_count["n"] += 1
            return await super().execute(sql, args)

    fake_mod = types.SimpleNamespace(
        connect=lambda _p: _CountingConn(global_rows=[_make_principles_row()]),
        Row=dict,
    )
    monkeypatch.setattr(ce, "_db", lambda: fake_mod)
    monkeypatch.setattr(ce, "_db_path", lambda: ":memory:")

    asyncio.run(get_active_constitution())
    asyncio.run(get_active_constitution())
    asyncio.run(invalidate_cache())
    asyncio.run(get_active_constitution())
    # invalidate 後に DB が再 hit
    assert call_count["n"] == 2


# ──────────────────────────────────────────────────────────────────────────
# AC-STATE: secretary vs other roles
# ──────────────────────────────────────────────────────────────────────────


def test_inject_for_secretary_includes_all_sections(monkeypatch) -> None:
    _patch_ce_db(monkeypatch, global_rows=[_make_principles_row()])
    text = asyncio.run(inject_for_session(role="secretary"))
    for sec in SECTION_KEYS:
        assert sec in text


def test_inject_for_non_secretary_only_includes_values_and_redlines(monkeypatch) -> None:
    _patch_ce_db(monkeypatch, global_rows=[_make_principles_row()])
    text = asyncio.run(inject_for_session(role="devon"))
    for sec in NON_SECRETARY_SECTIONS:
        assert sec in text
    # mission / methods / examples は含まれない
    assert "section_1_mission" not in text
    assert "section_3_methods" not in text
    assert "section_5_examples" not in text


def test_inject_for_other_roles_excludes_secretary_only_sections(monkeypatch) -> None:
    """秘書専用 section は他 role に出さない (情報漏洩防止)."""
    _patch_ce_db(monkeypatch, global_rows=[_make_principles_row()])
    text = asyncio.run(inject_for_session(role="mary"))
    assert "Build-Factory mission" not in text  # section_1
    assert "DROP TABLE 禁止" in text  # section_4_red_lines


# ──────────────────────────────────────────────────────────────────────────
# AC-OPTIONAL: workspace override (workspace wins on conflict)
# ──────────────────────────────────────────────────────────────────────────


def test_merge_constitutions_workspace_wins_on_conflict() -> None:
    base = Constitution(
        version=1, workspace_id=None,
        principles={
            "section_2_values": ["base value"],
            "section_4_red_lines": ["base red"],
        },
    )
    override = Constitution(
        version=2, workspace_id=42,
        principles={
            "section_2_values": ["ws value (override)"],
        },
    )
    merged = merge_constitutions(base, override)
    # workspace override wins for section_2
    assert merged.principles["section_2_values"] == ["ws value (override)"]
    # base section_4 が残る (override 未指定)
    assert merged.principles["section_4_red_lines"] == ["base red"]
    # version は max
    assert merged.version == 2


def test_merge_constitutions_with_none_override_returns_base() -> None:
    base = Constitution(version=1, workspace_id=None, principles=_DEFAULT_PRINCIPLES)
    out = merge_constitutions(base, None)
    assert out is base


def test_merge_skips_empty_override_values() -> None:
    """override の section が空 (None / [] / "") なら base を保持."""
    base = Constitution(
        version=1, workspace_id=None,
        principles={"section_2_values": ["keep"]},
    )
    override = Constitution(
        version=2, workspace_id=42,
        principles={"section_2_values": []},  # 空 list → base 保持
    )
    merged = merge_constitutions(base, override)
    assert merged.principles["section_2_values"] == ["keep"]


def test_inject_for_session_applies_workspace_override(monkeypatch) -> None:
    """AC-OPTIONAL: workspace_id 指定で workspace 設定が global を上書き."""
    _patch_ce_db(
        monkeypatch,
        global_rows=[_make_principles_row(principles={
            "section_2_values": ["global val"],
            "section_4_red_lines": ["global red"],
        })],
        ws_rows=[_make_principles_row(version=5, principles={
            "section_2_values": ["WORKSPACE val"],
        })],
    )
    text = asyncio.run(inject_for_session(role="default", workspace_id=42))
    assert "WORKSPACE val" in text
    assert "global val" not in text
    assert "global red" in text  # workspace で override してないので base


# ──────────────────────────────────────────────────────────────────────────
# AC-UNWANTED: corrupted/missing → block + alert
# ──────────────────────────────────────────────────────────────────────────


def test_missing_constitution_raises(monkeypatch) -> None:
    """AC-UNWANTED: DB と env が両方空なら MissingConstitution."""
    _patch_ce_db(monkeypatch, global_rows=[])
    monkeypatch.delenv("CONSTITUTION_TEXT", raising=False)
    with pytest.raises(MissingConstitution, match="not found"):
        asyncio.run(get_active_constitution())


def test_corrupt_constitution_principles_empty_raises(monkeypatch) -> None:
    import json
    row = {"id": 1, "version": 1, "authored_by": "x",
           "principles": json.dumps({})}  # empty dict
    _patch_ce_db(monkeypatch, global_rows=[row])
    with pytest.raises(CorruptConstitution, match="non-empty"):
        asyncio.run(get_active_constitution())


def test_corrupt_constitution_invalid_json_raises(monkeypatch) -> None:
    row = {"id": 1, "version": 1, "authored_by": "x",
           "principles": "not-a-json{{{"}
    _patch_ce_db(monkeypatch, global_rows=[row])
    with pytest.raises(CorruptConstitution, match="parse"):
        asyncio.run(get_active_constitution())


def test_inject_raises_when_section_4_missing(monkeypatch) -> None:
    """AC-UNWANTED inverse: section_4_red_lines 欠落で CorruptConstitution."""
    import json
    bad = {
        "section_2_values": ["x"],
        # section_4_red_lines 欠落
    }
    _patch_ce_db(monkeypatch, global_rows=[{
        "id": 1, "version": 1, "authored_by": "x",
        "principles": json.dumps(bad),
    }])
    with pytest.raises(CorruptConstitution, match="section_4"):
        asyncio.run(inject_for_session(role="default"))


def test_assert_constitution_available_passes_for_valid(monkeypatch) -> None:
    _patch_ce_db(monkeypatch, global_rows=[_make_principles_row()])
    c = asyncio.run(assert_constitution_available())
    assert c.version == 1


def test_assert_constitution_available_fails_when_red_lines_missing(monkeypatch) -> None:
    import json
    bad = {"section_2_values": ["x"]}
    _patch_ce_db(monkeypatch, global_rows=[{
        "id": 1, "version": 1, "authored_by": "x",
        "principles": json.dumps(bad),
    }])
    with pytest.raises(CorruptConstitution, match="red lines"):
        asyncio.run(assert_constitution_available())


def test_env_fallback_when_db_empty(monkeypatch) -> None:
    """DB 空 + env CONSTITUTION_TEXT → version=0 で env 内容を返す."""
    _patch_ce_db(monkeypatch, global_rows=[])
    monkeypatch.setenv("CONSTITUTION_TEXT", "env-only values")
    c = asyncio.run(get_active_constitution())
    assert c.version == 0
    assert c.principles["section_2_values"] == "env-only values"


# ──────────────────────────────────────────────────────────────────────────
# Constitution dataclass helpers
# ──────────────────────────────────────────────────────────────────────────


def test_section_text_for_list_renders_as_bullets() -> None:
    c = Constitution(version=1, workspace_id=None,
                      principles={"section_2_values": ["A", "B", "C"]})
    s = c.section_text("section_2_values")
    assert "- A" in s and "- B" in s and "- C" in s


def test_section_text_for_dict_renders_as_json() -> None:
    c = Constitution(version=1, workspace_id=None,
                      principles={"section_3_methods": {"k": "v"}})
    s = c.section_text("section_3_methods")
    assert '"k"' in s


def test_section_text_for_missing_section_returns_empty() -> None:
    c = Constitution(version=1, workspace_id=None, principles={})
    assert c.section_text("section_99") == ""


def test_to_prompt_skips_empty_sections(monkeypatch) -> None:
    c = Constitution(
        version=1, workspace_id=None,
        principles={"section_2_values": ["x"]},  # section_4 欠落
    )
    text = c.to_prompt(sections=("section_2_values", "section_4_red_lines"))
    assert "section_2_values" in text
    # 空 section は出力しない
    assert "section_4_red_lines" not in text


# ──────────────────────────────────────────────────────────────────────────
# DB error graceful
# ──────────────────────────────────────────────────────────────────────────


def test_get_active_handles_db_error_falls_back_to_env(monkeypatch) -> None:
    """DB 例外時は env fallback で起動 (block しない)."""
    _patch_ce_db(monkeypatch, raise_on_global=True)
    monkeypatch.setenv("CONSTITUTION_TEXT", "env safe")
    c = asyncio.run(get_active_constitution())
    assert c.version == 0


def test_get_active_blocks_when_db_error_and_no_env(monkeypatch) -> None:
    _patch_ce_db(monkeypatch, raise_on_global=True)
    monkeypatch.delenv("CONSTITUTION_TEXT", raising=False)
    with pytest.raises(MissingConstitution):
        asyncio.run(get_active_constitution())


# ──────────────────────────────────────────────────────────────────────────
# Exception hierarchy
# ──────────────────────────────────────────────────────────────────────────


def test_corrupt_and_missing_inherit_constitution_error() -> None:
    assert issubclass(CorruptConstitution, ConstitutionError)
    assert issubclass(MissingConstitution, ConstitutionError)
    assert issubclass(ConstitutionError, RuntimeError)
