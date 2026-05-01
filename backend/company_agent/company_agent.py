"""
Company OS Agent — powered by openai-agents-python.
Supports Claude, OpenAI, Ollama (local), LM Studio, LiteLLM.
"""

import json
import os
from agents import Agent, Runner, OpenAIChatCompletionsModel, set_tracing_disabled
from agents import function_tool

from db.queries import run_query, list_records, read_record, get_kpi_summary


set_tracing_disabled(disabled=True)


# ── Agent Tools ───────────────────────────────────────────────────────────────

@function_tool
async def query_database(sql: str) -> str:
    """
    Execute a SELECT SQL query against company.db and return results as JSON.
    Tables: pipeline, contacts, invoices, expenses, task_log, contracts,
    kpi_records, pl_records, seo_reports, sns_posts, outreach_log,
    knowledge_base, monthly_reviews, weekly_reviews, okr, cf_forecasts,
    brand_assets, portfolio_items, tools_inventory, outsource_jobs,
    cs_feedback, network, task_log.
    Only SELECT is allowed.
    """
    try:
        rows = await run_query(sql)
        return json.dumps(rows, ensure_ascii=False, default=str)
    except Exception as e:
        return f"Error: {e}"


@function_tool
async def get_company_kpi() -> str:
    """Get today's KPI summary: pipeline, revenue, expenses, profit, tasks, won deals."""
    try:
        data = await get_kpi_summary()
        return json.dumps(data, ensure_ascii=False, default=str)
    except Exception as e:
        return f"Error: {e}"


@function_tool
def list_skill_outputs(folder: str = "") -> str:
    """
    List Markdown output files from skill executions.
    folder: optional subfolder under records/ (e.g. '05_経営戦略', '03_財務')
    """
    try:
        records = list_records(folder or None)
        return json.dumps(records, ensure_ascii=False)
    except Exception as e:
        return f"Error: {e}"


@function_tool
def read_skill_output(relative_path: str) -> str:
    """
    Read a skill output Markdown file by its relative path under records/.
    Example: '05_経営戦略/strategy/STRATEGY-20240101.md'
    """
    try:
        return read_record(relative_path)
    except FileNotFoundError:
        return f"File not found: {relative_path}"
    except Exception as e:
        return f"Error: {e}"


TOOLS = [query_database, get_company_kpi, list_skill_outputs, read_skill_output]

SYSTEM_PROMPT = """あなたは会社運営OSのAIアシスタントです。
オーナーの会社（一人運営）の経営をサポートします。

利用可能なデータ：
- company.db（SQLite）: pipeline, contacts, invoices, expenses, task_log など23テーブル
- records/ フォルダ: 90のAIスキルが出力したMarkdownファイル群

できること：
- 会社の現状KPI・売上・経費・パイプラインを即座に分析
- SQLクエリで任意のデータを取得・集計
- スキルの実行結果（MDファイル）を読み込んで要約・分析
- 経営上の質問に対してデータドリブンで回答

回答は日本語で、簡潔かつ具体的な数値を含めて答えてください。"""


# ── Agent Factory ─────────────────────────────────────────────────────────────

def create_agent(openai_client, model_name: str) -> Agent:
    model = OpenAIChatCompletionsModel(
        model=model_name,
        openai_client=openai_client,
    )
    return Agent(
        name="CompanyOS",
        instructions=SYSTEM_PROMPT,
        tools=TOOLS,
        model=model,
    )


async def stream_response(agent: Agent, message: str):
    """Yield SSE-compatible text chunks."""
    result = Runner.run_streamed(agent, message)
    async for event in result.stream_events():
        if event.type == "raw_response_event":
            delta = getattr(event.data, "delta", None)
            if delta and hasattr(delta, "content"):
                for block in delta.content:
                    if hasattr(block, "text") and block.text:
                        yield block.text
