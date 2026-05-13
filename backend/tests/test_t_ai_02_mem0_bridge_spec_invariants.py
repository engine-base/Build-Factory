"""T-AI-02: Mem0 + Memory API bridge — 5 AC.

Production artifact 完成済
(backend/services/mem0_bridge.py mirror_fact_to_mem0 +
search_with_rerank + preload_secretary_facts + detect_divergence +
ScoredFact dataclass + MRR re-rank).
本 module は **spec contract layer**.

AC マッピング:
  AC-1 UBIQUITOUS    : 4 async public APIs + ScoredFact 4 fields /
                       reuse FactRecord + _row_to_fact / no langgraph.
  AC-2 EVENT-DRIVEN  : mirror_fact_to_mem0 → long_term_memory.
                       add_conversation + UPDATE mem0_id /
                       search_with_rerank → MRR + 0.6*v + 0.4*c
                       + sort DESC + top_k.
  AC-3 STATE-DRIVEN  : preload_secretary_facts secretary preload
                       (status='synced' + ORDER BY confidence DESC,
                       created_at DESC + LIMIT top_n) / synthetic
                       FactRecord for Mem0-only hits.
  AC-4 OPTIONAL      : empty Mem0 → return [] short-circuit /
                       ImportError tolerated.
  AC-5 UNWANTED      : detect_divergence emits
                       'memory_divergence_detected' / no langgraph /
                       no hardcoded secret.
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BRIDGE_PY = REPO_ROOT / "backend" / "services" / "mem0_bridge.py"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — 4 public APIs + ScoredFact + FactRecord reuse
# ══════════════════════════════════════════════════════════════════════


def test_ac1_module_exists():
    assert BRIDGE_PY.exists()


def test_ac1_four_public_apis_callable():
    from services.mem0_bridge import (
        mirror_fact_to_mem0, search_with_rerank,
        preload_secretary_facts, detect_divergence,
    )
    for fn in (mirror_fact_to_mem0, search_with_rerank,
               preload_secretary_facts, detect_divergence):
        assert inspect.iscoroutinefunction(fn), f"{fn.__name__} not async"


def test_ac1_scored_fact_four_fields():
    from services.mem0_bridge import ScoredFact
    hints = inspect.get_annotations(ScoredFact)
    for fld in ("fact", "vector_score", "confidence", "final_score"):
        assert fld in hints, f"ScoredFact missing field {fld}"


def test_ac1_reuses_fact_record_and_row_to_fact():
    src = BRIDGE_PY.read_text(encoding="utf-8")
    assert re.search(
        r"from\s+services\.memory_facts\s+import\s+[^\n]*FactRecord",
        src,
    )
    assert re.search(
        r"from\s+services\.memory_facts\s+import\s+[^\n]*_row_to_fact",
        src,
    )


def test_ac1_search_with_rerank_top_k_default():
    from services.mem0_bridge import search_with_rerank
    sig = inspect.signature(search_with_rerank)
    assert sig.parameters["top_k"].default == 5


def test_ac1_preload_secretary_facts_top_n_default():
    from services.mem0_bridge import preload_secretary_facts
    sig = inspect.signature(preload_secretary_facts)
    assert sig.parameters["top_n"].default == 50


def test_ac1_no_langgraph_langchain_litellm_imports():
    src = BRIDGE_PY.read_text(encoding="utf-8")
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"'''[\s\S]*?'''", "", src)
    src = re.sub(r"#[^\n]*", "", src)
    src = src.lower()
    for bad in ("langgraph", "langchain", "litellm"):
        assert f"import {bad}" not in src
        assert f"from {bad}" not in src


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — mirror + re-rank formula
# ══════════════════════════════════════════════════════════════════════


def test_ac2_mirror_calls_add_conversation():
    src = BRIDGE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def mirror_fact_to_mem0[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "from services.long_term_memory import add_conversation" in body
    assert "add_conversation(" in body
    assert "fingerprint" in body
    assert "source_session_id" in body
    assert "confidence_score" in body


def test_ac2_mirror_updates_mem0_id_with_fp_prefix():
    src = BRIDGE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def mirror_fact_to_mem0[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    body = m.group(0)
    assert "UPDATE memory_facts SET mem0_id" in body
    assert 'f"mem0:{fact.fingerprint}"' in body or \
           "f'mem0:{fact.fingerprint}'" in body


def test_ac2_rerank_formula_0_6_vector_0_4_confidence():
    src = BRIDGE_PY.read_text(encoding="utf-8")
    assert re.search(
        r"0\.6\s*\*\s*vector_score\s*\+\s*0\.4\s*\*\s*confidence",
        src,
    )


def test_ac2_rerank_uses_mrr_score_1_over_rank_plus_1():
    src = BRIDGE_PY.read_text(encoding="utf-8")
    assert re.search(
        r"vector_score\s*=\s*1\.0\s*/\s*\(\s*rank\s*\+\s*1\s*\)",
        src,
    )


def test_ac2_rerank_calls_search_relevant_memories_and_sorts():
    src = BRIDGE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def search_with_rerank[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "search_relevant_memories" in body
    assert re.search(
        r"scored\.sort\(\s*key\s*=\s*lambda\s+s\s*:\s*s\.final_score\s*,\s*reverse\s*=\s*True\s*\)",
        body,
    )
    assert "scored[:top_k]" in body


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — preload + synthetic FactRecord
# ══════════════════════════════════════════════════════════════════════


def test_ac3_preload_secretary_query_order():
    src = BRIDGE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def preload_secretary_facts[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "status = 'synced'" in body
    assert "deleted_at IS NULL" in body
    assert re.search(
        r"ORDER BY\s+confidence_score\s+DESC\s*,\s*created_at\s+DESC",
        body,
    )
    assert "LIMIT" in body


def test_ac3_synthetic_fact_record_for_mem0_only():
    src = BRIDGE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def search_with_rerank[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    body = m.group(0)
    # synthetic FactRecord で fingerprint=fp / confidence_score=0.5
    assert "FactRecord(" in body
    assert "confidence_score=0.5" in body
    assert 'status="pending"' in body or "status='pending'" in body


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — empty Mem0 short-circuit + ImportError tolerated
# ══════════════════════════════════════════════════════════════════════


def test_ac4_empty_mem0_returns_empty_list():
    src = BRIDGE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def search_with_rerank[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    body = m.group(0)
    # if not mem0_texts: return []
    assert re.search(r"if\s+not\s+mem0_texts[\s\S]*?return\s+\[\]", body)


def test_ac4_import_error_treated_as_empty():
    src = BRIDGE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def search_with_rerank[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    body = m.group(0)
    assert "except Exception" in body
    assert "mem0_texts = []" in body


def test_ac4_mirror_logs_and_returns_none_on_failure():
    src = BRIDGE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def mirror_fact_to_mem0[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    body = m.group(0)
    assert "except Exception" in body
    assert "logger.warning" in body
    assert re.search(r"return\s+None", body)


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — divergence audit + no langgraph + no secret
# ══════════════════════════════════════════════════════════════════════


def test_ac5_detect_divergence_emits_audit():
    src = BRIDGE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def detect_divergence[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "memory_divergence_detected" in body
    assert "emit_event" in body
    assert "missing_in_mem0" in body
    assert re.search(r"missing_ids[\s\S]+?missing\[:50\]", body)


def test_ac5_detect_divergence_query_filters():
    src = BRIDGE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def detect_divergence[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    body = m.group(0)
    assert "status = 'synced'" in body
    assert "deleted_at IS NULL" in body
    assert "ORDER BY id DESC LIMIT" in body


def test_ac5_no_hardcoded_supabase_or_anthropic_key():
    src = BRIDGE_PY.read_text(encoding="utf-8")
    assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_ai_02_canonical_ears():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-AI-02"), None)
    assert t is not None
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == [
        "UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED",
    ]


def test_tickets_t_ai_02_has_adr_link_and_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-AI-02"), None)
    assert t.get("adr_link") is not None
    assert "ADR-010" in t["adr_link"]
    files = t.get("existing_files", [])
    assert "backend/services/mem0_bridge.py" in files


def test_tickets_t_ai_02_ac_mentions_concrete_symbols():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-AI-02"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "mirror_fact_to_mem0",
        "search_with_rerank",
        "preload_secretary_facts",
        "detect_divergence",
        "ScoredFact",
        "FactRecord",
        "add_conversation",
        "search_relevant_memories",
        "memory_divergence_detected",
        "_row_to_fact",
        "ADR-010",
    ):
        assert sym in full, f"T-AI-02 AC missing: {sym}"
