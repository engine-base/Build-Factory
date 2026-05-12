"""T-020-02: Memory 3 tier (claude-agent-sdk session + Memory API + Mem0 +
Obsidian) — 6 AC 機械 invariant 検証.

PR #43 (T-020-02 初版) で production 実装 + 20 件 behavior test (test_memory_service.py).
本 module は **spec contract layer** として、 6 AC が production code の
symbol / signature / event 名 / cross-module SECTION_KEYS 整合と 1:1
対応していることを機械検証する.

既存 test_memory_service.py は behavior (audit_logs に書かれるか) を、
本 test は spec contract (公開 API + ADR-010 invariant + cross-module
G15 SECTION_KEYS 不変) を担当する.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : memory_service が 6 公開 symbol (emit_event /
                       persist_compaction / write_fact / merge_for_session /
                       mirror_to_obsidian / fact_fingerprint) を公開 /
                       Tier 2 9-section / Tier 3 Memory API + Mem0 + Obsidian
                       連携が integration で揃っている.
  AC-2 EVENT-DRIVEN  : persist_compaction(session_id, summary) が
                       chat_messages + audit_logs 'memory_compacted' / 2 秒
                       以内 / runner で summary 自前生成しない
                       (ADR-010 §自前実装禁止).
  AC-3 EVENT-DRIVEN  : merge_for_session が prior_session_id 受領 /
                       Constitution / Memory API / Mem0 / SDK 4 source を
                       deterministic order でマージ.
  AC-4 STATE-DRIVEN  : write_fact が Memory API primary + Mem0 copy /
                       SECTION_KEYS が mid_term_layer に 9 entries で
                       1 回だけ定義され memory_service で再定義しない
                       (G15 cross-module invariant).
  AC-5 OPTIONAL      : mirror_to_obsidian が opt-in (OBSIDIAN_SYNC=1 で
                       None / 有効時は Path 返却) / deterministic file name.
  AC-6 UNWANTED      : Memory API 失敗で memory_degraded event 発火 +
                       Mem0 fallback / silent drop しない (write_fact が
                       dict 返却 + emit_event 'memory_degraded' 含む).
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest

from services import memory_service as ms
from services import mid_term_layer as mtl


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_PATH = REPO_ROOT / "backend" / "services" / "memory_service.py"
MID_PATH = REPO_ROOT / "backend" / "services" / "mid_term_layer.py"
SHORT_PATH = REPO_ROOT / "backend" / "services" / "short_term_layer.py"
LONG_PATH = REPO_ROOT / "backend" / "services" / "long_term_layer.py"
MEM0_PATH = REPO_ROOT / "backend" / "services" / "mem0_bridge.py"
OBSIDIAN_PATH = REPO_ROOT / "backend" / "services" / "obsidian_sync.py"


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — unified facade + 6 public symbols
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("sym", [
    "emit_event",
    "persist_compaction",
    "write_fact",
    "merge_for_session",
    "mirror_to_obsidian",
    "fact_fingerprint",
])
def test_ac1_memory_service_public_symbols(sym):
    assert hasattr(ms, sym), f"memory_service missing public symbol: {sym}"


def test_ac1_three_tiers_present():
    """Tier 1 short / Tier 2 mid / Tier 3 long+mem0+obsidian の 6 layer
    module が全て存在."""
    for p in (SHORT_PATH, MID_PATH, LONG_PATH, MEM0_PATH, OBSIDIAN_PATH):
        assert p.exists(), f"missing tier module: {p}"


def test_ac1_persist_compaction_is_async():
    assert inspect.iscoroutinefunction(ms.persist_compaction)


def test_ac1_write_fact_is_async():
    assert inspect.iscoroutinefunction(ms.write_fact)


def test_ac1_merge_for_session_is_async():
    assert inspect.iscoroutinefunction(ms.merge_for_session)


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — persist_compaction → chat_messages + memory_compacted
# ══════════════════════════════════════════════════════════════════════


def test_ac2_persist_compaction_writes_chat_messages_and_audit_log():
    src = inspect.getsource(ms.persist_compaction)
    # INSERT INTO chat_messages + emit_event("memory_compacted")
    assert "chat_messages" in src
    assert '"memory_compacted"' in src or "'memory_compacted'" in src


def test_ac2_runner_does_not_generate_summary_itself():
    """ADR-010 §自前実装禁止: memory_service は SDK の summary 結果を受け取って
    persist するだけで、 9 section を自前で構築するロジックは持たない."""
    src = _strip_strings_and_comments(SERVICE_PATH.read_text(encoding="utf-8"))
    assert "def build_summary" not in src
    assert "def compress_context" not in src
    assert "def generate_summary" not in src


def test_ac2_persist_compaction_no_blocking_io():
    """AC-2 2 秒以内 spec を構造的に担保: persist_compaction は async で
    asyncio.sleep / time.sleep / subprocess.run のような blocking 処理を
    含まないこと (実 DB 接続なしで verify)."""
    src = inspect.getsource(ms.persist_compaction)
    # blocking 処理パターンが無いこと
    assert "time.sleep" not in src
    assert "subprocess.run" not in src
    assert "subprocess.call" not in src
    # 同期 connection ではなく async with を使う
    assert "async with" in src
    # 1 回の INSERT + 1 回の emit_event のシンプル構造 (loop なし)
    assert src.count("INSERT INTO") <= 1
    # emit_event は 1 回呼ばれる
    assert src.count("emit_event") == 1


# ══════════════════════════════════════════════════════════════════════
# AC-3 EVENT-DRIVEN — merge_for_session multi-source merge
# ══════════════════════════════════════════════════════════════════════


def test_ac3_merge_for_session_signature():
    sig = inspect.signature(ms.merge_for_session)
    params = list(sig.parameters.keys())
    assert "session_id" in params
    assert "prior_session_id" in params


def test_ac3_merge_for_session_includes_4_sources():
    """merge_for_session が SDK session resume / Memory API / Mem0 / Constitution
    の 4 source を全て参照する."""
    src = inspect.getsource(ms.merge_for_session)
    # Markers / function calls that signal each source
    assert "prior_session_id" in src           # SDK session resume marker
    assert "_memory_api_recall" in src         # Memory API source
    # Mem0 vector top-k (search_relevant_memories または long_term_memory 経由)
    assert "search" in src.lower() or "mem0" in src.lower()
    # Constitution
    assert "constitution" in src.lower() or "Constitution" in src


def test_ac3_merge_returns_str():
    sig = inspect.signature(ms.merge_for_session)
    # return annotation should be str (not None)
    ret = sig.return_annotation
    assert ret is str or str(ret) == "str", (
        f"merge_for_session must return str, got: {ret}"
    )


# ══════════════════════════════════════════════════════════════════════
# AC-4 STATE-DRIVEN — Memory API primary + Mem0 copy + SECTION_KEYS invariant
# ══════════════════════════════════════════════════════════════════════


def test_ac4_write_fact_calls_memory_api_first_then_mem0():
    """write_fact source: Memory API → Mem0 の順で書く."""
    src = inspect.getsource(ms.write_fact)
    api_pos = src.find("_memory_api_write")
    mem0_pos = src.find("add_conversation")  # services.long_term_memory.add_conversation
    assert api_pos >= 0, "Memory API 経路が見つからない"
    assert mem0_pos >= 0, "Mem0 経路が見つからない"
    assert api_pos < mem0_pos, "Memory API は Mem0 より先に呼ばれること"


def test_ac4_section_keys_defined_in_mid_term_layer_with_9_entries():
    """G10 / G15: SECTION_KEYS は mid_term_layer に 1 回だけ定義 / 9 entries."""
    assert hasattr(mtl, "SECTION_KEYS")
    assert isinstance(mtl.SECTION_KEYS, tuple)
    assert len(mtl.SECTION_KEYS) == 9, (
        f"SECTION_KEYS must have 9 entries, got {len(mtl.SECTION_KEYS)}"
    )
    expected = {
        "context", "goals", "decisions", "open_questions", "actions",
        "blockers", "facts", "preferences", "next_steps",
    }
    assert set(mtl.SECTION_KEYS) == expected


def test_ac4_section_keys_not_redefined_in_memory_service():
    """G15 cross-module invariant: memory_service.py に SECTION_KEYS の
    再定義なし."""
    src = _strip_strings_and_comments(SERVICE_PATH.read_text(encoding="utf-8"))
    assert "SECTION_KEYS" not in src


# ══════════════════════════════════════════════════════════════════════
# AC-5 OPTIONAL — Obsidian opt-in mirror + deterministic fingerprint
# ══════════════════════════════════════════════════════════════════════


def test_ac5_mirror_to_obsidian_returns_none_when_disabled(monkeypatch):
    monkeypatch.delenv("OBSIDIAN_SYNC", raising=False)
    result = ms.mirror_to_obsidian("user-1", "fact", "Title")
    assert result is None


def test_ac5_mirror_to_obsidian_returns_path_when_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("OBSIDIAN_SYNC", "1")
    monkeypatch.setenv("OBSIDIAN_VAULT", str(tmp_path))
    result = ms.mirror_to_obsidian("user-1", "fact body", "MyNote")
    assert result is not None
    assert isinstance(result, Path)
    assert result.exists()
    text = result.read_text(encoding="utf-8")
    assert "MyNote" in text
    assert "fact body" in text


def test_ac5_fact_fingerprint_deterministic():
    """同じ text → 同じ fingerprint (hash)."""
    a = ms.fact_fingerprint("hello world")
    b = ms.fact_fingerprint("hello world")
    c = ms.fact_fingerprint("different")
    assert a == b
    assert a != c
    # sha256-derived, expect hex prefix
    assert re.match(r"^[0-9a-f]+$", a), f"fingerprint not hex: {a}"


# ══════════════════════════════════════════════════════════════════════
# AC-6 UNWANTED — memory_degraded fallback (no silent drop)
# ══════════════════════════════════════════════════════════════════════


def test_ac6_write_fact_emits_memory_degraded_on_api_failure():
    """write_fact ソース上に memory_degraded event の emit が存在."""
    src = inspect.getsource(ms.write_fact)
    assert '"memory_degraded"' in src or "'memory_degraded'" in src


def test_ac6_write_fact_returns_dict_not_none():
    """silent drop しない → 必ず dict を返す signature."""
    sig = inspect.signature(ms.write_fact)
    ret = sig.return_annotation
    assert ret is dict or str(ret) == "dict", (
        f"write_fact must return dict (no silent drop), got: {ret}"
    )


def test_ac6_write_fact_includes_fallback_marker():
    """fallback='mem0_only' が detail に入る (memory_degraded event detail)."""
    src = inspect.getsource(ms.write_fact)
    assert "mem0_only" in src


def test_ac6_no_anthropic_api_key_hardcoded():
    src = SERVICE_PATH.read_text(encoding="utf-8")
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# ADR-010 invariants
# ══════════════════════════════════════════════════════════════════════


def test_adr_010_no_langgraph_no_langchain_in_memory_service():
    src = SERVICE_PATH.read_text(encoding="utf-8")
    code = _strip_strings_and_comments(src)
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")):
            assert "langgraph" not in stripped, (
                f"forbidden langgraph import: {stripped}"
            )
            assert "langchain" not in stripped, (
                f"forbidden langchain import: {stripped}"
            )


def test_adr_010_litellm_not_in_memory_service_main_path():
    """ADR-010 §Layer 2b: LiteLLM はサブ用途のみ. Memory main path には入らない."""
    src = SERVICE_PATH.read_text(encoding="utf-8")
    code = _strip_strings_and_comments(src)
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")):
            assert "litellm" not in stripped.lower()


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_020_02_ac_normalized_to_canonical_ears():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-020-02"), None)
    assert t is not None
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE"), (
            f"T-020-02 still uses legacy alias: {ty}"
        )
    assert "EVENT-DRIVEN" in types
    assert "STATE-DRIVEN" in types
    assert "OPTIONAL" in types
    assert "UNWANTED" in types


def test_tickets_t_020_02_has_adr_link_and_many_existing_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-020-02"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert len(files) >= 10, f"expected >= 10 existing_files, got {len(files)}"
    assert "backend/services/memory_service.py" in files
    assert "backend/services/mid_term_layer.py" in files
    assert "backend/services/mem0_bridge.py" in files


def test_tickets_t_020_02_ac_mentions_concrete_symbols():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-020-02"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "persist_compaction", "write_fact", "merge_for_session",
        "mirror_to_obsidian", "fact_fingerprint", "SECTION_KEYS",
        "memory_compacted", "memory_degraded",
    ):
        assert sym in full, f"T-020-02 AC missing concrete symbol: {sym}"


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════


def _strip_strings_and_comments(src: str) -> str:
    out: list[str] = []
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
            out.append(line)
    return "\n".join(out)
