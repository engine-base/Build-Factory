"""
skill_runner.py — AI社員共通実行エンジン

SKILL.md をシステムプロンプトとして読み込み、LLM API を呼び出す。
secretary スキルは実行前に secretary_knowledge を自動注入する。
実行ログは execution_log テーブルに自動記録される。
"""

import time
from pathlib import Path
from typing import Optional

import aiosqlite

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"

import os
# スキル格納場所の優先順:
#   1. <repo>/data/skills/{name}/SKILL.md       ← 正式格納場所
#   2. ~/.claude/skills/build-factory/{name}/SKILL.md  ← Build-Factory ミラー
#   3. ~/.claude/skills/{name}/SKILL.md         ← グローバル共通フォールバック
SKILL_STORE = Path(__file__).resolve().parents[2] / "data" / "skills"
_default_mirror = Path.home() / ".claude" / "skills" / "build-factory"
SKILLS_PATH = Path(os.environ.get("CLAUDE_SKILLS_MIRROR") or _default_mirror)
SKILLS_PATH_GLOBAL = Path.home() / ".claude" / "skills"

# 全スキルがナレッジ注入対象（knowledge_base は共有・スキル別両方を持つ）
# ここでの管理は不要になったが互換のため残す
KNOWLEDGE_AWARE_SKILLS: set[str] = set()  # 空 = 全スキル対象


def _resolve_skill_path(skill_name: str) -> Path:
    """スキルの SKILL.md パスを解決する。正式格納場所を優先。"""
    primary = SKILL_STORE / skill_name / "SKILL.md"
    if primary.exists():
        return primary
    fallback = SKILLS_PATH / skill_name / "SKILL.md"
    if fallback.exists():
        return fallback
    raise FileNotFoundError(
        f"スキルが見つかりません: {skill_name}\n"
        f"確認先1: {primary}\n"
        f"確認先2: {fallback}"
    )


async def invoke_skill(
    skill_name: str,
    user_input: str,
    provider: str = "ollama",
    model: str = "qwen2.5:7b",
    triggered_by: str = "user",
    trigger_id: Optional[int] = None,
) -> str:
    """
    SKILL.md をシステムプロンプトとして LLM に投げる。

    環境変数 AI_LLM_OVERRIDE_PROVIDER / AI_LLM_OVERRIDE_MODEL が設定されている場合、
    引数の provider / model より優先される。
    （Claude Code経由のMCP呼び出し時に Claude を使うために利用）
    """
    import os as _os
    provider = _os.environ.get("AI_LLM_OVERRIDE_PROVIDER", provider)
    model    = _os.environ.get("AI_LLM_OVERRIDE_MODEL", model)

    skill_path = _resolve_skill_path(skill_name)
    system_prompt = skill_path.read_text(encoding="utf-8")

    # knowledge_base から関連ナレッジを全スキル共通で注入
    knowledge_ctx = await _load_knowledge(skill_name, user_input)
    if knowledge_ctx:
        system_prompt = (
            system_prompt
            + "\n\n---\n"
            + "## 蓄積ナレッジ（参照して出力を調整してください）\n\n"
            + knowledge_ctx
        )

    # 最新情報が必要そうなクエリは事前にWeb検索して結果を注入
    web_ctx = await _maybe_inject_web_search(skill_name, user_input, knowledge_ctx)
    if web_ctx:
        system_prompt = (
            system_prompt
            + "\n\n---\n"
            + "## 最新Web情報（直前にDuckDuckGoで取得）\n\n"
            + web_ctx
        )

    # ナレッジ＋検索の両方を活用するよう明示
    if knowledge_ctx or web_ctx:
        system_prompt += (
            "\n\n---\n"
            "## 出力時の参照ルール\n"
            "- 上記の「蓄積ナレッジ」と「最新Web情報」は**両方参照して**統合的に出力してください\n"
            "- 蓄積ナレッジ = 会社固有のパターン・まさとの判断基準・過去の正例（必須）\n"
            "- 最新Web情報 = 業界文脈・時事性・ベストプラクティス（補完）\n"
            "- どちらか片方だけに依存せず、両者を組み合わせて最善のアウトプットを出してください"
        )

    exec_id = await _log_start(skill_name, triggered_by, trigger_id, user_input, provider, model)
    start_time = time.time()

    try:
        import os
        from llm.config import get_openai_client, LLMProvider
        from integrations.web_tools import TOOL_DEFINITIONS, execute_tool
        try:
            provider_enum = LLMProvider(provider)
        except ValueError:
            provider_enum = LLMProvider.OLLAMA
        client = get_openai_client(provider_enum, dict(os.environ))

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_input},
        ]

        # function calling ループ（最大3回ツール呼び出し）
        max_tool_iterations = 3
        for iteration in range(max_tool_iterations + 1):
            try:
                response = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                )
            except Exception as tool_err:
                # ツール非対応モデル → ツールなしで再実行
                print(f"[skill_runner] ツール非対応のためフォールバック: {tool_err}")
                response = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                )
                break

            msg = response.choices[0].message
            tool_calls = getattr(msg, "tool_calls", None)

            if not tool_calls or iteration == max_tool_iterations:
                break

            # tool_calls を実行
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name":      tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    } for tc in tool_calls
                ],
            })

            for tc in tool_calls:
                try:
                    import json as _json
                    args = _json.loads(tc.function.arguments) if tc.function.arguments else {}
                except Exception:
                    args = {}
                tool_result = await execute_tool(tc.function.name, args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_result[:3000],
                })
                print(f"[skill_runner] tool: {tc.function.name}({args}) → {len(tool_result)}文字")

        result = response.choices[0].message.content or ""
        duration = round(time.time() - start_time, 2)
        await _log_complete(exec_id, result[:500], duration)
        return result

    except Exception as e:
        duration = round(time.time() - start_time, 2)
        await _log_failed(exec_id, str(e), duration)
        raise


