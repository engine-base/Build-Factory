"""
mode_detector.py — 雑談 vs 業務タスク を判定する。

ルールベース 90% + 曖昧時のみ軽量 LLM 分類器（gpt-4o-mini）。
モデル非依存・同期で高速。

Mode は build_layered_prompt() で「業務 SKILL を読み込むか」「Tool-UI 厳格化するか」
に効く。誤って "task" 判定しても支障なし（フォールバックで会話可能）。
"""

from __future__ import annotations

import os
import re

# ──────────────────────────────────────────────────────
# ルールベース判定
# ──────────────────────────────────────────────────────

TASK_KEYWORDS = (
    # 組織変更
    "採用", "退職", "解雇", "雇い", "アサイン", "異動", "昇進",
    # スキル系
    "請求書", "見積", "契約書", "提案書", "営業メール", "フォローメール",
    "SNS投稿", "ブログ", "プレスリリース",
    # 分析・調査
    "市場調査", "競合", "リサーチ", "分析", "KPI", "PL", "予算",
    # 操作系
    "送信", "実行", "登録", "削除", "更新", "編集", "作成して", "保存して",
    "ナレッジ整理", "整理して", "クリーンアップ",
    # 組織図
    "組織図", "誰がいる", "体制", "メンバー一覧",
    # ブラウザ
    "ブラウザで", "Notion", "Slackに", "X に", "投稿",
)

CHAT_GREETINGS = (
    "こんにちは", "おはよう", "こんばんは", "ありがとう", "お疲れ",
    "了解", "はい", "いいえ", "ok", "うん", "そう",
    "ヤッホー", "やっほー", "hi", "hello", "やあ",
)


def rule_detect(message: str, history: list[dict] | None = None) -> str | None:
    """ルールベース判定。曖昧なら None を返して LLM 分類器にフォールバック。"""
    msg = (message or "").strip()
    if not msg:
        return "chat"

    # 業務キーワードヒット
    for kw in TASK_KEYWORDS:
        if kw in msg:
            return "task"

    # 短い挨拶系
    if len(msg) <= 30:
        for g in CHAT_GREETINGS:
            if g in msg.lower():
                return "chat"

    # 質問形（「？」終わり・短文）→ 雑談寄り
    if msg.endswith(("?", "？")) and len(msg) < 50:
        return "chat"

    # 自己紹介系
    if any(p in msg for p in ["僕は", "私は", "自分は", "名前は", "と申します", "って言う"]):
        return "chat"

    # 純粋な短文（1-15文字）は雑談
    if len(msg) < 15:
        return "chat"

    # 曖昧 → LLM へ
    return None


# ──────────────────────────────────────────────────────
# LLM 分類器（曖昧時のみ）
# ──────────────────────────────────────────────────────

CLASSIFY_PROMPT = """次のユーザー発言を「chat」か「task」のどちらかに分類してください。

- chat: 雑談・挨拶・自己紹介・質問・相談・情報確認
- task: 何かを作る/送る/実行する/編集する依頼、データ処理、明確な業務指示

JSON形式のみで答えてください（説明不要）：
{"mode":"chat"} または {"mode":"task"}

発言: """


async def llm_detect(message: str) -> str:
    """OpenAI gpt-4o-mini で軽量分類。失敗時は chat fallback。"""
    if not os.environ.get("OPENAI_API_KEY"):
        return "chat"
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI()
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": CLASSIFY_PROMPT + message[:300]}],
            max_tokens=20,
            temperature=0,
        )
        text = resp.choices[0].message.content or ""
        m = re.search(r'"mode"\s*:\s*"(chat|task)"', text)
        return m.group(1) if m else "chat"
    except Exception as e:
        print(f"[mode_detector] LLM分類失敗: {e}")
        return "chat"


# ──────────────────────────────────────────────────────
# 公開API
# ──────────────────────────────────────────────────────

async def detect_mode(message: str, history: list[dict] | None = None) -> str:
    """雑談 / 業務 を判定。返値: "chat" | "task"。"""
    rule = rule_detect(message, history)
    if rule is not None:
        return rule
    return await llm_detect(message)
