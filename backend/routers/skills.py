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
import time
from pathlib import Path
from typing import Any, Optional  # noqa: F401 (Any preserved for downstream typing)

from db import async_db as aiosqlite
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

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


@router.get("/-archived")
async def list_archived():
    """archive 済みスキル一覧 (T-002-02). 静的 path のため /{skill_name} より先に定義."""
    from services.skill_manager import list_archived_skills
    rows = await list_archived_skills()
    return rows


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
        if body.display_name is not None:
            updates["display_name"] = body.display_name
        if body.description is not None:
            updates["description"] = body.description
        if body.category is not None:
            updates["category"] = body.category
        if body.tags is not None:
            updates["tags"] = body.tags
        if body.is_active is not None:
            updates["is_active"] = body.is_active
        if body.content is not None:
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


# ──────────────────────────────────────────────────────────────────────────
# T-V3-B-03 (F-002): POST /api/skills/{id}/test
#
# spec: docs/api-design/2026-05-16_v3/openapi.yaml#/paths/~1api~1skills~1{id}~1test
#       docs/functional-breakdown/2026-05-16_v3/features.json#F-002 (api_endpoints[2])
#
# AC マッピング (audit: docs/audit/2026-05-16_v3/T-V3-B-03.md):
#   AC-F1 UNWANTED      : 10/min/user 超過は 429 (rate_limit)
#   AC-F2 EVENT-DRIVEN  : valid + authorized → 2xx {output, duration_ms}
#   AC-F3 UNWANTED      : auth token 欠如 → 401
#   AC-F4 UNWANTED      : body 検証失敗 → 422 + field-level error map
# ──────────────────────────────────────────────────────────────────────────


class SkillTestRequest(BaseModel):
    """POST /api/skills/{id}/test body (F-002 contract)."""

    test_input: str = Field(..., min_length=1, description="スキルに渡すテスト入力")


def _extract_bearer_user(authorization: Optional[str]) -> str:
    """`Authorization: Bearer <token>` → user_id を返す.

    本実装は Phase 1 minimum: token はそのまま user_id として扱う (Supabase Auth
    middleware が将来 sub claim を decode して書き戻す前提). 形式違反 / 欠如は
    401 で reject (AC-F3).
    """
    if not authorization or not authorization.strip():
        raise _error("skills.unauthorized", "missing auth token", status_code=401)
    parts = authorization.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise _error("skills.unauthorized", "invalid auth scheme (expected Bearer)",
                     status_code=401)
    return parts[1].strip()


def _resolve_skill_identifier(identifier: str) -> str:
    """path `{id}` は openapi 上 uuid だが、現行実装は skill_name 基準なので両対応.

    - UUID 形式なら skill_definitions.id (int) に変換できないため skill_name と
      みなす (404 は後段の DB 探索で確定する)
    - そうでなければ skill_name として validate
    """
    s = (identifier or "").strip()
    if not s:
        raise _error("skills.invalid_skill_id", "id must not be empty",
                     status_code=422)
    # 既存 _validate_skill_name は 400 を返すので、test endpoint では 422 に揃える
    try:
        return _validate_skill_name(s)
    except HTTPException as e:
        # 既存 detail.code を保ったまま 422 にリマップ (openapi outputs_4xx 準拠)
        detail = e.detail if isinstance(e.detail, dict) else {
            "code": "skills.invalid_skill_name", "message": str(e.detail),
        }
        raise HTTPException(status_code=422, detail=detail) from None


@router.post("/{skill_id}/test", status_code=201)
async def test_skill(
    skill_id: str,
    body: SkillTestRequest,
    authorization: Optional[str] = Header(default=None),
):
    """T-V3-B-03 (F-002): スキル評価実行 (test endpoint).

    Args:
        skill_id: path {id}. 現行 schema 上は skill_name (UUID 形式は未対応).
        body: SkillTestRequest. test_input は必須 (空文字 422).
        authorization: `Bearer <token>` (401 if missing/invalid).

    Returns:
        201 Created {"output": str, "duration_ms": int}
    """
    # AC-F3: 401 (missing / invalid auth token)
    user_id = _extract_bearer_user(authorization)

    # AC-F4: 422 (id 検証 / skill_name 形式違反)
    name = _resolve_skill_identifier(skill_id)

    # AC-F1: 429 (10/min/user 超過)
    from services.skill_test_rate_limiter import check_and_consume

    allowed, _remaining = await check_and_consume(user_id)
    if not allowed:
        raise _error(
            "skills.rate_limited",
            "rate limit exceeded: max 10 test invocations per minute per user",
            status_code=429,
        )

    # 404: skill 不在
    async with aiosqlite.connect(DB_PATH) as db:
        # row_factory は async_db.py 側で常に dict-like なので代入不要 (T-V3-B-03)
        rows = await db.execute_fetchall(
            "SELECT id, skill_name, md_path, is_active FROM skill_definitions "
            "WHERE skill_name=?",
            (name,),
        )
    if not rows:
        raise _error("skills.not_found", f"skill not found: {name}", status_code=404)
    item = dict(rows[0])
    if not item.get("is_active", 1):
        # archived/disabled は 404 同等 (AI 召喚不可)
        raise _error("skills.not_found", f"skill not active: {name}", status_code=404)

    # AC-F2: スキル評価実行 (existing skill_runner を再利用)
    from integrations.skill_runner import invoke_skill

    t0 = time.perf_counter()
    try:
        result = await invoke_skill(
            name,
            body.test_input,
            triggered_by="user",
        )
    except Exception as e:
        logger.error("[skills.test] invoke failed: %s -- %s", name, e)
        raise _error(
            "skills.execution_failed",
            f"skill execution failed: {e}",
            status_code=500,
        )
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    # output 正規化: skill_runner は dict / str / 任意型を返しうる
    if isinstance(result, dict):
        # 代表的 keys を fallback で拾う
        output_str = (
            result.get("output")
            or result.get("text")
            or result.get("content")
            or str(result)
        )
    elif isinstance(result, str):
        output_str = result
    else:
        output_str = str(result)

    await _audit(
        "skills.tested",
        user_id=user_id,
        detail={
            "skill_name": name,
            "input_len": len(body.test_input),
            "duration_ms": elapsed_ms,
        },
    )
    return {"output": output_str, "duration_ms": elapsed_ms}


