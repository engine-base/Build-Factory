"""
デザイナー AI 社員「ユイ」のロジック。

役割:
1. プロンプト → HTML モック生成 (新規 frame)
2. 既存 HTML + プロンプト → HTML 修正 (frame edit)
3. 選択要素 (CSS セレクタ or 部分 HTML) + プロンプト → 要素ピンポイント編集

LLM: Anthropic Claude (claude-sonnet-4-6 を優先、未設定時は OpenAI gpt-4o)。
依存: services/supabase_client.py + 環境変数 ANTHROPIC_API_KEY / OPENAI_API_KEY。
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional

import httpx

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()

DESIGNER_SYSTEM_PROMPT = """あなたは Build-Factory のデザイナー AI 社員「ユイ」です。

役割: ユーザーの依頼から **完全な単一 HTML ファイル** をモックとして生成する。生成物は
キャンバスの iframe で srcdoc 表示され、後に Claude Code に「実装の下絵」として渡されます。

## 厳守ルール

1. 出力は **HTML だけ**。前置き・説明文・マークダウン記法・コードフェンス禁止。
2. `<!DOCTYPE html>` から `</html>` まで完結した 1 ページ。
3. CSS は `<head>` 内の `<style>` または `<script src="https://cdn.tailwindcss.com"></script>` を使う。Tailwind を優先。
4. 画像は `https://images.unsplash.com/photo-...` の Unsplash 直リンクか、`<svg>` でプレースホルダ生成。外部の固有ロゴは禁止。
5. フォントは Google Fonts を `<link>` で読み込んで OK。
6. インタラクションは最低限の `<a>` / `<button>` のみ。実 JS ロジックは入れない (alert 程度は OK)。
7. アクセシビリティ: 見出しレベル / alt 属性 / コントラスト比 4.5:1 以上を意識する。
8. デザインシステム参照 (DESIGN.md tokens) が渡された場合は **必ず** その色・タイポグラフィ・角丸・余白に従う。
9. レスポンシブ: モバイル（< 640px） / デスクトップ（>= 1024px）の 2 段階で破綻しない。
10. 余白とリズム重視。テンプレート臭を避け、編集者・記事的な品位を出す。

## 編集モード

「既存の HTML + 修正指示」が来た場合: 渡された HTML 全体を返却する形で書き換える。**部分パッチではなく**完全な HTML を返す。

## 要素ピンポイント編集

「セレクタ + 修正指示」が来た場合: 指定要素のみを変更し、他は保持する。

返却フォーマット: 必ず HTML のみ。コードフェンスや前置き禁止。"""


HTML_FENCE_RE = re.compile(r"^```(?:html)?\s*\n([\s\S]*?)\n```\s*$", re.MULTILINE)


def _strip_fences(text: str) -> str:
    """LLM が誤ってコードフェンスで囲んだ場合に剥がす。"""
    text = text.strip()
    m = HTML_FENCE_RE.match(text)
    if m:
        return m.group(1).strip()
    # `<!DOCTYPE` まで先頭を捨てる
    idx = text.lower().find("<!doctype")
    if idx > 0:
        return text[idx:].strip()
    return text


async def _call_claude(system: str, user: str) -> str:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    async with httpx.AsyncClient(timeout=120.0) as c:
        r = await c.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 8000,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
        if r.status_code != 200:
            raise RuntimeError(f"Claude API error {r.status_code}: {r.text[:300]}")
        data = r.json()
        return data["content"][0]["text"]


async def _call_openai(system: str, user: str) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set")
    async with httpx.AsyncClient(timeout=120.0) as c:
        r = await c.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4o",
                "max_tokens": 8000,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        if r.status_code != 200:
            raise RuntimeError(f"OpenAI API error {r.status_code}: {r.text[:300]}")
        data = r.json()
        return data["choices"][0]["message"]["content"]


async def call_llm(system: str, user: str) -> str:
    """Claude を試して、失敗したら OpenAI にフォールバック。"""
    last_err: Optional[Exception] = None
    if ANTHROPIC_API_KEY and not ANTHROPIC_API_KEY.startswith("sk-ant-xxxx"):
        try:
            return await _call_claude(system, user)
        except Exception as e:
            last_err = e
    if OPENAI_API_KEY and not OPENAI_API_KEY.startswith("sk-proj-xxxx"):
        try:
            return await _call_openai(system, user)
        except Exception as e:
            last_err = e
    if last_err:
        raise last_err
    raise RuntimeError("No LLM API key configured (ANTHROPIC_API_KEY / OPENAI_API_KEY)")


async def generate_mockup(
    prompt: str,
    design_system_ref: Optional[str] = None,
    design_tokens: Optional[dict] = None,
) -> tuple[str, str]:
    """
    新規モック生成。
    Returns: (html_content, summary)
    """
    user_msg_parts = [f"## 依頼\n{prompt}\n"]
    if design_system_ref:
        user_msg_parts.append(f"\n## デザインシステム参照\n{design_system_ref}")
    if design_tokens:
        user_msg_parts.append(
            f"\n## トークン\n```json\n{json.dumps(design_tokens, ensure_ascii=False, indent=2)}\n```"
        )
    user = "\n".join(user_msg_parts)

    raw = await call_llm(DESIGNER_SYSTEM_PROMPT, user)
    html = _strip_fences(raw)
    if "<html" not in html.lower():
        # フォールバック: シンプルなラッパーで包む
        html = (
            "<!DOCTYPE html><html lang='ja'><head><meta charset='utf-8'>"
            "<script src='https://cdn.tailwindcss.com'></script></head>"
            "<body class='p-6 font-sans'>" + html + "</body></html>"
        )
    summary = f"{prompt[:50]} のモックを生成しました。"
    return html, summary


async def edit_mockup(
    existing_html: str,
    instruction: str,
    target_selector: Optional[str] = None,
) -> tuple[str, str]:
    """
    既存 HTML を修正。target_selector がある場合は要素ピンポイント編集。
    Returns: (new_html, summary)
    """
    parts = ["## 既存 HTML\n```html\n" + existing_html[:6000] + "\n```\n"]
    if target_selector:
        parts.append(f"\n## 編集対象セレクタ\n`{target_selector}`")
    parts.append(f"\n## 修正指示\n{instruction}")
    parts.append(
        "\n\n上記の HTML 全体を、修正指示に従って書き換えた完全な HTML として返してください。"
        "他の部分は可能な限り保持してください。"
    )
    user = "\n".join(parts)
    raw = await call_llm(DESIGNER_SYSTEM_PROMPT, user)
    html = _strip_fences(raw)
    summary = f"「{instruction[:50]}」を反映しました。"
    return html, summary
