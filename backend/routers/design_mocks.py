"""
Build-Factory ↔ Penpot 連携: デザインモック CRUD。

エンドポイント:
    GET    /api/workspaces/{ws}/designs                  画面一覧
    POST   /api/workspaces/{ws}/designs                  画面追加 (Penpot File 自動作成)
    GET    /api/workspaces/{ws}/designs/{id}             画面詳細
    PATCH  /api/workspaces/{ws}/designs/{id}             画面更新
    DELETE /api/workspaces/{ws}/designs/{id}             画面削除 (Penpot File も削除)
    GET    /api/workspaces/{ws}/designs/{id}/embed-url   Penpot 編集 URL を返す
"""
from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from db import async_db as aiosqlite
from services.penpot_client import get_penpot_client, PenpotError

router = APIRouter(prefix="/api/workspaces", tags=["design-mocks"])


# ─────────────────────────────────────────
# Models
# ─────────────────────────────────────────


class DesignMockCreate(BaseModel):
    name: str
    description: Optional[str] = None
    route_path: Optional[str] = None
    feature_id: Optional[int] = None
    page_id: Optional[int] = None


class DesignMockUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    route_path: Optional[str] = None
    status: Optional[str] = None
    spec_meta: Optional[dict[str, Any]] = None


class DesignMock(BaseModel):
    id: int
    workspace_id: int
    feature_id: Optional[int]
    page_id: Optional[int]
    name: str
    description: Optional[str]
    route_path: Optional[str]
    penpot_team_id: Optional[str]
    penpot_project_id: Optional[str]
    penpot_file_id: Optional[str]
    penpot_page_id: Optional[str]
    penpot_frame_id: Optional[str]
    preview_image_url: Optional[str]
    svg_url: Optional[str]
    spec_markdown: Optional[str]
    spec_meta: dict[str, Any] = Field(default_factory=dict)
    status: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


def _row_to_mock(r: dict) -> DesignMock:
    return DesignMock(
        id=r["id"],
        workspace_id=r["workspace_id"],
        feature_id=r.get("feature_id"),
        page_id=r.get("page_id"),
        name=r["name"],
        description=r.get("description"),
        route_path=r.get("route_path"),
        penpot_team_id=r.get("penpot_team_id"),
        penpot_project_id=r.get("penpot_project_id"),
        penpot_file_id=r.get("penpot_file_id"),
        penpot_page_id=r.get("penpot_page_id"),
        penpot_frame_id=r.get("penpot_frame_id"),
        preview_image_url=r.get("preview_image_url"),
        svg_url=r.get("svg_url"),
        spec_markdown=r.get("spec_markdown"),
        spec_meta=r.get("spec_meta") or {},
        status=r.get("status") or "draft",
        created_at=r["created_at"].isoformat() if r.get("created_at") else None,
        updated_at=r["updated_at"].isoformat() if r.get("updated_at") else None,
    )


async def _ensure_workspace_penpot_project(workspace_id: int) -> tuple[str, str]:
    """workspace に対応する Penpot Team/Project を取得 or 自動作成して (team_id, project_id) を返す。"""
    async with aiosqlite.connect() as db:
        cur = await db.execute(
            "SELECT name, penpot_team_id, penpot_project_id FROM workspaces WHERE id = %s",
            (workspace_id,),
        )
        ws = await cur.fetchone()
    if not ws:
        raise HTTPException(status_code=404, detail="workspace not found")

    if ws.get("penpot_team_id") and ws.get("penpot_project_id"):
        return ws["penpot_team_id"], ws["penpot_project_id"]

    client = await get_penpot_client()
    team_id = ws.get("penpot_team_id") or await client.get_default_team_id()
    project = await client.create_project(team_id=team_id, name=ws["name"])
    project_id = project["id"]

    async with aiosqlite.connect() as db:
        await db.execute(
            "UPDATE workspaces SET penpot_team_id = %s, penpot_project_id = %s WHERE id = %s",
            (team_id, project_id, workspace_id),
        )
        await db.commit()
    return team_id, project_id


# ─────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────


@router.get("/{workspace_id}/designs", response_model=list[DesignMock])
async def list_designs(workspace_id: int):
    async with aiosqlite.connect() as db:
        cur = await db.execute(
            "SELECT * FROM design_mocks WHERE workspace_id = %s ORDER BY id ASC",
            (workspace_id,),
        )
        rows = await cur.fetchall()
    return [_row_to_mock(r) for r in rows]


