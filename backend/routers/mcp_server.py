"""T-010a-01 / F-010a: MCP Server endpoint (REFACTOR).

ENGINE BASE バックエンドの DB / KPI / records を MCP プロトコル (HTTP+SSE) で公開する.
Claude Code / Claude Desktop はこの endpoint を MCP server として登録できる.

Endpoint:
  GET  /mcp                — SSE transport (server/info + keepalive)
  POST /mcp/tools/list     — 登録 tool 一覧
  POST /mcp/tools/call     — tool 実行 (name + arguments)

T-010a-01 AC:
  AC-1 UBIQUITOUS    : F-010a の MCP server を public 公開
  AC-2 EVENT-DRIVEN  : 2 秒以内に success / {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 既存 contract (tools name / arguments) は不変 — backwards compat
  AC-4 UNWANTED      : invalid input / unknown tool / unauthorized は 4xx + structured,
                       persistent state mutate しない
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from db.queries import run_query, get_kpi_summary, list_records

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])


# ──────────────────────────────────────────────────────────────────────────
# T-010a-01: error contract helpers (AC-2 / AC-4)
# ──────────────────────────────────────────────────────────────────────────


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    """{detail:{code,message}} 形式 (AC-2 / AC-4)."""
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str] = None, detail: dict) -> None:
    """audit_logs に MCP tool 呼び出しを emit (best-effort)."""
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover — best-effort
        logger.warning("mcp audit emit failed: %s -- %s", event_type, e)


# ──────────────────────────────────────────────────────────────────────────
# AC-3: 既存 tool contract (backwards compat)
# ──────────────────────────────────────────────────────────────────────────

MCP_TOOLS = [
    {
        "name": "query_company_db",
        "description": "Run a SELECT query against company.db (23 tables: pipeline, contacts, invoices, expenses, task_log, contracts, kpi_records, pl_records, seo_reports, sns_posts, etc.)",
        "inputSchema": {
            "type": "object",
            "properties": {"sql": {"type": "string", "description": "SELECT SQL query"}},
            "required": ["sql"],
        },
    },
    {
        "name": "get_kpi",
        "description": "Get today's company KPI snapshot: revenue, expenses, profit, pipeline, tasks.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_records",
        "description": "List skill output Markdown files. Optional folder filter.",
        "inputSchema": {
            "type": "object",
            "properties": {"folder": {"type": "string", "description": "Subfolder name (optional)"}},
        },
    },
]

# 既存 tool name set (validation で参照)
_KNOWN_TOOLS = {t["name"] for t in MCP_TOOLS}


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: input validation
# ──────────────────────────────────────────────────────────────────────────


def _validate_call_input(name: str, args: Any) -> dict:
    """AC-4: tool name / arguments の validation. invalid なら 4xx raise."""
    if not isinstance(name, str) or not name.strip():
        raise _error("mcp.invalid_tool_name", "tool name must not be empty")
    if name not in _KNOWN_TOOLS:
        raise _error(
            "mcp.unknown_tool",
            f"unknown tool {name!r}; known={sorted(_KNOWN_TOOLS)}",
            status_code=404,
        )
    if args is None:
        return {}
    if not isinstance(args, dict):
        raise _error("mcp.invalid_arguments", "arguments must be a JSON object")
    # 各 tool ごとの必須 field 検査
    if name == "query_company_db":
        sql = args.get("sql")
        if not isinstance(sql, str) or not sql.strip():
            raise _error("mcp.invalid_sql", "sql is required and must be non-empty string")
        # AC-4: 非 SELECT は reject (mutate 防止)
        head = sql.strip().split(None, 1)[0].upper() if sql.strip() else ""
        if head not in {"SELECT", "WITH", "PRAGMA"}:
            raise _error(
                "mcp.sql_not_readonly",
                f"only read-only queries allowed (got {head!r})",
                status_code=403,
            )
    return args


async def handle_tool_call(name: str, args: dict) -> str:
    """既存 contract (AC-3): tool name で分岐して JSON string を返す."""
    if name == "query_company_db":
        rows = await run_query(args["sql"])
        return json.dumps(rows, ensure_ascii=False, default=str)
    if name == "get_kpi":
        data = await get_kpi_summary()
        return json.dumps(data, ensure_ascii=False, default=str)
    if name == "list_records":
        records = list_records(args.get("folder"))
        return json.dumps(records, ensure_ascii=False)
    # validator が先に reject するので到達しないが、念のため structured raise
    raise _error("mcp.unknown_tool", f"unknown tool {name!r}", status_code=404)


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint 公開
# ──────────────────────────────────────────────────────────────────────────


@router.get("")
async def mcp_sse():
    """SSE transport for MCP protocol (AC-1)."""

    async def generate():
        info = {
            "jsonrpc": "2.0",
            "method": "server/info",
            "params": {"name": "CompanyOS", "version": "1.0"},
        }
        yield f"data: {json.dumps(info)}\n\n"
        while True:
            await asyncio.sleep(30)
            yield ": keepalive\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/tools/list")
async def tools_list() -> dict[str, Any]:
    """AC-1 / AC-3: 登録 tool 一覧 (既存 contract 不変)."""
    return {"tools": MCP_TOOLS}


# AC-3 backwards compat: 既存 contract は `{"name": ..., "arguments": ...}` の dict
class ToolCallRequest(BaseModel):
    name: str = Field(..., description="tool name")
    arguments: Any = Field(default_factory=dict, description="tool arguments (dict or null)")
    user_id: Optional[str] = Field(None, description="actor user_id (audit log 用)")


@router.post("/tools/call")
async def tools_call(body: dict) -> dict[str, Any]:
    """AC-2: tool 呼び出し. AC-4: invalid input は structured 4xx."""
    if not isinstance(body, dict):
        raise _error("mcp.invalid_body", "request body must be a JSON object")
    name = body.get("name", "")
    args_raw = body.get("arguments", {})
    user_id = body.get("user_id")
    if user_id is not None:
        if not isinstance(user_id, str) or not user_id.strip():
            raise _error("mcp.unauthorized", "user_id must be non-empty when provided", status_code=401)

    args = _validate_call_input(name, args_raw)
    try:
        text = await handle_tool_call(name, args)
    except HTTPException:
        raise
    except Exception as e:
        # 下流エラーも structured で返す (mutate 防止)
        raise _error("mcp.tool_failed", f"tool {name!r} failed: {e}", status_code=500)

    await _audit("mcp.tool.called", user_id=user_id, detail={"name": name, "result_len": len(text)})
    return {"content": [{"type": "text", "text": text}]}
