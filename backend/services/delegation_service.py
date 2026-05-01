"""
delegation_service.py — 秘書→社員AI 委任ロジック

まさとから自然言語で依頼を受けたとき:
1. 秘書AI に「どのスキルを呼ぶか」を判定させる
2. 該当スキルを skill_runner で実行
3. 結果を approval_queue に積む or 直接返す
"""

import json
import re
from pathlib import Path
from typing import Optional

import aiosqlite

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"

# 秘書AIに「ルーティング判定」をさせるためのメタプロンプト
ROUTING_PROMPT = """以下のユーザーからの依頼に対して、最適なスキルを1つ選び、
JSON形式で返してください。コードブロックや説明文は不要です。

利用可能なスキル（一部抜粋。SKILL.md のルーティング表を参照）:
- invoice-create: 請求書作成
- sales-email: 営業メール・フォローメール
- cashflow-forecast: キャッシュフロー予測
- expense-management: 経費管理・経費仕分け
- sns-management: SNS投稿
- email-marketing: メルマガ
- proposal: 提案書作成
- contract-review: 契約書チェック
- weekly-review: 週次レビュー
- monthly-review: 月次レビュー
- kpi-dashboard: KPI確認
- pl-management: PL確認
- support-response: CS返信
- competitive-analysis: 競合調査
- meeting-minutes: 議事録
- briefing: 全体ブリーフィング（自分で対応する場合）
- chat: 通常会話・雑談・質問への回答（特定スキル不要な場合）

出力形式（JSONのみ）:
{
  "skill": "skill-name",
  "reason": "なぜこのスキルを選んだか（30字以内）",
  "needs_approval": true/false,
  "input_for_skill": "そのスキルに渡す指示文",
  "missing_info": ["不足情報があれば列挙、なければ空配列"]
}

needs_approval の判定:
- 外部送信（メール送信・SNS投稿）/ 重要判断（請求書発行・契約） → true
- 調査・分析・社内保存のみ → false

ユーザーからの依頼:
"""


# 「単一スキルで足りるか / マルチエージェントが要るか / 雑談か」を秘書に判定させるメタプロンプト
MODE_DETECT_PROMPT = """以下のユーザー依頼に対して、最適な処理モードを判定してJSONで返してください。

判定モード:
- "single":  特定の1スキルで処理できる依頼（請求書作成・経費まとめ・営業メール等）
- "multi":   複数スキルが連携する必要がある依頼（提案書作成で市場調査+競合分析+価格設計が必要等）
- "chat":   雑談・質問・相談・確認・返答を伴う対話（特定スキル不要・秘書本人が答える）
- "missing": 情報不足で処理できない（「○○について」だが対象不明等）

出力（JSONのみ・コードブロック不要）:
{
  "mode": "single|multi|chat|missing",
  "reason": "判定理由（30字以内）",
  "missing_info": ["不足情報があれば列挙、なければ空配列"]
}

ユーザー依頼:
"""


