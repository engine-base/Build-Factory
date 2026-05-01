"""
inbox_service.py — 統合インボックス（重要度判定 + communication_log 保存）

朝昼晩3回 APScheduler から呼ばれる。
1. Gmail から未読取得
2. secretary AI で重要度判定（high/medium/low）
3. communication_log に保存（重複スキップ）
4. high/medium のみ Slack 通知
"""

import json
import re
from pathlib import Path

from db import async_db as aiosqlite

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"


async def run_inbox_check() -> dict:
    """
    統合インボックスチェックのメインエントリ。
    APScheduler から呼ばれる（朝8時・昼12時・夕18時）。

    Returns:
        {"checked": N, "high": N, "medium": N, "low": N}
    """
    from integrations.gmail_client import get_unread_messages
    from integrations.skill_runner import invoke_skill
    from integrations.slack_client import send_completion_notification

    # 1. Gmail 未読取得
    messages = get_unread_messages(max_results=20)
    if not messages:
        print("[inbox] 未読メールなし")
        return {"checked": 0, "high": 0, "medium": 0, "low": 0}

    # 2. 重複除外（既に communication_log に存在するものをスキップ）
    new_messages = await _filter_new_messages(messages)
    if not new_messages:
        print(f"[inbox] {len(messages)}件取得 → すべて処理済み")
        return {"checked": len(messages), "high": 0, "medium": 0, "low": 0}

    # 3. secretary AI で重要度判定
    judgments = await _judge_importance(new_messages, invoke_skill)

    # 4. communication_log に保存
    saved = await _save_to_log(new_messages, judgments)

    # 5. high/medium のみ集計して Slack 通知
    high = [j for j in judgments if j.get("importance") == "high"]
    medium = [j for j in judgments if j.get("importance") == "medium"]

    if high or medium:
        summary_lines = []
        for j in high + medium:
            idx = j["index"] - 1
            if 0 <= idx < len(new_messages):
                msg = new_messages[idx]
                label = "🔴 高" if j["importance"] == "high" else "🟡 中"
                summary_lines.append(f"{label} {msg['sender_name']}: {msg['subject']}")
        summary = "\n".join(summary_lines[:10])
        await send_completion_notification(
            f"インボックスチェック完了（重要 {len(high)+len(medium)}件）",
            summary,
        )

    result = {
        "checked": len(new_messages),
        "high": len(high),
        "medium": len(medium),
        "low": len([j for j in judgments if j.get("importance") == "low"]),
    }
    print(f"[inbox] 完了: {result}")
    return result


async def _filter_new_messages(messages: list[dict]) -> list[dict]:
    """communication_log に external_id が既存のメッセージを除外する。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        existing = await db.execute_fetchall(
            "SELECT external_id FROM communication_log WHERE channel='gmail'"
        )
    existing_ids = {r["external_id"] for r in existing}
    return [m for m in messages if m["external_id"] not in existing_ids]


async def _judge_importance(
    messages: list[dict], invoke_skill
) -> list[dict]:
    """secretary に重要度判定を依頼して JSON リストを返す。"""
    msg_text = "\n".join([
        f"[{i+1}] 件名:{m['subject']} 送信者:{m['sender_name']} 内容:{m['snippet'][:100]}"
        for i, m in enumerate(messages)
    ])
    prompt = (
        "以下のメールの重要度を判定してください。\n"
        "各メールに high/medium/low のいずれかを付けてJSON配列で返してください。\n"
        "形式: [{\"index\":1,\"importance\":\"high\",\"reason\":\"理由\"},...]"
        f"\n\nメール一覧:\n{msg_text}"
    )

    try:
        result_text = await invoke_skill(
            "secretary", prompt, provider="ollama", model="qwen2.5:7b",
            triggered_by="scheduler"
        )
        # JSON 抽出
        json_match = re.search(r'\[.*\]', result_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except Exception as e:
        print(f"[inbox] 重要度判定エラー: {e}")

    # フォールバック: すべて low
    return [{"index": i+1, "importance": "low", "reason": "判定失敗"} for i in range(len(messages))]


async def _save_to_log(messages: list[dict], judgments: list[dict]) -> int:
    """communication_log に保存して保存件数を返す。"""
    judgment_map = {j["index"]: j for j in judgments}
    saved = 0

    async with aiosqlite.connect(DB_PATH) as db:
        for i, msg in enumerate(messages, start=1):
            j = judgment_map.get(i, {"importance": "low"})
            try:
                await db.execute(
                    """INSERT OR IGNORE INTO communication_log
                       (channel, direction, sender_name, sender_id,
                        subject, body_summary, importance, status, external_id, received_at)
                       VALUES ('gmail','inbound',?,?,?,?,?,  'unread',?,?)""",
                    (
                        msg["sender_name"],
                        msg["sender_email"],
                        msg["subject"],
                        msg["snippet"][:500],
                        j.get("importance", "low"),
                        msg["external_id"],
                        msg["received_at"],
                    ),
                )
                saved += 1
            except Exception as e:
                print(f"[inbox] 保存エラー: {e}")
        await db.commit()

    return saved
