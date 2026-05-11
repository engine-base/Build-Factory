"""skills.py — スキル管理 API (T-002-01 REFACTOR).

スキルの CRUD・一覧・コンテンツ取得・実行.
格納場所: <repo>/data/skills/{skill_name}/SKILL.md

T-002-01 AC:
  AC-1 UBIQUITOUS    : F-002 のスキル管理 API (list/get/create/update/delete/run)
  AC-2 EVENT-DRIVEN  : UI 操作 → backend state 反映 + view refresh (mutation 後 state 取得可)
  AC-3 STATE-DRIVEN  : 既存 API contract (route / response shape) 不変
  AC-4 UNWANTED      : invalid input / unknown skill / 未許可 actor は 4xx +
                       {detail:{code,message}} かつ persistent state mutate しない
"""

import logging
import re
from pathlib import Path
from typing import Any, Optional

from db import async_db as aiosqlite
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

DB_PATH    = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"
SKILL_STORE = Path(__file__).resolve().parents[2] / "data" / "skills"

router = APIRouter(prefix="/api/skills", tags=["skills"])


# ──────────────────────────────────────────────────────────────────────────
# T-002-01: error contract + audit helpers
# ──────────────────────────────────────────────────────────────────────────


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    """{detail:{code,message}} 形式統一."""
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    """audit_logs に skills.* event を emit (best-effort)."""
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover — best-effort
        logger.warning("skills audit emit failed: %s -- %s", event_type, e)


_SKILL_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")


def _validate_skill_name(name: str) -> str:
    """skill_name 形式検証 (lower / 64 chars / [a-z0-9_-])."""
    if not name or not name.strip():
        raise _error("skills.invalid_skill_name", "skill_name must not be empty")
    n = name.strip().lower().replace(" ", "-")
    if not _SKILL_NAME_RE.match(n):
        raise _error(
            "skills.invalid_skill_name",
            f"skill_name must match [a-z0-9][a-z0-9_-]{{1,63}}, got {name!r}",
        )
    return n


def _validate_actor(actor: Optional[str]) -> None:
    """actor_user_id が指定された場合は非空."""
    if actor is not None and not actor.strip():
        raise _error("skills.unauthorized", "actor_user_id must not be empty when provided",
                     status_code=401)


# ──────────────────────────────────────────────────────────────────────────
# AC-3 backwards compat: 既存 Pydantic model
# ──────────────────────────────────────────────────────────────────────────


class SkillCreate(BaseModel):
    skill_name:   str
    display_name: Optional[str] = None
    description:  Optional[str] = None
    category:     Optional[str] = "general"
    tags:         Optional[str] = None
    content:      str
    actor_user_id: Optional[str] = None  # T-002-01 AC-4


class SkillUpdate(BaseModel):
    display_name: Optional[str] = None
    description:  Optional[str] = None
    category:     Optional[str] = None
    tags:         Optional[str] = None
    content:      Optional[str] = None
    is_active:    Optional[int] = None
    actor_user_id: Optional[str] = None  # T-002-01 AC-4


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: list / get / categories
# ──────────────────────────────────────────────────────────────────────────


