"""
tasks.py — プロジェクト・タスク階層・質問チケット API
"""

import json
from pathlib import Path
from typing import Optional

from db import async_db as aiosqlite
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"

router = APIRouter(prefix="/api", tags=["tasks"])


# ── プロジェクト ─────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    title: str
    description: Optional[str] = None
    goal: Optional[str] = None


@router.get("/projects")
async def list_projects(status: Optional[str] = None, limit: int = 50):
    cond = "WHERE status=?" if status else ""
    params = [status] if status else []
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            f"""SELECT p.*,
                       (SELECT COUNT(*) FROM tasks WHERE project_id=p.id) AS task_count,
                       (SELECT COUNT(*) FROM tasks WHERE project_id=p.id AND status='completed') AS done_count
                FROM projects p {cond}
                ORDER BY created_at DESC LIMIT ?""",
            (*params, limit)
        )
    return [dict(r) for r in rows]


@router.post("/projects")
async def create_project(body: ProjectCreate):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO projects (title, description, goal)
               VALUES (?, ?, ?) RETURNING id""",
            (body.title, body.description, body.goal)
        )
        _row = await cursor.fetchone()
        await db.commit()
    return {"id": _row["id"]}


@router.get("/projects/{project_id}")
async def get_project_detail(project_id: int):
    """プロジェクト詳細＋全タスクの階層ツリーを返す。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        proj_rows = await db.execute_fetchall(
            "SELECT * FROM projects WHERE id=?", (project_id,)
        )
        if not proj_rows:
            raise HTTPException(404)
        task_rows = await db.execute_fetchall(
            """SELECT t.*, e.display_name as assignee_name
               FROM tasks t
               LEFT JOIN ai_employee_config e ON e.id=t.assigned_to
               WHERE t.project_id=?
               ORDER BY t.parent_task_id NULLS FIRST, t.order_index, t.id""",
            (project_id,)
        )
    return {"project": dict(proj_rows[0]), "tasks": [dict(t) for t in task_rows]}


# ── タスク ──────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    project_id:     Optional[int] = None
    parent_task_id: Optional[int] = None
    title:          str
    description:    Optional[str] = None
    assigned_to:    Optional[int] = None
    skill_name:     Optional[str] = None
    depends_on:     Optional[list[int]] = None


@router.get("/tasks")
async def list_tasks(
    status:      Optional[str] = None,
    assigned_to: Optional[int] = None,
    project_id:  Optional[int] = None,
    limit:       int = 100,
):
    conditions, params = [], []
    if status:      conditions.append("t.status=?");      params.append(status)
    if assigned_to: conditions.append("t.assigned_to=?"); params.append(assigned_to)
    if project_id:  conditions.append("t.project_id=?");  params.append(project_id)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            f"""SELECT t.*, e.display_name as assignee_name
                FROM tasks t
                LEFT JOIN ai_employee_config e ON e.id=t.assigned_to
                {where}
                ORDER BY t.created_at DESC LIMIT ?""",
            (*params, limit)
        )
    return [dict(r) for r in rows]


@router.post("/tasks")
async def create_task(body: TaskCreate):
    async with aiosqlite.connect(DB_PATH) as db:
        # 親タスクのレベルから自分のレベルを決定
        level = 0
        if body.parent_task_id:
            db.row_factory = aiosqlite.Row
            parents = await db.execute_fetchall(
                "SELECT level, project_id FROM tasks WHERE id=?",
                (body.parent_task_id,)
            )
            if parents:
                level = (parents[0]["level"] or 0) + 1
                if not body.project_id:
                    body.project_id = parents[0]["project_id"]

        cursor = await db.execute(
            """INSERT INTO tasks
               (project_id, parent_task_id, title, description,
                assigned_to, skill_name, depends_on, level)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
            (
                body.project_id, body.parent_task_id, body.title, body.description,
                body.assigned_to, body.skill_name,
                json.dumps(body.depends_on or []), level
            )
        )
        _row = await cursor.fetchone()
        await db.commit()
    return {"id": _row["id"], "level": level}


@router.get("/tasks/{task_id}")
async def get_task(task_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT t.*, e.display_name as assignee_name
               FROM tasks t
               LEFT JOIN ai_employee_config e ON e.id=t.assigned_to
               WHERE t.id=?""", (task_id,)
        )
        if not rows:
            raise HTTPException(404)
        children = await db.execute_fetchall(
            """SELECT t.*, e.display_name as assignee_name
               FROM tasks t
               LEFT JOIN ai_employee_config e ON e.id=t.assigned_to
               WHERE t.parent_task_id=? ORDER BY order_index, id""",
            (task_id,)
        )
        questions = await db.execute_fetchall(
            "SELECT * FROM task_questions WHERE task_id=? ORDER BY created_at",
            (task_id,)
        )
    return {
        "task":      dict(rows[0]),
        "children":  [dict(c) for c in children],
        "questions": [dict(q) for q in questions],
    }


