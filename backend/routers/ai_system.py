"""
ai_system.py — AI社員システム専用ルーター

S-2 AI社員ステータス / S-5 スケジュール管理 / S-6 自律度設定
S-7 ナレッジブラウザ / S-8 実行ログ
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import aiosqlite
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"

router = APIRouter(prefix="/api", tags=["ai-system"])


# ── S-2: AI社員ステータス ──────────────────────────────────────────────────

@router.get("/ai-employees/status")
async def get_ai_employees_status():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall("""
            SELECT
                c.*,
                (SELECT status  FROM execution_log WHERE skill_name=c.primary_skill ORDER BY started_at DESC LIMIT 1) as last_status,
                (SELECT started_at FROM execution_log WHERE skill_name=c.primary_skill ORDER BY started_at DESC LIMIT 1) as last_run,
                (SELECT count(*) FROM execution_log WHERE skill_name=c.primary_skill) as run_count,
                (SELECT count(*) FROM approval_queue WHERE source_skill=c.employee_name AND status='pending') as pending_count
            FROM ai_employee_config c
            WHERE c.is_active = 1
            ORDER BY c.id
        """)
    result = []
    for r in rows:
        d = dict(r)
        # ステータス導出
        if d.get("pending_count", 0) > 0:
            d["computed_status"] = "pending"
        elif d.get("last_status") == "running":
            d["computed_status"] = "running"
        elif d.get("last_status") == "failed":
            d["computed_status"] = "error"
        else:
            d["computed_status"] = "idle"
        result.append(d)
    return result


# ── S-5: スケジュール管理 ─────────────────────────────────────────────────

@router.get("/schedule")
async def list_schedules():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT * FROM task_schedule ORDER BY run_time, frequency"
        )
    return [dict(r) for r in rows]


class ScheduleUpdate(BaseModel):
    is_active: Optional[int] = None
    run_time: Optional[str] = None
    autonomy: Optional[str] = None


@router.patch("/schedule/{schedule_id}")
async def update_schedule(schedule_id: int, body: ScheduleUpdate):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "更新するフィールドがありません")
    set_clause = ", ".join([f"{k}=?" for k in updates])
    values = list(updates.values()) + [schedule_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE task_schedule SET {set_clause}, updated_at=datetime('now','localtime') WHERE id=?",
            values,
        )
        await db.commit()
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall("SELECT * FROM task_schedule WHERE id=?", (schedule_id,))
    if not rows:
        raise HTTPException(404, "スケジュールが見つかりません")
    # スケジューラーにも反映
    try:
        from scheduler.scheduler import _register_job
        _register_job(dict(rows[0]))
    except Exception:
        pass
    return dict(rows[0])


class ScheduleCreate(BaseModel):
    task_name: str
    skill_name: str
    frequency: str  # daily / weekly / monthly
    run_time: str   # HH:MM
    description: Optional[str] = None
    day_of_week: Optional[str] = None
    day_of_month: Optional[int] = None
    autonomy: str = "confirm"


@router.post("/schedule")
async def create_schedule(body: ScheduleCreate):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO task_schedule
               (task_name, skill_name, description, frequency, run_time,
                day_of_week, day_of_month, is_active, autonomy)
               VALUES (?,?,?,?,?,?,?,1,?)""",
            (body.task_name, body.skill_name, body.description,
             body.frequency, body.run_time, body.day_of_week,
             body.day_of_month, body.autonomy),
        )
        await db.commit()
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT * FROM task_schedule WHERE id=?", (cursor.lastrowid,)
        )
    new_task = dict(rows[0])
    try:
        from scheduler.scheduler import _register_job
        _register_job(new_task)
    except Exception:
        pass
    return new_task


# ── S-6: 自律度設定 ───────────────────────────────────────────────────────

class AutonomyUpdate(BaseModel):
    autonomy_settings: dict  # {"email_send": "confirm", "report_save": "auto", ...}
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None