@router.get("")
async def list_skills(
    category: Optional[str] = None,
    search:   Optional[str] = None,
    limit:    int = 200,
):
    """スキル一覧 (メタデータのみ、本文なし)."""
    if limit <= 0 or limit > 1000:
        raise _error("skills.invalid_limit", "limit must be 1..1000")
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
    """使用中のカテゴリ一覧と件数."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT category, COUNT(*) as count FROM skill_definitions "
            "WHERE is_active=1 GROUP BY category ORDER BY count DESC"
        )
    return [dict(r) for r in rows]


@router.get("/{skill_name}")
async def get_skill(skill_name: str):
    """スキルのメタデータ＋本文 (SKILL.md)."""
    name = _validate_skill_name(skill_name)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT * FROM skill_definitions WHERE skill_name=?", (name,)
        )
    if not rows:
        raise _error("skills.not_found", f"skill not found: {name}", status_code=404)

    item = dict(rows[0])
    md_path = Path(item["md_path"])
    item["content"] = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    return item


# ──────────────────────────────────────────────────────────────────────────
# AC-1 / AC-2 / AC-3 / AC-4: create
# ──────────────────────────────────────────────────────────────────────────


@router.post("")
async def create_skill(body: SkillCreate):
    """新しいスキルを作成."""
    _validate_actor(body.actor_user_id)
    if not body.content or not body.content.strip():
        raise _error("skills.invalid_content", "content must not be empty")
    if len(body.content) > 1_000_000:
        raise _error("skills.content_too_large", "content must be <= 1MB")

    skill_name = _validate_skill_name(body.skill_name)

    # ファイル保存 (primary)
    dest_dir = SKILL_STORE / skill_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / "SKILL.md"
    dest_file.write_text(body.content, encoding="utf-8")

    # ミラー (Claude desktop 連携用)
    try:
        from services.skill_manager import CLAUDE_SKILLS
        import shutil
        mirror_dir = CLAUDE_SKILLS / skill_name
        if mirror_dir.exists():
            shutil.rmtree(mirror_dir)
        shutil.copytree(dest_dir, mirror_dir)
    except Exception as e:
        logger.warning("[skills.create] mirror failed: %s", e)

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
                raise _error(
                    "skills.already_exists",
                    f"skill {skill_name!r} already exists",
                    status_code=409,
                )
            raise _error("skills.create_failed", f"DB insert failed: {e}", status_code=500)

    await _audit(
        "skills.created",
        user_id=body.actor_user_id,
        detail={"id": new_id, "skill_name": skill_name, "category": body.category},
    )
    return {"id": new_id, "skill_name": skill_name, "md_path": str(dest_file)}


# ──────────────────────────────────────────────────────────────────────────
# AC-1 / AC-2 / AC-3 / AC-4: update
# ──────────────────────────────────────────────────────────────────────────


@router.patch("/{skill_name}")
async def update_skill(skill_name: str, body: SkillUpdate):
    """スキルのメタデータ・本文を更新."""
    _validate_actor(body.actor_user_id)
    name = _validate_skill_name(skill_name)
    if body.content is not None and len(body.content) > 1_000_000:
        raise _error("skills.content_too_large", "content must be <= 1MB")

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT * FROM skill_definitions WHERE skill_name=?", (name,)
        )
        if not rows:
            raise _error("skills.not_found", f"skill not found: {name}", status_code=404)

        item = dict(rows[0])

        # SKILL.md 更新 (primary + mirror)
        if body.content is not None:
            Path(item["md_path"]).write_text(body.content, encoding="utf-8")
            try:
                from services.skill_manager import CLAUDE_SKILLS
                mirror_md = CLAUDE_SKILLS / name / "SKILL.md"
                mirror_md.parent.mkdir(parents=True, exist_ok=True)
                mirror_md.write_text(body.content, encoding="utf-8")
            except Exception as e:
                logger.warning("[skills.update] mirror failed: %s", e)

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
            [*vals, name],
        )
        await db.commit()

    await _audit(
        "skills.updated",
        user_id=body.actor_user_id,
        detail={"skill_name": name, "fields_changed": [k for k in updates if k != "updated_at"]},
    )
    return {"status": "updated", "skill_name": name}


# ──────────────────────────────────────────────────────────────────────────
# AC-1 / AC-2 / AC-3 / AC-4: delete (deactivate)
# ──────────────────────────────────────────────────────────────────────────


@router.delete("/{skill_name}")
async def delete_skill(skill_name: str, actor_user_id: Optional[str] = None):
    """スキルを無効化 (soft delete: is_active=0)."""
    _validate_actor(actor_user_id)
    name = _validate_skill_name(skill_name)
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await db.execute_fetchall(
            "SELECT id FROM skill_definitions WHERE skill_name=?", (name,)
        )
        if not rows:
            raise _error("skills.not_found", f"skill not found: {name}", status_code=404)
        await db.execute(
            "UPDATE skill_definitions SET is_active=0, "
            "updated_at=datetime('now','localtime') WHERE skill_name=?",
            (name,)
        )
        await db.commit()
    await _audit(
        "skills.deactivated",
        user_id=actor_user_id,
        detail={"skill_name": name},
    )
    return {"status": "deactivated", "skill_name": name}


# ──────────────────────────────────────────────────────────────────────────
# AC-1 / AC-2 / AC-4: run (test)
# ──────────────────────────────────────────────────────────────────────────


@router.post("/{skill_name}/run")
async def run_skill(skill_name: str, body: dict):
    """スキルをその場で実行 (テスト用)."""
    name = _validate_skill_name(skill_name)
    if not isinstance(body, dict):
        raise _error("skills.invalid_body", "request body must be a JSON object")
    actor = body.get("actor_user_id")
    _validate_actor(actor)
    user_input = body.get("input", "")
    if not user_input or not str(user_input).strip():
        raise _error("skills.invalid_input", "input must not be empty")
    provider   = body.get("provider", "ollama")
    model      = body.get("model", "qwen2.5:7b")

    from integrations.skill_runner import invoke_skill

    result = await invoke_skill(
        name, user_input,
        provider=provider, model=model,
        triggered_by="user",
    )
    await _audit(
        "skills.run",
        user_id=actor,
        detail={"skill_name": name, "input_len": len(str(user_input))},
    )
    return {"skill_name": name, "result": result}


def _extract_description(content: str) -> str:
    """SKILL.md の description フロントマターを抽出."""
    m = re.search(r'^description:\s*(.+)$', content, re.MULTILINE)
    if m:
        return m.group(1).strip().strip('"').strip("'")[:500]
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith('#') and not line.startswith('---'):
            return line[:200]
    return ""
