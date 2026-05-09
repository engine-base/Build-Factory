"""
Design canvas frames + canvas state CRUD API.

Frontend (Onlook 由来 canvas) からの REST 呼び出しを受け付ける。

エンドポイント:
    GET    /api/workspaces/{workspace_id}/design/frames
    POST   /api/workspaces/{workspace_id}/design/frames
    PATCH  /api/workspaces/{workspace_id}/design/frames/{frame_id}
    DELETE /api/workspaces/{workspace_id}/design/frames/{frame_id}

    GET    /api/workspaces/{workspace_id}/design/canvas-state
    PUT    /api/workspaces/{workspace_id}/design/canvas-state
"""
from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from pathlib import Path

from db import async_db as aiosqlite
from services import designer_ai

router = APIRouter(prefix="/api/workspaces", tags=["design-frames"])

# ─────────────────────────────────────────
# Onlook preload script (inline 注入用)
# 起動時に 1 回読み込みキャッシュ。これを iframe HTML に <script> として埋め込むことで
# iframe 内で penpal クライアント・DOM 検査・theme API 等が動くようになる。
# ─────────────────────────────────────────

_PRELOAD_SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent / "static" / "onlook-preload-script.js"
)


def _load_preload_script() -> str:
    try:
        return _PRELOAD_SCRIPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


_PRELOAD_SCRIPT_CONTENT = _load_preload_script()


def _inject_preload(html: str) -> str:
    """生成 HTML に Onlook preload script を inline 注入する。"""
    if not _PRELOAD_SCRIPT_CONTENT:
        return html
    # Build-Factory フラグ用の小さなヘッダ + preload 本体
    script_tag = (
        "\n<script id=\"__bf_preload_marker\">"
        "window.__BF_DESIGN_CANVAS=true;"
        "</script>\n"
        "<script type=\"module\" id=\"__onlook_preload\">\n"
        + _PRELOAD_SCRIPT_CONTENT
        + "\n</script>\n"
    )
    # </body> 直前に挿入。無ければ末尾に追加
    lower = html.lower()
    idx = lower.rfind("</body>")
    if idx == -1:
        return html + script_tag
    return html[:idx] + script_tag + html[idx:]


# ─────────────────────────────────────────
# Models
# ─────────────────────────────────────────


class FrameCreate(BaseModel):
    name: str = "Frame"
    url: str
    frame_type: str = "web"
    position_x: float = 0
    position_y: float = 0
    width: float = 1440
    height: float = 900
    z_index: int = 0
    branch_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FrameUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    frame_type: Optional[str] = None
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None
    z_index: Optional[int] = None
    metadata: Optional[dict[str, Any]] = None


class Frame(BaseModel):
    id: int
    workspace_id: int
    branch_id: Optional[str]
    name: str
    url: str
    frame_type: str
    position_x: float
    position_y: float
    width: float
    height: float
    z_index: int
    metadata: dict[str, Any]
    has_content: bool = False  # mockup 型で content がある場合 true
    design_tokens: dict[str, Any] = Field(default_factory=dict)
    spec_meta: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CanvasState(BaseModel):
    workspace_id: int
    user_id: str = "__workspace_default__"
    scale: float = 1.0
    position_x: float = 0
    position_y: float = 0
    selected_frame_ids: list[int] = Field(default_factory=list)


def _row_to_frame(r: dict) -> Frame:
    return Frame(
        id=r["id"],
        workspace_id=r["workspace_id"],
        branch_id=r.get("branch_id"),
        name=r["name"],
        url=r["url"],
        frame_type=r["frame_type"],
        position_x=float(r["position_x"]),
        position_y=float(r["position_y"]),
        width=float(r["width"]),
        height=float(r["height"]),
        z_index=int(r["z_index"]),
        metadata=r.get("metadata") or {},
        has_content=bool(r.get("content")),
        design_tokens=r.get("design_tokens") or {},
        spec_meta=r.get("spec_meta") or {},
        created_at=r["created_at"].isoformat() if r.get("created_at") else None,
        updated_at=r["updated_at"].isoformat() if r.get("updated_at") else None,
    )


# ─────────────────────────────────────────
# Frames CRUD
# ─────────────────────────────────────────


@router.get("/{workspace_id}/design/frames", response_model=list[Frame])
async def list_frames(workspace_id: int, branch_id: Optional[str] = None):
    sql = "SELECT * FROM design_frames WHERE workspace_id = %s"
    params: list = [workspace_id]
    if branch_id:
        sql += " AND branch_id = %s"
        params.append(branch_id)
    sql += " ORDER BY z_index ASC, id ASC"
    async with aiosqlite.connect() as db:
        cur = await db.execute(sql, params)
        rows = await cur.fetchall()
    return [_row_to_frame(r) for r in rows]


