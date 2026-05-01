"""
employees.py — AI社員API（拡張版）

各社員の保有スキル一覧・直接対話・タスク受領などを担当。
"""

import json
from pathlib import Path
from typing import Optional

import aiosqlite
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"

router = APIRouter(prefix="/api/employees", tags=["employees"])


@router.get("")
async def list_employees():
    """社員一覧（保有スキル数・現在のステータス付き）。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT e.*,
                    (SELECT COUNT(*) FROM ai_employee_skills WHERE employee_id=e.id) AS skill_count,
                    (SELECT COUNT(*) FROM tasks WHERE assigned_to=e.id AND status='in_progress') AS active_tasks
               FROM ai_employee_config e
               WHERE e.is_active=1 ORDER BY e.id"""
        )
    return [dict(r) for r in rows]


@router.get("/{employee_id}")
async def get_employee(employee_id: int):
    """社員の詳細情報（保有スキル・最近の実行ログ・現在のタスク含む）。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        emp_rows = await db.execute_fetchall(
            "SELECT * FROM ai_employee_config WHERE id=?", (employee_id,)
        )
        if not emp_rows:
            raise HTTPException(404, "employee not found")
        emp = dict(emp_rows[0])

        # 保有スキル
        skill_rows = await db.execute_fetchall(
            """SELECT s.id, s.skill_name, s.display_name, s.description,
                      s.category, aes.is_primary
               FROM ai_employee_skills aes
               JOIN skill_definitions s ON s.id=aes.skill_id
               WHERE aes.employee_id=?
               ORDER BY aes.is_primary DESC, s.skill_name""",
            (employee_id,)
        )

        # 現在のタスク
        task_rows = await db.execute_fetchall(
            """SELECT id, title, status, created_at FROM tasks
               WHERE assigned_to=? AND status NOT IN ('completed','failed','cancelled')
               ORDER BY created_at DESC LIMIT 10""",
            (employee_id,)
        )

        # 直近の実行ログ
        log_rows = await db.execute_fetchall(
            """SELECT id, skill_name, status, started_at, duration_sec
               FROM execution_log WHERE skill_name IN
                 (SELECT s.skill_name FROM ai_employee_skills aes
                  JOIN skill_definitions s ON s.id=aes.skill_id
                  WHERE aes.employee_id=?)
               ORDER BY started_at DESC LIMIT 10""",
            (employee_id,)
        )

    return {
        "employee": emp,
        "skills":   [dict(s) for s in skill_rows],
        "tasks":    [dict(t) for t in task_rows],
        "recent_logs": [dict(l) for l in log_rows],
    }


class AddSkillBody(BaseModel):
    skill_id:   int
    is_primary: bool = False


@router.post("/{employee_id}/skills")
async def add_skill(employee_id: int, body: AddSkillBody):
    """社員にスキルを追加する。"""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                """INSERT INTO ai_employee_skills (employee_id, skill_id, is_primary)
                   VALUES (?, ?, ?)""",
                (employee_id, body.skill_id, 1 if body.is_primary else 0)
            )
            await db.commit()
        except Exception as e:
            if "UNIQUE" in str(e):
                raise HTTPException(409, "既に保有しているスキルです")
            raise
    return {"status": "added"}


@router.delete("/{employee_id}/skills/{skill_id}")
async def remove_skill(employee_id: int, skill_id: int):
    """社員からスキルを外す。"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM ai_employee_skills WHERE employee_id=? AND skill_id=?",
            (employee_id, skill_id)
        )
        await db.commit()
    return {"status": "removed"}


class ChatBody(BaseModel):
    message:    str
    task_id:    Optional[int] = None
    provider:   Optional[str] = "ollama"
    model:      Optional[str] = "qwen2.5:7b"


@router.post("/{employee_id}/chat")
async def chat_with_employee(employee_id: int, body: ChatBody):
    """
    特定の社員（秘書 / リーダー / メンバー）と直接対話する。
    個性プロンプト + スコープ付きナレッジを注入して応答する。
    会話は1スレッド継続・ホップなし・要約なしで認識ズレを防ぐ。
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        emp_rows = await db.execute_fetchall(
            "SELECT * FROM ai_employee_config WHERE id=?", (employee_id,)
        )
        if not emp_rows:
            raise HTTPException(404, "employee not found")
        emp = dict(emp_rows[0])

        if emp.get("retired_at"):
            raise HTTPException(410, "この社員は退職済みです")

        # ユーザー発言を保存
        await db.execute(
            """INSERT INTO conversation_log
               (channel, with_employee, role, message, task_id)
               VALUES ('web', ?, 'user', ?, ?)""",
            (employee_id, body.message, body.task_id)
        )
        await db.commit()

    primary_skill = emp.get("primary_skill") or "secretary"

    # 直近履歴を message list で取得
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        hist_rows = await db.execute_fetchall(
            "SELECT role, message FROM conversation_log "
            "WHERE with_employee=? AND channel='web' "
            "ORDER BY created_at DESC LIMIT 12",
            (employee_id,),
        )
    history = [
        {"role": r["role"], "content": r["message"]}
        for r in reversed(list(hist_rows))
        if r["role"] in ("user", "assistant")
    ]
    # 直前にINSERTした user メッセージ自身を除く
    if history and history[-1]["role"] == "user" and history[-1]["content"] == body.message:
        history = history[:-1]

    try:
        # Agent経由（persona + tools + scope + 履歴を message list で）
        from ai_agents.secretary_agent import build_agent_for_employee, _build_message_list
        from agents import Runner

        provider = body.provider or emp.get("llm_provider") or "ollama"
        model = body.model or emp.get("llm_model") or "qwen2.5:7b"
        agent = build_agent_for_employee(emp, provider=provider, model=model)
        input_items = _build_message_list(history, body.message)
        result = await Runner.run(agent, input_items, max_turns=8)
        reply = str(result.final_output or "")

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO conversation_log
                   (channel, with_employee, role, message, task_id)
                   VALUES ('web', ?, 'assistant', ?, ?)""",
                (employee_id, reply[:5000], body.task_id)
            )
            await db.commit()

        return {
            "reply": reply,
            "skill_used": primary_skill,
            "persona": {
                "name": emp.get("persona_name"),
                "avatar": emp.get("avatar_emoji"),
                "role_level": emp.get("role_level"),
            },
        }
    except Exception as e:
        raise HTTPException(500, f"実行エラー: {e}")


@router.get("/{employee_id}/conversation")
async def get_conversation(employee_id: int, limit: int = 50):
    """社員との会話履歴を取得する。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT id, role, message, task_id, created_at
               FROM conversation_log
               WHERE with_employee=?
               ORDER BY created_at DESC LIMIT ?""",
            (employee_id, limit)
        )
    return list(reversed([dict(r) for r in rows]))