class TaskUpdate(BaseModel):
    status:         Optional[str] = None
    result:         Optional[str] = None
    assigned_to:    Optional[int] = None
    parent_task_id: Optional[int] = None
    title:          Optional[str] = None
    description:    Optional[str] = None
    skill_name:     Optional[str] = None


@router.patch("/tasks/{task_id}")
async def update_task(task_id: int, body: TaskUpdate):
    updates, params = [], []
    if body.status:
        updates.append("status=?"); params.append(body.status)
        if body.status == "in_progress":
            updates.append("started_at=NOW()")
        elif body.status in ("completed", "failed"):
            updates.append("completed_at=NOW()")
    if body.result is not None:
        updates.append("result=?"); params.append(body.result)
    if body.assigned_to is not None:
        updates.append("assigned_to=?"); params.append(body.assigned_to)
    if body.parent_task_id is not None:
        # 0 / null で親解除
        new_parent = body.parent_task_id if body.parent_task_id > 0 else None
        updates.append("parent_task_id=?"); params.append(new_parent)
        # 親のレベル + 1 に再計算
        if new_parent is not None:
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                rows = await db.execute_fetchall(
                    "SELECT level FROM tasks WHERE id=?", (new_parent,)
                )
                if rows:
                    updates.append("level=?"); params.append((rows[0]["level"] or 0) + 1)
        else:
            updates.append("level=?"); params.append(0)
    if body.title is not None:
        updates.append("title=?"); params.append(body.title)
    if body.description is not None:
        updates.append("description=?"); params.append(body.description)
    if body.skill_name is not None:
        updates.append("skill_name=?"); params.append(body.skill_name)

    if not updates:
        raise HTTPException(400)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE tasks SET {', '.join(updates)} WHERE id=?",
            (*params, task_id)
        )
        await db.commit()
    return {"status": "updated"}


# ── 質問チケット ─────────────────────────────────────────────────────

class QuestionCreate(BaseModel):
    task_id:   int
    asked_by:  Optional[int] = None
    ask_to:    str  # "secretary" | "user"
    question:  str


