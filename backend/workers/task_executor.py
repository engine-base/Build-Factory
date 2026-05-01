"""
task_executor.py — タスク自動実行ワーカー

approval_worker と同じくAPSchedulerから10秒ごとに呼ばれる。
pending タスクを検出 → 担当社員のスキルで実行 → 結果を保存。

実行フロー:
  1. 依存関係解決（depends_on の全タスクが completed か）
  2. 担当社員のスキル特定（task.skill_name または primary_skill）
  3. skill_runner で実行
  4. action_type が承認必要系なら approval_queue へ
  5. それ以外は tasks.result に直接保存
  6. Obsidian の 04_AI社員フィードバック/ にもMD保存
  7. 失敗時はリトライ（最大3回・指数バックオフ）

並列処理: 1サイクルで複数タスクを asyncio.gather で並列実行。
"""

import asyncio
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from db import async_db as aiosqlite

import os
DB_PATH      = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"
# Obsidian vault 配下にフィードバックを書くが、未設定なら repo 内 data/feedback へ
_default_vault = Path(__file__).resolve().parents[2] / "data" / "obsidian"
_vault = Path(os.environ.get("OBSIDIAN_VAULT_PATH") or _default_vault)
FEEDBACK_DIR = _vault / "04_AI社員フィードバック"

# 承認必須の action_type
APPROVAL_REQUIRED_KEYWORDS = (
    "email_send", "post", "invoice_send", "contract_action",
    "send", "publish", "submit",
)

MAX_RETRIES = 3


async def process_pending_tasks() -> None:
    """APScheduler から10秒ごとに呼ばれるメインエントリ。"""
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT * FROM tasks
               WHERE status='pending'
                 AND assigned_to IS NOT NULL
                 AND (next_retry_at IS NULL OR next_retry_at <= ?)
               ORDER BY id LIMIT 5""",
            (now_str,)
        )

    if not rows:
        return

    # 各タスクを並列実行（最大5並列）
    await asyncio.gather(*[_execute_task(dict(r)) for r in rows])


async def execute_task_now(task_id: int) -> None:
    """
    秘書チャットからタスク作成直後に即時呼び出される。
    ポーリングを待たずに実行を開始する。
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT * FROM tasks WHERE id=? AND status='pending'", (task_id,)
        )
    if rows:
        await _execute_task(dict(rows[0]))


async def _execute_task(task: dict) -> None:
    task_id = task["id"]

    # 1. 依存関係チェック
    if not await _dependencies_satisfied(task):
        return  # 依存待ち

    # 2. 担当社員情報を取得
    assignee_id = task["assigned_to"]
    if not assignee_id:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        emp_rows = await db.execute_fetchall(
            "SELECT employee_name, display_name, primary_skill FROM ai_employee_config WHERE id=?",
            (assignee_id,)
        )
        if not emp_rows:
            await _mark_failed(task_id, "担当社員が見つかりません")
            return
        emp = dict(emp_rows[0])

    skill_name = task.get("skill_name") or emp["primary_skill"]
    if not skill_name:
        await _mark_failed(task_id, "実行スキルが特定できません")
        return

    # 3. 状態を実行中に
    await _update_status(task_id, "in_progress", started=True)

    # 4. 依存タスクの結果を input に含める
    enriched_input = await _build_input_with_deps(task)

    # 5. skill_runner で実行
    print(f"[task_executor] 実行開始 #{task_id} ({emp['display_name']} / {skill_name})")
    try:
        from integrations.skill_runner import invoke_skill
        result = await invoke_skill(
            skill_name, enriched_input,
            triggered_by="task_executor",
            trigger_id=task_id,
        )
    except Exception as e:
        await _handle_failure(task_id, task.get("retry_count", 0), str(e))
        return

    # 6. 結果を保存
    await _save_result(task_id, result)

    # 7. 承認が必要なアクションかどうか判定
    action_type = (task.get("title", "") + " " + skill_name).lower()
    needs_approval = any(kw in action_type for kw in APPROVAL_REQUIRED_KEYWORDS)

    # スキル名から推定（メール系/SNS系/請求書系など）
    if any(kw in skill_name for kw in ["email", "sns", "invoice", "post", "press", "contract"]):
        needs_approval = True

    # 8. 承認キューに積む or 完了
    if needs_approval:
        await _push_to_approval(task, result, skill_name)
        await _update_status(task_id, "review_needed", completed=True)
    else:
        await _update_status(task_id, "completed", completed=True)

    # 9. Obsidian にフィードバック書き戻し
    await _write_feedback(task, emp, skill_name, result)

    # 10. 秘書チャットに「タスク完了カード」を投入
    await _post_task_completion_card(task, emp, skill_name, result, needs_approval)

    # 11. Slack通知（成功）
    try:
        from integrations.slack_client import send_completion_notification
        await send_completion_notification(
            f"タスク #{task_id} 完了 ({emp['display_name']})",
            f"{task['title']}\n結果: {result[:200]}"
        )
    except Exception:
        pass

    print(f"[task_executor] 完了 #{task_id}")


