"""
conversation_summarizer.py — 会話の現状を構造化して RAG コンテキストに注入する。

直前数ターンから「確定情報・否定された仮説・未解決事項」を抽出して
プロンプト先頭に整理して渡す。LLMの推論補助を強化する。

補助LLM のモデル選択:
  - デフォルト: メインと同じ provider/model
  - 環境変数で上書き可能 (RAG_SUMMARIZER_PROVIDER / RAG_SUMMARIZER_MODEL)
  - frontend からも override できる（チャットボディで helper_provider/model を渡す）
"""

from __future__ import annotations

import os
import re
from typing import Optional


SUMMARY_PROMPT = """次は AI と ユーザー の最近の会話です。
今このターンの応答品質を上げるため、以下の3項目を JSON で抽出してください。
説明や前置き不要・JSON のみ返答。

抽出ルール:
- "facts": ユーザーが確定として伝えた事実（名前・好み・状況など）の配列
- "rejected": 直近で AI が提案して ユーザーが否定した仮説の配列
- "open": まだ未解決でユーザーが回答を待っている事項の配列

例:
{"facts":["ユーザー名はまさと","『高本』は正解の漢字"],"rejected":["『正人』(まさとの漢字として)"],"open":["まさとの正しい漢字"]}

会話:
"""


def _format_history(history: list[dict], max_turns: int = 8) -> str:
    """直近 N ターンを整形。"""
    lines = []
    for h in (history or [])[-max_turns:]:
        role = "ユーザー" if h.get("role") == "user" else "AI"
        content = (h.get("content") or h.get("message") or "")[:300]
        lines.append(f"[{role}] {content}")
    return "\n".join(lines)


async def generate_summary(
    history: list[dict],
    main_provider: str = "ollama",
    main_model: str = "qwen2.5:7b",
    helper_provider: Optional[str] = None,   # None=auto (= main)
    helper_model: Optional[str] = None,
) -> dict:
    """会話履歴から確定/否定/未解決を抽出。
    返却: {"facts":[...], "rejected":[...], "open":[...]}
    エラー時は空辞書。
    """
    if not history or len(history) < 2:
        return {}

    # ── 補助LLM のモデル決定（auto = メインと同じ）─────
    env_provider = os.environ.get("RAG_SUMMARIZER_PROVIDER", "auto")
    env_model = os.environ.get("RAG_SUMMARIZER_MODEL", "auto")
    provider = (helper_provider or env_provider or "auto")
    model = (helper_model or env_model or "auto")
    if provider == "auto" or not provider:
        provider = main_provider
    if model == "auto" or not model:
        model = main_model

    # ── プロンプト組み立て ─────────────────
    convo_text = _format_history(history)
    if not convo_text.strip():
        return {}
    prompt = SUMMARY_PROMPT + convo_text

    # ── LLM 呼出 ────────────────────────
    try:
        from llm.config import get_openai_client, LLMProvider
        try:
            provider_enum = LLMProvider(provider)
        except ValueError:
            provider_enum = LLMProvider.OLLAMA
        client = get_openai_client(provider_enum, dict(os.environ))

        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0,
        )
        text = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[summarizer] LLM呼出失敗 ({provider}/{model}): {e}")
        return {}

    # ── JSON 抽出 ────────────────────────
    import json
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return {}
    try:
        data = json.loads(m.group())
        if not isinstance(data, dict):
            return {}
        return {
            "facts":    list(data.get("facts") or [])[:8],
            "rejected": list(data.get("rejected") or [])[:8],
            "open":     list(data.get("open") or [])[:8],
        }
    except Exception as e:
        print(f"[summarizer] JSON parse失敗: {e}")
        return {}


def format_for_prompt(summary: dict) -> str:
    """サマリをプロンプト用文字列に整形。空なら空文字。"""
    if not summary:
        return ""
    parts = []
    if summary.get("facts"):
        parts.append("【会話の確定情報】\n" + "\n".join(f"- {f}" for f in summary["facts"]))
    if summary.get("rejected"):
        parts.append("【不採用仮説（再提示しない）】\n" + "\n".join(f"- {r}" for r in summary["rejected"]))
    if summary.get("open"):
        parts.append("【未解決事項】\n" + "\n".join(f"- {o}" for o in summary["open"]))
    return "\n\n".join(parts)