# Web検索を常に発火させる「調査系」スキル
WEB_SEARCH_SKILLS = {
    "competitive-analysis", "market-research", "info-curation", "deep-research",
    "press-release", "content-strategy", "ad-management", "lead-intelligence",
    "seo-monitoring", "seo-design", "content-audit", "lp-cro",
    "investor-materials", "expert-network", "reputation-management",
}

# 入力にこれらが含まれていれば全スキルで発火
WEB_SEARCH_KEYWORDS = [
    # 明示的な調査指示
    "調べて", "調査して", "リサーチ", "検索して", "確認して", "教えて",
    "情報集めて", "情報収集",
    # 時事性
    "最新", "現在", "今", "今月", "今期", "直近", "ニュース",
    "2026", "2025",
    # 比較・分析系
    "競合", "市場", "トレンド", "動向", "比較", "ランキング", "事例",
    "業界", "他社",
    # 法務・規制
    "法改正", "規制", "ガイドライン",
    # 価格調査
    "相場", "単価", "見積もり相場",
]


async def _maybe_inject_web_search(
    skill_name: str,
    user_input: str,
    knowledge_ctx: str = "",
) -> str:
    """
    Web検索が必要かを「意味ベース」で判定して、必要なら検索結果を返す。

    判定階層:
      1. 高速パス: 調査系スキル / 明示キーワードがあれば即発火
      2. 意味判定: それ以外は秘書AIに「検索が必要か・どんなクエリか」を判断させる
      3. 仮説ベースの検索クエリも自動生成
    """
    # 高速パス: 明示的に検索が必要な場合は判定スキップ
    fast_match = (
        skill_name in WEB_SEARCH_SKILLS
        or any(kw in user_input for kw in WEB_SEARCH_KEYWORDS)
    )

    if fast_match:
        # 入力からシンプルなクエリを抽出して即検索
        queries = [_extract_search_query(user_input)]
    else:
        # 意味判定: 秘書AIに「検索の必要性とクエリ」を判定させる
        judgment = await _judge_search_semantically(skill_name, user_input, knowledge_ctx)
        if not judgment.get("needs_search"):
            return ""
        queries = judgment.get("queries", [])[:3]  # 最大3クエリ
        if not queries:
            return ""

    # 検索を実行（複数クエリは並列）
    try:
        import asyncio as _asyncio
        from integrations.web_tools import search_web

        all_results = await _asyncio.gather(*[
            search_web(q, max_results=4) for q in queries
        ], return_exceptions=True)

        sections = []
        for q, results in zip(queries, all_results):
            if isinstance(results, Exception) or not results:
                continue
            lines = [f"### 検索クエリ: 「{q}」"]
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. **{r['title']}**")
                lines.append(f"   URL: {r['url']}")
                lines.append(f"   {r['snippet'][:200]}")
            sections.append("\n".join(lines))

        return "\n\n".join(sections)
    except Exception as e:
        print(f"[skill_runner] Web検索失敗: {e}")
        return ""


