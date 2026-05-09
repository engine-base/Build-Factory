"""
estimate.py — Phase 5 見積書 対話駆動 API
"""
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from services import estimate_service as es

router = APIRouter(prefix="/api/workspaces", tags=["estimate"])


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


@router.post("/{workspace_id}/estimate/start-step")
async def start_step(workspace_id: int, body: StartStepBody):
    res = await es.start_step(workspace_id, body.step)
    if "error" in res:
        raise HTTPException(400, res["error"])
    return res


@router.post("/{workspace_id}/estimate/reply")
async def reply(workspace_id: int, body: ReplyBody):
    if not body.message.strip():
        raise HTTPException(400, "empty message")
    return await es.reply(workspace_id, body.step, body.message.strip())


@router.post("/{workspace_id}/estimate/complete-step")
async def complete_step(workspace_id: int, body: CompleteStepBody):
    return await es.complete_step(workspace_id, body.step)


@router.get("/{workspace_id}/estimate/state")
async def get_state(workspace_id: int):
    return await es.get_state(workspace_id)


@router.get("/{workspace_id}/estimate/aggregated-view")
async def aggregated_view(workspace_id: int):
    return await es.get_aggregated_view(workspace_id)


@router.patch("/{workspace_id}/estimate/center")
async def update_center(workspace_id: int, body: CenterUpdateBody, step: int):
    art = await es.get_or_create_center_artifact(workspace_id, step)
    center = body.center
    center["edited_by_pm"] = True
    updated = await es.update_center_artifact(art["id"], center)
    return {"artifact": updated, "center": center}


@router.get("/{workspace_id}/estimate/download/{tab}.{fmt}")
async def download(workspace_id: int, tab: str, fmt: str):
    fmt = fmt.lower()
    if fmt not in ("html", "md", "json"):
        raise HTTPException(400, "format must be html|md|json")
    if fmt == "html":
        body = await es.render_html(workspace_id, tab)
        return Response(content=body, media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="estimate-{tab}.html"'})
    if fmt == "md":
        body = await es.render_markdown(workspace_id, tab)
        return Response(content=body, media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="estimate-{tab}.md"'})
    import json as _json
    payload = await es.render_json(workspace_id, tab)
    return Response(
        content=_json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="estimate-{tab}.json"'},
    )
