"""memory domain — public barrel (T-001-01b AC-2).

責務: 3-tier memory (chat/Mem0/Obsidian) / fact extraction / search.
"""
from __future__ import annotations

from services.memory_service import (
    emit_event,
    persist_compaction,
    write_fact,
)
from services.memory_facts import (
    FactRecord,
    fingerprint,
    extract_facts_from_text,
    extract_facts_from_session,
)
from services.mem0_bridge import (
    ScoredFact,
    mirror_fact_to_mem0,
    search_with_rerank,
)
from services.chat_search import (
    HybridHit,
    hybrid_search,
)

__all__ = [
    "emit_event",
    "persist_compaction",
    "write_fact",
    "FactRecord",
    "fingerprint",
    "extract_facts_from_text",
    "extract_facts_from_session",
    "ScoredFact",
    "mirror_fact_to_mem0",
    "search_with_rerank",
    "HybridHit",
    "hybrid_search",
]
