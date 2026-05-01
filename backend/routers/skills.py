"""
skills.py — スキル管理 API

スキルの CRUD・一覧・コンテンツ取得・実行。
格納場所: <repo>/data/skills/{skill_name}/SKILL.md
"""

import re
from pathlib import Path
from typing import Optional

from db import async_db as aiosqlite
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

DB_PATH    = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"
SKILL_STORE = Path(__file__).resolve().parents[2] / "data" / "skills"

router = APIRouter(prefix="/api/skills", tags=["skills"])


class SkillCreate(BaseModel):
    skill_name:   str
    display_name: Optional[str] = None
    description:  Optional[str] = None
    category:     Optional[str] = "general"
    tags:         Optional[str] = None
    content:      str            # SKILL.md の本文


class SkillUpdate(BaseModel):
    display_name: Optional[str] = None
    description:  Optional[str] = None
    category:     Optional[str] = None
    tags:         Optional[str] = None
    content:      Optional[str] = None
    is_active:    Optional[int] = None


@router.get("")
async def list_skills(
    category: Optional[str] = None,
    search:   Optional[str] = None,
    limit:    int = 200,
):
    """スキル一覧を返す（メタデータのみ、本文なし）。"""
    conditions = []
    params: list = []
    if category:
        conditions.append("category = ?")
        params.append(category)
    if search:
        conditions.append("(skill_name LIKE ? OR display_name LIKE ? OR description LIKE ?)")
        params += [f"%{search}%"] * 3

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            f"SELECT id, skill_name, display_name, description, category, tags, "
            f"is_active, version, updated_at FROM skill_definitions {where} "
            f"ORDER BY category, skill_name LIMIT ?",
            [*params, limit],
        )
    return [dict(r) for r in rows]


@router.get("/categories")
async def list_categories():
    """使用中のカテゴリ一覧と件数を返す。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT category, COUNT(*) as count FROM skill_definitions "
            "WHERE is_active=1 GROUP BY category ORDER BY count DESC"
        )
    return [dict(r) for r in rows]


@router.get("/{skill_name}")
async def get_skill(skill_name: str):
    """スキルのメタデータ＋本文（SKILL.md）を返す。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT * FROM skill_definitions WHERE skill_name=?", (skill_name,)
        )
    if not rows:
        raise HTTPException(404, f"スキルが見つかりません: {skill_name}")

    item = dict(rows[0])
    md_path = Path(item["md_path"])
    item["content"] = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    return item


@router.post("")
async def create_skill(body: SkillCreate):
    """新しいスキルを作成する。"""
    skill_name = body.skill_name.strip().lower().replace(" ", "-")

    # ファイル保存（primary）
    dest_dir = SKILL_STORE / skill_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / "SKILL.md"
    dest_file.write_text(body.content, encoding="utf-8")

    # ミラー（Claude desktop 連携用）
    try:
        from services.skill_manager import CLAUDE_SKILLS
        import shutil
        mirror_dir = CLAUDE_SKILLS / skill_name
        if mirror_dir.exists():
            shutil.rmtree(mirror_dir)
        shutil.copytree(dest_dir, mirror_dir)
    except Exception as e:
        print(f"[skills.create] mirror 失敗: {e}")

    display_name = body.display_name or skill_name
    description  = body.description or _extract_description(body.content)

    async with aiosqlite.connect(DB_PATH) as db:
        try:
            cursor = await db.execute(
                """INSERT INTO skill_definitions
                   (skill_name, display_name, description, category, tags, md_path)
                   VALUES (?, ?, ?, ?, ?, ?) RETURNING id""",
                (skill_name, display_name, description, body.category or "general",
                 body.tags or f"#{skill_name}", str(dest_file)),
            )
            _row = await cursor.fetchone()
            await db.commit()
            new_id = _row["id"]
        except Exception as e:
            if "UNIQUE" in str(e):
                raise HTTPException(409, f"スキル '{skill_name}' は既に存在します")
            raise

    return {"id": new_id, "skill_name": skill_name, "md_path": str(dest_file)}


@router.patch("/{skill_name}")
async def update_skill(skill_name: str, body: SkillUpdate):
    """スキルのメタデータ・本文を更新する。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT * FROM skill_definitions WHERE skill_name=?", (skill_name,)
        )
        if not rows:
            raise HTTPException(404, f"スキルが見つかりません: {skill_name}")

        item = dict(rows[0])

        # SKILL.md 更新（primary + mirror）
        if body.content is not None:
            Path(item["md_path"]).write_text(body.content, encoding="utf-8")
            try:
                from services.skill_manager import CLAUDE_SKILLS
                mirror_md = CLAUDE_SKILLS / skill_name / "SKILL.md"
                mirror_md.parent.mkdir(parents=True, exist_ok=True)
                mirror_md.write_text(body.content, encoding="utf-8")
            except Exception as e:
                print(f"[skills.update] mirror 失敗: {e}")

        # DB 更新
        updates: dict = {}
        if body.display_name is not None: updates["display_name"] = body.display_name
        if body.description  is not None: updates["description"]  = body.description
        if body.category     is not None: updates["category"]     = body.category
        if body.tags         is not None: updates["tags"]         = body.tags
        if body.is_active    is not None: updates["is_active"]    = body.is_active
        if body.content      is not None:
            updates["description"] = updates.get("description") or _extract_description(body.content)
        updates["updated_at"] = "datetime('now','localtime')"

        set_parts = [f"{k}=datetime('now','localtime')" if v == "datetime('now','localtime')"
                     else f"{k}=?" for k, v in updates.items()]
        vals = [v for v in updates.values() if v != "datetime('now','localtime')"]

        await db.execute(
            f"UPDATE skill_definitions SET {', '.join(set_parts)} WHERE skill_name=?",
            [*vals, skill_name],
        )
        await db.commit()

    return {"status": "updated", "skill_name": skill_name}


@router.delete("/{skill_name}")
async def delete_skill(skill_name: str):
    """スキルを無効化する（ファイルは保持）。"""
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await db.execute_fetchall(
            "SELECT id FROM skill_definitions WHERE skill_name=?", (skill_name,)
        )
        if not rows:
            raise HTTPException(404, f"スキルが見つかりません: {skill_name}")
        await db.execute(
            "UPDATE skill_definitions SET is_active=0, updated_at=datetime('now','localtime') WHERE skill_name=?",
            (skill_name,)
        )
        await db.commit()
    return {"status": "deactivated", "skill_name": skill_name}


@router.post("/{skill_name}/run")
async def run_skill(skill_name: str, body: dict):
    """スキルをその場で実行する（テスト用）。"""
    user_input = body.get("input", "")
    provider   = body.get("provider", "ollama")
    model      = body.get("model", "qwen2.5:7b")
    if not user_input:
        raise HTTPException(400, "input が必要です")

    from integrations.skill_runner import invoke_skill
    import asyncio

    async def _run():
        return await invoke_skill(
            skill_name, user_input,
            provider=provider, model=model,
            triggered_by="user"
        )

    result = await _run()
    return {"skill_name": skill_name, "result": result}


def _extract_description(content: str) -> str:
    """SKILL.md の description フロントマターを抽出する。"""
    m = re.search(r'^description:\s*(.+)$', content, re.MULTILINE)
    if m:
        return m.group(1).strip().strip('"').strip("'")[:500]
    # フロントマターがなければ最初の非空行を使う
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith('#') and not line.startswith('---'):
            return line[:200]
    return ""
