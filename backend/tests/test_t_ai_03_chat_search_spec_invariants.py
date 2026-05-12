"""T-AI-03: chat_messages hybrid search — 5 AC.

Production artifact 完成済
(backend/services/chat_search.py hybrid_search + parse_query +
trgm_similarity + char_bigrams + _vector_score_for +
hybrid_search_postgres Phase 2 hook + backend/routers/chat_search.py
GET /api/search/chat).
本 module は **spec contract layer**.

AC マッピング:
  AC-1 UBIQUITOUS    : hybrid_search signature + HybridHit dataclass +
                       GET /api/search/chat + final = 0.5*trgm +
                       0.5*vector.
  AC-2 EVENT-DRIVEN  : parse_query → _candidate_rows LIKE → trgm_similarity
                       + _vector_score_for → sort DESC → top_k /
                       char_bigrams 2-gram with `  ...  ` padding.
  AC-3 STATE-DRIVEN  : hybrid_search_postgres NotImplementedError /
                       embedding_service unavailable → vector=0.0.
  AC-4 OPTIONAL      : date:YYYY-MM regex + LIKE 'YYYY-MM%' + cleaned
                       query whitespace collapse.
  AC-5 UNWANTED      : _candidate_rows except → [] / cleaned empty →
                       short-circuit / no langgraph / no secret.
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_PY = REPO_ROOT / "backend" / "services" / "chat_search.py"
ROUTER_PY = REPO_ROOT / "backend" / "routers" / "chat_search.py"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — hybrid_search signature + router + score formula
# ══════════════════════════════════════════════════════════════════════


def test_ac1_service_and_router_exist():
    assert SERVICE_PY.exists()
    assert ROUTER_PY.exists()


def test_ac1_hybrid_search_signature():
    from services.chat_search import hybrid_search
    assert inspect.iscoroutinefunction(hybrid_search)
    sig = inspect.signature(hybrid_search)
    params = sig.parameters
    assert "query" in params
    for kw in ("user_id", "workspace_id", "top_k", "use_vector",
               "weight_trgm", "weight_vector"):
        assert kw in params, f"hybrid_search missing kw {kw}"
        assert params[kw].kind == inspect.Parameter.KEYWORD_ONLY
    assert params["top_k"].default == 20
    assert params["use_vector"].default is True
    assert params["weight_trgm"].default == 0.5
    assert params["weight_vector"].default == 0.5


def test_ac1_hybrid_hit_dataclass_fields():
    from services.chat_search import HybridHit
    hit = HybridHit(
        message_id=1, thread_id=2, role="user",
        content="hello", created_at=None,
        trgm_score=0.3, vector_score=0.6, final_score=0.45,
    )
    assert hit.to_dict()["message_id"] == 1
    assert "trgm_score" in hit.to_dict()
    assert "vector_score" in hit.to_dict()
    assert "final_score" in hit.to_dict()


def test_ac1_router_prefix_and_endpoint():
    src = ROUTER_PY.read_text(encoding="utf-8")
    assert re.search(
        r"APIRouter\(\s*prefix\s*=\s*[\"']/api/search[\"']",
        src,
    )
    assert re.search(r"@router\.get\(\s*[\"']/chat[\"']", src)


def test_ac1_final_score_formula():
    """final = weight_trgm * trgm + weight_vector * vector."""
    src = SERVICE_PY.read_text(encoding="utf-8")
    assert re.search(
        r"final\s*=\s*weight_trgm\s*\*\s*trgm\s*\+\s*weight_vector\s*\*\s*vector",
        src,
    )


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — parse_query → candidate → trgm → vector → sort
# ══════════════════════════════════════════════════════════════════════


def test_ac2_parse_query_returns_clean_and_date():
    from services.chat_search import parse_query
    cleaned, date_p = parse_query("error message date:2026-04")
    assert cleaned == "error message"
    assert date_p == "2026-04"
    # no date filter
    cleaned, date_p = parse_query("normal query")
    assert cleaned == "normal query"
    assert date_p is None


def test_ac2_candidate_rows_uses_like_and_limit():
    src = SERVICE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def _candidate_rows[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "LOWER(content) LIKE" in body
    assert "LIMIT" in body
    assert "candidate_limit" in body


def test_ac2_char_bigrams_uses_2gram_padding():
    """char_bigrams 関数は ' ... ' でパディングして bigram 抽出."""
    from services.chat_search import char_bigrams
    grams = char_bigrams("abc")
    # `  abc  ` (4 spaces + lowercase) → bigrams contain '  ', ' a', 'ab', 'bc', 'c ', ' '
    assert "ab" in grams or "AB" in grams
    assert isinstance(grams, set)


def test_ac2_trgm_similarity_jaccard():
    from services.chat_search import trgm_similarity
    assert trgm_similarity("hello", "hello") > 0.5
    assert trgm_similarity("", "anything") == 0.0
    assert trgm_similarity("a", "b") < 0.5


def test_ac2_hybrid_search_sorts_desc_and_top_k():
    src = SERVICE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def hybrid_search[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    # hits.sort(key=lambda h: h.final_score, reverse=True)
    assert re.search(
        r"hits\.sort\(\s*key\s*=\s*lambda\s+h\s*:\s*h\.final_score\s*,\s*reverse\s*=\s*True\s*\)",
        body,
    )
    assert "hits[:top_k]" in body


def test_ac2_vector_uses_embedding_service_when_available():
    src = SERVICE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def _vector_score_for[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "embedding_service" in body
    assert "cosine_similarity" in body
    assert "embed" in body


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — postgres path + embedding unavailable graceful
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_ac3_postgres_path_raises_not_implemented():
    from services.chat_search import hybrid_search_postgres
    with pytest.raises(NotImplementedError):
        await hybrid_search_postgres("test", user_id="u1")


def test_ac3_embedding_unavailable_returns_zero():
    src = SERVICE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def _vector_score_for[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    # ImportError → 0.0
    assert "ImportError" in body
    assert re.search(r"return\s+0\.0", body)


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — date:YYYY-MM regex + LIKE + whitespace collapse
# ══════════════════════════════════════════════════════════════════════


def test_ac4_date_filter_regex_pattern():
    from services.chat_search import _DATE_FILTER_RE
    m = _DATE_FILTER_RE.search("query date:2026-04 something")
    assert m is not None
    assert m.group(1) == "2026-04"
    m2 = _DATE_FILTER_RE.search("date:2026-04-15")
    assert m2 is not None
    assert m2.group(1) == "2026-04"


def test_ac4_candidate_rows_adds_date_like():
    src = SERVICE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def _candidate_rows[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "created_at LIKE" in body
    assert re.search(r'date_prefix[}\s]*%', body) or "f\"{date_prefix}%\"" in body


def test_ac4_parse_query_collapses_whitespace():
    from services.chat_search import parse_query
    cleaned, _ = parse_query("query   date:2026-04   extra")
    # whitespace 連続を 1 つに
    assert "  " not in cleaned, f"whitespace not collapsed: {cleaned!r}"


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — DB fail → [] / empty query → [] / no langgraph
# ══════════════════════════════════════════════════════════════════════


def test_ac5_candidate_rows_catches_exception_returns_empty():
    src = SERVICE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def _candidate_rows[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "except Exception" in body
    assert "logger.warning" in body
    assert re.search(r"return\s+\[\]", body)


def test_ac5_hybrid_search_empty_cleaned_returns_empty():
    src = SERVICE_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def hybrid_search[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    # if not cleaned_query: return []
    assert re.search(r"if\s+not\s+cleaned_query[\s\S]*?return\s+\[\]", body)


def test_ac5_no_langgraph_langchain_litellm():
    for path in (SERVICE_PY, ROUTER_PY):
        src = path.read_text(encoding="utf-8")
        src = re.sub(r'"""[\s\S]*?"""', "", src)
        src = re.sub(r"'''[\s\S]*?'''", "", src)
        src = re.sub(r"#[^\n]*", "", src)
        src = src.lower()
        for bad in ("langgraph", "langchain", "litellm"):
            assert f"import {bad}" not in src, f"{path.name} imports {bad}"
            assert f"from {bad}" not in src, f"{path.name} from {bad}"


def test_ac5_no_hardcoded_supabase_or_anthropic_key():
    for path in (SERVICE_PY, ROUTER_PY):
        src = path.read_text(encoding="utf-8")
        assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)
        assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_ai_03_canonical_ears():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-AI-03"), None)
    assert t is not None
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == [
        "UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED",
    ]


def test_tickets_t_ai_03_has_adr_link_and_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-AI-03"), None)
    assert t.get("adr_link") is not None
    assert "ADR-010" in t["adr_link"]
    files = t.get("existing_files", [])
    assert "backend/services/chat_search.py" in files
    assert "backend/routers/chat_search.py" in files


def test_tickets_t_ai_03_ac_mentions_concrete_symbols():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-AI-03"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "hybrid_search",
        "HybridHit",
        "parse_query",
        "trgm_similarity",
        "char_bigrams",
        "_vector_score_for",
        "/api/search/chat",
        "hybrid_search_postgres",
        "_DATE_FILTER_RE",
        "embedding_service",
        "ADR-010",
    ):
        assert sym in full, f"T-AI-03 AC missing: {sym}"
