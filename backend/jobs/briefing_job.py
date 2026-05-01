"""
briefing_job.py — 朝ブリーフィング定時実行ジョブ

APScheduler から毎朝 08:00 に呼ばれる。
1. データ収集 → 2. secretary で生成 → 3. MDファイル保存 → 4. Slack通知
Slack失敗時は5分後にリトライ（最大2回）。
"""

import asyncio
from datetime import date
from pathlib import Path

RECORDS_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "records"
    / "13_セルフマネジメント" / "briefings"
)


async def run_morning_briefing() -> None:
    """朝ブリーフィングのメインエントリ。APScheduler から呼び出す。"""
    from services.briefing_service import gather_briefing_context
    from integrations.skill_runner import invoke_skill
    from integrations.slack_client import send_completion_notification, send_error_notification

    try:
        # 1. データ収集
        context = await gather_briefing_context()
        print(f"[briefing] データ収集完了")

        # 2. secretary で生成
        result = await invoke_skill(
            "secretary",
            context,
            provider="ollama",
            model="qwen2.5:7b",
            triggered_by="scheduler",
        )
        print(f"[briefing] 生成完了 ({len(result)} 文字)")

        # 3. MDファイル保存
        RECORDS_PATH.mkdir(parents=True, exist_ok=True)
        today_str = date.today().strftime("%Y%m%d")
        out_path = RECORDS_PATH / f"BRIEF-{today_str}.md"
        out_path.write_text(result, encoding="utf-8")
        print(f"[briefing] 保存完了: {out_path}")

        # 4. Slack通知（失敗してもリトライ）
        await _notify_with_retry(result, today_str)

    except Exception as e:
        print(f"[briefing] エラー: {e}")
        from integrations.slack_client import send_error_notification
        await send_error_notification("secretary/briefing", str(e))
        raise


async def _notify_with_retry(result: str, today_str: str, max_retries: int = 2) -> None:
    """Slack通知を失敗時にリトライする（最大2回・5分間隔）。"""
    from integrations.slack_client import send_completion_notification

    for attempt in range(max_retries + 1):
        try:
            await send_completion_notification(
                f"朝ブリーフィング {today_str[:4]}/{today_str[4:6]}/{today_str[6:]}",
                result[:400],
            )
            return
        except Exception as e:
            if attempt < max_retries:
                print(f"[briefing] Slack通知失敗 (attempt {attempt+1}): {e} — 5分後リトライ")
                await asyncio.sleep(300)
            else:
                print(f"[briefing] Slack通知リトライ上限到達: {e}")
