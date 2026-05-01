"""
sales_service.py — 01_営業AI サービス層

フォローメール生成・パイプライン分析などの営業AI業務を担当。
01_sales SKILL.md を invoke_skill() 経由で呼び出し、
結果を approval_queue に追加して Slack 通知する。
"""

import json
import re
from pathlib import Path

import aiosqlite

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"
RECORDS_PATH = Path(__file__).resolve().parents[2] / "data" / "records"


async def generate_follow_email(pipeline_id: int) -> int:
    """
    指定の pipeline 案件のフォローメールドラフトを生成し approval_queue に追加する。

    Args:
        pipeline_id: pipeline.id

    Returns:
        approval_id: 作成された approval_queue レコードの id
    """
    from integrations.skill_runner import invoke_skill
    from integrations.slack_client import send_approval_notification

    # 1. 案件情報取得
    pipeline, contact = await _get_pipeline_and_contact(pipeline_id)
    if not pipeline:
        raise ValueError(f"pipeline_id={pipeline_id} が見つかりません")

    # 2. ナレッジ取得（confirmed_by_user=1 のみ）
    knowledge_text = await _get_sales_knowledge()

    # 3. 01_sales へのプロンプト組み立て
    prompt = _build_prompt(pipeline, contact, knowledge_text)

    # 4. スキル実行
    result = await invoke_skill(
        "01_sales",
        prompt,
        provider="ollama",
        model="qwen2.5:7b",
        triggered_by="user",
    )

    # 5. JSON 抽出（スキルは JSON を返す設計）
    draft = _extract_json(result)
    if not draft:
        # JSON が取れない場合はテキストをそのまま使う
        draft = {
            "action": "email_draft",
            "to": contact.get("email", "") if contact else "",
            "subject": f"【フォロー】{pipeline.get('client', '')} 様",
            "body": result,
            "notes": "JSON形式での出力が得られなかったため、テキストをそのまま使用しています",
        }

    # 6. approval_queue に追加
    approval_id = await _add_to_approval_queue(pipeline, draft)

    # 7. Slack 通知（未接続なら print のみ）
    await send_approval_notification(
        approval_id,
        f"フォローメール: {pipeline.get('client', '案件')} 様",
        draft.get("body", "")[:200],
    )

    return approval_id


async def get_pipeline_summary() -> dict:
    """
    パイプラインのサマリーを生成して返す（ブリーフィング・API用）。
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT id, client, project, stage, amount, probability,
                      next_action_date, last_contact, notes
               FROM pipeline
               WHERE stage NOT IN ('won', 'lost', '成約', '失注', 'closed')
               ORDER BY next_action_date ASC"""
        )

    items = [dict(r) for r in rows]

    # フォロー必要案件（next_action_date が今日以前）
    from datetime import date
    today = date.today().isoformat()
    follow_required = [
        p for p in items
        if p.get("next_action_date") and p["next_action_date"] <= today
    ]

    # 加重合計
    total_weighted = sum(
        (p.get("amount") or 0) * (p.get("probability") or 0) / 100
        for p in items
    )

    return {
        "total_active": len(items),
        "total_weighted_value": int(total_weighted),
        "follow_required": follow_required,
        "all_items": items,
    }


# ── プライベートヘルパー ──────────────────────────────────────────────────

async def _get_pipeline_and_contact(pipeline_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        pipelines = await db.execute_fetchall(
            "SELECT * FROM pipeline WHERE id=?", (pipeline_id,)
        )
        if not pipelines:
            return None, None
        pipeline = dict(pipelines[0])

        # contacts テーブルから会社名で検索
        client_name = pipeline.get("client", "")
        contacts = await db.execute_fetchall(
            "SELECT * FROM contacts WHERE company LIKE ? LIMIT 1",
            (f"%{client_name}%",),
        )
        contact = dict(contacts[0]) if contacts else {}

    return pipeline, contact


async def _get_sales_knowledge() -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT title, summary
               FROM knowledge_base
               WHERE (tags LIKE '%01_営業%' OR tags LIKE '%共通%')
               AND confirmed_by_user = 1
               ORDER BY use_count DESC
               LIMIT 5"""
        )
    if not rows:
        return "参照ナレッジなし"
    return "\n".join([f"- {r['title']}: {r['summary']}" for r in rows])


def _build_prompt(pipeline: dict, contact: dict, knowledge: str) -> str:
    return (
        f"COMPANY: {pipeline.get('client', '不明')}\n"
        f"CONTACT: {contact.get('name', '担当者不明')}\n"
        f"EMAIL: {contact.get('email', '不明')}\n"
        f"STAGE: {pipeline.get('stage', '不明')}\n"
        f"LAST_CONTACT: {pipeline.get('last_contact', '不明')}\n"
        f"AMOUNT: {pipeline.get('amount', '不明')}\n"
        f"NOTES: {pipeline.get('notes', 'なし')}\n"
        f"KNOWLEDGE: {knowledge}"
    )


def _extract_json(text: str) -> dict | None:
    """LLM出力からJSONブロックを抽出する。"""
    # ```json ... ``` または { ... } を探す
    patterns = [
        r"```json\s*([\s\S]*?)\s*```",
        r"```\s*([\s\S]*?)\s*```",
        r"(\{[\s\S]*\})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
    return None


async def _add_to_approval_queue(pipeline: dict, draft: dict) -> int:
    from datetime import datetime, timedelta
    expires_at = (datetime.now() + timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")
    metadata = {
        "to": draft.get("to", ""),
        "subject": draft.get("subject", ""),
        "pipeline_id": pipeline.get("id"),
        "client": pipeline.get("client", ""),
        "notes": draft.get("notes", ""),
    }
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO approval_queue
               (action_type, title, content, metadata, source_skill, expires_at)
               VALUES ('email_send', ?, ?, ?, '01_sales', ?)""",
            (
                f"フォローメール: {pipeline.get('client', '')} 様",
                draft.get("body", ""),
                json.dumps(metadata, ensure_ascii=False),
                expires_at,
            ),
        )
        await db.commit()
        return cursor.lastrowid