@router.patch("/ai-employees/{employee_id}/autonomy")
async def update_autonomy(employee_id: int, body: AutonomyUpdate):
    updates: dict = {"autonomy_settings": json.dumps(body.autonomy_settings, ensure_ascii=False)}
    if body.llm_provider:
        updates["llm_provider"] = body.llm_provider
    if body.llm_model:
        updates["llm_model"] = body.llm_model
    set_clause = ", ".join([f"{k}=?" for k in updates])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE ai_employee_config SET {set_clause}, updated_at=datetime('now','localtime') WHERE id=?",
            [*updates.values(), employee_id],
        )
        await db.commit()
    return {"status": "updated"}


# ── S-7: ナレッジブラウザ ─────────────────────────────────────────────────

@router.get("/knowledge")
async def list_knowledge(
    skill: Optional[str] = None,
    source: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 100,
):
    """
    ナレッジ一覧を取得する。
    skill フィルタ: 全体共有(NULL) + 指定スキルのナレッジ
    """
    conditions = []
    params: list = []
    if skill:
        conditions.append("(skill_tags IS NULL OR skill_tags LIKE ?)")
        params.append(f"%{skill}%")
    if source:
        conditions.append("source = ?")
        params.append(source)
    if category:
        conditions.append("category = ?")
        params.append(category)
    if search:
        conditions.append("(title LIKE ? OR content LIKE ? OR summary LIKE ?)")
        params += [f"%{search}%"] * 3

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            f"""SELECT id, title, category, tags, skill_tags, summary, content,
                       md_path, source, confidence, use_count,
                       last_updated, created_at
                FROM knowledge_base {where}
                ORDER BY use_count DESC, created_at DESC LIMIT ?""",
            [*params, limit],
        )
    return [dict(r) for r in rows]


@router.get("/knowledge/sources")
async def knowledge_sources():
    """ナレッジのソース別件数を返す。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT source, COUNT(*) as count FROM knowledge_base
               GROUP BY source ORDER BY count DESC"""
        )
    return [dict(r) for r in rows]


@router.post("/knowledge/sync-obsidian")
async def trigger_obsidian_sync():
    """Obsidian Vault との同期を即時実行する。"""
    from services.obsidian_sync import run_obsidian_sync
    result = await run_obsidian_sync()
    return result


@router.get("/knowledge/tree")
async def get_knowledge_tree():
    """
    ナレッジをObsidian Vaultのツリー構造で返す。
    md_path がある: Vault配下のフォルダで分類
    md_path がない: "_DB専用" 仮想フォルダ配下にカテゴリ別
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT id, title, category, tags, skill_tags, md_path,
                      source, confidence, use_count, summary
               FROM knowledge_base ORDER BY id DESC"""
        )

    tree: dict = {"name": "root", "children": {}, "items": []}

    for r in rows:
        item = dict(r)
        path = item.get("md_path") or ""
        # Obsidian Vault配下のパスを正規化
        if "Obsidian/ENGINE-BASE/" in path:
            rel = path.split("Obsidian/ENGINE-BASE/", 1)[1]
            parts = rel.split("/")
            folders = parts[:-1]
        else:
            # DB専用ナレッジ
            folders = ["_DB専用", item.get("source") or "manual"]

        # ツリーに挿入
        node = tree
        for f in folders:
            if f not in node["children"]:
                node["children"][f] = {"name": f, "children": {}, "items": []}
            node = node["children"][f]
        node["items"].append(item)

    return tree