async def _detect_mode(user_request: str) -> dict:
    """秘書AIに処理モードを判定させる。"""
    try:
        from integrations.skill_runner import invoke_skill
        prompt = MODE_DETECT_PROMPT + user_request
        response = await invoke_skill(
            "secretary", prompt,
            provider="ollama", model="qwen2.5:7b",
            triggered_by="user"
        )
        m = re.search(r'\{.*?\}', response, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception as e:
        print(f"[delegation] モード判定失敗: {e}")
    return {"mode": "single", "reason": "判定失敗・単一で試行"}


async def delegate(user_request: str, channel_say=None) -> dict:
    """
    まさとからの自然言語依頼をルーティングして実行する。
    秘書AIが「単一/マルチ/雑談/情報不足」を動的判定してから処理する。
    """
    say = channel_say if channel_say else _print_say

    # ステップ0: 処理モードを秘書AIに動的判定させる
    mode_judge = await _detect_mode(user_request)
    mode = mode_judge.get("mode", "single")
    print(f"[delegation] mode={mode} reason={mode_judge.get('reason','')}")

    # 情報不足
    if mode == "missing":
        missing = mode_judge.get("missing_info", [])
        if missing:
            await say("以下の情報が必要です:\n" + "\n".join(f"・{m}" for m in missing))
            return {"status": "needs_info", "missing": missing}

    # 雑談・対話 → 秘書がそのまま答える
    if mode == "chat":
        from integrations.skill_runner import invoke_skill
        result = await invoke_skill("secretary", user_request, triggered_by="user")
        await say(result[:1500])
        return {"status": "executed", "mode": "chat", "skill": "secretary", "result": result}

    # マルチエージェント → ワークフロー実行
    if mode == "multi":
        try:
            from services.workflow_service import run_workflow
            wf_result = await run_workflow(user_request, channel_say=say)
            if wf_result.get("status") == "completed":
                return {
                    "status": "delegated",
                    "mode": "multi_agent",
                    "workflow_id": wf_result.get("workflow_id"),
                    "approval_id": wf_result.get("approval_id"),
                }
            await say("→ 単一スキルで再試行します")
        except Exception as e:
            print(f"[delegation] workflow失敗、単一スキルで再試行: {e}")

    # 単一スキル: 秘書にルーティング判定させる
    routing = await _ask_secretary_routing(user_request)
    if not routing:
        await say("⚠️ ルーティング判定に失敗しました")
        return {"status": "error", "error": "routing_failed"}

    skill = routing.get("skill", "")
    reason = routing.get("reason", "")
    needs_approval = bool(routing.get("needs_approval", True))
    skill_input = routing.get("input_for_skill", user_request)
    missing = routing.get("missing_info", [])

    # ステップ2: 不足情報があれば確認
    if missing:
        msg = f"以下の情報が必要です：\n"
        msg += "\n".join([f"・{m}" for m in missing])
        await say(msg)
        return {"status": "needs_info", "missing": missing, "skill": skill}

    # ステップ3: 通常会話・雑談 → 秘書がそのまま返答
    if skill in ("chat", "briefing", ""):
        from integrations.skill_runner import invoke_skill
        result = await invoke_skill("secretary", user_request, triggered_by="user")
        await say(result[:1500])
        return {"status": "executed", "skill": "secretary", "result": result}

    # ステップ4: 該当スキルを実行
    await say(f"📌 `{skill}` で対応します（理由: {reason}）")

    try:
        from integrations.skill_runner import invoke_skill
        result = await invoke_skill(skill, skill_input, triggered_by="user")
    except FileNotFoundError:
        await say(f"⚠️ スキル `{skill}` が見つかりません。秘書で対応します。")
        result = await invoke_skill("secretary", user_request, triggered_by="user")
        await say(result[:1500])
        return {"status": "executed", "skill": "secretary", "result": result}
    except Exception as e:
        await say(f"❌ 実行エラー: {e}")
        return {"status": "error", "error": str(e)}

    # ステップ5: 承認が必要 → approval_queue へ
    if needs_approval:
        approval_id = await _create_approval(skill, user_request, result)
        await say(
            f"✅ 下書き完成 → 承認キューに追加（#{approval_id}）\n"
            f"確認後 `承認 {approval_id}` で実行されます"
        )
        return {
            "status": "delegated",
            "skill": skill,
            "approval_id": approval_id,
            "result": result,
        }

    # ステップ6: 承認不要 → そのまま結果を返す
    await say(f"✅ 完了\n```\n{result[:1500]}\n```")
    return {"status": "executed", "skill": skill, "result": result}


async def _ask_secretary_routing(user_request: str) -> Optional[dict]:
    """秘書AIにルーティング判定をさせる。"""
    try:
        from integrations.skill_runner import invoke_skill
        prompt = ROUTING_PROMPT + user_request
        response = await invoke_skill(
            "secretary", prompt,
            provider="ollama", model="qwen2.5:7b",
            triggered_by="user"
        )
        # JSON 抽出
        m = re.search(r'\{.*?\}', response, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception as e:
        print(f"[delegation] ルーティング失敗: {e}")
    return None


async def _create_approval(skill: str, request: str, result: str) -> int:
    """承認キューに項目を追加して ID を返す。"""
    from datetime import datetime, timedelta

    # action_type をスキルから推定
    action_type_map = {
        "invoice-create":   "invoice_send",
        "sales-email":      "email_send",
        "email-marketing":  "email_send",
        "sns-management":   "post",
        "proposal":         "report_save",
        "support-response": "email_send",
    }
    action_type = action_type_map.get(skill, "report_save")
    expires_at = (datetime.now() + timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")

    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO approval_queue
               (action_type, title, content, source_skill, expires_at)
               VALUES (?, ?, ?, ?, ?)""",
            (action_type, request[:80], result, skill, expires_at)
        )
        await db.commit()
        return cursor.lastrowid


async def _print_say(msg: str):
    print(f"[delegation] {msg}")
