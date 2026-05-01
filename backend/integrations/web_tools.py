"""
web_tools.py — Webツール統合（検索 / URL取得 / ブラウザ操作）

提供ツール:
  - search_web(query)      : DuckDuckGo検索（軽量・無料）
  - fetch_url(url)         : URL本文取得（mcp-server-fetch経由）
  - browse_page(url, query): Playwright で実ブラウザ操作（深掘り用）

LLM の function calling から呼ばれる。
"""

import asyncio
import json
import os
from contextlib import AsyncExitStack
from typing import Optional

# ──────────────────────────────────────────────────────────────────────
# 1. DuckDuckGo 検索（直接呼び出し・最も軽量）
# ──────────────────────────────────────────────────────────────────────

async def search_web(query: str, max_results: int = 5) -> list[dict]:
    """
    DuckDuckGo で Web 検索する。

    Returns:
        [{"title": "...", "url": "...", "snippet": "..."}, ...]
    """
    try:
        from ddgs import DDGS
        loop = asyncio.get_event_loop()
        # ddgs は同期的なので executor で実行
        results = await loop.run_in_executor(
            None,
            lambda: list(DDGS().text(query, max_results=max_results))
        )
        return [
            {
                "title":   r.get("title", ""),
                "url":     r.get("href", ""),
                "snippet": r.get("body", "")[:300],
            }
            for r in results
        ]
    except Exception as e:
        print(f"[web_tools] search_web エラー: {e}")
        return []


# ──────────────────────────────────────────────────────────────────────
# 2. URL本文取得（mcp-server-fetch を使うと余計なクリーンアップが入る）
# ──────────────────────────────────────────────────────────────────────

async def fetch_url(url: str, max_chars: int = 4000) -> str:
    """
    URLを取得して本文テキストを返す（HTMLタグ除去・主要部分抽出）。
    """
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=15),
                headers={"User-Agent": "Mozilla/5.0 (compatible; ENGINE-BASE-AI/1.0)"}
            ) as resp:
                if resp.status != 200:
                    return f"[エラー] HTTP {resp.status}"
                html = await resp.text()
        # 簡易テキスト抽出
        text = _extract_text_from_html(html)
        return text[:max_chars]
    except Exception as e:
        return f"[エラー] {e}"


def _extract_text_from_html(html: str) -> str:
    """HTMLから本文テキストを抽出する。"""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        # 不要要素を削除
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        # 連続改行を圧縮
        import re
        return re.sub(r"\n{3,}", "\n\n", text)
    except ImportError:
        # bs4 がなければそのまま返す
        return html
    except Exception as e:
        return f"[抽出エラー] {e}"


# ──────────────────────────────────────────────────────────────────────
# 3. Playwright MCP（深掘り・JS必要なサイト用）
# ──────────────────────────────────────────────────────────────────────

_playwright_session = None
_exit_stack = None


async def browse_page(url: str, action: str = "screenshot") -> str:
    """
    Playwright MCP で実ブラウザを使ってページにアクセスする。
    JS必須サイト・SPA・ログイン要のページに使う。

    Args:
        url:    開くURL
        action: "screenshot" | "text" | "links"
    """
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command="npx",
            args=["-y", "@playwright/mcp@latest", "--headless"]
        )

        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                # ページに遷移
                await session.call_tool("browser_navigate", {"url": url})
                # アクションに応じて結果を取得
                if action == "text":
                    result = await session.call_tool("browser_snapshot", {})
                    return _stringify_mcp_result(result)[:5000]
                elif action == "links":
                    result = await session.call_tool("browser_snapshot", {})
                    return _stringify_mcp_result(result)[:3000]
                else:
                    result = await session.call_tool("browser_snapshot", {})
                    return _stringify_mcp_result(result)[:5000]
    except Exception as e:
        return f"[browse_page エラー] {e}"


def _stringify_mcp_result(result) -> str:
    """MCP の CallToolResult を文字列化する。"""
    if hasattr(result, "content") and result.content:
        parts = []
        for c in result.content:
            if hasattr(c, "text"):
                parts.append(c.text)
            else:
                parts.append(str(c))
        return "\n".join(parts)
    return str(result)


# ──────────────────────────────────────────────────────────────────────
# 4. LLM Function Calling 用ツール定義
# ──────────────────────────────────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "DuckDuckGoで最新のWeb情報を検索する。最新情報・競合動向・市場価格・法改正等を調べたい時に使う。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "検索クエリ。日本語可"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "結果件数（デフォルト5）",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "URLにアクセスして本文を取得する。検索結果のURLから詳細を読みたい時に使う。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "取得するURL"
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browse_page",
            "description": "Playwrightで実ブラウザを使ってページを取得する。JS必須・SPA・通常fetchで取れないサイト用。重いので必要な時だけ。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url":    {"type": "string"},
                    "action": {"type": "string", "enum": ["text", "links"], "default": "text"}
                },
                "required": ["url"]
            }
        }
    },
]


async def execute_tool(name: str, arguments: dict) -> str:
    """LLM の tool_call を実行してテキスト結果を返す。"""
    try:
        if name == "search_web":
            results = await search_web(
                arguments.get("query", ""),
                arguments.get("max_results", 5),
            )
            return json.dumps(results, ensure_ascii=False, indent=2)

        elif name == "fetch_url":
            return await fetch_url(arguments.get("url", ""))

        elif name == "browse_page":
            return await browse_page(
                arguments.get("url", ""),
                arguments.get("action", "text"),
            )

        return f"[エラー] 未知のツール: {name}"
    except Exception as e:
        return f"[ツール実行エラー] {name}: {e}"
