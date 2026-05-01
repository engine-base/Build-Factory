#!/usr/bin/env python3
"""
Claude Desktop 用 stdio MCP サーバー。

ENGINE BASE バックエンド（http://localhost:8000）に接続し、
ブラウザタスクキューと安全な認証情報注入を Claude Desktop に提供する。

設定先（macOS）:
  ~/Library/Application Support/Claude/claude_desktop_config.json

  {
    "mcpServers": {
      "engine-base": {
        "command": "python3",
        "args": ["/Users/masato0420/Documents/company-dashboard/mcp_stdio_server.py"]
      }
    }
  }

使い方（Claude Desktop チャット内で）:
  「溜まってるブラウザタスク見せて」
    → list_pending_browser_tasks
  「タスク #5 を実行する」
    → start_browser_task(5) → claude-in-chrome MCPで操作 → complete_browser_task(5, "...")
  ログインフィールドにフォーカスしてから:
    → inject_credential("notion", "password")  # 値はチャットに出ない
"""

import asyncio
import json
import sys
import urllib.parse
from typing import Any, Optional

import urllib.request

BACKEND = "http://localhost:8000"


def http(method: str, path: str, body: Optional[dict] = None) -> dict:
    url = f"{BACKEND}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return {"error": f"{e.code} {e.reason}", "body": e.read().decode()[:500]}
    except Exception as e:
        return {"error": str(e)}


