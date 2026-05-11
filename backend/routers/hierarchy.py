"""T-022-02 / F-022: 階層循環参照 (cycle) 防止 REST endpoint.

DB layer (supabase migration 20260512300000) の trigger が最終 SoT だが、
application 層で事前判定することで:
  - DB round-trip + RAISE EXCEPTION の cost 回避
  - frontend が「依存追加 ⇄ cycle 確認」 を 2 秒以内に対話可能
  - drag&drop UI (T-009-05) のリアルタイム validation

Endpoint:
  POST /api/hierarchy/validate-edge        edge 追加が cycle を作るか事前判定
  POST /api/hierarchy/detect-cycles        既存 graph 内の全 cycle 列挙
  POST /api/hierarchy/topo-order           topological 順を取得 (cycle なら 400)

AC マッピング:
  AC-1 UBIQUITOUS    : F-022 階層循環参照 trigger (DB + app 層)
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : RLS / audit_logs は CLAUDE.md §5.3 通り
                       (read-only validator のため state mutate 無し)
  AC-4 UNWANTED      : invalid edges / cycle 検出は 4xx + structured /
                       persistent state mutate しない
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import hierarchy_validator as hv

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/hierarchy", tags=["hierarchy"])


def _error(code: str, message: str, *, status_code: int = 400,
           extra: Optional[dict] = None) -> HTTPException:
    detail: dict[str, Any] = {"code": code, "message": message}
    if extra:
        detail.update(extra)
    return HTTPException(status_code=status_code, detail=detail)


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("hierarchy audit emit failed: %s -- %s", event_type, e)


class ValidateEdgeRequest(BaseModel):
    edges: list[list[int]] = Field(...)
    new_from: int = Field(..., gt=0)
    new_to: int = Field(..., gt=0)
    actor_user_id: Optional[str] = None


class DetectCyclesRequest(BaseModel):
    edges: list[list[int]] = Field(...)
    actor_user_id: Optional[str] = None


class TopoOrderRequest(BaseModel):
    edges: list[list[int]] = Field(...)
    nodes: Optional[list[int]] = None
    actor_user_id: Optional[str] = None


def _check_actor(actor: Optional[str]) -> None:
    if actor is not None and not actor.strip():
        raise _error("hierarchy.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)


@router.post("/validate-edge")
async def validate_edge(req: ValidateEdgeRequest) -> dict[str, Any]:
    _check_actor(req.actor_user_id)
    try:
        cycle = hv.detect_cycle_on_add(req.edges, req.new_from, req.new_to)
    except hv.HierarchyError as e:
        raise _error("hierarchy.invalid", str(e))
    if cycle is not None:
        # cycle 検出時は 409 + structured detail (path 付き)
        path_str = " → ".join(str(n) for n in cycle)
        raise _error(
            "hierarchy.cycle_detected",
            f"adding ({req.new_from}→{req.new_to}) forms cycle: {path_str}",
            status_code=409,
            extra={"cycle_path": cycle},
        )
    # 監査は emit するが state mutate しない (graph は client 側保持)
    await _audit(
        "hierarchy.edge.validated",
        user_id=req.actor_user_id,
        detail={
            "edges_count": len(req.edges),
            "new_from": req.new_from,
            "new_to": req.new_to,
            "result": "ok",
        },
    )
    return {
        "valid": True,
        "new_from": req.new_from,
        "new_to": req.new_to,
        "edges_count": len(req.edges),
    }


@router.post("/detect-cycles")
async def detect_cycles(req: DetectCyclesRequest) -> dict[str, Any]:
    _check_actor(req.actor_user_id)
    try:
        cycles = hv.find_all_cycles(req.edges)
    except hv.HierarchyError as e:
        raise _error("hierarchy.invalid", str(e))
    return {
        "edges_count": len(req.edges),
        "cycle_count": len(cycles),
        "cycles": cycles,
    }


@router.post("/topo-order")
async def topo_order(req: TopoOrderRequest) -> dict[str, Any]:
    _check_actor(req.actor_user_id)
    try:
        order = hv.topological_order(req.edges, req.nodes)
    except hv.HierarchyError as e:
        msg = str(e)
        if "cycle_detected" in msg:
            raise _error("hierarchy.cycle_detected", msg, status_code=409)
        raise _error("hierarchy.invalid", msg)
    return {
        "edges_count": len(req.edges),
        "node_count": len(order),
        "order": order,
    }
