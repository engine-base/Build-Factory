"""
requirements.py — Phase 2 要件定義 対話駆動 API

7 STEP の対話フロー + IDE タブ集約ビュー + ダウンロード (HTML/MD/JSON)。
"""
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from services import requirements_service as rs

router = APIRouter(prefix="/api/workspaces", tags=["requirements"])


class StartStepBody(BaseModel):
    step: int


class ReplyBody(BaseModel):
    step: int
    message: str


class CompleteStepBody(BaseModel):
    step: int


class CenterUpdateBody(BaseModel):
    center: dict
    edited_by_pm: bool = True


@router.post("/{workspace_id}/requirements/start-step")
async def start_step(workspace_id: int, body: StartStepBody):
    res = await rs.start_step(workspace_id, body.step)
    if "error" in res:
        raise HTTPException(400, res["error"])
    return res


@router.post("/{workspace_id}/requirements/reply")
async def reply(workspace_id: int, body: ReplyBody):
    if not body.message.strip():
        raise HTTPException(400, "empty message")
    return await rs.reply(workspace_id, body.step, body.message.strip())


@router.post("/{workspace_id}/requirements/complete-step")
async def complete_step(workspace_id: int, body: CompleteStepBody):
    return await rs.complete_step(workspace_id, body.step)


@router.get("/{workspace_id}/requirements/state")
async def get_state(workspace_id: int):
    return await rs.get_state(workspace_id)


@router.get("/{workspace_id}/requirements/aggregated-view")
async def aggregated_view(workspace_id: int):
    """IDE タブ単位で集約したビュー (タブ名 → セクション群)。"""
    return await rs.get_aggregated_view(workspace_id)


@router.patch("/{workspace_id}/requirements/center")
async def update_center(workspace_id: int, body: CenterUpdateBody, step: int):
    """PM の直接編集 (BlockNote / フィールドモーダル経由) を反映。"""
    art = await rs.get_or_create_center_artifact(workspace_id, step)
    center = body.center
    center["edited_by_pm"] = True
    updated = await rs.update_center_artifact(art["id"], center)
    return {"artifact": updated, "center": center}


@router.get("/{workspace_id}/requirements/download/{tab}.{fmt}")
async def download(workspace_id: int, tab: str, fmt: str):
    """タブ単位のダウンロード。tab='all' で全結合。fmt = html | md | json。"""
    fmt = fmt.lower()
    if fmt not in ("html", "md", "json"):
        raise HTTPException(400, "format must be html|md|json")

    if fmt == "html":
        body = await rs.render_html(workspace_id, tab)
        return Response(
            content=body,
            media_type="text/html; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="requirements-{tab}.html"'
            },
        )
    if fmt == "md":
        body = await rs.render_markdown(workspace_id, tab)
        return Response(
            content=body,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="requirements-{tab}.md"'
            },
        )
    # json
    import json as _json

    payload = await rs.render_json(workspace_id, tab)
    return Response(
        content=_json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="requirements-{tab}.json"'
        },
    )
