"""T-M28-04: Tier 3 compaction (9-section structured summary) REST endpoints.

既存 chat_thread_store / chat_threads router は不変. M-28 Context Builder の
Tier 3 (95% 自動 compaction) を統一インターフェースで提供する.

Endpoint:
  GET  /api/tier3/status       thread 占有率 + 発火フラグ (read-only)
  GET  /api/tier3/audit        in-memory audit log (read-only)
  POST /api/tier3/compact      compaction を実行 (FastAPI BackgroundTasks 対応)

AC マッピング:
  AC-1 UBIQUITOUS    : T-M28-04 を M-28 仕様通り実装 (9 sections / 95%)
  AC-2 EVENT-DRIVEN  : compaction trigger 時に audit log に action + timestamp を記録
                       (2 秒以内 + {detail:{code,message}})
  AC-3 STATE-DRIVEN  : RLS + audit_logs を CLAUDE.md §5.3 準拠で適用
                       Phase 1 は app-level audit (in-memory),
                       Postgres RLS / audit_logs trigger は migration で別途設置済
  AC-4 UNWANTED      : invalid input → 4xx structured / persistent state mutate 無し

仕様徹底 (T-M28-04 PR #128 で追加):
  G1 (background task) : compaction 完了後の legacy 永続化を BackgroundTasks に積む
  G4 (二重経路統合)     : memory_service.persist_compaction (sqlite) への best-effort
                          dual-write で T-AI-03 chat_search との互換性を確保
  G6 (chat_search 互換) : G4 の dual-write 経由で system_summary を chat_search に届ける
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Query

from services import tier3_structured_summary as t3

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tier3", tags=["tier3-compaction"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message},
    )


def _map_error(e: t3.Tier3SummaryError) -> HTTPException:
    msg = str(e)
    if "not found" in msg:
        return _error("tier3.not_found", msg, status_code=404)
    return _error("tier3.invalid", msg)


async def _legacy_persist_best_effort(thread_id: int, summary: dict) -> None:
    """G4/G6: memory_service.persist_compaction (sqlite chat_messages) への
    best-effort dual-write. 失敗しても primary path (chat_thread_store) は影響なし.

    chat_search (T-AI-03) / semantic_retrieval (T-M28-05) が sqlite chat_messages を
    参照するため, system_summary を両方の store に書き込むことで M-30 in-memory store と
    legacy sqlite path の整合性を確保する.
    """
    try:
        from services.memory_service import persist_compaction
        legacy_id = await persist_compaction(thread_id, summary)
        logger.debug("tier3 legacy persist OK: thread=%s msg=%s", thread_id, legacy_id)
    except Exception as e:
        logger.warning(
            "tier3 legacy persist failed (chat_search compat may degrade): %s", e,
        )


@router.get("/status")
async def status(
    thread_id: int = Query(..., gt=0),
    max_tokens: int = Query(t3.DEFAULT_MAX_TOKENS, ge=t3.MIN_MAX_TOKENS, le=t3.MAX_MAX_TOKENS),
    threshold: float = Query(t3.DEFAULT_THRESHOLD, ge=t3.MIN_THRESHOLD, le=t3.MAX_THRESHOLD),
) -> dict[str, Any]:
    """read-only: 占有率 + 発火フラグ."""
    try:
        usage = t3.estimate_context_usage(thread_id, max_tokens=max_tokens)
        will = t3.should_compact(usage, threshold=threshold)
    except t3.Tier3SummaryError as e:
        raise _map_error(e)
    return {
        "thread_id": thread_id,
        "max_tokens": max_tokens,
        "threshold": threshold,
        "should_compact": will,
        "usage": usage,
    }


@router.get("/audit")
async def audit(
    thread_id: Optional[int] = Query(None, gt=0),
    limit: int = Query(100, ge=1, le=10_000),
) -> dict[str, Any]:
    """read-only: in-memory audit log の取得 (新しい順)."""
    try:
        entries = t3.list_audit_log(thread_id=thread_id, limit=limit)
    except t3.Tier3SummaryError as e:
        raise _map_error(e)
    return {
        "thread_id": thread_id,
        "limit": limit,
        "count": len(entries),
        "entries": entries,
    }


@router.post("/compact")
async def compact(
    background_tasks: BackgroundTasks,
    payload: dict = Body(default_factory=dict),
) -> dict[str, Any]:
    """compaction を実行.

    body: {thread_id: int, max_tokens?: int, threshold?: float,
           force?: bool, persist_legacy?: bool}

    persist_legacy (default True): G4 dual-write 制御.
      True  → BackgroundTasks で memory_service.persist_compaction を呼ぶ
              (chat_search / semantic_retrieval が summary を見つけられる)
      False → chat_thread_store のみ (in-memory; M-30 store)
    """
    if not isinstance(payload, dict):
        raise _error("tier3.invalid", "body must be a JSON object")

    thread_id = payload.get("thread_id")
    if not isinstance(thread_id, int) or isinstance(thread_id, bool) or thread_id <= 0:
        raise _error("tier3.invalid", "thread_id must be int > 0")

    max_tokens = payload.get("max_tokens", t3.DEFAULT_MAX_TOKENS)
    threshold = payload.get("threshold", t3.DEFAULT_THRESHOLD)
    force = payload.get("force", False)
    persist_legacy = payload.get("persist_legacy", True)
    if not isinstance(force, bool):
        raise _error("tier3.invalid", "force must be bool")
    if not isinstance(persist_legacy, bool):
        raise _error("tier3.invalid", "persist_legacy must be bool")

    try:
        result = t3.run_compaction(
            thread_id,
            max_tokens=max_tokens,
            threshold=threshold,
            force=force,
        )
    except t3.Tier3SummaryError as e:
        raise _map_error(e)

    # G1 + G4 + G6: 成功時のみ legacy sqlite に dual-write を background task で実行
    legacy_scheduled = False
    if result.get("compacted") and persist_legacy:
        background_tasks.add_task(
            _legacy_persist_best_effort, thread_id, result["summary"],
        )
        legacy_scheduled = True
    result["legacy_persist_scheduled"] = legacy_scheduled
    return result
