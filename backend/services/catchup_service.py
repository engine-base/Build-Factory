"""
catchup_service.py — キャッチアップ処理

不在中（指定時間以降）に発生したイベントを集約し、
secretary AI に要約させて Markdown で返す。

使い方:
  - API: POST /api/catchup?hours=4
  - 直接: python -m services.catchup_service
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from db import async_db as aiosqlite

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"
RECORDS_PATH = Path(__file__).resolve().parents[2] / "data" / "records" / "13_セルフマネジメント" / "catchups"


async def run_catchup(hours: int = 4) -> dict:
    """
    過去 N 時間のアクティビティを集約して要約する。

    Returns:
        {
          "summary_md": str,       # secretary が生成した要約 Markdown
          "since": str,            # 集計開始日時 (ISO)
          "counts": { ... },       # 各カテゴリの件数
          "saved_path": str | None # 保存先ファイルパス
        }
    """
    since = datetime.now() - timedelta(hours=hours)
    since_str = since.strftime("%Y-%m-%d %H:%M:%S")

    counts, context = await _gather_context(since_str)

    summary_md = await _generate_summary(context, since, hours)

    saved_path = _save_catchup(summary_md, since)

    return {
        "summary_md": summary_md,
        "since": since.isoformat(),
        "counts": counts,
        "saved_path": str(saved_path) if saved_path else None,
    }


async def _gather_context(since_str: str) -> tuple[dict, str]:
    """DB から指定日時以降のアクティビティを収集してテキストにまとめる。"""
    lines = []
    counts = {}

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # 1. 承認キュー（新規 + 処理済み）
        pending = await db.execute_fetchall(
            "SELECT id, title, source_skill, action_type, created_at FROM approval_queue "
            "WHERE created_at >= ? ORDER BY created_at DESC",
            (since_str,)
        )
        resolved = await db.execute_fetchall(
            "SELECT id, title, source_skill, status, resolved_at FROM approval_queue "
            "WHERE resolved_at >= ? AND status IN ('approved','rejected','done') ORDER BY resolved_at DESC",
            (since_str,)
        )
        counts["approval_new"] = len(pending)
        counts["approval_resolved"] = len(resolved)

        if pending:
            lines.append("## 承認待ち（新規）")
            for r in pending:
                lines.append(f"- [{r['id']}] {r['title']} ({r['source_skill']} / {r['action_type']}) {r['created_at']}")

        if resolved:
            lines.append("\n## 承認キュー処理済み")
            for r in resolved:
                lines.append(f"- [{r['id']}] {r['title']} → {r['status']} ({r['resolved_at']})")

        # 2. 受信メール（communication_log）
        emails = await db.execute_fetchall(
            "SELECT sender_name, subject, importance, received_at FROM communication_log "
            "WHERE channel='gmail' AND created_at >= ? ORDER BY received_at DESC",
            (since_str,)
        )
        counts["emails"] = len(emails)
        if emails:
            lines.append("\n## 受信メール")
            for e in emails:
                mark = {"high": "🔴", "medium": "🟡", "low": "⚪"}.get(e["importance"], "⚪")
                lines.append(f"- {mark} {e['sender_name']}: {e['subject']} ({e['received_at']})")

        # 3. 実行ログ（完了・失敗）
        exec_logs = await db.execute_fetchall(
            "SELECT skill_name, status, duration_sec, completed_at FROM execution_log "
            "WHERE completed_at >= ? ORDER BY completed_at DESC",
            (since_str,)
        )
        counts["executions"] = len(exec_logs)
        completed = [e for e in exec_logs if e["status"] == "completed"]
        failed = [e for e in exec_logs if e["status"] == "failed"]

        if exec_logs:
            lines.append("\n## AI社員実行ログ")
            if completed:
                lines.append(f"完了: {len(completed)}件")
                for e in completed[:5]:
                    lines.append(f"  ✅ {e['skill_name']} ({e['duration_sec']}秒) {e['completed_at']}")
            if failed:
                lines.append(f"失敗: {len(failed)}件")
                for e in failed:
                    lines.append(f"  ❌ {e['skill_name']} {e['completed_at']}")

        # 4. パイプライン動向
        pipeline = await db.execute_fetchall(
            "SELECT client, stage, amount, updated_at FROM pipeline "
            "WHERE updated_at >= ? ORDER BY updated_at DESC LIMIT 10",
            (since_str,)
        )
        counts["pipeline_updates"] = len(pipeline)
        if pipeline:
            lines.append("\n## パイプライン更新")
            for p in pipeline:
                lines.append(f"- {p['client']}: {p['stage']} / ¥{p['amount']:,} ({p['updated_at']})")

    context_text = "\n".join(lines) if lines else "この期間に特記すべき変動はありませんでした。"
    return counts, context_text


async def _generate_summary(context: str, since: datetime, hours: int) -> str:
    """secretary スキルで要約を生成する。失敗時はコンテキストをそのまま返す。"""
    since_label = since.strftime("%m月%d日 %H:%M")
    prompt = (
        f"## キャッチアップ要求\n"
        f"不在期間: {since_label} 以降（約{hours}時間）\n\n"
        f"## 収集データ\n{context}\n\n"
        f"## 指示\n"
        f"上記データをもとに、経営者向けのキャッチアップサマリーを日本語Markdownで生成してください。\n"
        f"以下の構成で簡潔にまとめてください:\n"
        f"1. ⚡ 即対応が必要な事項（承認待ち・エラーなど）\n"
        f"2. 📬 重要メッセージ（high/medium のメール）\n"
        f"3. ✅ 完了した処理\n"
        f"4. 📊 パイプライン動向（あれば）\n"
        f"特記事項がないセクションは「なし」と記載してください。"
    )

    try:
        from integrations.skill_runner import invoke_skill
        result = await invoke_skill(
            "secretary", prompt,
            provider="ollama", model="qwen2.5:7b",
            triggered_by="user"
        )
        header = (
            f"# キャッチアップサマリー\n"
            f"集計期間: {since.strftime('%Y年%m月%d日 %H:%M')} 以降（過去{hours}時間）\n"
            f"生成日時: {datetime.now().strftime('%Y年%m月%d日 %H:%M')}\n\n"
        )
        return header + result
    except Exception as e:
        print(f"[catchup] secretary 呼び出し失敗: {e} — コンテキストをそのまま返します")
        return (
            f"# キャッチアップサマリー（secretary 未応答）\n"
            f"集計期間: {since.strftime('%Y年%m月%d日 %H:%M')} 以降\n\n"
            + context
        )


def _save_catchup(summary_md: str, since: datetime) -> Path | None:
    """キャッチアップサマリーをファイルに保存する。"""
    try:
        RECORDS_PATH.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M")
        path = RECORDS_PATH / f"CATCHUP-{ts}.md"
        path.write_text(summary_md, encoding="utf-8")
        return path
    except Exception as e:
        print(f"[catchup] 保存失敗: {e}")
        return None