@router.patch("/knowledge/{knowledge_id}")
async def update_knowledge(knowledge_id: int, body: dict):
    """
    ナレッジを編集する。content が変更されたら:
      - DB の content/summary を更新
      - Obsidian Vault の MD ファイルも同期
      - Embedding を再計算
    """
    allowed = {"confirmed_by_user", "tags", "skill_tags", "summary",
               "title", "content", "category", "confidence"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(400, "更新可能なフィールドがありません")

    # 既存レコード取得
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT * FROM knowledge_base WHERE id=?", (knowledge_id,)
        )
        if not rows:
            raise HTTPException(404, "ナレッジが見つかりません")
        existing = dict(rows[0])

    # content が変わったら Obsidian MD ファイルも更新
    md_path = existing.get("md_path")
    if "content" in updates and md_path:
        try:
            from pathlib import Path as _P
            f = _P(md_path)
            if f.exists():
                # 既存ファイルの YAML フロントマターを保持しつつ本文だけ書き換え
                old_text = f.read_text(encoding="utf-8")
                new_content = updates["content"]
                title = updates.get("title", existing.get("title", ""))
                # 簡易的にフロントマター以下を置き換え
                if old_text.startswith("---"):
                    parts = old_text.split("---", 2)
                    if len(parts) >= 3:
                        frontmatter = parts[1]
                        new_text = f"---{frontmatter}---\n\n# {title}\n\n{new_content}\n"
                        f.write_text(new_text, encoding="utf-8")
                else:
                    f.write_text(f"# {title}\n\n{new_content}\n", encoding="utf-8")
        except Exception as e:
            print(f"[knowledge] MD更新失敗: {e}")

    # DB 更新
    set_clause = ", ".join([f"{k}=?" for k in updates])
    set_clause += ", last_updated=date('now','localtime')"
    if "content" in updates:
        set_clause += ", embedding=NULL"  # 再計算のためクリア

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE knowledge_base SET {set_clause} WHERE id=?",
            [*updates.values(), knowledge_id],
        )
        await db.commit()

    # Embedding 再計算（content/title変更時のみ）
    if "content" in updates or "title" in updates:
        try:
            from services.embedding_service import embed_and_save
            await embed_and_save(knowledge_id)
        except Exception as e:
            print(f"[knowledge] Embedding再計算失敗: {e}")

    return {"status": "updated", "id": knowledge_id}


