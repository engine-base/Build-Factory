"""
proposal.py — Phase 4 提案書 対話駆動 API

5 STEP / 8 章 (TOC) のスクロール表示 + ダウンロード (HTML/MD/JSON)。
"""
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from services import proposal_service as ps

router = APIRouter(prefix="/api/workspaces", tags=["proposal"])


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


@router.post("/{workspace_id}/proposal/start-step")
async def start_step(workspace_id: int, body: StartStepBody):
    res = await ps.start_step(workspace_id, body.step)
    if "error" in res:
        raise HTTPException(400, res["error"])
    return res


@router.post("/{workspace_id}/proposal/reply")
async def reply(workspace_id: int, body: ReplyBody):
    if not body.message.strip():
        raise HTTPException(400, "empty message")
    return await ps.reply(workspace_id, body.step, body.message.strip())


@router.post("/{workspace_id}/proposal/complete-step")
async def complete_step(workspace_id: int, body: CompleteStepBody):
    return await ps.complete_step(workspace_id, body.step)


@router.get("/{workspace_id}/proposal/state")
async def get_state(workspace_id: int):
    return await ps.get_state(workspace_id)


@router.get("/{workspace_id}/proposal/aggregated-view")
async def aggregated_view(workspace_id: int):
    return await ps.get_aggregated_view(workspace_id)


@router.patch("/{workspace_id}/proposal/center")
async def update_center(workspace_id: int, body: CenterUpdateBody, step: int):
    art = await ps.get_or_create_center_artifact(workspace_id, step)
    center = body.center
    center["edited_by_pm"] = True
    updated = await ps.update_center_artifact(art["id"], center)
    return {"artifact": updated, "center": center}


@router.get("/{workspace_id}/proposal/download/{chapter}.{fmt}")
async def download(workspace_id: int, chapter: str, fmt: str):
    fmt = fmt.lower()
    if fmt not in ("html", "md", "json"):
        raise HTTPException(400, "format must be html|md|json")

    if fmt == "html":
        body = await ps.render_html(workspace_id, chapter)
        return Response(
            content=body, media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="proposal-{chapter}.html"'},
        )
    if fmt == "md":
        body = await ps.render_markdown(workspace_id, chapter)
        return Response(
            content=body, media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="proposal-{chapter}.md"'},
        )

    import json as _json
    payload = await ps.render_json(workspace_id, chapter)
    return Response(
        content=_json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="proposal-{chapter}.json"'},
    )
