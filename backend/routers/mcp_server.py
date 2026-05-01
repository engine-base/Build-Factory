"""
MCP Server endpoint — exposes company.db tools over HTTP/SSE.
Claude Code can connect to this via MCP settings.
Endpoint: GET /mcp  (SSE transport)
"""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import json
import asyncio
from db.queries import run_query, get_kpi_summary, list_records

router = APIRouter(prefix="/mcp", tags=["mcp"])

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


async def handle_tool_call(name: str, args: dict) -> str:
    if name == "query_company_db":
        rows = await run_query(args["sql"])
        return json.dumps(rows, ensure_ascii=False, default=str)
    if name == "get_kpi":
        data = await get_kpi_summary()
        return json.dumps(data, ensure_ascii=False, default=str)
    if name == "list_records":
        records = list_records(args.get("folder"))
        return json.dumps(records, ensure_ascii=False)
    return json.dumps({"error": f"Unknown tool: {name}"})


@router.get("")
async def mcp_sse():
    """SSE transport for MCP protocol."""

    async def generate():
        # Send server info
        yield f"data: {json.dumps({'jsonrpc':'2.0','method':'server/info','params':{'name':'CompanyOS','version':'1.0'}})}\n\n"
        # Keep alive
        while True:
            await asyncio.sleep(30)
            yield ": keepalive\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/tools/list")
async def tools_list():
    return {"tools": MCP_TOOLS}


@router.post("/tools/call")
async def tools_call(body: dict):
    name = body.get("name", "")
    args = body.get("arguments", {})
    result = await handle_tool_call(name, args)
    return {"content": [{"type": "text", "text": result}]}