@router.post(
    "/{workspace_id}/designs", response_model=DesignMock, status_code=201,
)
async def create_design(workspace_id: int, payload: DesignMockCreate):
    """BF 画面 + Penpot File を一発で作成。"""
    team_id, project_id = await _ensure_workspace_penpot_project(workspace_id)

    client = await get_penpot_client()
    try:
        penpot_file = await client.create_file(
            project_id=project_id, name=payload.name,
        )
    except PenpotError as e:
        raise HTTPException(status_code=502, detail=f"Penpot create-file failed: {e}")

    file_id = penpot_file["id"]
    # Penpot file の最初の page id を取得 (data.pages[0])
    page_id = None
    try:
        page_id = (penpot_file.get("data") or {}).get("pages", [None])[0]
    except Exception:
        page_id = None

    async with aiosqlite.connect() as db:
        cur = await db.execute(
            """
            INSERT INTO design_mocks
                (workspace_id, feature_id, page_id, name, description, route_path,
                 penpot_team_id, penpot_project_id, penpot_file_id, penpot_page_id,
                 status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'draft')
            RETURNING *
            """,
            (
                workspace_id, payload.feature_id, payload.page_id,
                payload.name, payload.description, payload.route_path,
                team_id, project_id, file_id, page_id,
            ),
        )
        row = await cur.fetchone()
        await db.commit()
    if not row:
        raise HTTPException(status_code=500, detail="insert failed")
    return _row_to_mock(row)


@router.get("/{workspace_id}/designs/{design_id}", response_model=DesignMock)
async def get_design(workspace_id: int, design_id: int):
    async with aiosqlite.connect() as db:
        cur = await db.execute(
            "SELECT * FROM design_mocks WHERE workspace_id = %s AND id = %s",
            (workspace_id, design_id),
        )
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="design not found")
    return _row_to_mock(row)


@router.patch("/{workspace_id}/designs/{design_id}", response_model=DesignMock)
async def update_design(workspace_id: int, design_id: int, payload: DesignMockUpdate):
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="no fields to update")
    sets = []
    params: list = []
    for k, v in fields.items():
        if k == "spec_meta":
            sets.append("spec_meta = %s::jsonb")
            params.append(json.dumps(v))
        else:
            sets.append(f"{k} = %s")
            params.append(v)
    params += [workspace_id, design_id]
    async with aiosqlite.connect() as db:
        cur = await db.execute(
            f"UPDATE design_mocks SET {', '.join(sets)} "
            f"WHERE workspace_id = %s AND id = %s RETURNING *",
            params,
        )
        row = await cur.fetchone()
        await db.commit()
    if not row:
        raise HTTPException(status_code=404, detail="design not found")
    return _row_to_mock(row)


@router.delete("/{workspace_id}/designs/{design_id}", status_code=204)
async def delete_design(workspace_id: int, design_id: int):
    async with aiosqlite.connect() as db:
        cur = await db.execute(
            "SELECT penpot_file_id FROM design_mocks WHERE workspace_id = %s AND id = %s",
            (workspace_id, design_id),
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="design not found")
        # 先に DB から削除
        await db.execute(
            "DELETE FROM design_mocks WHERE workspace_id = %s AND id = %s",
            (workspace_id, design_id),
        )
        await db.commit()
    # Penpot File を削除 (失敗してもログのみ)
    if row.get("penpot_file_id"):
        try:
            client = await get_penpot_client()
            await client.delete_file(row["penpot_file_id"])
        except Exception as e:
            print(f"[design_mocks] failed to delete penpot file: {e}")
    return None


class EmbedUrlResponse(BaseModel):
    embed_url: str
    file_id: str


@router.get(
    "/{workspace_id}/designs/{design_id}/embed-url",
    response_model=EmbedUrlResponse,
)
async def get_embed_url(workspace_id: int, design_id: int):
    """iframe で読み込む Penpot 編集 URL を返す。"""
    async with aiosqlite.connect() as db:
        cur = await db.execute(
            "SELECT penpot_team_id, penpot_file_id, penpot_page_id FROM design_mocks "
            "WHERE workspace_id = %s AND id = %s",
            (workspace_id, design_id),
        )
        row = await cur.fetchone()
    if not row or not row.get("penpot_file_id"):
        raise HTTPException(status_code=404, detail="design or penpot file not found")
    file_id = row["penpot_file_id"]
    page_id = row.get("penpot_page_id") or ""
    team_id = row.get("penpot_team_id") or ""
    # Penpot 2.x の workspace URL (実機検証で確定):
    #   /#/workspace?team-id=X&file-id=Y&page-id=Z
    # iframe は直接 PENPOT URL を読む (proxy 経由は routing 壊れる)
    import os as _os
    penpot_base = _os.environ.get("PENPOT_PUBLIC_URL", "http://localhost:9001")
    params = []
    if team_id:
        params.append(f"team-id={team_id}")
    params.append(f"file-id={file_id}")
    if page_id:
        params.append(f"page-id={page_id}")
    embed_url = f"{penpot_base}/#/workspace?{'&'.join(params)}"
    return EmbedUrlResponse(embed_url=embed_url, file_id=file_id)
