"""
slack_client.py — Slack Bolt Socket Mode 統合

- Socket Mode で公開URL不要で Slack と双方向通信
- 環境変数未設定の場合は起動をスキップ（他機能への影響なし）
- T5-01: セットアップ / T5-02: 受信→approval更新 / T5-03: 通知送信
"""

import os
import re
import asyncio
from pathlib import Path
from typing import Optional

import aiosqlite

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"

# Slack アプリインスタンス（環境変数がある場合のみ初期化）
_app = None
_handler = None
_slack_enabled = False


def _init_app():
    """SLACK_BOT_TOKEN が設定されている場合のみ App を初期化する"""
    global _app, _slack_enabled
    bot_token = os.environ.get("SLACK_BOT_TOKEN")
    if not bot_token:
        return
    try:
        from slack_bolt.async_app import AsyncApp
        _app = AsyncApp(token=bot_token)
        _slack_enabled = True
        _register_handlers()
    except Exception as e:
        print(f"[slack] App 初期化失敗: {e}")


async def start_slack() -> None:
    """FastAPI lifespan 起動時に呼ぶ。SLACK_APP_TOKEN が未設定なら何もしない。"""
    global _handler

    _init_app()
    if not _slack_enabled:
        print("[slack] SLACK_BOT_TOKEN 未設定 — Slack 連携をスキップ")
        return

    app_token = os.environ.get("SLACK_APP_TOKEN")
    if not app_token:
        print("[slack] SLACK_APP_TOKEN 未設定 — Socket Mode をスキップ")
        return

    try:
        from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
        _handler = AsyncSocketModeHandler(_app, app_token)
        await _handler.connect_async()
        result = await _app.client.auth_test()
        print(f"[slack] ✅ Connected — bot: {result.get('bot_id')} / user: {result.get('user')}")

        # 起動時キャッチアップ: PCがオフラインだった間のメッセージを取得して処理
        import asyncio as _asyncio
        _asyncio.create_task(_catchup_unprocessed_messages())
    except Exception as e:
        print(f"[slack] Socket Mode 接続失敗: {e}")


async def stop_slack() -> None:
    """FastAPI lifespan 終了時に呼ぶ。"""
    global _handler
    if _handler:
        try:
            await _handler.close_async()
            print("[slack] Socket Mode 切断")
        except Exception:
            pass
        _handler = None


# ── T5-03: 通知送信ユーティリティ ────────────────────────────────────────

CHANNEL = os.environ.get("SLACK_CHANNEL_ID", "#build-factory-ai")


async def send_approval_notification(
    approval_id: int, title: str, preview: str
) -> Optional[str]:
    """
    承認待ち通知を Slack に投稿し slack_ts を返す。
    Slack 未接続の場合は None を返す（エラーは出さない）。
    """
    if not _slack_enabled or not _app:
        print(f"[slack] (未接続) 承認待ち通知スキップ: [{approval_id}] {title}")
        return None
    try:
        result = await _app.client.chat_postMessage(
            channel=CHANNEL,
            text=f"*【確認待ち #{approval_id}】* {title}",
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"*【確認待ち #{approval_id}】* {title}\n"
                            f"> {preview[:200]}"
                        ),
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"`承認 {approval_id}` で承認 ／ "
                            f"`却下 {approval_id}` で却下 ／ "
                            f"`修正 {approval_id}: 内容` で修正依頼"
                        ),
                    },
                },
            ],
        )
        slack_ts = result.get("ts")
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE approval_queue SET slack_ts=?, channel_notified='slack' WHERE id=?",
                (slack_ts, approval_id),
            )
            await db.commit()
        return slack_ts
    except Exception as e:
        print(f"[slack] 承認通知送信失敗: {e}")
        return None


