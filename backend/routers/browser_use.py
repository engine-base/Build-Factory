"""
browser_use.py — ブラウザuse API

タスクキュー（基本はキューに積む。即時実行は run-now のみ）。
- POST   /api/browser/queue                  タスクをキューに積む（実行しない）
- GET    /api/browser/queue?status=pending   キュー一覧
- GET    /api/browser/queue/{id}             1件取得
- POST   /api/browser/queue/{id}/run         1件即時実行
- POST   /api/browser/queue/{id}/start       1件running化（Claude Desktop用）
- POST   /api/browser/queue/{id}/done        完了マーク（Claude Desktop用）
- POST   /api/browser/queue/{id}/fail        失敗マーク（Claude Desktop用）
- POST   /api/browser/queue/{id}/cancel      キャンセル
- GET    /api/browser/queue/stats            状態別件数

認証情報（パスワード等）は チャットに出さずブラウザに直接注入：
- POST /api/browser/credentials/inject       CDP経由で focused element に直接入力（値はレスポンスに返さない）

その他既存：
- POST   /api/browser/run                    （即時実行・後方互換）
- GET    /api/browser/services / status
- POST   /api/browser/credentials  / DELETE
"""

import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from services.credentials_store import (
    set_credential, get_credential, list_services, delete_credential,
)
from services import browser_queue

router = APIRouter(prefix="/api/browser", tags=["browser"])


# ── デフォルト LLM 設定（.env 上書き可） ──────────────────────
DEFAULT_PROVIDER = os.environ.get("BROWSER_USE_DEFAULT_PROVIDER", "openai")
DEFAULT_MODEL    = os.environ.get("BROWSER_USE_DEFAULT_MODEL", "gpt-4o-mini")


class CredentialBody(BaseModel):
    service:   str
    username:  str
    password:  str
    login_url: Optional[str] = None
    notes:     Optional[str] = None


@router.post("/credentials")
async def save_credential(body: CredentialBody):
    """SaaS認証情報を暗号化保存する。"""
    extra = {}
    if body.login_url: extra["login_url"] = body.login_url
    if body.notes:     extra["notes"] = body.notes
    set_credential(body.service, body.username, body.password, **extra)
    return {"status": "saved", "service": body.service.lower()}


@router.get("/services")
async def list_registered_services():
    """登録済みサービス名一覧（パスワードは含まない）。"""
    services = list_services()
    detail = []
    for s in services:
        c = get_credential(s)
        detail.append({
            "service":   s,
            "username":  c.get("username", "") if c else "",
            "login_url": c.get("login_url", "") if c else "",
            "notes":     c.get("notes", "") if c else "",
        })
    return {"services": detail}


@router.delete("/credentials/{service}")
async def remove_credential(service: str):
    """認証情報を削除する。"""
    ok = delete_credential(service)
    if not ok:
        raise HTTPException(404, "service not found")
    return {"status": "deleted", "service": service}


class BrowserTaskBody(BaseModel):
    task:     str
    service:  Optional[str] = None
    headless: bool = False
    provider: Optional[str] = None
    model:    Optional[str] = None
    max_steps: int = 25


class QueueAddBody(BaseModel):
    task:     str
    service:  Optional[str] = None
    priority: int = 3
    max_steps: int = 20
    provider: Optional[str] = None
    model:    Optional[str] = None
    requested_by: Optional[str] = None
    requested_via_thread: Optional[int] = None


class QueueDoneBody(BaseModel):
    result: str = ""
    screenshot_path: Optional[str] = None
    steps_summary: Optional[list] = None


class QueueFailBody(BaseModel):
    error: str


class CredentialInjectBody(BaseModel):
    """フォーカス中のフィールドへ認証情報を CDP 経由で直接入力する。
    値はレスポンスに含めない（チャット履歴に流出しない）。"""
    service: str
    field:   str  # "username" | "password"


# ── キューAPI ─────────────────────────────────────────────────

