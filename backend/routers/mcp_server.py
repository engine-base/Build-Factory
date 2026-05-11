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
    # T-010a-02: Build-Factory 専用 MCP tools (runner 連携)
    {
        "name": "bf_get_spec",
        "description": (
            "Get the specification (description + acceptance_criteria + linked artifacts) "
            "for a Build-Factory task. Runner uses this to read context before implementation."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Build-Factory task id"},
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "bf_post_progress",
        "description": (
            "Report progress on a Build-Factory task (percent_done + note). "
            "Updates audit_logs but does not change task status."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "percent_done": {"type": "number", "description": "0.0..1.0"},
                "note": {"type": "string"},
            },
            "required": ["task_id", "percent_done"],
        },
    },
    {
        "name": "bf_attach_artifact",
        "description": (
            "Link an artifact (already created via /api/artifacts) to a Build-Factory task. "
            "Both ids must exist."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "artifact_id": {"type": "string"},
            },
            "required": ["task_id", "artifact_id"],
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
    # T-010a-02: BF tools の入力検査
    if name in ("bf_get_spec", "bf_post_progress", "bf_attach_artifact"):
        task_id = args.get("task_id")
        if not isinstance(task_id, int) or task_id <= 0:
            raise _error("mcp.invalid_task_id", "task_id must be a positive int")
    if name == "bf_post_progress":
        p = args.get("percent_done")
        if not isinstance(p, (int, float)) or not (0.0 <= float(p) <= 1.0):
            raise _error("mcp.invalid_percent_done",
                         "percent_done must be 0.0..1.0")
        note = args.get("note")
        if note is not None and (not isinstance(note, str) or len(note) > 2000):
            raise _error("mcp.invalid_note", "note must be str (<= 2000 chars)")
    if name == "bf_attach_artifact":
        aid = args.get("artifact_id")
        if not isinstance(aid, str) or not aid.strip():
            raise _error("mcp.invalid_artifact_id",
                         "artifact_id must be a non-empty string")
        if len(aid) > 200:
            raise _error("mcp.invalid_artifact_id",
                         "artifact_id must be <= 200 chars")
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
    # T-010a-02: Build-Factory tools
    if name == "bf_get_spec":
        result = await _bf_get_spec(args["task_id"])
        return json.dumps(result, ensure_ascii=False, default=str)
    if name == "bf_post_progress":
        result = await _bf_post_progress(
            args["task_id"],
            float(args["percent_done"]),
            args.get("note"),
        )
        return json.dumps(result, ensure_ascii=False, default=str)
    if name == "bf_attach_artifact":
        result = await _bf_attach_artifact(args["task_id"], args["artifact_id"])
        return json.dumps(result, ensure_ascii=False, default=str)
    # validator が先に reject するので到達しないが、念のため structured raise
    raise _error("mcp.unknown_tool", f"unknown tool {name!r}", status_code=404)


# ──────────────────────────────────────────────────────────────────────────
# T-010a-02: Build-Factory tools 実装 (loader 注入式)
# ──────────────────────────────────────────────────────────────────────────


async def _bf_get_spec(task_id: int) -> dict:
    """task の spec を返す.

    AC-3 backwards compat: 既存 tasks 表から description + acceptance_criteria を抽出.
    """
    try:
        from db import async_db as aiosqlite
        from pathlib import Path
        DB = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"
        async with aiosqlite.connect(DB) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT id, title, description, status, acceptance_criteria, "
                "project_id, assigned_to FROM tasks WHERE id=?",
                (task_id,),
            )
            if not rows:
                raise _error("mcp.task_not_found",
                             f"task not found: {task_id}", status_code=404)
            task = dict(rows[0])
        # 紐づく artifacts も付ける (best-effort)
        artifacts: list[dict] = []
        try:
            async with aiosqlite.connect(DB) as db:
                db.row_factory = aiosqlite.Row
                arows = await db.execute_fetchall(
                    "SELECT id, type, title FROM artifacts "
                    "WHERE task_id=? AND is_archived=0 ORDER BY updated_at DESC LIMIT 20",
                    (task_id,),
                )
                artifacts = [dict(a) for a in arows]
        except Exception:
            pass
        return {
            "task_id": task_id,
            "title": task.get("title"),
            "description": task.get("description") or "",
            "status": task.get("status"),
            "acceptance_criteria": task.get("acceptance_criteria"),
            "project_id": task.get("project_id"),
            "assigned_to": task.get("assigned_to"),
            "artifacts": artifacts,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise _error("mcp.bf_get_spec_failed",
                     f"bf_get_spec failed: {e}", status_code=500)


async def _bf_post_progress(task_id: int, percent_done: float, note: Optional[str]) -> dict:
    """task に progress event を audit_logs に emit.

    task status は変更しない (AC-3: backwards compat).
    """
    try:
        from services.memory_service import emit_event
        await emit_event(
            "mcp.task.progress",
            session_id=None,
            user_id=None,
            detail={
                "task_id": task_id,
                "percent_done": round(percent_done, 4),
                "note": note,
            },
        )
        return {
            "task_id": task_id,
            "percent_done": round(percent_done, 4),
            "note": note,
            "recorded": True,
        }
    except Exception as e:
        raise _error("mcp.bf_post_progress_failed",
                     f"bf_post_progress failed: {e}", status_code=500)


async def _bf_attach_artifact(task_id: int, artifact_id: str) -> dict:
    """artifact を task に紐付ける (artifacts.task_id を update)."""
    try:
        from services.artifact_service import get_artifact
        artifact = await get_artifact(artifact_id)
        if artifact is None:
            raise _error("mcp.artifact_not_found",
                         f"artifact not found: {artifact_id}", status_code=404)
        from db import async_db as aiosqlite
        from pathlib import Path
        DB = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"
        async with aiosqlite.connect(DB) as db:
            db.row_factory = aiosqlite.Row
            trows = await db.execute_fetchall(
                "SELECT id FROM tasks WHERE id=?",
                (task_id,),
            )
            if not trows:
                raise _error("mcp.task_not_found",
                             f"task not found: {task_id}", status_code=404)
            await db.execute(
                "UPDATE artifacts SET task_id=?, updated_at=datetime('now','localtime') "
                "WHERE id=?",
                (task_id, artifact_id),
            )
            await db.commit()
        return {
            "task_id": task_id,
            "artifact_id": artifact_id,
            "linked": True,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise _error("mcp.bf_attach_artifact_failed",
                     f"bf_attach_artifact failed: {e}", status_code=500)


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
