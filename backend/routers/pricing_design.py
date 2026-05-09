"""
pricing_design.py — Phase 3 価格設計 対話駆動 API

3 STEP の対話フロー + 4 タブ集約ビュー + ダウンロード (HTML/MD/JSON)。
"""
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from services import pricing_design_service as ps

router = APIRouter(prefix="/api/workspaces", tags=["pricing-design"])


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


@router.post("/{workspace_id}/pricing/start-step")
async def start_step(workspace_id: int, body: StartStepBody):
    res = await ps.start_step(workspace_id, body.step)
    if "error" in res:
        raise HTTPException(400, res["error"])
    return res


@router.post("/{workspace_id}/pricing/reply")
async def reply(workspace_id: int, body: ReplyBody):
    if not body.message.strip():
        raise HTTPException(400, "empty message")
    return await ps.reply(workspace_id, body.step, body.message.strip())


@router.post("/{workspace_id}/pricing/complete-step")
async def complete_step(workspace_id: int, body: CompleteStepBody):
    return await ps.complete_step(workspace_id, body.step)


@router.get("/{workspace_id}/pricing/state")
async def get_state(workspace_id: int):
    return await ps.get_state(workspace_id)


@router.get("/{workspace_id}/pricing/aggregated-view")
async def aggregated_view(workspace_id: int):
    return await ps.get_aggregated_view(workspace_id)


@router.patch("/{workspace_id}/pricing/center")
async def update_center(workspace_id: int, body: CenterUpdateBody, step: int):
    art = await ps.get_or_create_center_artifact(workspace_id, step)
    center = body.center
    center["edited_by_pm"] = True
    updated = await ps.update_center_artifact(art["id"], center)
    return {"artifact": updated, "center": center}


@router.get("/{workspace_id}/pricing/download/{tab}.{fmt}")
async def download(workspace_id: int, tab: str, fmt: str):
    fmt = fmt.lower()
    if fmt not in ("html", "md", "json"):
        raise HTTPException(400, "format must be html|md|json")

    if fmt == "html":
        body = await ps.render_html(workspace_id, tab)
        return Response(
            content=body,
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="pricing-{tab}.html"'},
        )
    if fmt == "md":
        body = await ps.render_markdown(workspace_id, tab)
        return Response(
            content=body,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="pricing-{tab}.md"'},
        )

    import json as _json
    payload = await ps.render_json(workspace_id, tab)
    return Response(
        content=_json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="pricing-{tab}.json"'},
    )
