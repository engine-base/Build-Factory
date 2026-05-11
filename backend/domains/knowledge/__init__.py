"""knowledge domain — public barrel (T-001-01b AC-2).

責務: RAG search / curation / scoped knowledge.

Note: embedding_service は numpy 依存のため optional barrel (lazy import).
"""
from __future__ import annotations

from typing import Any

from services.scoped_knowledge import (
    get_scope_folders,
    search_in_scope,
    classify_target_category,
    save_knowledge,
)
from services.knowledge_curator import (
    classify_and_save,
)


def __getattr__(name: str) -> Any:
    # lazy access to embedding_service (numpy 依存)
    if name in {"embed", "encode", "decode", "cosine_similarity", "search_knowledge"}:
        from services import embedding_service as _es
        return getattr(_es, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# 注意: embed / encode / decode / cosine_similarity / search_knowledge は
# numpy 必須のため __all__ から除外 (`from domain.knowledge import embed` でアクセス可能)
__all__ = [
    "get_scope_folders",
    "search_in_scope",
    "classify_target_category",
    "save_knowledge",
    "classify_and_save",
]
