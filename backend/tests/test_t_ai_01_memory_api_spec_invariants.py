"""T-AI-01: Anthropic Memory API integration — 5 AC.

Production artifact 完成済
(backend/services/memory_facts.py write_fact + extract_facts_from_session
+ recall_facts + request_deletion + process_retry_queue +
process_pending_deletions + _memory_api_write_with_retry +
_physical_delete_fact + FactRecord + fingerprint SHA-256).
本 module は **spec contract layer**.

AC マッピング:
  AC-1 UBIQUITOUS    : 6 public APIs + FactRecord 14 fields +
                       fingerprint helper / no langgraph.
  AC-2 EVENT-DRIVEN  : _FACT_RE D/P/C-XXX MULTILINE / INSERT OR IGNORE
                       status='pending' / with_retry idempotency_key /
                       _mark_synced / RetryExhaustedError audit.
  AC-3 STATE-DRIVEN  : ANTHROPIC_API_KEY guard / SDK availability guard
                       / memory_stores append-or-create guard.
  AC-4 OPTIONAL      : request_deletion soft-delete +
                       'memory_fact_deletion_requested' /
                       process_pending_deletions delete cascade
                       (memory_stores + Mem0 + DB row) +
                       'memory_facts_deleted_batch' audit.
  AC-5 UNWANTED      : _mark_failed retry_count++ + retry_count < 5 +
                       fact_text empty short-circuit / no langgraph /
                       no hardcoded secret.
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MEMORY_PY = REPO_ROOT / "backend" / "services" / "memory_facts.py"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — 6 public APIs + FactRecord + fingerprint
# ══════════════════════════════════════════════════════════════════════


def test_ac1_module_exists():
    assert MEMORY_PY.exists()


def test_ac1_six_public_apis_callable():
    from services.memory_facts import (
        write_fact, extract_facts_from_session, recall_facts,
        request_deletion, process_retry_queue, process_pending_deletions,
    )
    for fn in (write_fact, extract_facts_from_session, recall_facts,
               request_deletion, process_retry_queue,
               process_pending_deletions):
        assert inspect.iscoroutinefunction(fn), f"{fn.__name__} not async"


def test_ac1_write_fact_signature():
    from services.memory_facts import write_fact
    sig = inspect.signature(write_fact)
    p = sig.parameters
    for kw in ("user_id", "fact_text", "source_session_id", "workspace_id",
               "confidence_score", "kind"):
        assert kw in p, f"write_fact missing kw {kw}"
        assert p[kw].kind == inspect.Parameter.KEYWORD_ONLY
    assert p["confidence_score"].default == 0.7
    assert p["kind"].default == "durable"


def test_ac1_recall_facts_top_k_default():
    from services.memory_facts import recall_facts
    sig = inspect.signature(recall_facts)
    assert sig.parameters["top_k"].default == 5


def test_ac1_fact_record_14_fields():
    from services.memory_facts import FactRecord
    hints = inspect.get_annotations(FactRecord)
    for fld in (
        "id", "user_id", "workspace_id", "fact_text", "kind",
        "source_session_id", "confidence_score", "fingerprint",
        "status", "retry_count", "memory_api_id", "mem0_id",
        "last_error", "created_at", "synced_at", "deleted_at",
    ):
        assert fld in hints, f"FactRecord missing field {fld}"


def test_ac1_fingerprint_sha256_head_16():
    from services.memory_facts import fingerprint
    fp = fingerprint("hello world")
    assert isinstance(fp, str)
    assert len(fp) == 16
    assert re.fullmatch(r"[0-9a-f]{16}", fp)
    # same input → same fingerprint
    assert fingerprint("hello world") == fp
    # whitespace normalized
    assert fingerprint("  HELLO   world  ") == fp


def test_ac1_no_langgraph_langchain_litellm_imports():
    src = MEMORY_PY.read_text(encoding="utf-8")
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"'''[\s\S]*?'''", "", src)
    src = re.sub(r"#[^\n]*", "", src)
    src = src.lower()
    for bad in ("langgraph", "langchain", "litellm"):
        assert f"import {bad}" not in src, f"forbidden import {bad}"
        assert f"from {bad}" not in src, f"forbidden from {bad}"


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — extract regex + INSERT pending + with_retry + audit
# ══════════════════════════════════════════════════════════════════════


def test_ac2_fact_regex_captures_dpc_prefixes():
    from services.memory_facts import _FACT_RE, extract_facts_from_text
    text = (
        "## D-001: Supabase Postgres adoption\n"
        "P-002 ユーザは絵文字を嫌う\n"
        "**C-003** クライアント受託のため\n"
        "noise without prefix\n"
    )
    pairs = extract_facts_from_text(text)
    prefixes = [p for p, _ in pairs]
    assert "D-001" in prefixes
    assert "P-002" in prefixes
    assert "C-003" in prefixes


def test_ac2_write_fact_uses_with_retry_and_idempotency():
    src = MEMORY_PY.read_text(encoding="utf-8")
    # `from services.anthropic_retry import RetryExhaustedError, with_retry`
    assert re.search(
        r"from\s+services\.anthropic_retry\s+import\s+[^\n]*with_retry",
        src,
    )
    # with_retry(... idempotency_key=fp ...)
    assert re.search(
        r"with_retry\([\s\S]+?idempotency_key\s*=\s*fp",
        src,
    )
    assert "label=\"memory_api.append\"" in src or \
           "label='memory_api.append'" in src


def test_ac2_insert_pending_status_in_write_fact():
    src = MEMORY_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def write_fact[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "INSERT OR IGNORE INTO memory_facts" in body
    assert "'pending'" in body
    assert "fingerprint" in body


def test_ac2_retry_exhausted_audit_event():
    src = MEMORY_PY.read_text(encoding="utf-8")
    assert "RetryExhaustedError" in src
    assert "memory_api_write_failed" in src
    assert "memory_api_write_error" in src
    # _mark_synced / _mark_failed branches
    assert "_mark_synced" in src
    assert "_mark_failed" in src


def test_ac2_extract_reads_chat_messages_by_thread():
    src = MEMORY_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def extract_facts_from_session[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert re.search(
        r"SELECT[\s\S]+?FROM\s+chat_messages[\s\S]+?WHERE\s+thread_id",
        body,
    )


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — ANTHROPIC_API_KEY / SDK / memory_stores guards
# ══════════════════════════════════════════════════════════════════════


def test_ac3_api_key_unset_raises_runtime_error():
    src = MEMORY_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def _memory_api_write_with_retry[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "ANTHROPIC_API_KEY" in body
    assert re.search(
        r"raise\s+RuntimeError\([\"']ANTHROPIC_API_KEY not set[\"']",
        body,
    )


def test_ac3_memory_stores_availability_guarded():
    src = MEMORY_PY.read_text(encoding="utf-8")
    # memory_stores is None → raise
    assert "memory_stores is None" in src or \
           "memory_stores = getattr" in src
    assert "anthropic Memory API not available" in src
    assert "memory_stores has neither append nor create" in src


def test_ac3_uses_client_beta_memory_stores():
    src = MEMORY_PY.read_text(encoding="utf-8")
    # client.beta.memory_stores (via getattr chain)
    assert re.search(
        r"getattr\(\s*getattr\(\s*client\s*,\s*[\"']beta[\"']\s*,\s*None\s*\)\s*,\s*[\"']memory_stores[\"']",
        src,
    )


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — request_deletion + process_pending_deletions cascade
# ══════════════════════════════════════════════════════════════════════


def test_ac4_request_deletion_soft_marks_and_audits():
    src = MEMORY_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def request_deletion[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "status = 'deleted'" in body
    assert "deleted_at" in body
    assert "memory_fact_deletion_requested" in body


def test_ac4_physical_delete_cascades_memory_api_mem0_db():
    src = MEMORY_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def _physical_delete_fact[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    # Memory API delete
    assert "memory_stores" in body
    assert "delete" in body
    assert "bf_user_" in body  # store_id = f"bf_user_{user_id}"
    # Mem0 delete
    assert "long_term_memory" in body or "delete_user_memories" in body
    # DB row delete
    assert "DELETE FROM memory_facts" in body


def test_ac4_process_pending_emits_batch_audit():
    src = MEMORY_PY.read_text(encoding="utf-8")
    assert "memory_facts_deleted_batch" in src


def test_ac4_dry_run_returns_would_delete():
    src = MEMORY_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def process_pending_deletions[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "dry_run" in body
    assert "would_delete" in body


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — failed fact preserved + retry_count limit + empty skip
# ══════════════════════════════════════════════════════════════════════


def test_ac5_retry_queue_limits_to_5_attempts():
    src = MEMORY_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def process_retry_queue[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "retry_count < 5" in body
    assert re.search(
        r"status\s+IN\s*\(\s*[\"']failed[\"']\s*,\s*[\"']pending[\"']\s*\)",
        body,
    )
    assert "ORDER BY created_at ASC" in body


def test_ac5_mark_failed_increments_retry_count():
    src = MEMORY_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def _mark_failed[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "retry_count = retry_count + 1" in body
    assert "status = 'failed'" in body
    assert "last_error" in body


def test_ac5_empty_fact_text_returns_none():
    src = MEMORY_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def write_fact[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    # if not fact_text or not fact_text.strip(): return None
    assert re.search(
        r"if\s+not\s+fact_text[\s\S]+?return\s+None",
        body,
    )


def test_ac5_db_insert_failure_logs_and_returns_none():
    src = MEMORY_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def write_fact[\s\S]+?(?=\nasync def |\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "except Exception" in body
    assert "logger.warning" in body
    assert "DB insert failed" in body


def test_ac5_no_hardcoded_supabase_or_anthropic_key():
    src = MEMORY_PY.read_text(encoding="utf-8")
    assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_ai_01_canonical_ears():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-AI-01"), None)
    assert t is not None
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == [
        "UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED",
    ]


def test_tickets_t_ai_01_has_adr_link_and_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-AI-01"), None)
    assert t.get("adr_link") is not None
    assert "ADR-010" in t["adr_link"]
    assert "backend/services/memory_facts.py" in t.get("existing_files", [])


def test_tickets_t_ai_01_ac_mentions_concrete_symbols():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-AI-01"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "write_fact",
        "extract_facts_from_session",
        "recall_facts",
        "request_deletion",
        "process_retry_queue",
        "process_pending_deletions",
        "_memory_api_write_with_retry",
        "FactRecord",
        "fingerprint",
        "_FACT_RE",
        "memory_api_write_failed",
        "memory_fact_deletion_requested",
        "memory_facts_deleted_batch",
        "ANTHROPIC_API_KEY",
        "ADR-010",
    ):
        assert sym in full, f"T-AI-01 AC missing: {sym}"