async def _catchup_unprocessed_messages() -> None:
    """
    起動時にPCがオフラインだった間のSlackメッセージを取得して処理する。
    最後に処理したタイムスタンプ以降のメッセージを順次処理。
    """
    if not _slack_enabled or not _app:
        return
    try:
        # 最後に処理したtsを取得
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT MAX(ts) as last_ts FROM slack_processed_messages"
            )
            last_ts = (dict(rows[0]).get("last_ts") if rows else None) or "0"

        # 設定チャンネルの履歴を取得
        result = await _app.client.conversations_history(
            channel=CHANNEL,
            oldest=last_ts,
            limit=20,
        )
        messages = result.get("messages", [])
        # 古い順に処理
        messages.sort(key=lambda m: float(m.get("ts", "0")))

        processed = 0
        for m in messages:
            if m.get("bot_id"):  # bot自身は無視
                continue
            ts = m.get("ts", "")
            if ts <= last_ts:
                continue
            text = m.get("text", "").strip()
            if not text or text.startswith("/"):
                continue
            # 処理済みマーク
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "INSERT OR IGNORE INTO slack_processed_messages (channel, ts) VALUES (?, ?)",
                    (CHANNEL, ts)
                )
                await db.commit()
            processed += 1

        if processed > 0:
            await _app.client.chat_postMessage(
                channel=CHANNEL,
                text=f"♻️ 起動時キャッチアップ: {processed}件のメッセージをスキップしました。新規メッセージは通常通り処理されます。"
            )
            print(f"[slack] catchup: {processed} messages noted")
    except Exception as e:
        print(f"[slack] catchup失敗: {e}")


async def send_completion_notification(title: str, summary: str) -> None:
    """完了通知を Slack に投稿する。"""
    if not _slack_enabled or not _app:
        print(f"[slack] (未接続) 完了通知スキップ: {title}")
        return
    try:
        await _app.client.chat_postMessage(
            channel=CHANNEL,
            text=f"✅ *完了:* {title}\n{summary[:300]}",
        )
    except Exception as e:
        print(f"[slack] 完了通知送信失敗: {e}")


async def send_rich_message(text_with_tool_ui: str, channel: Optional[str] = None) -> None:
    """
    tool-ui ブロックを含むメッセージを Slack に Block Kit 形式で投稿する。

    秘書/社員AIの応答を Slack へ流す際に使う。
    通常テキスト＋Tool-UIブロックを綺麗に変換して投稿する。
    """
    if not _slack_enabled or not _app:
        return
    try:
        from integrations.slack_block_kit import render_message_for_slack
        plain_text, blocks = render_message_for_slack(text_with_tool_ui)

        # blocks が空の場合はプレーンテキストとして送る
        if not blocks:
            await _app.client.chat_postMessage(
                channel=channel or CHANNEL,
                text=plain_text or text_with_tool_ui[:2900],
            )
            return

        # Block Kit で送る（textはfallback用に短いサマリ）
        fallback = (plain_text or text_with_tool_ui)[:200] or "AIからのメッセージ"
        await _app.client.chat_postMessage(
            channel=channel or CHANNEL,
            text=fallback,
            blocks=blocks[:50],  # Slack上限
        )
    except Exception as e:
        print(f"[slack] rich送信失敗: {e}")
        # フォールバック: プレーンテキストで再送
        try:
            await _app.client.chat_postMessage(
                channel=channel or CHANNEL,
                text=text_with_tool_ui[:2900]
            )
        except Exception:
            pass


async def send_error_notification(skill_name: str, error: str) -> None:
    """エラー通知を Slack に投稿する。"""
    if not _slack_enabled or not _app:
        print(f"[slack] (未接続) エラー通知スキップ: {skill_name} — {error}")
        return
    try:
        await _app.client.chat_postMessage(
            channel=CHANNEL,
            text=f"🔴 *エラー:* `{skill_name}`\n```{error[:400]}```",
        )
    except Exception as e:
        print(f"[slack] エラー通知送信失敗: {e}")


# ── T5-02: メッセージ受信 → approval_queue 更新 ───────────────────────────

