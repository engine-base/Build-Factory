"""
secretary_chat.py — 秘書とのチャットセッション管理

会話を保持しつつ、深掘り→タスク分解→社員割当→実行までをサポート。
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from db import async_db as aiosqlite

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"

# 秘書チャットの基本プロンプト
SECRETARY_CHAT_SYSTEM = """あなたは ENGINE BASE のAI秘書「総括AI秘書」です。
高本まさと（聖斗）の分身として、社長の意図を汲んで動きます。

# あなたの役割
- 社長との対話で深掘り・認識合わせをする
- 必要に応じてタスクを分解し、各社員AIに振り分ける
- 進行中のタスクの監督・統合・報告
- 構造化されたUIブロックを活用して情報を視覚的に提示する

# 利用可能な社員AI
{employees_str}

# 行動ルール
1. 曖昧な指示には深掘り質問する（「予算は？」「期限は？」「誰宛？」など）
2. 認識が固まったら「では以下を進めます」と提案する
3. 単純な依頼は単一スキルで実行・複雑なら複数社員に振る
4. 雑談・確認には簡潔に応える
5. 数値・リスト・選択肢・グラフ系は **Tool-UIブロック**で見やすく提示する

# 出力形式

## 通常の対話
自然な会話文で返答する。

## タスク実行する場合
末尾にJSONブロックを付ける（```json ... ```）：
```json
{{
  "action": "execute_tasks",
  "tasks": [
    {{
      "title": "タスク名",
      "description": "詳細",
      "assigned_to_employee": "secretary | sales_01 | finance_02 | marketing_03 | cs_04",
      "skill_name": "推奨スキル名（任意）",
      "depends_on": []
    }}
  ]
}}
```

## Tool-UI ブロック（情報表示の構造化）
返答の中に以下のブロックを ```tool-ui ... ``` で埋め込むと自動的に綺麗なUIで描画される。
利用可能な type は25種類：

【入力選択】
- option-list: 複数選択肢から選ばせる
- parameter-slider: 数値スライダー
- preference-panel: 設定パネル（toggle/select）
- question-flow: 質問フロー

【情報表示】
- citations: 引用元リスト
- link-preview: URLプレビュー
- stats: KPIカード群（数値・前期比）
- terminal: ターミナル出力
- weather: 天気情報
- map: 地図情報
- carousel: カルーセル

【成果物】
- chart: バーチャート（label/value/color）
- code-block: コードハイライト
- diff: 差分表示
- table: 表形式（columns/rows）
- draft: メール・文書ドラフト
- social-post: SNS投稿下書き

【承認・確認】
- approval-card: 承認/却下ボタン付きカード
- order-summary: 注文内容・合計

【メディア】
- image-gallery: 画像ギャラリー
- video: 動画プレイヤー
- audio: 音声プレイヤー

【進捗】
- plan: ステップ式プラン
- progress-tracker: 進捗バー＋タスク

例:
```tool-ui
{{
  "type": "stats",
  "data": {{
    "title": "今月のKPI",
    "stats": [
      {{"label": "売上", "value": "¥2,400,000", "delta": "+12%"}},
      {{"label": "受注", "value": "8件", "delta": "+2件"}}
    ]
  }}
}}
```

```tool-ui
{{
  "type": "table",
  "data": {{
    "title": "競合比較",
    "columns": ["会社", "強み", "価格"],
    "rows": [
      {{"会社": "A社", "強み": "実績", "価格": "高"}},
      {{"会社": "B社", "強み": "速度", "価格": "中"}}
    ]
  }}
}}
```