@router.post("/{workspace_id}/design/frames", response_model=Frame, status_code=201)
async def create_frame(workspace_id: int, payload: FrameCreate):
    async with aiosqlite.connect() as db:
        cur = await db.execute(
            """
            INSERT INTO design_frames
                (workspace_id, branch_id, name, url, frame_type,
                 position_x, position_y, width, height, z_index, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING *
            """,
            (
                workspace_id, payload.branch_id, payload.name, payload.url,
                payload.frame_type, payload.position_x, payload.position_y,
                payload.width, payload.height, payload.z_index,
                json.dumps(payload.metadata),
            ),
        )
        row = await cur.fetchone()
        await db.commit()
    if not row:
        raise HTTPException(status_code=500, detail="insert failed")
    return _row_to_frame(row)


@router.patch("/{workspace_id}/design/frames/{frame_id}", response_model=Frame)
async def update_frame(workspace_id: int, frame_id: int, payload: FrameUpdate):
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="no fields to update")
    sets = []
    params: list = []
    for k, v in fields.items():
        if k == "metadata":
            sets.append("metadata = %s::jsonb")
            params.append(json.dumps(v))
        else:
            sets.append(f"{k} = %s")
            params.append(v)
    params += [workspace_id, frame_id]
    sql = (
        f"UPDATE design_frames SET {', '.join(sets)} "
        f"WHERE workspace_id = %s AND id = %s RETURNING *"
    )
    async with aiosqlite.connect() as db:
        cur = await db.execute(sql, params)
        row = await cur.fetchone()
        await db.commit()
    if not row:
        raise HTTPException(status_code=404, detail="frame not found")
    return _row_to_frame(row)


@router.delete("/{workspace_id}/design/frames/{frame_id}", status_code=204)
async def delete_frame(workspace_id: int, frame_id: int):
    async with aiosqlite.connect() as db:
        cur = await db.execute(
            "DELETE FROM design_frames WHERE workspace_id = %s AND id = %s RETURNING id",
            (workspace_id, frame_id),
        )
        row = await cur.fetchone()
        await db.commit()
    if not row:
        raise HTTPException(status_code=404, detail="frame not found")
    return None


# ─────────────────────────────────────────
# Canvas state
# ─────────────────────────────────────────


@router.get("/{workspace_id}/design/canvas-state", response_model=CanvasState)
async def get_canvas_state(workspace_id: int, user_id: str = "__workspace_default__"):
    async with aiosqlite.connect() as db:
        cur = await db.execute(
            "SELECT * FROM design_canvas_state WHERE workspace_id = %s AND user_id = %s",
            (workspace_id, user_id),
        )
        row = await cur.fetchone()
    if not row:
        return CanvasState(workspace_id=workspace_id, user_id=user_id)
    return CanvasState(
        workspace_id=row["workspace_id"],
        user_id=row["user_id"],
        scale=float(row["scale"]),
        position_x=float(row["position_x"]),
        position_y=float(row["position_y"]),
        selected_frame_ids=row.get("selected_frame_ids") or [],
    )


# ─────────────────────────────────────────
# AI Mockup Generation (designer persona "ユイ")
# ─────────────────────────────────────────


class MockupGenerateRequest(BaseModel):
    prompt: str
    name: Optional[str] = None
    design_system_ref: Optional[str] = None
    design_tokens: Optional[dict[str, Any]] = None


class MockupGenerateResponse(BaseModel):
    frame: Frame
    summary: str
    html: str


class MockupEditRequest(BaseModel):
    instruction: str
    target_selector: Optional[str] = None