@router.post("/questions")
async def create_question(body: QuestionCreate):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO task_questions
               (task_id, asked_by, ask_to, question)
               VALUES (?, ?, ?, ?) RETURNING id""",
            (body.task_id, body.asked_by, body.ask_to, body.question)
        )
        _row = await cursor.fetchone()
        await db.execute(
            "UPDATE tasks SET status='blocked_question' WHERE id=?",
            (body.task_id,)
        )
        await db.commit()
    return {"id": _row["id"]}


class QuestionAnswer(BaseModel):
    answer: str


@router.patch("/questions/{question_id}")
async def answer_question(question_id: int, body: QuestionAnswer):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT task_id FROM task_questions WHERE id=?", (question_id,)
        )
        if not rows:
            raise HTTPException(404)
        await db.execute(
            """UPDATE task_questions SET answer=?, status='answered',
               answered_at=datetime('now','localtime') WHERE id=?""",
            (body.answer, question_id)
        )
        # 質問が解決したらタスクを進行中に戻す
        await db.execute(
            "UPDATE tasks SET status='in_progress' WHERE id=?",
            (rows[0]["task_id"],)
        )
        await db.commit()
    return {"status": "answered"}


@router.get("/questions/pending")
async def pending_questions():
    """未回答の質問チケット一覧。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT q.*, t.title as task_title, e.display_name as asker_name
               FROM task_questions q
               LEFT JOIN tasks t ON t.id=q.task_id
               LEFT JOIN ai_employee_config e ON e.id=q.asked_by
               WHERE q.status='pending'
               ORDER BY q.created_at"""
        )
    return [dict(r) for r in rows]


# ── Claude Code 引き継ぎ用 spec bundle ────────────────────────────────

def _extract_acceptance_criteria(description: Optional[str]) -> list[str]:
    if not description:
        return []
    out: list[str] = []
    in_ac = False
    for raw in description.splitlines():
        line = raw.strip()
        low = line.lower()
        is_header = (
            "受入条件" in line
            or "受け入れ条件" in line
            or low.startswith("acceptance criteria")
            or low.startswith("ac:")
            or low in ("ac", "## ac", "# ac")
        )
        if is_header:
            in_ac = True
            continue
        if in_ac:
            if line.startswith("##") or line == "":
                if out:
                    break
                continue
            if line.startswith(("-", "*", "•")):
                out.append(line.lstrip("-*• ").strip())
    return out


@router.get("/tasks/{task_id}/handoff")
async def get_task_handoff(task_id: int):
    """
    Claude Code MCP 引き継ぎ用の完全な spec bundle を返す。
    Drawer の `引き継ぎ` タブと bf_get_spec が同じ shape を共有。
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        task_rows = await db.execute_fetchall(
            """SELECT t.*, e.display_name as assignee_name
               FROM tasks t
               LEFT JOIN ai_employee_config e ON e.id=t.assigned_to
               WHERE t.id=?""",
            (task_id,),
        )
        if not task_rows:
            raise HTTPException(404, "task not found")
        task = dict(task_rows[0])

        # 親プロジェクト
        project: dict = {}
        if task.get("project_id"):
            proj_rows = await db.execute_fetchall(
                "SELECT * FROM projects WHERE id=?", (task["project_id"],)
            )
            if proj_rows:
                project = dict(proj_rows[0])

        # 兄弟タスク (同じ parent を持つ)
        siblings = []
        if task.get("parent_task_id"):
            sib_rows = await db.execute_fetchall(
                """SELECT id, title, status, skill_name
                   FROM tasks
                   WHERE parent_task_id=? AND id<>?
                   ORDER BY order_index, id""",
                (task["parent_task_id"], task_id),
            )
            siblings = [dict(r) for r in sib_rows]

        # 子タスク
        child_rows = await db.execute_fetchall(
            """SELECT id, title, status, skill_name
               FROM tasks WHERE parent_task_id=? ORDER BY order_index, id""",
            (task_id,),
        )
        children = [dict(r) for r in child_rows]

        # workspace 連携: project_meta 経由 or 名前一致
        workspace: dict = {}
        ws_rows = await db.execute_fetchall(
            """SELECT id, name, description, design_system_ref
               FROM workspaces
               WHERE name=? LIMIT 1""",
            (project.get("title", ""),),
        )
        if ws_rows:
            workspace = dict(ws_rows[0])

        # 関連 artifact (workspace 紐付け)
        artifacts: list[dict] = []
        if workspace.get("id"):
            art_rows = await db.execute_fetchall(
                """SELECT id, type, title, category_tags, created_at
                   FROM artifacts
                   WHERE workspace_id=? AND is_archived=0
                   ORDER BY updated_at DESC LIMIT 10""",
                (workspace["id"],),
            )
            artifacts = [dict(r) for r in art_rows]

        # design_system_ref 経由で DESIGN.md
        design_md = ""
        ds_ref = workspace.get("design_system_ref")
        if ds_ref:
            ds_path = (
                Path(__file__).resolve().parents[2]
                / "data" / "design-systems" / ds_ref / "DESIGN.md"
            )
            if ds_path.exists():
                design_md = ds_path.read_text(encoding="utf-8", errors="ignore")[:8000]

    acceptance = _extract_acceptance_criteria(task.get("description"))

    return {
        "task": task,
        "project": project,
        "workspace": {
            "id": workspace.get("id"),
            "name": workspace.get("name"),
            "design_system_ref": ds_ref,
        },
        "design_md_excerpt": design_md,
        "related_artifacts": artifacts,
        "related_skills": [{"name": task["skill_name"]}] if task.get("skill_name") else [],
        "acceptance_criteria": acceptance,
        "siblings": siblings,
        "children": children,
    }
