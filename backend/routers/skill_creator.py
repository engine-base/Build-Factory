"""
skill_creator.py — Web/Slack から呼べる skill 管理 API

GET  /api/skill-creator/list                スキル一覧
GET  /api/skill-creator/skill/{name}        詳細
POST /api/skill-creator/skill                新規作成
PUT  /api/skill-creator/skill/{name}         本文上書き
PATCH /api/skill-creator/skill/{name}/description  説明だけ更新
DELETE /api/skill-creator/skill/{name}       削除
POST /api/skill-creator/eval/{name}          テストケース追加
GET  /api/skill-creator/evals/{name}         テストケース一覧
POST /api/skill-creator/run/{name}/{eval_id} テスト実行
POST /api/skill-creator/package/{name}        .skill 生成
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services import skill_manager as sm

router = APIRouter(prefix="/api/skill-creator", tags=["skill-creator"])


class SkillCreate(BaseModel):
    name: str
    description: str
    body: str
    overwrite: bool = False


class SkillUpdate(BaseModel):
    skill_md: str


class DescriptionUpdate(BaseModel):
    description: str


class EvalCreate(BaseModel):
    prompt: str
    expected_output: str = ""
    files: Optional[list[str]] = None


@router.get("/list")
async def list_skills():
    return {"skills": await sm.list_skills()}


@router.post("/sync")
async def sync_to_db():
    """ファイルシステム上の全スキルを skill_definitions テーブルに登録/更新する。
    管理 UI で skill-creator や staff-management が見えない時に呼ぶ。"""
    return await sm.sync_filesystem_to_db()


@router.get("/skill/{name}")
async def get_skill(name: str):
    s = await sm.get_skill(name)
    if not s:
        raise HTTPException(404, f"skill '{name}' not found")
    return s


@router.post("/skill")
async def create_skill(body: SkillCreate):
    try:
        return await sm.create_skill(
            name=body.name, description=body.description,
            body=body.body, overwrite=body.overwrite,
        )
    except (ValueError, FileExistsError) as e:
        raise HTTPException(400, str(e))


@router.put("/skill/{name}")
async def update_skill(name: str, body: SkillUpdate):
    try:
        return await sm.update_skill_md(name, body.skill_md)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@router.patch("/skill/{name}/description")
async def update_description(name: str, body: DescriptionUpdate):
    try:
        return await sm.update_description(name, body.description)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@router.delete("/skill/{name}")
async def delete_skill(name: str):
    return await sm.delete_skill(name)


@router.get("/evals/{name}")
async def list_evals(name: str):
    return {"evals": await sm.list_evals(name)}


@router.post("/eval/{name}")
async def add_eval(name: str, body: EvalCreate):
    try:
        return await sm.add_eval(
            name, body.prompt, body.expected_output, body.files,
        )
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@router.post("/run/{name}/{eval_id}")
async def run_eval(name: str, eval_id: int,
                   provider: str = "openai", model: str = "gpt-4o-mini"):
    try:
        return await sm.run_eval_inline(name, eval_id, provider=provider, model=model)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(400, str(e))


@router.post("/package/{name}")
async def package(name: str):
    try:
        return await sm.package_skill(name)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
