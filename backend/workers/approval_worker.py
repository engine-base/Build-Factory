"""
approval_worker.py — 承認キュー実行ワーカー

APScheduler から 10 秒ごとに呼ばれ、
approval_queue の status='approved' レコードを検出してアクションを実行する。
"""

import json
from pathlib import Path
from datetime import datetime

from db import async_db as aiosqlite

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"
RECORDS_PATH = Path(__file__).resolve().parents[2] / "data" / "records"


async def process_approved_items() -> None:
    """APScheduler から定期呼び出しされるメインエントリ"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT * FROM approval_queue WHERE status = 'approved'"
        )

    for row in rows:
        item = dict(row)
        try:
            await _execute_action(item)
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE approval_queue SET status='done', resolved_at=datetime('now','localtime') WHERE id=?",
                    (item["id"],)
                )
                await db.commit()
            # 承認済みパターンをナレッジに蓄積
            await _save_approved_pattern(item)
            print(f"[worker] 完了 id={item['id']} ({item['action_type']}): {item['title']}")

        except Exception as e:
            print(f"[worker] 失敗 id={item['id']}: {e}")
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE approval_queue SET status='failed' WHERE id=?",
                    (item["id"],)
                )
                await db.commit()


async def _execute_action(item: dict) -> None:
    """action_type に応じて実際のアクションを実行する"""
    action = item["action_type"]
    meta = json.loads(item["metadata"]) if item.get("metadata") else {}

    if action == "report_save":
        await _action_report_save(item, meta)

    elif action == "email_send":
        await _action_email_send(item, meta)

    elif action == "db_update":
        await _action_db_update(meta)

    elif action == "post":
        # Slack/Discord 投稿 — T5-01 実装後に接続
        print(f"[worker] post: Slack未接続のためスキップ — {item['title']}")

    else:
        print(f"[worker] 未知の action_type: {action}")


async def _action_email_send(item: dict, meta: dict) -> None:
    """Gmail でメール送信する（approval_queue 承認後のみ）"""
    from integrations.gmail_client import send_email, is_configured
    to = meta.get("to", "")
    subject = meta.get("subject", item["title"])
    body = item["content"]

    if not to:
        print(f"[worker] email_send: 送信先が未設定 — {item['title']}")
        return

    if not is_configured():
        print(f"[worker] email_send: Gmail 未設定のためスキップ — to={to}")
        return

    success = send_email(to, subject, body)
    if success:
        # pipeline.last_contact を更新（pipeline_id がある場合）
        pipeline_id = meta.get("pipeline_id")
        if pipeline_id:
            from datetime import date
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE pipeline SET last_contact=? WHERE id=?",
                    (date.today().isoformat(), pipeline_id),
                )
                await db.commit()
            print(f"[worker] pipeline.last_contact 更新: id={pipeline_id}")

        # Slack 完了通知
        from integrations.slack_client import send_completion_notification
        await send_completion_notification(f"メール送信完了: {subject}", f"宛先: {to}")
    else:
        raise RuntimeError(f"Gmail 送信失敗: to={to} subject={subject}")


async def _action_report_save(item: dict, meta: dict) -> None:
    """records/ にMarkdownファイルを保存する"""
    category = meta.get("category", "99_その他")
    filename = meta.get("filename") or f"REPORT-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
    out_path = RECORDS_PATH / category / filename
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(item["content"], encoding="utf-8")
    print(f"[worker] 保存完了: {out_path}")


async def _save_approved_pattern(item: dict) -> None:
    """
    承認・修正されたアウトプットを knowledge_base に保存する。
    秘書AIによる自動分類（カテゴリ・知識タイプ・重要度）を経由する。
    """
    try:
        from services.knowledge_curator import classify_and_save

        source_skill = item.get("source_skill") or "secretary"
        content = item.get("content", "")[:3000]
        revision_memo = item.get("revision_memo") or ""

        memo_for_curator = None
        if revision_memo:
            # 修正指示があった場合はメモとして渡す
            memo_for_curator = f"修正指示: {revision_memo}"

        result = await classify_and_save(
            content=content,
            masato_memo=memo_for_curator,
            source_skill=source_skill,
            source="approval",
            source_id=item["id"],
            full_content=True,
        )
        print(f"[worker] ナレッジ蓄積: {result.get('category')}/{result.get('knowledge_type')} — {result.get('title','')[:40]}")
    except Exception as e:
        print(f"[worker] ナレッジ蓄積失敗: {e}")


async def _action_db_update(meta: dict) -> None:
    """指定テーブルの指定レコードを更新する"""
    table = meta.get("table")
    updates = meta.get("updates", {})
    where_id = meta.get("id")
    if not (table and updates and where_id):
        print(f"[worker] db_update: 必要なパラメータが不足 — {meta}")
        return
    # テーブル名をホワイトリスト検証（SQL インジェクション対策）
    allowed_tables = {
        "pipeline", "contacts", "task_schedule", "approval_queue",
        "ai_employee_config", "knowledge_base"
    }
    if table not in allowed_tables:
        raise ValueError(f"許可されていないテーブル: {table}")
    set_clause = ", ".join([f"{k}=?" for k in updates.keys()])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE {table} SET {set_clause} WHERE id=?",
            (*updates.values(), where_id),
        )
        await db.commit()
    print(f"[worker] db_update 完了: {table} id={where_id}")