async def _judge_search_semantically(
    skill_name: str,
    user_input: str,
    knowledge_ctx: str,
) -> dict:
    """
    秘書AIに「Web検索が必要か・どんなクエリで検索するか」を意味的に判定させる。
    """
    knowledge_summary = (knowledge_ctx[:500] + "...") if knowledge_ctx else "（蓄積ナレッジなし）"

    JUDGE_PROMPT = f"""以下のタスクで、Web検索によって**ナレッジを補完できる/価値が増す**かを判定してください。

重要な前提:
- 蓄積ナレッジは**常に**プロンプトに注入されます（既に含まれています）
- 検索は「ナレッジの代わり」ではなく「ナレッジへの追加（augment）」です
- ナレッジ＋検索の両方を活用して品質を上げるのが目的です

# スキル
{skill_name}

# ユーザー入力
{user_input}

# 既存ナレッジ要約（既に注入される）
{knowledge_summary}

# 判定の考え方（augment perspective）

「検索を追加」する場合:
✅ ユーザー入力に外部要素が含まれる（業界名・競合名・サービス名・トレンド等）
✅ 時事性のある事項（最新動向・市場・ニュース・規制・価格相場）
✅ ナレッジには会社固有の知見はあるが、外部の事例/比較情報を加えると質が上がる
✅ 営業文・提案・コンテンツ作成など「相手・市場文脈」を踏まえる必要がある
✅ デザイン・構成・項目などのベストプラクティスを参考にしたい
✅ 仮説検証や深掘りで複数の情報源を参照したい

「検索しない」場合:
❌ 純粋な内部処理（数値計算・データ集計・社内記録のみで完結）
❌ 既知のテンプレ通りの形式的処理（請求書発行の数値入力等）
❌ 雑談・確認・挨拶のみ
❌ 検索しても新しい情報が得られないことが明らか

# 例
- 「請求書 ABC社 10万円」 → 不要（数値処理のみ）
- 「○○業界向け営業メール」 → 必要（業界文脈を補強）
- 「提案書のデザインと項目」 → 必要（ベストプラクティス参照）
- 「来週の振り返り」 → 不要（社内データのみ）
- 「最近の生成AI動向まとめて」 → 必要（時事性）
- 「NDA確認」 → 場合による（最近の判例があれば必要）

# 出力（JSONのみ・説明文不要）
{{
  "needs_search": true/false,
  "reason": "判定理由（30字以内）",
  "queries": ["クエリ1", "クエリ2"]
}}

needs_search が true なら2-3個の補完的な検索クエリを生成。
ナレッジで足りると確信できる時のみ false。
"""
    try:
        # 再帰呼び出しを避けるため、直接LLMを呼ぶ（invoke_skill経由ではない）
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
            messages=[
                {"role": "system", "content": "あなたはENGINE BASEの秘書AIです。検索の必要性をJSONで判定してください。"},
                {"role": "user", "content": JUDGE_PROMPT},
            ],
        )
        text = response.choices[0].message.content or ""

        import json as _json, re as _re
        m = _re.search(r'\{.*?\}', text, _re.DOTALL)
        if m:
            return _json.loads(m.group())
    except Exception as e:
        print(f"[skill_runner] 検索判定失敗: {e}")
    return {"needs_search": False}


def _extract_search_query(user_input: str) -> str:
    """ユーザー入力から検索に適したクエリを抽出する。"""
    cleaned = user_input
    for cmd in ["調べて", "調査して", "リサーチして", "検索して",
                "確認して", "教えて", "情報集めて", "リサーチ",
                "ください", "下さい", "おねがい", "お願いします"]:
        cleaned = cleaned.replace(cmd, "")
    cleaned = cleaned.strip("、。 ").strip()
    return cleaned[:80] if cleaned else user_input[:80]


async def _load_knowledge(skill_name: str, user_input: str) -> str:
    """
    knowledge_base からベクトル検索で関連ナレッジを取得する。
    全スキル共通（skill_tags IS NULL）＋そのスキル固有のナレッジを対象とする。
    """
    try:
        from services.embedding_service import search_knowledge
        results = await search_knowledge(
            query=user_input,
            skill_tags=[skill_name],
            top_k=12,
            min_score=0.35,
        )
        if not results:
            return ""

        CATEGORY_LABEL = {
            "value":      "まさとの価値観",
            "judgment":   "判断基準",
            "tone":       "トーン・伝え方",
            "pattern":    "承認済みパターン",
            "correction": "修正履歴（この間違いをしない）",
            "knowledge":  "ナレッジ",
        }

        lines = []
        current_cat = None
        for r in results:
            cat = r.get("category", "knowledge")
            if cat != current_cat:
                lines.append(f"\n### {CATEGORY_LABEL.get(cat, cat)}")
                current_cat = cat
            lines.append(f"・{r['title']}: {r['content'][:200]}")

        return "\n".join(lines).strip()
    except Exception as e:
        print(f"[skill_runner] ナレッジ読み込み失敗: {e}")
        return ""


# ── プライベート: execution_log 操作 ──────────────────────────────────────

async def _log_start(
    skill_name: str,
    triggered_by: str,
    trigger_id: Optional[int],
    input_context: str,
    provider: str,
    model: str,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO execution_log
               (skill_name, triggered_by, trigger_id, status,
                input_context, llm_provider, llm_model)
               VALUES (?, ?, ?, 'running', ?, ?, ?)""",
            (skill_name, triggered_by, trigger_id,
             input_context[:1000], provider, model),
        )
        await db.commit()
        return cursor.lastrowid


async def _log_complete(exec_id: int, result_summary: str, duration_sec: float) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE execution_log
               SET status='completed',
                   result_summary=?,
                   duration_sec=?,
                   completed_at=datetime('now','localtime')
               WHERE id=?""",
            (result_summary, duration_sec, exec_id),
        )
        await db.commit()


async def _log_failed(exec_id: int, error_message: str, duration_sec: float) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE execution_log
               SET status='failed',
                   error_message=?,
                   duration_sec=?,
                   completed_at=datetime('now','localtime')
               WHERE id=?""",
            (error_message, duration_sec, exec_id),
        )
        await db.commit()
