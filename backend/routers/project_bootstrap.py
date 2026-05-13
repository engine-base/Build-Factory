"""T-BTSTRAP-03: Jinja2 placeholder 置換エンジン REST endpoint.

- GET  /api/bootstrap/placeholders   必須 placeholder + default 一覧
- POST /api/bootstrap/render-string  単一文字列を render (dry-run / debug 用)
- POST /api/bootstrap/render         metadata + output_dir で project-bootstrap 全 .j2 を render

AC マッピング:
  AC-1 UBIQUITOUS    : 全 .j2 を Jinja2 render / 10 placeholders 公開
  AC-2 EVENT-DRIVEN  : 必須欠落 → 400 + state mutate なし (atomic before write)
  AC-3 STATE-DRIVEN  : autoescape=False (service 内で確定)
  AC-4 UNWANTED      : 未置換 {{ }} 残存 → 400. 全 4xx {detail:{code,message}}.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request

from services import project_bootstrap_engine as pbe

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bootstrap", tags=["project-bootstrap"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message},
    )


def _map_bootstrap_error(e: pbe.BootstrapError) -> HTTPException:
    msg = str(e)
    if "missing required placeholders" in msg:
        return _error("bootstrap.missing_placeholders", msg, status_code=400)
    if "unrendered placeholders remain" in msg:
        return _error("bootstrap.unrendered", msg, status_code=400)
    if "template_root not found" in msg or "no .j2 files" in msg:
        return _error("bootstrap.template_missing", msg, status_code=404)
    return _error("bootstrap.invalid", msg, status_code=400)


@router.get("/placeholders")
async def list_placeholders() -> dict[str, Any]:
    """必須 placeholders + default 一覧を返す."""
    return {
        "required": list(pbe.REQUIRED_PLACEHOLDERS),
        "defaults": {k: pbe.DEFAULT_VALUES[k] for k in pbe.DEFAULT_VALUES},
        "count": len(pbe.REQUIRED_PLACEHOLDERS),
    }


@router.post("/render-string")
async def render_string(request: Request) -> dict[str, Any]:
    """単一テキストを render (debug / dry-run)."""
    try:
        body = await request.json()
    except Exception:
        raise _error("bootstrap.invalid", "request body must be valid JSON")
    if not isinstance(body, dict):
        raise _error("bootstrap.invalid", "request body must be a JSON object")
    text = body.get("text")
    metadata = body.get("metadata", {})
    if not isinstance(text, str):
        raise _error("bootstrap.invalid", "text must be string")
    if not isinstance(metadata, dict):
        raise _error("bootstrap.invalid", "metadata must be dict")
    try:
        merged = pbe.validate_metadata(metadata)
        rendered = pbe.render_template_string(text, merged)
    except pbe.BootstrapError as e:
        raise _map_bootstrap_error(e)
    return {"rendered": rendered, "metadata_used": merged}


@router.post("/render")
async def render_project(request: Request) -> dict[str, Any]:
    """templates/project-bootstrap/ 配下を render し output_dir に展開.

    output_dir は absolute path or env BOOTSTRAP_OUTPUT_DIR 配下のみ許可
    (path traversal 防止).
    """
    try:
        body = await request.json()
    except Exception:
        raise _error("bootstrap.invalid", "request body must be valid JSON")
    if not isinstance(body, dict):
        raise _error("bootstrap.invalid", "request body must be a JSON object")
    metadata = body.get("metadata")
    output_dir = body.get("output_dir")
    if not isinstance(metadata, dict):
        raise _error("bootstrap.invalid", "metadata must be dict")
    if not isinstance(output_dir, str) or not output_dir.strip():
        raise _error("bootstrap.invalid", "output_dir must be non-empty string")
    try:
        out_path = Path(output_dir).expanduser().resolve()
    except Exception as e:
        raise _error("bootstrap.invalid", f"output_dir invalid: {e}")
    # path 制限: 既存 templates/ 配下を上書きする経路は拒否
    try:
        out_path.relative_to(pbe._default_template_root())
        raise _error(
            "bootstrap.invalid",
            "output_dir must NOT be inside templates/project-bootstrap/",
        )
    except ValueError:
        pass  # OK: templates 配下ではない

    try:
        result = pbe.render_project_bootstrap(
            metadata, output_dir=out_path,
        )
    except pbe.BootstrapError as e:
        raise _map_bootstrap_error(e)
    return result