# ──────────────────────────────────────────────────────────────────────────
# T-002-02: archive / restore endpoint
# ──────────────────────────────────────────────────────────────────────────


class ContextRequest(BaseModel):
    employee_id: Optional[int] = None
    include_constitution: bool = True
    include_claude_rules: bool = True
    actor_user_id: Optional[str] = None


@router.post("/{skill_name}/context")
async def get_skill_context(skill_name: str, body: ContextRequest):
    """T-003-04: スキル context 注入 (CLAUDE.md ルール + SKILL.md + persona chain + Constitution)."""
    _validate_actor(body.actor_user_id)
    name = _validate_skill_name(skill_name)
    if body.employee_id is not None and body.employee_id <= 0:
        raise _error("skills.invalid_employee_id", "employee_id must be > 0 when provided")

    from services.skill_context_injector import (
        inject_context, SkillMdNotFoundError, SkillContextError,
    )

    # T-003-03 / T-AI-04 連携
    async def _resolve_guideline(employee_id: int) -> dict:
        from services.guideline_inheritance import resolve_guideline
        from routers.personas_guideline import (
            _default_hierarchy_loader, _default_persona_loader,
        )
        return await resolve_guideline(
            employee_id,
            hierarchy_loader=_default_hierarchy_loader,
            persona_loader=_default_persona_loader,
        )

    async def _load_constitution() -> str:
        try:
            from services.constitution_engine import _load_from_db, _load_from_env
            c = await _load_from_db()
            if c is None:
                c = _load_from_env()
            if c is None:
                return ""
            return c.full_text or ""
        except Exception:
            return ""

    try:
        result = await inject_context(
            name,
            employee_id=body.employee_id,
            include_constitution=body.include_constitution,
            include_claude_rules=body.include_claude_rules,
            guideline_resolver=_resolve_guideline if body.employee_id else None,
            constitution_loader=_load_constitution if body.include_constitution else None,
        )
    except SkillMdNotFoundError as e:
        raise _error("skills.skill_md_not_found", str(e), status_code=404)
    except SkillContextError as e:
        raise _error("skills.context_invalid", str(e))

    await _audit(
        "skills.context.injected",
        user_id=body.actor_user_id,
        detail={
            "skill_name": name,
            "employee_id": body.employee_id,
            "rendered_size": result["rendered_size"],
            "section_count": len(result["sections"]),
        },
    )
    return result


class ArchiveRequest(BaseModel):
    actor_user_id: Optional[str] = None
    reason: Optional[str] = None


class RestoreRequest(BaseModel):
    actor_user_id: Optional[str] = None
    archived_at: Optional[str] = None


@router.post("/{skill_name}/archive")
async def archive_skill_endpoint(skill_name: str, body: ArchiveRequest):
    """スキルを archive する (T-002-02)."""
    _validate_actor(body.actor_user_id)
    name = _validate_skill_name(skill_name)
    if body.reason is not None and len(body.reason) > 2000:
        raise _error("skills.reason_too_large", "reason must be <= 2000 chars")

    from services.skill_manager import (
        archive_skill,
        SkillNotFoundError,
        SkillAlreadyArchivedError,
    )
    try:
        result = await archive_skill(
            name, actor_user_id=body.actor_user_id, reason=body.reason,
        )
    except SkillNotFoundError as e:
        raise _error("skills.not_found", str(e), status_code=404)
    except SkillAlreadyArchivedError as e:
        raise _error("skills.already_archived", str(e), status_code=409)
    except Exception as e:
        raise _error("skills.archive_failed", f"archive failed: {e}", status_code=500)

    await _audit(
        "skills.archived",
        user_id=body.actor_user_id,
        detail={"skill_name": name, "reason": body.reason,
                "archive_dir": result.get("archive_dir")},
    )
    return {"status": "archived", **result}


@router.post("/{skill_name}/restore")
async def restore_skill_endpoint(skill_name: str, body: RestoreRequest):
    """archive からスキルを restore する (T-002-02)."""
    _validate_actor(body.actor_user_id)
    name = _validate_skill_name(skill_name)

    from services.skill_manager import (
        restore_skill,
        SkillNotFoundError,
        SkillAlreadyArchivedError,
    )
    try:
        result = await restore_skill(
            name, actor_user_id=body.actor_user_id, archived_at=body.archived_at,
        )
    except SkillNotFoundError as e:
        raise _error("skills.archive_not_found", str(e), status_code=404)
    except SkillAlreadyArchivedError as e:
        raise _error("skills.already_active", str(e), status_code=409)
    except Exception as e:
        raise _error("skills.restore_failed", f"restore failed: {e}", status_code=500)

    await _audit(
        "skills.restored",
        user_id=body.actor_user_id,
        detail={"skill_name": name, "restored_from": result.get("restored_from")},
    )
    return {"status": "restored", **result}


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