@router.post(
    "/{workspace_id}/design/generate-mockup",
    response_model=MockupGenerateResponse,
)
async def generate_mockup(workspace_id: int, payload: MockupGenerateRequest):
    """ユーザープロンプトから HTML モックを生成して新規 frame に保存。"""
    # design_system_ref は workspace から自動取得する
    if not payload.design_system_ref:
        async with aiosqlite.connect() as db:
            cur = await db.execute(
                "SELECT design_system_ref FROM workspaces WHERE id = %s",
                (workspace_id,),
            )
            row = await cur.fetchone()
            if row:
                payload.design_system_ref = row.get("design_system_ref")

    try:
        html, summary = await designer_ai.generate_mockup(
            prompt=payload.prompt,
            design_system_ref=payload.design_system_ref,
            design_tokens=payload.design_tokens,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI generation failed: {e}")

    name = payload.name or payload.prompt[:30]
    history = [{"role": "user", "content": payload.prompt}, {"role": "assistant", "content": summary}]

    # 既存フレーム数で配置オフセット
    async with aiosqlite.connect() as db:
        cur = await db.execute(
            "SELECT COUNT(*) AS c FROM design_frames WHERE workspace_id = %s",
            (workspace_id,),
        )
        cnt = (await cur.fetchone()).get("c", 0)
        offset = int(cnt) * 60

        cur = await db.execute(
            """
            INSERT INTO design_frames
                (workspace_id, name, url, frame_type, content,
                 position_x, position_y, width, height, prompt_history)
            VALUES (%s, %s, %s, 'mockup', %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING *
            """,
            (
                workspace_id, name,
                f"about:blank#mockup-{cnt + 1}",  # url は識別子のみ (実体は content)
                html,
                100 + offset, 100 + offset, 1440, 900,
                json.dumps(history),
            ),
        )
        row = await cur.fetchone()
        await db.commit()
    if not row:
        raise HTTPException(status_code=500, detail="frame creation failed")
    return MockupGenerateResponse(frame=_row_to_frame(row), summary=summary, html=html)


@router.post(
    "/{workspace_id}/design/frames/{frame_id}/edit",
    response_model=MockupGenerateResponse,
)
async def edit_mockup(workspace_id: int, frame_id: int, payload: MockupEditRequest):
    """既存モックを AI で修正。"""
    async with aiosqlite.connect() as db:
        cur = await db.execute(
            "SELECT * FROM design_frames WHERE workspace_id = %s AND id = %s",
            (workspace_id, frame_id),
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="frame not found")
        existing_html = row.get("content") or ""
        if not existing_html:
            raise HTTPException(
                status_code=400, detail="frame has no content to edit (frame_type=mockup required)"
            )
        try:
            new_html, summary = await designer_ai.edit_mockup(
                existing_html=existing_html,
                instruction=payload.instruction,
                target_selector=payload.target_selector,
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"AI edit failed: {e}")

        history = list(row.get("prompt_history") or [])
        history.append({"role": "user", "content": payload.instruction})
        history.append({"role": "assistant", "content": summary})

        cur = await db.execute(
            """
            UPDATE design_frames SET content = %s, prompt_history = %s::jsonb
            WHERE workspace_id = %s AND id = %s
            RETURNING *
            """,
            (new_html, json.dumps(history), workspace_id, frame_id),
        )
        updated = await cur.fetchone()
        await db.commit()
    return MockupGenerateResponse(
        frame=_row_to_frame(updated), summary=summary, html=new_html,
    )


class FrameContentUpdate(BaseModel):
    content: str


@router.put(
    "/{workspace_id}/design/frames/{frame_id}/content",
    response_model=Frame,
)
async def update_frame_content(
    workspace_id: int, frame_id: int, payload: FrameContentUpdate,
):
    """フレームの HTML 本文を直接更新 (Code エディタの保存用)。"""
    async with aiosqlite.connect() as db:
        cur = await db.execute(
            """
            UPDATE design_frames SET content = %s
            WHERE workspace_id = %s AND id = %s
            RETURNING *
            """,
            (payload.content, workspace_id, frame_id),
        )
        row = await cur.fetchone()
        await db.commit()
    if not row:
        raise HTTPException(status_code=404, detail="frame not found")
    return _row_to_frame(row)


@router.get("/{workspace_id}/design/frames/{frame_id}/preview")
async def preview_mockup(workspace_id: int, frame_id: int):
    """frame の HTML 本文を text/html として返す (iframe src で読み込む用)。"""
    async with aiosqlite.connect() as db:
        cur = await db.execute(
            "SELECT content FROM design_frames WHERE workspace_id = %s AND id = %s",
            (workspace_id, frame_id),
        )
        row = await cur.fetchone()
    if not row or not row.get("content"):
        raise HTTPException(status_code=404, detail="no preview content")
    html_with_preload = _inject_preload(row["content"])
    return Response(
        content=html_with_preload,
        media_type="text/html; charset=utf-8",
        headers={
            "X-Frame-Options": "SAMEORIGIN",
            # canvas からの cross-origin 読み取りを許可（penpal RPC のため）
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.put("/{workspace_id}/design/canvas-state", response_model=CanvasState)
async def save_canvas_state(workspace_id: int, payload: CanvasState):
    async with aiosqlite.connect() as db:
        cur = await db.execute(
            """
            INSERT INTO design_canvas_state
                (workspace_id, user_id, scale, position_x, position_y, selected_frame_ids)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (workspace_id, user_id)
            DO UPDATE SET
                scale = EXCLUDED.scale,
                position_x = EXCLUDED.position_x,
                position_y = EXCLUDED.position_y,
                selected_frame_ids = EXCLUDED.selected_frame_ids
            RETURNING *
            """,
            (
                workspace_id,
                payload.user_id,
                payload.scale,
                payload.position_x,
                payload.position_y,
                json.dumps(payload.selected_frame_ids),
            ),
        )
        row = await cur.fetchone()
        await db.commit()
    return CanvasState(
        workspace_id=row["workspace_id"],
        user_id=row["user_id"],
        scale=float(row["scale"]),
        position_x=float(row["position_x"]),
        position_y=float(row["position_y"]),
        selected_frame_ids=row.get("selected_frame_ids") or [],
    )