@router.delete("/knowledge/{knowledge_id}")
async def delete_knowledge(knowledge_id: int):
    """ナレッジを削除する。Obsidian MDファイルも削除。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT md_path FROM knowledge_base WHERE id=?", (knowledge_id,)
        )
        if not rows:
            raise HTTPException(404, "ナレッジが見つかりません")
        md_path = dict(rows[0]).get("md_path")

        await db.execute("DELETE FROM knowledge_base WHERE id=?", (knowledge_id,))
        await db.commit()

    # Obsidian MD 削除
    if md_path:
        try:
            from pathlib import Path as _P
            f = _P(md_path)
            if f.exists():
                f.unlink()
        except Exception as e:
            print(f"[knowledge] MD削除失敗: {e}")

    return {"status": "deleted", "id": knowledge_id}


# ── ナレッジ クリーンアップ（未使用・古いものをフィルタ＆一括削除） ──────

@router.get("/knowledge/cleanup/preview")
async def knowledge_cleanup_preview(
    use_count_lte: int = 0,
    not_used_for_days: Optional[int] = None,   # last_updated が N日以上前
    older_than_days: Optional[int] = None,     # created_at が N日以上前
    source: Optional[str] = None,
    confirmed_by_user: Optional[int] = None,   # 0=未確認のみ
    exclude_obsidian: bool = True,             # Obsidian Vault 由来は守る
    limit: int = 500,
):
    """削除候補のプレビュー（実際は削除しない）。
    UIのフィルタとAI秘書の事前確認に使う。"""
    conditions = []
    params: list = []

    conditions.append("COALESCE(use_count, 0) <= ?")
    params.append(use_count_lte)

    if not_used_for_days is not None:
        conditions.append(
            "(last_updated IS NULL OR "
            f"date(last_updated) <= date('now','-{int(not_used_for_days)} days'))"
        )

    if older_than_days is not None:
        conditions.append(
            f"date(created_at) <= date('now','-{int(older_than_days)} days')"
        )

    if source:
        conditions.append("source = ?")
        params.append(source)

    if confirmed_by_user is not None:
        conditions.append("COALESCE(confirmed_by_user, 0) = ?")
        params.append(confirmed_by_user)

    if exclude_obsidian:
        conditions.append("(md_path IS NULL OR md_path NOT LIKE '%Obsidian/ENGINE-BASE/%')")

    where = "WHERE " + " AND ".join(conditions)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            f"""SELECT id, title, category, source, use_count,
                       confirmed_by_user, md_path, last_updated, created_at,
                       substr(content, 1, 120) as preview
                FROM knowledge_base {where}
                ORDER BY COALESCE(use_count,0) ASC, created_at ASC LIMIT ?""",
            [*params, limit],
        )

    items = [dict(r) for r in rows]
    return {
        "count": len(items),
        "filters": {
            "use_count_lte": use_count_lte,
            "not_used_for_days": not_used_for_days,
            "older_than_days": older_than_days,
            "source": source,
            "confirmed_by_user": confirmed_by_user,
            "exclude_obsidian": exclude_obsidian,
        },
        "items": items,
    }


@router.post("/knowledge/cleanup/bulk-delete")
async def knowledge_cleanup_bulk_delete(body: dict):
    """ナレッジを一括削除する。
    body:
      ids: int[] — 個別指定（推奨。プレビューで確認した結果を渡す）
      または filter: {use_count_lte, not_used_for_days, older_than_days, source,
                      confirmed_by_user, exclude_obsidian} — フィルタ条件で削除
      dry_run: bool — true なら削除対象数だけ返す
    """
    ids = body.get("ids") or []
    filt = body.get("filter") or {}
    dry_run = bool(body.get("dry_run", False))

    target_ids: list[int] = []

    if ids:
        target_ids = [int(i) for i in ids]
    elif filt:
        preview = await knowledge_cleanup_preview(
            use_count_lte=int(filt.get("use_count_lte", 0)),
            not_used_for_days=filt.get("not_used_for_days"),
            older_than_days=filt.get("older_than_days"),
            source=filt.get("source"),
            confirmed_by_user=filt.get("confirmed_by_user"),
            exclude_obsidian=bool(filt.get("exclude_obsidian", True)),
            limit=10000,
        )
        target_ids = [it["id"] for it in preview["items"]]
    else:
        raise HTTPException(400, "ids または filter のどちらかが必要です")

    if not target_ids:
        return {"deleted": 0, "ids": [], "dry_run": dry_run}

    if dry_run:
        return {"would_delete": len(target_ids), "ids": target_ids[:50], "dry_run": True}

    # 削除実行（MD も削除）
    deleted = 0
    md_failures: list[str] = []
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # md_path 取得
        placeholders = ",".join(["?"] * len(target_ids))
        rows = await db.execute_fetchall(
            f"SELECT id, md_path FROM knowledge_base WHERE id IN ({placeholders})",
            target_ids,
        )
        md_paths = [dict(r).get("md_path") for r in rows]

        await db.execute(
            f"DELETE FROM knowledge_base WHERE id IN ({placeholders})", target_ids,
        )
        await db.commit()
        deleted = len(target_ids)

    # Obsidian MD 削除（除外フィルタが効いてれば対象なしのはずだが念のため）
    from pathlib import Path as _P
    for mp in md_paths:
        if not mp:
            continue
        try:
            f = _P(mp)
            if f.exists() and "Obsidian/ENGINE-BASE/" not in str(f):
                f.unlink()
        except Exception as e:
            md_failures.append(f"{mp}: {e}")

    return {
        "deleted": deleted,
        "ids": target_ids,
        "md_deletion_failures": md_failures,
        "dry_run": False,
    }


# ── S-8: 実行ログ ──────────────────────────────────────────────────────────

@router.get("/logs")
async def list_execution_logs(
    skill_name: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
):
    conditions = []
    params = []
    if skill_name:
        conditions.append("skill_name = ?")
        params.append(skill_name)
    if status:
        conditions.append("status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            f"SELECT * FROM execution_log {where} ORDER BY started_at DESC LIMIT ?",
            [*params, limit],
        )
    return [dict(r) for r in rows]


# ── communication_log（インボックス） ─────────────────────────────────────

@router.get("/inbox")
async def list_inbox(
    channel: Optional[str] = None,
    importance: Optional[str] = None,
    status: Optional[str] = "unread",
    limit: int = 50,
):
    conditions = []
    params = []
    if channel:
        conditions.append("channel = ?")
        params.append(channel)
    if importance:
        conditions.append("importance = ?")
        params.append(importance)
    if status:
        conditions.append("status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            f"SELECT * FROM communication_log {where} ORDER BY received_at DESC LIMIT ?",
            [*params, limit],
        )
    return [dict(r) for r in rows]