TOOLS = [
    {
        "name": "list_pending_browser_tasks",
        "description": "未実行のブラウザタスクキューを一覧する。Claude Desktop で消化する対象を見るのに使う。",
        "inputSchema": {"type": "object", "properties": {
            "limit": {"type": "integer", "default": 50},
        }},
    },
    {
        "name": "list_all_browser_tasks",
        "description": "すべてのブラウザタスクを一覧する（done/failed 含む）。",
        "inputSchema": {"type": "object", "properties": {
            "status": {"type": "string", "enum": ["pending", "running", "done", "failed", "cancelled"]},
            "limit":  {"type": "integer", "default": 50},
        }},
    },
    {
        "name": "get_browser_task",
        "description": "ブラウザタスク1件の詳細を取得する。",
        "inputSchema": {"type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"]},
    },
    {
        "name": "add_browser_task",
        "description": "ブラウザタスクをキューに追加する（実行はしない）。",
        "inputSchema": {"type": "object",
            "properties": {
                "task":     {"type": "string", "description": "自然言語の操作内容"},
                "service":  {"type": "string", "description": "サービス名（notion/slack/x/google など）"},
                "priority": {"type": "integer", "default": 3},
            },
            "required": ["task"]},
    },
    {
        "name": "start_browser_task",
        "description": "タスクを running 状態に切り替える（Claude Desktop で claude-in-chrome MCP を使って実行する直前に呼ぶ）。",
        "inputSchema": {"type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"]},
    },
    {
        "name": "complete_browser_task",
        "description": "タスクを done としてマークする。実行結果テキストを記録。",
        "inputSchema": {"type": "object",
            "properties": {
                "id":     {"type": "integer"},
                "result": {"type": "string"},
            },
            "required": ["id", "result"]},
    },
    {
        "name": "fail_browser_task",
        "description": "タスクを failed としてマークする。エラー内容を記録。",
        "inputSchema": {"type": "object",
            "properties": {
                "id":    {"type": "integer"},
                "error": {"type": "string"},
            },
            "required": ["id", "error"]},
    },
    {
        "name": "cancel_browser_task",
        "description": "pending のタスクをキャンセルする。",
        "inputSchema": {"type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"]},
    },
    {
        "name": "list_credential_services",
        "description": "登録済みのサービス名一覧を返す（パスワードは含まない）。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "inject_credential",
        "description": (
            "現在ブラウザでフォーカス中のフィールドに、登録済みの認証情報（username または password）を直接 type する。"
            "値はレスポンスに含まれず、チャット履歴にも漏れない。"
            "事前に claude-in-chrome MCP でログインフォームのフィールドをクリック・フォーカスしておくこと。"
        ),
        "inputSchema": {"type": "object",
            "properties": {
                "service": {"type": "string", "description": "サービス名（例: notion）"},
                "field":   {"type": "string", "enum": ["username", "password"]},
            },
            "required": ["service", "field"]},
    },
    {
        "name": "browser_queue_stats",
        "description": "キューの状態別カウントを返す（pending / running / done / failed / cancelled）。",
        "inputSchema": {"type": "object", "properties": {}},
    },

    # ── AI社員管理（staff-management スキル経由） ──────
    {
        "name": "staff_list",
        "description": "AI社員（秘書・リーダー・メンバー）の一覧を返す。",
        "inputSchema": {"type": "object", "properties": {
            "include_retired": {"type": "boolean", "default": False},
        }},
    },
    {
        "name": "staff_orgchart",
        "description": "組織図（階層ツリー + ナレッジ件数 + キャパ警告）を返す。「組織図見せて」で使う。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "staff_get",
        "description": "AI社員1名の詳細を取得。",
        "inputSchema": {"type": "object",
            "properties": {"id": {"type": "integer"}}, "required": ["id"]},
    },
    {
        "name": "staff_hire",
        "description": (
            "新しいAI社員を採用する。staff-management スキルのHIREフロー。"
            "必ずまさとに最終承認を取ってから呼ぶこと。"
        ),
        "inputSchema": {"type": "object",
            "properties": {
                "persona_name": {"type": "string"},
                "role_level":   {"type": "string", "enum": ["leader", "member"]},
                "category":     {"type": "string"},
                "parent_id":    {"type": "integer"},
                "specialty":    {"type": "string"},
                "handles":      {"type": "string"},
                "personality":  {"type": "string"},
                "tone_style":   {"type": "string"},
                "catchphrase":  {"type": "string"},
                "avatar_emoji": {"type": "string"},
                "inherit_knowledge_ids": {"type": "array", "items": {"type": "integer"}},
            },
            "required": ["persona_name", "role_level", "category"]},
    },
    {
        "name": "staff_update",
        "description": "既存社員の個性・担当・ナレッジスコープ・役職を編集。",
        "inputSchema": {"type": "object",
            "properties": {
                "id":      {"type": "integer"},
                "updates": {"type": "object"},
            },
            "required": ["id", "updates"]},
    },
    {
        "name": "staff_retire",
        "description": "AI社員を退職処理。ナレッジは inheritance_to または共通ナレッジへ自動移管。",
        "inputSchema": {"type": "object",
            "properties": {
                "id":                {"type": "integer"},
                "inheritance_to":    {"type": "integer"},
                "promote_to_common": {"type": "boolean"},
                "reason":            {"type": "string"},
            },
            "required": ["id"]},
    },
    {
        "name": "staff_transfer_propose",
        "description": "親リーダーから新メンバーへ引継ぐナレッジ候補を抽出（採用前確認用）。",
        "inputSchema": {"type": "object",
            "properties": {
                "from_employee_id": {"type": "integer"},
                "query_text":       {"type": "string"},
                "top_k":            {"type": "integer", "default": 30},
            },
            "required": ["from_employee_id", "query_text"]},
    },
    {
        "name": "staff_transfer_execute",
        "description": "ナレッジを別社員（または共通）へ実際に移管する。退職・採用・編集時の最終ステップ。",
        "inputSchema": {"type": "object",
            "properties": {
                "knowledge_ids":     {"type": "array", "items": {"type": "integer"}},
                "from_employee_id":  {"type": "integer"},
                "to_employee_id":    {"type": "integer"},
                "reason":            {"type": "string"},
                "move_md_to_folder": {"type": "string"},
            },
            "required": ["knowledge_ids"]},
    },
    {
        "name": "scoped_knowledge_search",
        "description": "社員スコープ付きでナレッジ検索（共通+部+個人の3層）。",
        "inputSchema": {"type": "object",
            "properties": {
                "employee_id": {"type": "integer"},
                "query":       {"type": "string"},
                "top_k":       {"type": "integer", "default": 10},
            },
            "required": ["query"]},
    },
    {
        "name": "scoped_knowledge_propose_target",
        "description": "ナレッジ追加先を AI 分類で提案する（保存はしない）。",
        "inputSchema": {"type": "object",
            "properties": {
                "content":             {"type": "string"},
                "current_employee_id": {"type": "integer"},
            },
            "required": ["content"]},
    },
    {
        "name": "scoped_knowledge_save",
        "description": "ナレッジを実際に保存する。target_employee_id / target_folder を確認後に呼ぶ。",
        "inputSchema": {"type": "object",
            "properties": {
                "title":              {"type": "string"},
                "content":            {"type": "string"},
                "target_employee_id": {"type": "integer"},
                "target_folder":      {"type": "string"},
                "category":           {"type": "string"},
            },
            "required": ["title", "content"]},
    },
]


