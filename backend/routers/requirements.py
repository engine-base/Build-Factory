"""requirements.py — Phase 2 要件定義 対話駆動 API (T-005-03 REFACTOR).

Preston (PM) が 6 STEP の対話フローで要件を引き出す.
+ IDE タブ集約ビュー + ダウンロード (HTML/MD/JSON).

T-005-03 AC:
  AC-1 UBIQUITOUS    : F-005 の 7 endpoint (start/reply/complete/state/aggregated/center/download)
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 route prefix / response shape 不変 + audit_logs emit
  AC-4 UNWANTED      : invalid workspace_id / step / 空 message / 不正 fmt は 4xx +
                       {detail:{code,message}} かつ persistent state mutate しない
"""
from __future__ import annotations

import json as _json
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel

from services import requirements_service as rs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workspaces", tags=["requirements"])


# ──────────────────────────────────────────────────────────────────────────
# T-005-03: error contract + audit helpers
# ──────────────────────────────────────────────────────────────────────────


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover
        logger.warning("requirements audit emit failed: %s -- %s", event_type, e)


# Preston は 6 STEP で要件を整理する (1..6)
MIN_STEP = 1
MAX_STEP = 6
VALID_FORMATS = ("html", "md", "json")


def _validate_workspace_id(workspace_id: int) -> None:
    if workspace_id is None or workspace_id <= 0:
        raise _error("requirements.invalid_workspace_id",
                     "workspace_id must be > 0")


def _validate_step(step: int) -> None:
    if step is None or step < MIN_STEP or step > MAX_STEP:
        raise _error(
            "requirements.invalid_step",
            f"step must be {MIN_STEP}..{MAX_STEP}, got {step}",
        )


def _validate_actor(actor: Optional[str]) -> None:
    if actor is not None and not actor.strip():
        raise _error("requirements.unauthorized",
                     "actor_user_id must not be empty when provided",
                     status_code=401)


# ──────────────────────────────────────────────────────────────────────────
# Request models
# ──────────────────────────────────────────────────────────────────────────


class StartStepBody(BaseModel):
    step: int
    actor_user_id: Optional[str] = None


class ReplyBody(BaseModel):
    step: int
    message: str
    actor_user_id: Optional[str] = None


class CompleteStepBody(BaseModel):
    step: int
    actor_user_id: Optional[str] = None


class CenterUpdateBody(BaseModel):
    center: dict
    edited_by_pm: bool = True
    actor_user_id: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────────
# AC-1 / AC-2 / AC-3 / AC-4: endpoints
# ──────────────────────────────────────────────────────────────────────────


@router.post("/{workspace_id}/requirements/start-step")
async def start_step(workspace_id: int, body: StartStepBody):
    _validate_workspace_id(workspace_id)
    _validate_step(body.step)
    _validate_actor(body.actor_user_id)
    res = await rs.start_step(workspace_id, body.step)
    if isinstance(res, dict) and "error" in res:
        raise _error("requirements.start_failed", str(res["error"]))
    await _audit(
        "requirements.step.started",
        user_id=body.actor_user_id,
        detail={"workspace_id": workspace_id, "step": body.step},
    )
    return res


@router.post("/{workspace_id}/requirements/reply")
async def reply(workspace_id: int, body: ReplyBody):
    _validate_workspace_id(workspace_id)
    _validate_step(body.step)
    _validate_actor(body.actor_user_id)
    msg = (body.message or "").strip()
    if not msg:
        raise _error("requirements.invalid_message", "message must not be empty")
    if len(msg) > 20000:
        raise _error("requirements.message_too_long", "message must be <= 20000 chars")
    res = await rs.reply(workspace_id, body.step, msg)
    await _audit(
        "requirements.message.replied",
        user_id=body.actor_user_id,
        detail={"workspace_id": workspace_id, "step": body.step,
                "message_size": len(msg)},
    )
    return res


@router.post("/{workspace_id}/requirements/complete-step")
async def complete_step(workspace_id: int, body: CompleteStepBody):
    _validate_workspace_id(workspace_id)
    _validate_step(body.step)
    _validate_actor(body.actor_user_id)
    res = await rs.complete_step(workspace_id, body.step)
    await _audit(
        "requirements.step.completed",
        user_id=body.actor_user_id,
        detail={"workspace_id": workspace_id, "step": body.step},
    )
    return res