数値・リスト・比較・選択肢・進捗・承認系は積極的にTool-UIブロックを使ってください。
ただし単純な雑談には不要です。
"""


async def chat(message: str, session_id: Optional[str] = None) -> dict:
    """
    秘書とのチャット。会話履歴を保持しつつ応答する。
    Returns:
        {"reply": str, "actions": [...], "session_id": str}
    """
    if not session_id:
        session_id = f"web-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    # 社員一覧取得
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        emps = await db.execute_fetchall(
            """SELECT employee_name, display_name, category, primary_skill
               FROM ai_employee_config WHERE is_active=1"""
        )
        # 直近会話履歴
        history = await db.execute_fetchall(
            """SELECT role, message FROM conversation_log
               WHERE channel='web_secretary' AND with_employee=1
               ORDER BY created_at DESC LIMIT 10"""
        )

    employees_str = "\n".join(
        f"- {e['employee_name']} ({e['display_name']}): {e['category']}" for e in emps
    )

    # システムプロンプト構築
    system_prompt = SECRETARY_CHAT_SYSTEM.format(employees_str=employees_str)

    # 会話履歴を反転して時系列順に
    messages = [{"role": "system", "content": system_prompt}]
    for h in reversed(list(history)):
        messages.append({"role": h["role"], "content": h["message"]})
    messages.append({"role": "user", "content": message})

    # ユーザーメッセージを保存
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO conversation_log
               (channel, with_employee, role, message)
               VALUES ('web_secretary', 1, 'user', ?)""",
            (message,)
        )
        await db.commit()

    # LLM呼び出し
    try:
        import os
        from llm.config import get_openai_client, LLMProvider
        provider_str = os.environ.get("AI_LLM_OVERRIDE_PROVIDER", "ollama")
        model_str    = os.environ.get("AI_LLM_OVERRIDE_MODEL", "qwen2.5:7b")
        try:
            provider_enum = LLMProvider(provider_str)
        except ValueError:
            provider_enum = LLMProvider.OLLAMA
        client = get_openai_client(provider_enum, dict(os.environ))
        response = await client.chat.completions.create(
            model=model_str,
            messages=messages,
        )
        reply = response.choices[0].message.content or ""
    except Exception as e:
        reply = f"申し訳ありません、応答中にエラーが発生しました: {e}"

    # JSON ブロックを検出してアクション抽出
    actions = []
    json_match = re.search(r'```json\s*(\{.*?\})\s*```', reply, re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group(1))
            if parsed.get("action") == "execute_tasks":
                tasks_to_create = parsed.get("tasks", [])
                actions = await _create_and_dispatch(message, tasks_to_create)
        except Exception as e:
            print(f"[secretary_chat] アクション解析失敗: {e}")

    # 返答を保存
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO conversation_log
               (channel, with_employee, role, message)
               VALUES ('web_secretary', 1, 'assistant', ?)""",
            (reply[:5000],)
        )
        await db.commit()

    return {
        "reply":      reply,
        "actions":    actions,
        "session_id": session_id,
    }


async def _create_and_dispatch(user_request: str, tasks: list[dict]) -> list[dict]:
    """秘書が分解したタスクをDBに登録し、各社員に割り当てる。"""
    if not tasks:
        return []

    # プロジェクトを作成
    async with aiosqlite.connect(DB_PATH) as db:
        proj_cursor = await db.execute(
            """INSERT INTO projects (title, description, initiated_by)
               VALUES (?, ?, 'secretary') RETURNING id""",
            (user_request[:80], user_request)
        )
        _proj_row = await proj_cursor.fetchone()
        project_id = _proj_row["id"]

        # 社員名→IDマップ
        db.row_factory = aiosqlite.Row
        emp_rows = await db.execute_fetchall(
            "SELECT id, employee_name FROM ai_employee_config WHERE is_active=1"
        )
        emp_map = {r["employee_name"]: r["id"] for r in emp_rows}

        created_tasks = []
        for i, t in enumerate(tasks):
            assignee = emp_map.get(t.get("assigned_to_employee"))
            cursor = await db.execute(
                """INSERT INTO tasks
                   (project_id, title, description, assigned_to,
                    skill_name, depends_on, order_index)
                   VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id""",
                (
                    project_id,
                    t.get("title", "")[:200],
                    t.get("description", ""),
                    assignee,
                    t.get("skill_name"),
                    json.dumps(t.get("depends_on", [])),
                    i,
                )
            )
            _task_row = await cursor.fetchone()
            task_id = _task_row["id"]
            created_tasks.append({
                "task_id":  task_id,
                "title":    t.get("title"),
                "assignee": t.get("assigned_to_employee"),
                "skill":    t.get("skill_name"),
            })

        await db.commit()

    # 即時発火: 各タスクを並列で起動（依存関係はworker側で解決）
    if created_tasks:
        import asyncio
        from workers.task_executor import execute_task_now
        for t in created_tasks:
            asyncio.create_task(execute_task_now(t["task_id"]))

    return created_tasks


async def get_history(limit: int = 50) -> list[dict]:
    """秘書との会話履歴を取得する（時系列順・system role含む）。"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            """SELECT id, role, message, task_id, created_at
               FROM conversation_log
               WHERE channel='web_secretary' AND with_employee=1
               ORDER BY created_at DESC LIMIT ?""",
            (limit,)
        )
    return list(reversed([dict(r) for r in rows]))
