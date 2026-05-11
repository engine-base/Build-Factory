"""T-016-02 / F-016: artifact MD 化 (obsidian_sync 連携) REST endpoint.

Endpoint:
  POST /api/artifacts/md/render    artifact → Markdown 文字列 (read-only)
  POST /api/artifacts/md/save      artifact → Markdown 保存 (mutate)

AC マッピング:
  AC-1 UBIQUITOUS    : F-016 artifact → MD 変換 endpoint + service
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 obsidian_sync REUSE (backwards compat) + audit emit
  AC-4 UNWANTED      : invalid input / path traversal は 4xx + structured /
                       persistent state mutate しない
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import artifact_md_renderer as amd

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/artifacts/md", tags=["artifact-md"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("artifact-md audit emit failed: %s -- %s", event_type, e)


class RenderRequest(BaseModel):
    artifact: dict
    actor_user_id: Optional[str] = None


class SaveRequest(BaseModel):
    artifact: dict
    actor_user_id: Optional[str] = None


@router.post("/render")
async def render(req: RenderRequest) -> dict[str, Any]:
    if req.actor_user_id is not None and not req.actor_user_id.strip():
        raise _error("artifact_md.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    if not isinstance(req.artifact, dict):
        raise _error("artifact_md.invalid_artifact",
                     "artifact must be a dict")
    try:
        md = amd.render_artifact_md(req.artifact)
    except amd.ArtifactMDError as e:
        raise _error("artifact_md.invalid", str(e))
    return {
        "size": len(md),
        "markdown": md,
    }


@router.post("/save")
async def save(req: SaveRequest) -> dict[str, Any]:
    if req.actor_user_id is not None and not req.actor_user_id.strip():
        raise _error("artifact_md.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)
    if not isinstance(req.artifact, dict):
        raise _error("artifact_md.invalid_artifact",
                     "artifact must be a dict")
    try:
        result = amd.save_artifact_md(req.artifact)
    except amd.ArtifactMDError as e:
        msg = str(e)
        if "unsafe path segment" in msg or "invalid characters" in msg:
            raise _error("artifact_md.unsafe_path", msg, status_code=403)
        raise _error("artifact_md.invalid", msg)
    except Exception as e:
        raise _error("artifact_md.save_failed",
                     f"failed to write artifact MD: {e}", status_code=500)
    await _audit(
        "artifact_md.saved",
        user_id=req.actor_user_id,
        detail={
            "path": result["path"],
            "size": result["size"],
            "id": result["id"],
        },
    )
    return result