@router.get("/{workspace_id}/requirements/state")
async def get_state(workspace_id: int):
    _validate_workspace_id(workspace_id)
    return await rs.get_state(workspace_id)


@router.get("/{workspace_id}/requirements/aggregated-view")
async def aggregated_view(workspace_id: int):
    """IDE タブ単位で集約したビュー (タブ名 → セクション群)."""
    _validate_workspace_id(workspace_id)
    return await rs.get_aggregated_view(workspace_id)


@router.patch("/{workspace_id}/requirements/center")
async def update_center(
    workspace_id: int,
    body: CenterUpdateBody,
    step: int = Query(...),
):
    """PM の直接編集 (BlockNote / フィールドモーダル経由) を反映."""
    _validate_workspace_id(workspace_id)
    _validate_step(step)
    _validate_actor(body.actor_user_id)
    if not isinstance(body.center, dict):
        raise _error("requirements.invalid_center", "center must be a dict")
    art = await rs.get_or_create_center_artifact(workspace_id, step)
    center = body.center
    center["edited_by_pm"] = bool(body.edited_by_pm)
    updated = await rs.update_center_artifact(art["id"], center)
    await _audit(
        "requirements.center.updated",
        user_id=body.actor_user_id,
        detail={"workspace_id": workspace_id, "step": step,
                "artifact_id": art["id"]},
    )
    return {"artifact": updated, "center": center}


class SpecGenerateRequest(BaseModel):
    project_name: Optional[str] = None
    version: Optional[str] = "draft"
    actor_user_id: Optional[str] = None


@router.post("/{workspace_id}/spec/generate-html")
async def generate_spec_html(workspace_id: int, body: SpecGenerateRequest):
    """T-005-04: 仕様書 HTML を 1 ファイルで生成する."""
    _validate_workspace_id(workspace_id)
    _validate_actor(body.actor_user_id)

    project_name = (body.project_name or "").strip() or f"Workspace #{workspace_id}"
    if len(project_name) > 200:
        raise _error("requirements.project_name_too_long",
                     "project_name must be <= 200 chars")
    version = (body.version or "draft").strip()
    if not version:
        raise _error("requirements.invalid_version", "version must not be empty")
    if len(version) > 50:
        raise _error("requirements.version_too_long", "version must be <= 50 chars")

    from services.spec_html_generator import (
        SpecMeta, build_sections_from_view, render_spec_html, SpecHtmlError,
    )
    try:
        view = await rs.get_aggregated_view(workspace_id)
        sections = build_sections_from_view(view if isinstance(view, dict) else {})
        meta = SpecMeta(
            project_name=project_name,
            workspace_id=workspace_id,
            version=version,
        )
        rendered = render_spec_html(meta, sections)
    except SpecHtmlError as e:
        raise _error("requirements.spec_invalid", str(e))
    except Exception as e:
        raise _error("requirements.spec_generation_failed",
                     f"spec generation failed: {e}", status_code=500)

    await _audit(
        "requirements.spec.generated",
        user_id=body.actor_user_id,
        detail={
            "workspace_id": workspace_id,
            "version": version,
            "section_count": len(sections),
            "html_size": len(rendered),
        },
    )
    return Response(
        content=rendered,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition":
                f'attachment; filename="spec-{workspace_id}-{version}.html"',
        },
    )


@router.get("/{workspace_id}/requirements/download/{tab}.{fmt}")
async def download(workspace_id: int, tab: str, fmt: str):
    """タブ単位のダウンロード. tab='all' で全結合. fmt = html | md | json."""
    _validate_workspace_id(workspace_id)
    if not tab or not tab.strip():
        raise _error("requirements.invalid_tab", "tab must not be empty")
    f = fmt.lower()
    if f not in VALID_FORMATS:
        raise _error(
            "requirements.invalid_format",
            f"format must be one of {VALID_FORMATS}, got {fmt!r}",
        )

    if f == "html":
        body = await rs.render_html(workspace_id, tab)
        return Response(
            content=body,
            media_type="text/html; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="requirements-{tab}.html"'
            },
        )
    if f == "md":
        body = await rs.render_markdown(workspace_id, tab)
        return Response(
            content=body,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="requirements-{tab}.md"'
            },
        )
    # json
    payload = await rs.render_json(workspace_id, tab)
    return Response(
        content=_json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="requirements-{tab}.json"'
        },
    )