@router.post("/queue")
async def queue_add(body: QueueAddBody):
    """タスクをキューに積む（実行しない）。"""
    task_id = await browser_queue.add_task(
        task=body.task,
        service=body.service,
        priority=body.priority,
        max_steps=body.max_steps,
        provider=body.provider or DEFAULT_PROVIDER,
        model=body.model or DEFAULT_MODEL,
        requested_by=body.requested_by,
        requested_via_thread=body.requested_via_thread,
    )
    return {
        "id": task_id,
        "status": "queued",
        "message": f"タスク #{task_id} をキューに追加しました（後で実行されます）。",
    }


@router.get("/queue")
async def queue_list(status: Optional[str] = None, limit: int = 100):
    tasks = await browser_queue.list_tasks(status=status, limit=limit)
    return {"tasks": tasks, "count": len(tasks)}


@router.get("/queue/stats")
async def queue_stats():
    return await browser_queue.stats()


@router.get("/queue/{task_id}")
async def queue_get(task_id: int):
    t = await browser_queue.get_task(task_id)
    if not t:
        raise HTTPException(404, "task not found")
    return t


@router.post("/queue/{task_id}/start")
async def queue_start(task_id: int):
    """Claude Desktop 等から「これから実行する」と宣言する。"""
    ok = await browser_queue.mark_running(task_id)
    if not ok:
        raise HTTPException(409, "task not pending or not found")
    return {"status": "running", "id": task_id}


@router.post("/queue/{task_id}/done")
async def queue_done(task_id: int, body: QueueDoneBody):
    ok = await browser_queue.mark_done(
        task_id, body.result, body.screenshot_path, body.steps_summary,
    )
    if not ok:
        raise HTTPException(404, "task not found")
    return {"status": "done", "id": task_id}


@router.post("/queue/{task_id}/fail")
async def queue_fail(task_id: int, body: QueueFailBody):
    ok = await browser_queue.mark_failed(task_id, body.error)
    if not ok:
        raise HTTPException(404, "task not found")
    return {"status": "failed", "id": task_id}


@router.post("/queue/{task_id}/cancel")
async def queue_cancel(task_id: int):
    ok = await browser_queue.cancel(task_id)
    if not ok:
        raise HTTPException(409, "task not pending")
    return {"status": "cancelled", "id": task_id}


# /queue/{id}/run（即時実行）は意図的に削除。実行は Claude Desktop 経由のみ。


# ── 認証情報の安全注入 ────────────────────────────────────────

@router.post("/credentials/inject")
async def credentials_inject(body: CredentialInjectBody):
    """CDP接続で 現在フォーカス中の input element に値を直接 type する。
    値はレスポンスに含めず、チャット履歴に出ない。"""
    cred = get_credential(body.service)
    if not cred:
        raise HTTPException(404, f"service '{body.service}' not registered")

    if body.field not in ("username", "password"):
        raise HTTPException(400, "field must be 'username' or 'password'")

    value = cred.get(body.field, "")
    if not value:
        raise HTTPException(404, f"{body.field} not stored for {body.service}")

    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            ctx = browser.contexts[0] if browser.contexts else None
            if not ctx or not ctx.pages:
                raise HTTPException(500, "no active page in CDP browser")
            page = ctx.pages[-1]
            await page.keyboard.type(value, delay=20)
            await browser.close()
        return {
            "status": "injected",
            "service": body.service,
            "field": body.field,
            "length": len(value),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"inject failed: {e}")


@router.get("/status")
async def browser_status():
    """ブラウザ接続状態を返す（CDP接続可能か等）。"""
    from services.browser_use_service import get_connection_status
    return await get_connection_status()


@router.post("/run")
async def run_task(body: BrowserTaskBody):
    """互換レイヤー: 即時実行は廃止し、内部でキュー追加にフォールバックする。
    実行は Claude Desktop 経由のみ。"""
    task_id = await browser_queue.add_task(
        task=body.task,
        service=body.service,
        max_steps=body.max_steps,
        provider=body.provider or DEFAULT_PROVIDER,
        model=body.model or DEFAULT_MODEL,
        requested_by="api-run",
    )
    return {
        "success": True,
        "mode": "queued",
        "id": task_id,
        "message": (
            f"タスク #{task_id} をキューに追加しました。"
            "実行は Claude Desktop（claude-in-chrome MCP）経由のみです。"
        ),
    }
