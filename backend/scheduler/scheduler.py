"""
scheduler.py — APScheduler 管理モジュール

FastAPI の lifespan に統合する AsyncIOScheduler。
task_schedule テーブルを読み込んでジョブを動的登録する。
"""

from pathlib import Path
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from db import async_db as aiosqlite

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"

scheduler = AsyncIOScheduler(timezone="Asia/Tokyo")


async def load_jobs_from_db() -> None:
    """task_schedule テーブルのアクティブなジョブをスケジューラーに登録する"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT * FROM task_schedule WHERE is_active = 1"
        )
    for row in rows:
        _register_job(dict(row))

    # 朝ブリーフィング専用ジョブ（毎朝 08:00）
    from jobs.briefing_job import run_morning_briefing
    scheduler.add_job(
        run_morning_briefing,
        CronTrigger(hour=8, minute=0, timezone="Asia/Tokyo"),
        id="morning_briefing",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # 統合インボックスチェック（朝8時・昼12時・夕18時）
    from services.inbox_service import run_inbox_check
    for hour, job_id in [(8, "inbox_morning"), (12, "inbox_noon"), (18, "inbox_evening")]:
        scheduler.add_job(
            run_inbox_check,
            CronTrigger(hour=hour, minute=5, timezone="Asia/Tokyo"),
            id=job_id,
            replace_existing=True,
            misfire_grace_time=3600,
        )

    # Obsidian Vault 同期（5分ごと）
    from services.obsidian_sync import run_obsidian_sync
    scheduler.add_job(
        run_obsidian_sync,
        "interval",
        minutes=5,
        id="obsidian_sync",
        replace_existing=True,
    )

    total_jobs = len(scheduler.get_jobs())
    print(f"[scheduler] 登録完了 — 合計 {total_jobs} ジョブ（タスク{len(rows)}件 + ブリーフィング + インボックス×3 + Obsidian同期）")


def _register_job(task: dict) -> None:
    """task_schedule レコードを APScheduler ジョブとして登録する"""
    job_id = f"task_{task['id']}"

    # 既存ジョブは上書き
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    freq = task["frequency"]
    run_time = task["run_time"]  # "HH:MM"
    try:
        hour, minute = run_time.split(":")
    except ValueError:
        print(f"[scheduler] 不正な run_time: {run_time} (task_id={task['id']})")
        return

    if freq == "daily":
        trigger = CronTrigger(
            hour=int(hour), minute=int(minute), timezone="Asia/Tokyo"
        )
    elif freq == "weekly":
        day = task.get("day_of_week") or "monday"
        trigger = CronTrigger(
            day_of_week=day, hour=int(hour), minute=int(minute), timezone="Asia/Tokyo"
        )
    elif freq == "monthly":
        dom = task.get("day_of_month") or 1
        trigger = CronTrigger(
            day=dom, hour=int(hour), minute=int(minute), timezone="Asia/Tokyo"
        )
    else:
        print(f"[scheduler] 不明な frequency: {freq} (task_id={task['id']})")
        return

    scheduler.add_job(
        _run_skill_job,
        trigger=trigger,
        id=job_id,
        args=[task],
        replace_existing=True,
        misfire_grace_time=3600,  # 1時間以内の遅延は実行する
    )


async def _run_skill_job(task: dict) -> None:
    """スケジューラーから呼ばれるジョブ実行関数"""
    from integrations.skill_runner import invoke_skill
    skill_name = task["skill_name"]
    task_name = task["task_name"]
    print(f"[scheduler] 実行開始: {task_name} ({skill_name})")

    try:
        user_input = task.get("params") or f"{task_name}を実行してください"
        await invoke_skill(
            skill_name=skill_name,
            user_input=user_input,
            triggered_by="scheduler",
            trigger_id=task["id"],
        )
        # last_run_at を更新
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE task_schedule SET last_run_at=datetime('now','localtime') WHERE id=?",
                (task["id"],)
            )
            await db.commit()
        print(f"[scheduler] 完了: {task_name}")

    except Exception as e:
        print(f"[scheduler] 失敗: {task_name} — {e}")
        # T5-03 実装後に Slack エラー通知を追加


async def reload_jobs() -> None:
    """task_schedule テーブルの変更をスケジューラーに反映する（動的更新用）"""
    # 既存の task_ プレフィックスジョブをすべて削除
    for job in scheduler.get_jobs():
        if job.id.startswith("task_"):
            scheduler.remove_job(job.id)
    await load_jobs_from_db()
