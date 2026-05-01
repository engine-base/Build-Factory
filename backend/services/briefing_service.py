"""
briefing_service.py — 朝ブリーフィング用データ収集

pipeline / approval_queue / task_schedule / communication_log を
asyncio.gather で並列取得し、secretary SKILL.md への入力テキストを生成する。
各データソースの取得失敗は個別にスキップ（部分失敗OK）。
"""

import asyncio
from datetime import date
from pathlib import Path

from db import async_db as aiosqlite

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"


async def gather_briefing_context() -> str:
    """
    全データソースを並列取得して secretary への入力コンテキストを生成する。

    Returns:
        DATE:/PIPELINE:/PENDING_APPROVALS:/TODAY_TASKS:/UNREAD_MESSAGES:/GOALS: 形式のテキスト
    """
    today = date.today().strftime("%Y-%m-%d")

    pipeline, approvals, tasks, messages = await asyncio.gather(
        _get_pipeline_summary(),
        _get_pending_approvals(),
        _get_today_tasks(),
        _get_unread_messages(),
        return_exceptions=True,
    )

    # 例外はそのセクションを「取得失敗」に置き換える
    def safe(val, fallback: str) -> str:
        return fallback if isinstance(val, Exception) else str(val)

    return (
        f"DATE: {today}\n"
        f"PIPELINE: {safe(pipeline, '取得失敗')}\n"
        f"PENDING_APPROVALS: {safe(approvals, '取得失敗')}\n"
        f"TODAY_TASKS: {safe(tasks, '取得失敗')}\n"
        f"UNREAD_MESSAGES: {safe(messages, '取得失敗')}\n"
        f"GOALS: 目標進捗データなし（okrテーブル未連携）"
    )


async def _get_pipeline_summary() -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT client, project, stage, amount, next_action_date
               FROM pipeline
               WHERE stage NOT IN ('won', 'lost', '成約', '失注', 'closed')
               ORDER BY next_action_date ASC
               LIMIT 10"""
        )
    if not rows:
        return "アクティブな案件なし"
    lines = []
    for r in rows:
        amount = f"¥{int(r['amount']):,}" if r['amount'] else "金額未設定"
        name = r['client'] or r['project'] or "不明"
        lines.append(
            f"- {name} [{r['stage']}] {amount} "
            f"次回:{r['next_action_date'] or '未設定'}"
        )
    return "\n".join(lines)


async def _get_pending_approvals() -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT id, title, action_type, expires_at
               FROM approval_queue
               WHERE status = 'pending'
               ORDER BY created_at ASC"""
        )
    if not rows:
        return "承認待ちなし"
    lines = [
        f"[{r['id']}] {r['title']} ({r['action_type']}) 期限:{r['expires_at']}"
        for r in rows
    ]
    return "\n".join(lines)


async def _get_today_tasks() -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT task_name, run_time, frequency
               FROM task_schedule
               WHERE is_active = 1 AND frequency = 'daily'
               ORDER BY run_time ASC"""
        )
    if not rows:
        return "本日の定型タスクなし"
    return "\n".join([f"{r['run_time']} {r['task_name']}" for r in rows])


async def _get_unread_messages() -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT channel, sender_name, subject, importance
               FROM communication_log
               WHERE status = 'unread' AND importance IN ('high', 'medium')
               ORDER BY importance DESC, received_at DESC
               LIMIT 10"""
        )
    if not rows:
        return "重要メッセージなし"
    lines = [
        f"[{r['importance'].upper()}] {r['channel']} / {r['sender_name']}: {r['subject']}"
        for r in rows
    ]
    return "\n".join(lines)
