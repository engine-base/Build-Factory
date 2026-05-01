"""
intent_preprocessor.py — 明示的なキーワードからインテントを検出して強制処理する

LLM の function calling が不安定なモデル（Ollama qwen2.5:7b 等）でも
「覚えて○○」のような明示指示を確実に処理するための前処理。
"""

import re


REMEMBER_PATTERNS = [
    r"^(覚えておいて|覚えて|記憶して|メモして|残しておいて|残して)[:：\s]?(.+)",
    r"^(これ|これは|この情報)(も|を)?(覚えて|メモ|記憶|保存)(しておいて|して)?[:：\s]?(.*)",
    r"^大事(な|なこと)\s*(覚えて|メモ|記憶|保存)[:：\s]?(.+)",
    r"^(ナレッジ|nallege|knowledge)に(保存|追加|記録)[:：\s]?(.+)",
]


def detect_explicit_intent(text: str) -> dict | None:
    """
    入力テキストから明示的な意図を検出する。

    Returns:
        {"type": "remember", "content": "..."} 等
        該当なしなら None
    """
    text = text.strip()

    # 「覚えて」系
    for pattern in REMEMBER_PATTERNS:
        m = re.match(pattern, text, re.DOTALL)
        if m:
            # 最後のグループから内容を取得（パターン毎に位置が違う）
            groups = [g for g in m.groups() if g and g.strip() and g not in ("覚えて", "覚えておいて", "メモして", "記憶して", "保存", "残して", "残しておいて", "を", "も", "は", "これ", "この情報", "大事", "なこと", "な", "メモ", "記憶", "ナレッジ", "に", "追加", "記録", "保存", "してね", "しておいて", "して", "knowledge", "nallege")]
            content = groups[-1].strip(" 、。:：") if groups else ""
            if content and len(content) >= 3:
                return {"type": "remember", "content": content}

    return None