def call_tool(name: str, args: dict) -> Any:
    if name == "list_pending_browser_tasks":
        limit = args.get("limit", 50)
        return http("GET", f"/api/browser/queue?status=pending&limit={limit}")
    if name == "list_all_browser_tasks":
        params = []
        if args.get("status"): params.append(f"status={args['status']}")
        if args.get("limit"):  params.append(f"limit={args['limit']}")
        qs = ("?" + "&".join(params)) if params else ""
        return http("GET", f"/api/browser/queue{qs}")
    if name == "get_browser_task":
        return http("GET", f"/api/browser/queue/{args['id']}")
    if name == "add_browser_task":
        return http("POST", "/api/browser/queue", {
            "task":     args["task"],
            "service":  args.get("service"),
            "priority": args.get("priority", 3),
            "requested_by": "claude-desktop",
        })
    if name == "start_browser_task":
        return http("POST", f"/api/browser/queue/{args['id']}/start")
    if name == "complete_browser_task":
        return http("POST", f"/api/browser/queue/{args['id']}/done",
                    {"result": args["result"]})
    if name == "fail_browser_task":
        return http("POST", f"/api/browser/queue/{args['id']}/fail",
                    {"error": args["error"]})
    if name == "cancel_browser_task":
        return http("POST", f"/api/browser/queue/{args['id']}/cancel")
    if name == "list_credential_services":
        return http("GET", "/api/browser/services")
    if name == "inject_credential":
        result = http("POST", "/api/browser/credentials/inject",
                      {"service": args["service"], "field": args["field"]})
        # 念押し: 値そのものが返ることはないが、念のため username/password キーを除去
        if isinstance(result, dict):
            for k in ("username", "password", "value"):
                result.pop(k, None)
        return result
    if name == "browser_queue_stats":
        return http("GET", "/api/browser/queue/stats")

    # ── 社員管理 ──
    if name == "staff_list":
        ir = "true" if args.get("include_retired") else "false"
        return http("GET", f"/api/staff?include_retired={ir}")
    if name == "staff_orgchart":
        return http("GET", "/api/staff/orgchart")
    if name == "staff_get":
        return http("GET", f"/api/staff/{args['id']}")
    if name == "staff_hire":
        body = {
            "persona_name": args["persona_name"],
            "role_level":   args["role_level"],
            "category":     args["category"],
            "parent_id":    args.get("parent_id"),
            "specialty":    args.get("specialty"),
            "handles":      args.get("handles", ""),
            "personality":  args.get("personality", ""),
            "tone_style":   args.get("tone_style", ""),
            "catchphrase":  args.get("catchphrase", ""),
            "avatar_emoji": args.get("avatar_emoji", "👤"),
            "inherit_knowledge_ids": args.get("inherit_knowledge_ids", []),
            "triggered_by": "claude-desktop",
        }
        return http("POST", "/api/staff/hire", body)
    if name == "staff_update":
        return http("PATCH", f"/api/staff/{args['id']}", {"updates": args["updates"]})
    if name == "staff_retire":
        return http("POST", f"/api/staff/{args['id']}/retire", {
            "inheritance_to":    args.get("inheritance_to"),
            "promote_to_common": args.get("promote_to_common", False),
            "reason":            args.get("reason", ""),
            "triggered_by":      "claude-desktop",
        })
    if name == "staff_transfer_propose":
        return http("POST", "/api/staff/transfer/propose", {
            "from_employee_id": args["from_employee_id"],
            "query_text":       args["query_text"],
            "top_k":            args.get("top_k", 30),
        })
    if name == "staff_transfer_execute":
        return http("POST", "/api/staff/transfer/execute", {
            "knowledge_ids":     args["knowledge_ids"],
            "from_employee_id":  args.get("from_employee_id"),
            "to_employee_id":    args.get("to_employee_id"),
            "reason":            args.get("reason", "manual"),
            "move_md_to_folder": args.get("move_md_to_folder"),
            "triggered_by":      "claude-desktop",
        })
    if name == "scoped_knowledge_search":
        return http("POST", "/api/staff/knowledge/search", {
            "employee_id": args.get("employee_id"),
            "query":       args["query"],
            "top_k":       args.get("top_k", 10),
        })
    if name == "scoped_knowledge_propose_target":
        return http("POST", "/api/staff/knowledge/propose-target", {
            "content":             args["content"],
            "current_employee_id": args.get("current_employee_id"),
        })
    if name == "scoped_knowledge_save":
        return http("POST", "/api/staff/knowledge/save", {
            "title":              args["title"],
            "content":            args["content"],
            "target_employee_id": args.get("target_employee_id"),
            "target_folder":      args.get("target_folder", "02_共通ナレッジ"),
            "category":           args.get("category"),
            "source":             "claude-desktop",
            "triggered_by":       "claude-desktop",
        })

    return {"error": f"unknown tool: {name}"}


# ── JSON-RPC stdio loop ─────────────────────────────────────

async def main():
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        line = await reader.readline()
        if not line:
            break
        try:
            req = json.loads(line.decode())
        except json.JSONDecodeError:
            continue

        method = req.get("method")
        rid = req.get("id")
        params = req.get("params", {}) or {}

        if method == "initialize":
            resp = {"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "engine-base-browser-queue", "version": "1.0.0"},
            }}
        elif method == "tools/list":
            resp = {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
        elif method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments", {}) or {}
            result = call_tool(name, args)
            resp = {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
            }}
        elif method == "notifications/initialized":
            continue
        else:
            resp = {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32601, "message": f"Method not found: {method}"}}

        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, BrokenPipeError):
        pass
