"""
Company OS Dashboard — FastAPI Backend
Supports Claude, OpenAI, Ollama (local), LM Studio, LiteLLM
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

load_dotenv(Path(__file__).parent.parent / ".env")

from config import validate_required_env

from routers import chat, dashboard, records, llm, mcp_server
from routers.approval import router as approval_router
from routers.ai_system import router as ai_system_router
from routers.chatwork import router as chatwork_router
from routers.skills import router as skills_router
from routers.documents import router as documents_router
from routers.workflows import router as workflows_router
from routers.employees import router as employees_router
from routers.tasks import router as tasks_router
from routers.secretary import router as secretary_router
from routers.secretary_stream import router as secretary_stream_router
from routers.llm_providers import router as llm_providers_router
from routers.knowledge_actions import router as knowledge_actions_router
from routers.threads import router as threads_router
from routers.browser_use import router as browser_use_router
from routers.staff import router as staff_router
from routers.slot_admin import router as slot_admin_router
from routers.skill_creator import router as skill_creator_router
from routers.artifacts import router as artifacts_router
from routers.accounts import router as accounts_router
from routers.workspaces import router as workspaces_router, invitations_router
from routers.hearing import router as hearing_router
from routers.requirements import router as requirements_router
from routers.pricing_design import router as pricing_design_router
from routers.proposal import router as proposal_router
from routers.estimate import router as estimate_router
from routers.account_settings import router as account_settings_router
from routers.uploads import router as uploads_router
from routers.template_builder import router as template_builder_router
from routers.design_pipeline import router as design_pipeline_router
from routers.reviewer import router as reviewer_router
from routers.knowledge_search import router as knowledge_search_router
from routers.design_frames import router as design_frames_router
from routers.design_mocks import router as design_mocks_router
from routers.references import router as references_router
from routers.swarm import router as swarm_router
from routers.memory import router as memory_router
from routers.context import router as context_router
from routers.oauth import router as oauth_router
from routers.user_lifecycle import router as user_lifecycle_router
from routers.memory_facts import router as memory_facts_router
from routers.mem0_bridge import router as mem0_bridge_router
from routers.chat_search import router as chat_search_router
from routers.bf_profile import router as bf_profile_router
from routers.ws import router as ws_router
from routers.admin_fallback import router as admin_fallback_router
from routers.phases import router as phases_router
from routers.task_dependencies import router as task_dependencies_router
from routers.slack_integration import router as slack_integration_router
from routers.agent_runner import router as agent_runner_router
from routers.admin_seed import router as admin_seed_router
from routers.personas_guideline import router as personas_guideline_router
from routers.spec_mock_links import router as spec_mock_links_router
from routers.feature_decomposer import router as feature_decomposer_router
from routers.impact_analyzer import router as impact_analyzer_router
from routers.task_list_view import router as task_list_view_router
from routers.impact_highlight import router as impact_highlight_router
from routers.mcp_tokens import router as mcp_tokens_router
from routers.parallel_runner import router as parallel_runner_router
from scheduler.scheduler import scheduler, load_jobs_from_db
from integrations.slack_client import start_slack, stop_slack


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── 起動時 ──────────────────────────────────
    # T-001-01 AC-3: 必須 SUPABASE_* env vars が欠けていたら fail fast
    validate_required_env()

    await load_jobs_from_db()
    scheduler.start()
    print(f"[lifespan] Scheduler started — {len(scheduler.get_jobs())} jobs")

    # approval_worker を10秒ごとに登録
    from workers.approval_worker import process_approved_items
    scheduler.add_job(
        process_approved_items,
        "interval",
        seconds=10,
        id="approval_worker",
        replace_existing=True,
    )

    # task_executor を10秒ごとに登録（pending タスクを自動実行）
    from workers.task_executor import process_pending_tasks
    scheduler.add_job(
        process_pending_tasks,
        "interval",
        seconds=10,
        id="task_executor",
        replace_existing=True,
    )

    # Slack Socket Mode（SLACK_BOT_TOKEN が設定されている場合のみ）
    await start_slack()

    yield

    # ── 終了時 ──────────────────────────────────
    await stop_slack()
    scheduler.shutdown(wait=False)
    print("[lifespan] Scheduler stopped")


app = FastAPI(
    title="Company OS Dashboard",
    description="AI-powered company management dashboard",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all local ports (3000-3099, etc.)
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(dashboard.router)
app.include_router(records.router)
app.include_router(llm.router)
app.include_router(mcp_server.router)
app.include_router(approval_router)
app.include_router(ai_system_router)
app.include_router(chatwork_router)
app.include_router(skills_router)
app.include_router(documents_router)
app.include_router(workflows_router)
app.include_router(employees_router)
app.include_router(tasks_router)
app.include_router(secretary_router)
app.include_router(secretary_stream_router)
app.include_router(llm_providers_router)
app.include_router(knowledge_actions_router)
app.include_router(threads_router)
app.include_router(browser_use_router)
app.include_router(staff_router)
app.include_router(slot_admin_router)
app.include_router(skill_creator_router)
app.include_router(artifacts_router)
app.include_router(accounts_router)
app.include_router(workspaces_router)
app.include_router(invitations_router)
app.include_router(hearing_router)
app.include_router(requirements_router)
app.include_router(pricing_design_router)
app.include_router(proposal_router)
app.include_router(estimate_router)
app.include_router(account_settings_router)
app.include_router(uploads_router)
app.include_router(template_builder_router)
app.include_router(design_pipeline_router)
app.include_router(reviewer_router)
app.include_router(knowledge_search_router)
app.include_router(design_frames_router)
app.include_router(design_mocks_router)
app.include_router(references_router)
app.include_router(swarm_router)
app.include_router(memory_router)
app.include_router(context_router)
app.include_router(oauth_router)
app.include_router(user_lifecycle_router)
app.include_router(memory_facts_router)
app.include_router(mem0_bridge_router)
app.include_router(chat_search_router)
app.include_router(bf_profile_router)
app.include_router(ws_router)
app.include_router(admin_fallback_router)
app.include_router(phases_router)
app.include_router(task_dependencies_router)
app.include_router(slack_integration_router)
app.include_router(agent_runner_router)
app.include_router(admin_seed_router)
app.include_router(personas_guideline_router)
app.include_router(spec_mock_links_router)
app.include_router(feature_decomposer_router)
app.include_router(impact_analyzer_router)
app.include_router(task_list_view_router)
app.include_router(impact_highlight_router)
app.include_router(mcp_tokens_router)
app.include_router(parallel_runner_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "company-os-dashboard"}


@app.post("/api/briefing/run")
async def run_briefing_now():
    """朝ブリーフィングを即時手動実行する（テスト・確認用）"""
    from jobs.briefing_job import run_morning_briefing
    import asyncio
    asyncio.create_task(run_morning_briefing())
    return {"status": "started", "message": "ブリーフィング生成を開始しました（バックグラウンド実行）"}


@app.get("/api/briefing/latest")
async def get_latest_briefing():
    """最新のブリーフィングMDを返す"""
    from fastapi.responses import PlainTextResponse
    from datetime import date
    records_path = Path(__file__).resolve().parents[2] / "data" / "records" / "13_セルフマネジメント" / "briefings"
    today_str = date.today().strftime("%Y%m%d")
    today_file = records_path / f"BRIEF-{today_str}.md"
    if today_file.exists():
        return PlainTextResponse(today_file.read_text(encoding="utf-8"))
    files = sorted(records_path.glob("BRIEF-*.md"), reverse=True)
    if files:
        return PlainTextResponse(files[0].read_text(encoding="utf-8"))
    return PlainTextResponse("本日のブリーフィングはまだ生成されていません")


@app.post("/api/sales/follow-email/{pipeline_id}")
async def api_generate_follow_email(pipeline_id: int):
    """指定した pipeline 案件のフォローメールドラフトを生成して approval_queue に追加する"""
    from services.sales_service import generate_follow_email
    approval_id = await generate_follow_email(pipeline_id)
    return {
        "approval_id": approval_id,
        "message": f"フォローメールドラフトを approval_queue (id={approval_id}) に追加しました",
    }


@app.get("/api/sales/pipeline")
async def api_pipeline_summary():
    """パイプラインのサマリーを返す"""
    from services.sales_service import get_pipeline_summary
    return await get_pipeline_summary()


@app.post("/api/inbox/check")
async def api_inbox_check():
    """統合インボックスチェックを即時手動実行する"""
    from services.inbox_service import run_inbox_check
    import asyncio
    asyncio.create_task(run_inbox_check())
    return {"status": "started", "message": "インボックスチェックを開始しました"}


@app.get("/api/channels/status")
async def api_channels_status():
    """各チャンネルの接続状態を返す（S-9 チャンネル設定画面用）"""
    import os
    from integrations.gmail_client import is_configured as gmail_configured, TOKEN_PATH
    from integrations.slack_client import _slack_enabled, _app as slack_app
    from integrations.chatwork_client import is_configured as cw_configured

    # Slack チーム名・Bot ID を取得（接続中のみ）
    slack_team = None
    slack_bot_id = None
    if _slack_enabled and slack_app:
        try:
            result = await slack_app.client.auth_test()
            slack_team = result.get("team")
            slack_bot_id = result.get("bot_id")
        except Exception:
            pass

    # Gmail 認証メールアドレス取得
    gmail_email = None
    if gmail_configured() and TOKEN_PATH.exists():
        try:
            from integrations.gmail_client import GMAIL_BUSINESS_ADDRESS
            gmail_email = GMAIL_BUSINESS_ADDRESS
        except Exception:
            pass

    return {
        "slack": {
            "connected": _slack_enabled,
            "bot_user_id": slack_bot_id,
            "team": slack_team,
            "error": None if _slack_enabled else (
                "SLACK_BOT_TOKEN / SLACK_APP_TOKEN を .env に設定してください"
                if not os.environ.get("SLACK_BOT_TOKEN") else "接続失敗"
            ),
        },
        "gmail": {
            "connected": gmail_configured() and TOKEN_PATH.exists(),
            "email": gmail_email,
            "error": None if (gmail_configured() and TOKEN_PATH.exists()) else (
                "Gmail OAuth2 認証を完了してください"
            ),
        },
        "chatwork": {
            "connected": cw_configured(),
            "room_id": os.environ.get("CHATWORK_ROOM_ID", ""),
            "error": None if cw_configured() else "CHATWORK_API_TOKEN を .env に設定してください",
        },
        "scheduler": {
            "running": scheduler.running,
            "job_count": len(scheduler.get_jobs()),
        },
    }


@app.post("/api/catchup")
async def api_catchup(hours: int = 4):
    """不在中のアクティビティをキャッチアップ要約する。"""
    from services.catchup_service import run_catchup
    result = await run_catchup(hours=hours)
    return result


@app.get("/api/config")
async def config():
    return {
        "db_path": str(Path(__file__).resolve().parents[2] / "data" / "db" / "build.db"),
        "records_path": str(Path(__file__).resolve().parents[2] / "data" / "records"),
        "has_anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
        "has_openai": bool(os.getenv("OPENAI_API_KEY")),
    }