def _register_handlers() -> None:
    """_app が初期化された後に呼ばれる。メッセージハンドラを登録する。"""

    @_app.message(re.compile(r"^(承認|approve|ok)\s+(\d+)", re.IGNORECASE))
    async def handle_approve(message, say):
        text = message.get("text", "")
        match = re.search(r"(\d+)", text)
        if not match:
            await say("承認するIDを指定してください（例: `承認 1`）")
            return
        await _update_approval(int(match.group(1)), "approved", say)

    @_app.message(re.compile(r"^(却下|reject|no)\s+(\d+)", re.IGNORECASE))
    async def handle_reject(message, say):
        text = message.get("text", "")
        match = re.search(r"(\d+)", text)
        if not match:
            await say("却下するIDを指定してください（例: `却下 1`）")
            return
        await _update_approval(int(match.group(1)), "rejected", say)

    @_app.message(re.compile(r"^修正\s+(\d+)\s*[:：](.+)", re.DOTALL))
    async def handle_revision(message, say):
        text = message.get("text", "")
        match = re.match(r"修正\s+(\d+)\s*[:：](.+)", text, re.DOTALL)
        if not match:
            return
        approval_id = int(match.group(1))
        memo = match.group(2).strip()
        await _update_approval(approval_id, "revision", say, revision_memo=memo)

    @_app.message(re.compile(r"^覚えて[:：\s](.+)", re.DOTALL))
    async def handle_learn(message, say):
        """「覚えて: ○○」でナレッジを手動追加する。"""
        text = message.get("text", "")
        match = re.match(r"^覚えて[:：\s](.+)", text, re.DOTALL)
        if not match:
            return
        content = match.group(1).strip()
        await _save_manual_knowledge(content, say)

    @_app.message(re.compile(r"^(いい感じ|good|グッド|完璧|そう|それでいい)\s*$", re.IGNORECASE))
    async def handle_good_feedback(message, say):
        """直前の出力が良かったことをナレッジに記録する。"""
        await _save_positive_signal(message.get("channel"), say)

    # @社員名 で直接対話するパターン: @経理 ○○ / @営業 ○○ / @マーケ ○○ / @CS ○○ / @秘書 ○○
    EMPLOYEE_ALIASES = {
        "秘書": 1, "秘書AI": 1, "secretary": 1,
        "営業": 2, "sales": 2,
        "経理": 6, "finance": 6, "財務": 6,
        "マーケ": 7, "マーケティング": 7, "marketing": 7,
        "CS": 8, "cs": 8, "サポート": 8, "カスタマー": 8,
    }

    @_app.message(re.compile(r"^[@＠](\S+)\s+(.+)", re.DOTALL))
    async def handle_direct_employee(message, say):
        """@経理 ○○ のような直接呼び出し。"""
        text = (message.get("text") or "").strip()
        if message.get("bot_id"):
            return
        m = re.match(r"^[@＠](\S+)\s+(.+)", text, re.DOTALL)
        if not m:
            return
        alias = m.group(1)
        request = m.group(2).strip()

        emp_id = EMPLOYEE_ALIASES.get(alias)
        if not emp_id:
            await say(f"⚠️ '{alias}' に該当する社員が見つかりません。利用可能: {', '.join(EMPLOYEE_ALIASES.keys())}")
            return

        await say(f"📨 {alias} に直接依頼します...")
        channel = message.get("channel")
        try:
            import aiohttp
            async with aiohttp.ClientSession() as sess:
                async with sess.post(
                    f"http://localhost:8000/api/employees/{emp_id}/chat",
                    json={"message": request},
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as resp:
                    data = await resp.json()
                    reply = data.get("reply", "応答なし")
            # tool-ui を含む場合は Block Kit で投稿
            if "tool-ui" in reply:
                await send_rich_message(f"💬 {alias} からの返信:\n\n{reply}", channel=channel)
            else:
                await say(f"💬 {alias} からの返信:\n{reply[:1500]}")
        except Exception as e:
            await say(f"❌ エラー: {e}")

    # 既存コマンドにマッチしないメッセージは秘書AIに委任する
    @_app.message(re.compile(r"^(?!/llm|[@＠]|承認|却下|修正|覚えて|いい感じ|good|ok|完璧|そう|それでいい|承認一覧)", re.IGNORECASE))
    async def handle_delegation(message, say):
        """まさとからの自然言語依頼を秘書AIに委任する。"""
        text = (message.get("text") or "").strip()
        if not text:
            return
        if message.get("bot_id"):
            return

        channel = message.get("channel")
        user_id = message.get("user", "")

        # ユーザーごとのLLM選択を環境変数経由でskill_runnerに渡す
        from integrations.slack_llm_session import get_user_llm
        provider, model = get_user_llm(user_id)
        os.environ["AI_LLM_OVERRIDE_PROVIDER"] = provider
        os.environ["AI_LLM_OVERRIDE_MODEL"]    = model

        try:
            # Web と同一仕様の統一経路（LangGraph + slot + RAG + skill 全部経由）
            from ai_agents.secretary_agent import run_as_employee_unified
            from services.slack_history import load_recent_history
            from routers.threads import get_or_create_thread

            # Slack channel ごとに 1 スレッドを継続利用（Web の thread と同じ概念）
            thread_id = await get_or_create_thread(
                channel=f"slack_{channel}",
                with_employee=1,        # 秘書 = id=1
                thread_id=None,
                force_new=False,
            )

            history = await load_recent_history(channel=channel, limit=10)
            agent_result = await run_as_employee_unified(
                employee_id=1,            # 秘書
                user_message=text,
                history=history,
                provider=provider,
                model=model,
                thread_id=thread_id,
                helper_provider="openai" if os.environ.get("OPENAI_API_KEY") else None,
                helper_model="gpt-4o-mini" if os.environ.get("OPENAI_API_KEY") else None,
            )
            output = (agent_result.get("output") or "").strip()
            if not output:
                output = "（応答なし）"

            if "tool-ui" in output:
                await send_rich_message(output, channel=channel)
            else:
                await say(output[:3000])

            # 履歴に保存（Slack 専用ログ + conversation_log 両方）
            try:
                from services.slack_history import save_message
                await save_message(channel, user_id, "user", text)
                await save_message(channel, "secretary", "assistant", output)
            except Exception as he:
                print(f"[slack] history保存失敗: {he}")

            # conversation_log にも保存（Web と同じテーブルに揃える・slot tracking が機能する）
            try:
                import aiosqlite
                from db.queries import DB_PATH
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute(
                        """INSERT INTO conversation_log
                           (channel, with_employee, role, message, thread_id)
                           VALUES (?, 1, 'user', ?, ?)""",
                        (f"slack_{channel}", text[:5000], thread_id),
                    )
                    await db.execute(
                        """INSERT INTO conversation_log
                           (channel, with_employee, role, message, thread_id)
                           VALUES (?, 1, 'assistant', ?, ?)""",
                        (f"slack_{channel}", output[:5000], thread_id),
                    )
                    await db.execute(
                        "UPDATE threads SET last_active_at=datetime('now','localtime') WHERE id=?",
                        (thread_id,),
                    )
                    await db.commit()
            except Exception as he:
                print(f"[slack] conversation_log 保存失敗: {he}")
        except Exception as e:
            print(f"[slack] delegation エラー: {e}")
            await say(f"⚠️ 処理中にエラーが発生しました: {e}")
        finally:
            os.environ.pop("AI_LLM_OVERRIDE_PROVIDER", None)
            os.environ.pop("AI_LLM_OVERRIDE_MODEL", None)

    # ── Block Kit ボタンインタラクション（approval-card 等）──
    @_app.action(re.compile(r"^approve_(\d+)$"))
    async def handle_button_approve(ack, body, say):
        await ack()
        m = re.match(r"^approve_(\d+)$", body["actions"][0]["action_id"])
        if m:
            await _update_approval(int(m.group(1)), "approved", say)

    @_app.action(re.compile(r"^reject_(\d+)$"))
    async def handle_button_reject(ack, body, say):
        await ack()
        m = re.match(r"^reject_(\d+)$", body["actions"][0]["action_id"])
        if m:
            await _update_approval(int(m.group(1)), "rejected", say)

    @_app.action(re.compile(r"^option_.+$"))
    async def handle_option_select(ack, body, say):
        """option-list ブロックのボタンクリック処理。"""
        await ack()
        action_id = body["actions"][0]["action_id"]
        value = body["actions"][0].get("value", "")
        user = body.get("user", {}).get("name", "user")
        await say(f"✅ {user} が選択: `{value}`")

    # /llm コマンド: LLM切替
    @_app.message(re.compile(r"^/llm(?:\s+(.+))?$"))
    async def handle_llm_cmd(message, say):
        from integrations.slack_llm_session import (
            get_user_llm, set_user_llm, reset_user_llm,
            parse_llm_command, list_available_models
        )
        text = (message.get("text") or "").strip()
        user = message.get("user", "")
        args = text[len("/llm"):].strip() if text.startswith("/llm") else ""

        if not args:
            cur_p, cur_m = get_user_llm(user)
            await say(f"🧠 現在のLLM: `{cur_p}/{cur_m}`\n\n{list_available_models()}\n\n切替: `/llm gemma3:12b` / `/llm reset`")
            return

        provider, model = parse_llm_command(args)
        if model == "reset":
            reset_user_llm(user)
            cur_p, cur_m = get_user_llm(user)
            await say(f"♻️ デフォルトに戻しました: `{cur_p}/{cur_m}`")
            return

        if not provider or not model:
            await say(f"⚠️ 形式: `/llm <モデル名>` 例: `/llm gemma3:12b`")
            return

        set_user_llm(user, provider, model)
        await say(f"✅ LLM 切替: `{provider}/{model}`（このSlackユーザー専用設定）")

    @_app.message(re.compile(r"^承認一覧$"))
    async def handle_list(message, say):
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT id, title, action_type, expires_at FROM approval_queue WHERE status='pending' ORDER BY created_at ASC"
            )
        if not rows:
            await say("✅ 承認待ちはありません")
            return
        lines = [f"*承認待ち一覧*"]
        for r in rows:
            lines.append(f"• `{r['id']}` [{r['action_type']}] {r['title']} （期限: {r['expires_at']}）")
        await say("\n".join(lines))


