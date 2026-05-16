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

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from services import requirements_service as rs
from services import requirements_v3_service as rv3

# T-V3-B-10: services.auth_middleware は supabase_client を間接 import するため,
# Supabase env 未設定の test 環境で import error を起こさないよう
# request-time の遅延 import で auth dependency を解決する.
_v3_bearer = HTTPBearer(auto_error=False)


async def _v3_require_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_v3_bearer),
) -> dict:
    """Lazy 版 require_user (auth_middleware.require_user と同等)."""
    from services.auth_middleware import (
        DEV_BYPASS, DEV_USER, verify_jwt,
    )
    if DEV_BYPASS and not credentials:
        return DEV_USER
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthenticated",
        )
    claims = verify_jwt(credentials.credentials)
    if not claims and DEV_BYPASS:
        return DEV_USER
    if not claims:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthenticated",
        )
    return claims

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


# ══════════════════════════════════════════════════════════════════════════
# T-V3-B-10 / F-006: Requirements CRUD + versions (EARS-conformant)
#
# spec: docs/api-design/2026-05-16_v3/openapi.yaml#F-006
#       docs/functional-breakdown/2026-05-16_v3/features.json#F-006
#
# Endpoints:
#   GET  /api/workspaces/{id}/requirements           (member)
#   PUT  /api/workspaces/{id}/requirements           (workspace_admin)
#   POST /api/workspaces/{id}/requirements/versions  (workspace_admin)
#
# Auth: bearerAuth (services.auth_middleware.require_user) → 401 if missing.
#       role check は v3 段階では認証済みなら通す (workspace_member RLS が
#       Supabase 側で enforce. T-V3-B-10 では tenancy 二段強制を見送り,
#       Group D で role 強制を追加する予定).
#
# AC マッピング:
#   AC-F1  EVENT-DRIVEN PUT persist + return version+1
#   AC-F2  UNWANTED      PUT items が EARS 違反 → 422 + offending indices
#   AC-F3  EVENT-DRIVEN POST versions snapshot + return version_id
#   AC-F4  EVENT-DRIVEN GET 2xx + {requirements, version}
#   AC-F5  UNWANTED     GET no auth → 401
#   AC-F6  UNWANTED     GET body validation → 422
#   AC-F7  EVENT-DRIVEN PUT 2xx + {id, version}
#   AC-F8  UNWANTED     PUT no auth → 401
#   AC-F9  UNWANTED     PUT body validation → 422
#   AC-F10 EVENT-DRIVEN POST 2xx + {version_id, version_number}
#   AC-F11 UNWANTED     POST no auth → 401
#   AC-F12 UNWANTED     POST body validation → 422
# ══════════════════════════════════════════════════════════════════════════


class RequirementItemBody(BaseModel):
    """PUT /api/workspaces/{id}/requirements の items 要素.

    spec: features.json#F-006 RequirementItem.
    """

    ears_type: str = Field(
        ...,
        description="UBIQUITOUS / EVENT-DRIVEN / STATE-DRIVEN / OPTIONAL / UNWANTED",
    )
    text: str = Field(..., min_length=1, description="EARS-conformant text")
    title: Optional[str] = None
    category: Optional[str] = None


class PutRequirementsBody(BaseModel):
    items: list[RequirementItemBody] = Field(..., min_length=0)


class CreateVersionBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


def _v3_validation_error(field_errors: list[dict[str, Any]]) -> HTTPException:
    """422 (validation error) 用の HTTPException.

    AC-F6 / AC-F9 / AC-F12 / AC-F15:
      body validation failure → 422 + field-level error map.
    """
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "code": "validation_error",
            "message": "request body failed validation",
            "errors": field_errors,
        },
    )


def _v3_workspace_id_or_422(workspace_id: int) -> None:
    """workspace_id の最小バリデーション (>= 1)."""
    if workspace_id is None or workspace_id <= 0:
        raise _v3_validation_error([{
            "loc": ["path", "id"],
            "code": "invalid_workspace_id",
            "message": "workspace_id must be a positive integer",
        }])


@router.get(
    "/{workspace_id}/requirements",
    response_model=None,
)
async def v3_list_requirements(
    workspace_id: int,
    user: dict = Depends(_v3_require_user),  # noqa: ARG001 (401 enforcement)
) -> dict:
    """AC-F4 / AC-F5 / AC-F6: GET /api/workspaces/{id}/requirements."""
    _v3_workspace_id_or_422(workspace_id)
    res = await rv3.list_requirements(workspace_id)
    await _audit(
        "requirements.v3.listed",
        user_id=str(user.get("sub")) if isinstance(user, dict) else None,
        detail={
            "workspace_id": workspace_id,
            "item_count": len(res.get("requirements", [])),
            "version": res.get("version"),
        },
    )
    return res


@router.put(
    "/{workspace_id}/requirements",
    response_model=None,
)
async def v3_put_requirements(
    workspace_id: int,
    body: PutRequirementsBody,
    user: dict = Depends(_v3_require_user),
) -> dict:
    """AC-F1 / AC-F2 / AC-F7 / AC-F8 / AC-F9: PUT requirements (EARS persist)."""
    _v3_workspace_id_or_422(workspace_id)
    items = [it.model_dump() for it in body.items]
    actor = str(user.get("sub")) if isinstance(user, dict) else None
    try:
        res = await rv3.upsert_requirements(
            workspace_id, items, actor_user_id=actor,
        )
    except rv3.EarsValidationError as e:
        # AC-F2: items が EARS 違反 → 422 + offending indices
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "ears_validation_failed",
                "message": "items failed EARS form validation",
                "offending_indices": e.offending_indices,
                "errors": e.field_errors,
            },
        )
    await _audit(
        "requirements.v3.upserted",
        user_id=actor,
        detail={
            "workspace_id": workspace_id,
            "item_count": len(items),
            "version": res.get("version"),
        },
    )
    return res


@router.post(
    "/{workspace_id}/requirements/versions",
    status_code=status.HTTP_201_CREATED,
    response_model=None,
)
async def v3_create_version(
    workspace_id: int,
    body: CreateVersionBody,
    user: dict = Depends(_v3_require_user),
) -> dict:
    """AC-F3 / AC-F10 / AC-F11 / AC-F12: snapshot requirements as a new version."""
    _v3_workspace_id_or_422(workspace_id)
    actor = str(user.get("sub")) if isinstance(user, dict) else None
    res = await rv3.create_version(
        workspace_id, body.message, actor_user_id=actor,
    )
    await _audit(
        "requirements.v3.version_created",
        user_id=actor,
        detail={
            "workspace_id": workspace_id,
            "version_number": res.get("version_number"),
            "message_size": len(body.message or ""),
        },
    )
    return res