async def _post_task_completion_card(
    task: dict, emp: dict, skill: str, result: str, needs_approval: bool
) -> None:
    """秘書チャットの conversation_log に特殊フォーマットの完了カードを投入する。
    フロント側がこの system メッセージを検出して TaskCompletionCard を描画する。"""
    try:
        card_payload = json.dumps({
            "type": "task_completed",
            "task_id": task["id"],
            "title": task["title"],
            "assignee": emp["display_name"],
            "skill": skill,
            "result_preview": result[:1500],
            "needs_approval": needs_approval,
            "completed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }, ensure_ascii=False)

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO conversation_log
                   (channel, with_employee, role, message, task_id)
                   VALUES ('web_secretary', 1, 'system', ?, ?)""",
                (card_payload, task["id"])
            )
            await db.commit()
    except Exception as e:
        print(f"[task_executor] 完了カード投入失敗: {e}")


# ── ヘルパー ──────────────────────────────────────────────────────────

async def _dependencies_satisfied(task: dict) -> bool:
    """depends_on の全タスクが completed か確認。"""
    deps_str = task.get("depends_on") or "[]"
    try:
        deps = json.loads(deps_str) if isinstance(deps_str, str) else deps_str
    except Exception:
        deps = []
    if not deps:
        return True

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        placeholders = ",".join("?" * len(deps))
        rows = await db.execute_fetchall(
            f"SELECT id, status FROM tasks WHERE id IN ({placeholders})",
            deps
        )
    statuses = {r["id"]: r["status"] for r in rows}
    return all(statuses.get(d) in ("completed", "review_needed") for d in deps)


async def _build_input_with_deps(task: dict) -> str:
    """依存タスクの結果を input の冒頭に含めて文字列化する。"""
    base = (
        f"# タスク\n{task['title']}\n\n"
        f"# 詳細\n{task.get('description') or '（詳細なし）'}\n"
    )
    deps_str = task.get("depends_on") or "[]"
    try:
        deps = json.loads(deps_str) if isinstance(deps_str, str) else deps_str
    except Exception:
        deps = []
    if not deps:
        return base

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        placeholders = ",".join("?" * len(deps))
        rows = await db.execute_fetchall(
            f"SELECT id, title, result FROM tasks WHERE id IN ({placeholders})",
            deps
        )
    if not rows:
        return base

    base += "\n# 前段タスクの結果（参照してください）\n"
    for r in rows:
        result_snip = (r["result"] or "")[:1500]
        base += f"\n## ステップ #{r['id']} {r['title']}\n{result_snip}\n"
    return base


async def _update_status(task_id: int, status: str, started: bool = False, completed: bool = False) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        sets = ["status=?"]
        params: list = [status]
        if started:
            sets.append("started_at=datetime('now','localtime')")
        if completed:
            sets.append("completed_at=datetime('now','localtime')")
        await db.execute(
            f"UPDATE tasks SET {', '.join(sets)} WHERE id=?",
            (*params, task_id)
        )
        await db.commit()


async def _save_result(task_id: int, result: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE tasks SET result=? WHERE id=?",
            (result[:10000], task_id)
        )
        await db.commit()


async def _handle_failure(task_id: int, retry_count: int, error: str) -> None:
    """失敗時のリトライ処理。"""
    new_count = retry_count + 1
    if new_count >= MAX_RETRIES:
        await _mark_failed(task_id, error)
        # Slack通知
        try:
            from integrations.slack_client import send_error_notification
            await send_error_notification(f"task #{task_id}", f"3回試行後失敗: {error}")
        except Exception:
            pass
    else:
        # 指数バックオフ: 30秒 → 1分 → 2分
        delay = 30 * (2 ** retry_count)
        next_at = (datetime.now() + timedelta(seconds=delay)).strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """UPDATE tasks SET status='pending', retry_count=?,
                   last_error=?, next_retry_at=? WHERE id=?""",
                (new_count, error[:500], next_at, task_id)
            )
            await db.commit()
        print(f"[task_executor] リトライ予約 #{task_id} ({new_count}/{MAX_RETRIES}) → {next_at}")


async def _mark_failed(task_id: int, error: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE tasks SET status='failed', last_error=?,
               completed_at=datetime('now','localtime') WHERE id=?""",
            (error[:500], task_id)
        )
        await db.commit()


async def _push_to_approval(task: dict, result: str, skill_name: str) -> None:
    """承認が必要な成果物を approval_queue に積む。"""
    expires_at = (datetime.now() + timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")
    metadata = {"task_id": task["id"], "skill": skill_name}
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO approval_queue
               (action_type, title, content, source_skill,
                source_execution_id, metadata, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                f"task_result",
                task["title"][:80],
                result[:5000],
                skill_name,
                task["id"],
                json.dumps(metadata, ensure_ascii=False),
                expires_at,
            )
        )
        await db.commit()


async def _write_feedback(task: dict, emp: dict, skill: str, result: str) -> None:
    """Obsidian の 04_AI社員フィードバック/{年月}/{社員カテゴリ}/ にMDで書き戻す。"""
    try:
        # 月別フォルダ（2026-04 形式）
        month_str = datetime.now().strftime("%Y-%m")
        # 社員カテゴリでサブフォルダ（01_営業, 02_経理など）
        category = emp.get("category") or "00_総括"
        # カテゴリのスペース・スラッシュをサニタイズ
        safe_category = re.sub(r'[/\\:*?"<>|]', "_", category)

        target_dir = FEEDBACK_DIR / month_str / safe_category
        target_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{ts}-task{task['id']}-{emp['employee_name']}.md"
        path = target_dir / filename
        content = (
            f"---\n"
            f"task_id: {task['id']}\n"
            f"assignee: {emp['display_name']}\n"
            f"skill: {skill}\n"
            f"completed_at: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"---\n\n"
            f"# タスク #{task['id']}: {task['title']}\n\n"
            f"- 担当: **{emp['display_name']}**\n"
            f"- 使用スキル: `{skill}`\n"
            f"- 元依頼: {task.get('description') or ''}\n\n"
            f"## 成果物\n\n{result}\n"
        )
        path.write_text(content, encoding="utf-8")
    except Exception as e:
        print(f"[task_executor] Obsidian書き戻し失敗: {e}")
