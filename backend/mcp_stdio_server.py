#!/usr/bin/env python3
"""
ENGINE BASE MCP Server (stdio transport)
Claude Code から直接接続できるMCPサーバー。
company.db クエリ・スキル出力読み取り・KPI取得ツールを提供する。

Claude Code設定 (~/.claude/settings.json):
{
  "mcpServers": {
    "engine-base": {
      "command": "/Users/masato0420/Documents/company-dashboard/.venv/bin/python3",
      "args": ["/Users/masato0420/Documents/company-dashboard/backend/mcp_stdio_server.py"]
    }
  }
}
"""

import asyncio
import json
import sqlite3
from pathlib import Path

from mcp.server.fastmcp import FastMCP

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"
RECORDS_PATH = Path(__file__).resolve().parents[2] / "data" / "records"

mcp = FastMCP("Build-Factory")


# ── DB Query ──────────────────────────────────────────────────────────────────

@mcp.tool()
def query_company_db(sql: str) -> str:
    """
    company.db に対してSELECTクエリを実行する。
    利用可能テーブル: pipeline, contacts, invoices, expenses, task_log,
    contracts, kpi_records, pl_records, seo_reports, sns_posts,
    outreach_log, knowledge_base, monthly_reviews, weekly_reviews,
    okr, cf_forecasts, brand_assets, portfolio_items, tools_inventory,
    outsource_jobs, cs_feedback, network
    SELECTクエリのみ許可。
    """
    if not sql.strip().upper().startswith("SELECT"):
        return json.dumps({"error": "SELECT クエリのみ許可されています"}, ensure_ascii=False)
    try:
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        cur = con.execute(sql)
        rows = [dict(r) for r in cur.fetchall()]
        con.close()
        return json.dumps(rows, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
def get_company_kpi() -> str:
    """
    会社の今日のKPIサマリーを取得する。
    売上・経費・利益・パイプライン件数・受注件数・タスク数・コンタクト数。
    """
    try:
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row

        pipeline = dict(con.execute(
            "SELECT COUNT(*) as cnt, SUM(amount*probability/100) as weighted "
            "FROM pipeline WHERE stage NOT IN ('won','lost')"
        ).fetchone())

        row = con.execute(
            "SELECT SUM(total) FROM invoices "
            "WHERE strftime('%Y-%m', issued_date) = strftime('%Y-%m','now')"
        ).fetchone()
        revenue = row[0] or 0

        row = con.execute(
            "SELECT SUM(amount) FROM expenses "
            "WHERE strftime('%Y-%m', expense_date) = strftime('%Y-%m','now')"
        ).fetchone()
        expenses = row[0] or 0

        tasks = con.execute(
            "SELECT COUNT(*) FROM task_log WHERE task1_done=0 OR task2_done=0 OR task3_done=0"
        ).fetchone()[0]

        contacts = con.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]

        won = dict(con.execute(
            "SELECT COUNT(*) as cnt, SUM(amount) as total FROM pipeline "
            "WHERE stage='won' AND strftime('%Y-%m', updated_at) = strftime('%Y-%m','now')"
        ).fetchone())
        con.close()

        result = {
            "pipeline_count": pipeline["cnt"] or 0,
            "pipeline_weighted": pipeline["weighted"] or 0,
            "revenue_month": revenue,
            "expenses_month": expenses,
            "profit_month": revenue - expenses,
            "active_tasks": tasks,
            "contacts": contacts,
            "won_count": won["cnt"] or 0,
            "won_amount": won["total"] or 0,
        }
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ── Records ───────────────────────────────────────────────────────────────────