async def _save_manual_knowledge(content: str, say) -> None:
    """「覚えて」コマンドで手動ナレッジを secretary_knowledge に保存する。"""
    # 簡易カテゴリ判定
    if any(w in content for w in ["判断", "決め方", "基準", "優先"]):
        category = "judgment"
    elif any(w in content for w in ["トーン", "言い方", "伝え方", "口調"]):
        category = "tone"
    elif any(w in content for w in ["価値観", "大事", "重要", "嫌い", "好き"]):
        category = "value"
    else:
        category = "value"

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """INSERT INTO secretary_knowledge
                   (category, title, content, source, tags, confidence)
                   VALUES (?, ?, ?, 'slack_manual', '#手動追加', 1.0)""",
                (category, content[:60], content)
            )
            await db.commit()
        await say(f"✅ 覚えました（カテゴリ: {category}）\n> {content[:100]}")
    except Exception as e:
        await say(f"❌ 保存失敗: {e}")


async def _save_positive_signal(channel: str, say) -> None:
    """直前の肯定的フィードバックを記録する（簡易版）。"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            # 直近の execution_log を取得
            rows = await db.execute_fetchall(
                "SELECT skill_name, result_summary, completed_at FROM execution_log "
                "WHERE status='completed' ORDER BY completed_at DESC LIMIT 1"
            )
            if rows:
                row = dict(rows[0]) if hasattr(rows[0], 'keys') else {}
                skill = row.get("skill_name", "")
                summary = row.get("result_summary", "")
                await db.execute(
                    """INSERT INTO secretary_knowledge
                       (category, title, content, source, tags, confidence)
                       VALUES ('pattern', ?, ?, 'slack_feedback', ?, 1.0)""",
                    (
                        f"好評パターン: {skill}",
                        summary[:500],
                        f"#{skill}, #好評",
                    )
                )
                await db.commit()
        await say("👍 フィードバックを記録しました")
    except Exception as e:
        print(f"[slack] positive signal 保存失敗: {e}")


async def _update_approval(
    approval_id: int, status: str, say, revision_memo: str = None
) -> None:
    """approval_queue のステータスを更新する共通処理。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT * FROM approval_queue WHERE id=?", (approval_id,)
        )
        if not rows:
            await say(f"ID {approval_id} の承認待ちが見つかりません")
            return
        current = dict(rows[0])
        if current["status"] in ("approved", "rejected", "done"):
            await say(f"ID {approval_id} は既に処理済みです（{current['status']}）")
            return
        await db.execute(
            "UPDATE approval_queue SET status=?, revision_memo=?, resolved_at=datetime('now','localtime') WHERE id=?",
            (status, revision_memo, approval_id),
        )
        await db.commit()

    labels = {"approved": "✅ 承認", "rejected": "❌ 却下", "revision": "✏️ 修正依頼"}
    await say(f"{labels[status]} しました: [{approval_id}] {current['title']}")