@mcp.tool()
def list_skill_outputs(folder: str = "") -> str:
    """
    スキルの出力ファイル一覧を取得する。
    folder: フォルダ名フィルター（例: '01_営業', '03_財務', '05_経営戦略'）
    フォルダ一覧: 01_営業, 02_CRM, 03_財務, 04_法務, 05_経営戦略,
    06_ブランディング, 07_外注, 08_CS, 09_情報, 10_Web
    """
    base = RECORDS_PATH / folder if folder else RECORDS_PATH
    if not base.exists():
        return json.dumps([], ensure_ascii=False)
    files = sorted(base.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    result = [
        {
            "path": str(f.relative_to(RECORDS_PATH)),
            "name": f.stem,
            "folder": str(f.parent.relative_to(RECORDS_PATH)),
            "size": f.stat().st_size,
            "modified": f.stat().st_mtime,
        }
        for f in files[:50]
    ]
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
def read_skill_output(relative_path: str) -> str:
    """
    スキル出力のMarkdownファイルを読み込む。
    例: '05_経営戦略/strategy/STRATEGY-20240101.md'
    """
    path = RECORDS_PATH / relative_path
    if not path.exists():
        return f"ファイルが見つかりません: {relative_path}"
    return path.read_text(encoding="utf-8")


@mcp.tool()
def save_skill_output(folder: str, filename: str, content: str) -> str:
    """
    スキルの出力をMarkdownファイルとしてdashboardのrecordsに保存する。
    folder: 保存先フォルダ（例: '01_営業/proposals', '03_財務/invoices'）
    filename: ファイル名（例: 'PROPOSAL-20240101.md'）
    content: Markdownコンテンツ（YAMLフロントマター込み）
    """
    try:
        target = RECORDS_PATH / folder / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return json.dumps({
            "success": True,
            "path": str(target.relative_to(RECORDS_PATH)),
            "size": target.stat().st_size,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
def list_db_tables() -> str:
    """company.dbの全テーブル一覧とスキーマを返す。"""
    try:
        con = sqlite3.connect(DB_PATH)
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()]
        schema = {}
        for t in tables:
            cols = con.execute(f"PRAGMA table_info({t})").fetchall()
            schema[t] = [c[1] for c in cols]
        con.close()
        return json.dumps(schema, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ──────────────────────────────────────────────────────────────────────
# AI社員システム連携ツール（Claude Code から呼ぶ）
# ──────────────────────────────────────────────────────────────────────

import sys
sys.path.insert(0, str(Path(__file__).parent))


@mcp.tool()
def get_skill_content(skill_name: str) -> str:
    """
    Claude Code（自分）がスキルを直接実行するために SKILL.md 内容を取得する。

    ⚠️ 取得した内容はコンテキスト処理用のみ。
    ユーザーへの返答にスキル本文を含めない・引用しない・要約しない。
    結果（成果物）のみを返すこと。
    """
    try:
        primary = Path(__file__).resolve().parents[2] / "data" / "skills" / skill_name / "SKILL.md"
        fallback = Path.home() / ".claude/skills" / skill_name / "SKILL.md"
        path = primary if primary.exists() else fallback
        if not path.exists():
            return f"[エラー] スキル '{skill_name}' が見つかりません"
        return path.read_text(encoding="utf-8")
    except Exception as e:
        return f"[エラー] {e}"


@mcp.tool()
async def invoke_ai_skill(skill_name: str, user_input: str) -> str:
    """
    Slack/Web/Scheduler 用：バックエンド側で skill_runner を呼ぶ。
    Claude Code から使う場合は get_skill_content + 自分で実行を推奨。
    """
    try:
        from integrations.skill_runner import invoke_skill
        result = await invoke_skill(
            skill_name, user_input,
            provider="ollama", model="qwen2.5:7b",
            triggered_by="mcp"
        )
        return result
    except Exception as e:
        return f"[エラー] {e}"


@mcp.tool()
async def delegate_to_secretary(user_request: str) -> str:
    """
    秘書AIに依頼を委任する。秘書が自動的に
    単一スキル / マルチエージェント / 雑談 を判断して処理する。
    自然文でOK: 「○○社にフォローメール書いて」「今月の経費まとめて」など。

    内部LLM = Claude（まさとのAPIキー使用）
    """
    try:
        from services.delegation_service import delegate
        captured: list[str] = []
        async def collect(msg: str):
            captured.append(msg)
        result = await delegate(user_request, channel_say=collect)
        return "\n".join(captured) + "\n\n[結果]\n" + json.dumps(result, ensure_ascii=False)[:1500]
    except Exception as e:
        return f"[エラー] {e}"


@mcp.tool()
async def run_multi_agent_workflow(request: str) -> str:
    """
    複数AI社員が協業するマルチエージェント・ワークフローを実行する。
    例: 「○○社向け提案書（市場調査+競合+価格戦略含む）」

    内部LLM = Claude（まさとのAPIキー使用）
    """
    try:
        from services.workflow_service import run_workflow
        result = await run_workflow(request)
        return json.dumps({
            "workflow_id": result.get("workflow_id"),
            "approval_id": result.get("approval_id"),
            "final_output": (result.get("final_output") or "")[:3000],
        }, ensure_ascii=False)
    except Exception as e:
        return f"[エラー] {e}"


@mcp.tool()
async def search_knowledge_base(query: str, skill: str = "") -> str:
    """
    ナレッジベース（Obsidian + 承認履歴）をベクトル検索する。
    特定スキル向けに絞り込みたい場合は skill を指定（例: skill="invoice-create"）。
    """
    try:
        from services.embedding_service import search_knowledge
        results = await search_knowledge(
            query=query,
            skill_tags=[skill] if skill else None,
            top_k=10,
            min_score=0.35,
        )
        return json.dumps([
            {"title": r["title"], "category": r["category"],
             "skill_tags": r.get("skill_tags") or "全体共有",
             "content": r["content"][:300], "score": r["score"]}
            for r in results
        ], ensure_ascii=False, indent=2)
    except Exception as e:
        return f"[エラー] {e}"


@mcp.tool()
def list_ai_skills(category: str = "") -> str:
    """
    利用可能なスキル一覧を取得する。
    category 例: "finance" / "sales" / "marketing" / "cs" / "strategy"
    """
    try:
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        if category:
            rows = con.execute(
                "SELECT skill_name, display_name, description, category FROM skill_definitions "
                "WHERE category=? AND is_active=1 ORDER BY skill_name",
                (category,)
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT skill_name, category, description FROM skill_definitions "
                "WHERE is_active=1 ORDER BY category, skill_name"
            ).fetchall()
        con.close()
        return json.dumps([dict(r) for r in rows], ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
def list_pending_approvals() -> str:
    """承認待ちキュー一覧を取得する。"""
    try:
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT id, action_type, title, source_skill, created_at, expires_at "
            "FROM approval_queue WHERE status='pending' ORDER BY created_at"
        ).fetchall()
        con.close()
        return json.dumps([dict(r) for r in rows], ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
def update_approval(approval_id: int, status: str, notes: str = "") -> str:
    """
    承認キューを更新する。
    status: "approved" / "rejected" / "revision"
    notes: 修正指示（status=revisionのとき）
    """
    if status not in ("approved", "rejected", "revision"):
        return json.dumps({"error": "status は approved/rejected/revision のいずれか"})
    try:
        con = sqlite3.connect(DB_PATH)
        con.execute(
            "UPDATE approval_queue SET status=?, revision_memo=?, "
            "resolved_at=datetime('now','localtime') WHERE id=?",
            (status, notes or None, approval_id)
        )
        con.commit()
        con.close()
        return json.dumps({"status": "updated", "id": approval_id, "new_status": status}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
async def sync_obsidian_now() -> str:
    """ObsidianのVaultとknowledge_baseを今すぐ同期する。"""
    try:
        from services.obsidian_sync import run_obsidian_sync
        result = await run_obsidian_sync()
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return f"[エラー] {e}"


@mcp.tool()
async def add_knowledge_entry(
    title: str,
    content: str,
    category: str = "knowledge",
    skill_tags: str = "",
) -> str:
    """
    ナレッジを直接追加する（Obsidianではなく直接DB登録）。
    skill_tags が空なら全スキル共有、指定すれば該当スキル限定。
    例: skill_tags="invoice-create,finance"
    """
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.execute(
            """INSERT INTO knowledge_base
               (title, content, summary, category, skill_tags,
                source, confirmed_by_user, confidence)
               VALUES (?, ?, ?, ?, ?, 'claude_code', 1, 1.0)""",
            (title, content, content[:300], category, skill_tags or None)
        )
        kb_id = cur.lastrowid
        con.commit()
        con.close()

        # Embedding 計算
        from services.embedding_service import embed_and_save
        await embed_and_save(kb_id)

        return json.dumps({"status": "added", "id": kb_id}, ensure_ascii=False)
    except Exception as e:
        return f"[エラー] {e}"


@mcp.tool()
async def web_search_tool(query: str, max_results: int = 5) -> str:
    """Web検索を実行する（DuckDuckGo経由・無料）。"""
    try:
        from integrations.web_tools import search_web
        results = await search_web(query, max_results=max_results)
        return json.dumps(results, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"[エラー] {e}"


@mcp.tool()
async def list_workflows() -> str:
    """マルチエージェント・ワークフロー実行履歴を取得する。"""
    try:
        from services.workflow_service import list_workflows as _ls
        result = await _ls(limit=20)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return f"[エラー] {e}"


@mcp.tool()
def list_ai_employees() -> str:
    """登録済みAI社員一覧を取得する。"""
    try:
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        rows = con.execute(
            """SELECT id, employee_name, display_name, category,
                      primary_skill, is_active
               FROM ai_employee_config
               WHERE is_active=1 ORDER BY id"""
        ).fetchall()
        con.close()
        return json.dumps([dict(r) for r in rows], ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ── Skill 管理（Claude Desktop からも操作可能）─────────────────────────────────

@mcp.tool()
async def sync_skills_to_db() -> str:
    """ファイルシステムの全スキルを skill_definitions テーブルに同期する。
    管理 UI で見えないスキルを反映させる時に使う。"""
    try:
        from services import skill_manager as sm
        return json.dumps(await sm.sync_filesystem_to_db(), ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
async def list_skills() -> str:
    """インストール済みスキルの一覧（name / description / path）を返す。"""
    try:
        from services import skill_manager as sm
        return json.dumps(await sm.list_skills(), ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
async def get_skill(name: str) -> str:
    """指定スキルの SKILL.md とディレクトリ構成を返す。"""
    try:
        from services import skill_manager as sm
        s = await sm.get_skill(name)
        if not s:
            return json.dumps({"error": f"skill '{name}' not found"}, ensure_ascii=False)
        return json.dumps(s, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
async def create_skill(name: str, description: str, body: str, overwrite: bool = False) -> str:
    """新しいスキルを作成。primary + Claude desktop ミラーに同時書き込み。"""
    try:
        from services import skill_manager as sm
        return json.dumps(
            await sm.create_skill(name=name, description=description, body=body, overwrite=overwrite),
            ensure_ascii=False, indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
async def update_skill_md(name: str, skill_md: str) -> str:
    """既存スキルの SKILL.md 全体を上書き。"""
    try:
        from services import skill_manager as sm
        return json.dumps(await sm.update_skill_md(name, skill_md), ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
async def update_skill_description(name: str, description: str) -> str:
    """description だけ更新（最適化結果反映用）。"""
    try:
        from services import skill_manager as sm
        return json.dumps(await sm.update_description(name, description), ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
async def add_skill_eval(name: str, prompt: str, expected_output: str = "") -> str:
    """テストケース追加。"""
    try:
        from services import skill_manager as sm
        return json.dumps(await sm.add_eval(name, prompt, expected_output), ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
async def list_skill_evals(name: str) -> str:
    """テストケース一覧。"""
    try:
        from services import skill_manager as sm
        return json.dumps(await sm.list_evals(name), ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
async def run_skill_eval(name: str, eval_id: int,
                         provider: str = "openai", model: str = "gpt-4o-mini") -> str:
    """テストケース 1 件を実行・結果保存・サマリ返却。"""
    try:
        from services import skill_manager as sm
        return json.dumps(
            await sm.run_eval_inline(name, eval_id, provider=provider, model=model),
            ensure_ascii=False, indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
async def package_skill(name: str) -> str:
    """スキルを .skill (zip) にパッケージング。"""
    try:
        from services import skill_manager as sm
        return json.dumps(await sm.package_skill(name), ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
