"""
browser_use_service.py — browser-use 統合サービス

優先順位:
  1. CDP接続（既存Chromeに繋ぐ）→ ログイン状態フル活用・credentials不要
  2. 永続プロファイル + credentials（フォールバック）

CDP接続の前提:
  Chrome を以下で起動しておく:
    open -a "Google Chrome" --args --remote-debugging-port=9222
  または scripts/start-chrome-cdp.sh を実行
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiohttp

CDP_URL_DEFAULT = "http://localhost:9222"

CONFIG_DIR = Path.home() / ".engine-base"
BROWSER_PROFILE_DIR = CONFIG_DIR / "browser_profiles"
BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

SCREENSHOTS_DIR = Path(__file__).resolve().parents[2] / "data" / "browser_screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


async def _is_cdp_alive(cdp_url: str = CDP_URL_DEFAULT) -> bool:
    """CDP エンドポイントが応答するか確認する。"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{cdp_url}/json/version",
                timeout=aiohttp.ClientTimeout(total=2),
            ) as resp:
                return resp.status == 200
    except Exception:
        return False


async def run_browser_task(
    task: str,
    service: Optional[str] = None,
    use_login: bool = True,
    headless: bool = False,
    max_steps: int = 25,
    provider: str = "ollama",
    model: str = "gemma3:12b",
    force_new_browser: bool = False,
) -> dict:
    """
    ブラウザを起動してタスクを実行する。

    Args:
        force_new_browser: True なら CDP接続を試さず、必ず新規プロファイルで起動
    """
    try:
        from browser_use import Agent
        from browser_use.browser.profile import BrowserProfile

        # 1. CDP接続を優先（既存Chromeにアタッチ）
        cdp_url = None
        connection_mode = "new_profile"
        if not force_new_browser and await _is_cdp_alive(CDP_URL_DEFAULT):
            cdp_url = CDP_URL_DEFAULT
            connection_mode = "cdp"

        # 2. ログイン情報の準備（credentials のヒント・CDP時はスキップ）
        login_hint = ""
        sensitive_data = None
        if connection_mode == "new_profile" and use_login and service:
            from services.credentials_store import get_credential
            cred = get_credential(service)
            if cred:
                # browser-use の sensitive_data 機能で安全に渡す
                sensitive_data = {
                    "username": cred.get("username", ""),
                    "password": cred.get("password", ""),
                }
                login_hint = (
                    f"\n\n# 認証情報\n"
                    f"このサービスにログインする時は username / password プレースホルダを使ってください。\n"
                )
                if cred.get("login_url"):
                    login_hint += f"ログインURL: {cred['login_url']}\n"

        full_task = task + login_hint

        # 3. BrowserProfile 構築
        if connection_mode == "cdp":
            profile = BrowserProfile(cdp_url=cdp_url, headless=False)
        else:
            profile_name = service or "default"
            user_data_dir = BROWSER_PROFILE_DIR / profile_name
            user_data_dir.mkdir(parents=True, exist_ok=True)
            profile = BrowserProfile(
                user_data_dir=str(user_data_dir),
                headless=headless,
            )

        # 4. LLM クライアント
        llm = _build_llm_for_browser_use(provider=provider, model=model)

        agent_kwargs = dict(task=full_task, llm=llm, browser_profile=profile)
        if sensitive_data:
            agent_kwargs["sensitive_data"] = sensitive_data

        agent = Agent(**agent_kwargs)
        history = await agent.run(max_steps=max_steps)

        # 5. 最終スクショ保存
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        screenshot_path = SCREENSHOTS_DIR / f"browser-{service or 'task'}-{ts}.png"
        try:
            session = getattr(agent, "browser_session", None) or getattr(agent, "browser", None)
            if session and hasattr(session, "get_current_page"):
                page = await session.get_current_page()
                if page:
                    await page.screenshot(path=str(screenshot_path), full_page=False)
        except Exception:
            pass

        # 6. CDP接続時はブラウザを閉じない（既存Chromeなので）
        if connection_mode != "cdp":
            try:
                if hasattr(agent, "close"):
                    await agent.close()
            except Exception:
                pass

        return {
            "success": True,
            "connection_mode": connection_mode,
            "result":  history.final_result() if hasattr(history, "final_result") else str(history),
            "steps":   _summarize_steps(history),
            "screenshot": str(screenshot_path) if screenshot_path.exists() else None,
            "service": service,
        }

    except Exception as e:
        return {
            "success": False,
            "error":   str(e),
            "result":  "",
            "steps":   [],
            "screenshot": None,
            "service": service,
            "connection_mode": "failed",
        }


def _build_llm_for_browser_use(provider: str, model: str):
    """browser-use 用の LLM を構築する。"""
    if provider == "claude":
        from browser_use import ChatAnthropic
        return ChatAnthropic(model=model, api_key=os.environ.get("ANTHROPIC_API_KEY", ""), temperature=0.3)
    elif provider == "openai":
        from browser_use import ChatOpenAI
        return ChatOpenAI(model=model, api_key=os.environ.get("OPENAI_API_KEY", ""), temperature=0.3)
    else:
        from browser_use import ChatOpenAI
        return ChatOpenAI(
            model=model,
            base_url="http://localhost:11434/v1",
            api_key="ollama",
            temperature=0.3,
        )


def _summarize_steps(history) -> list[dict]:
    try:
        steps = []
        if hasattr(history, "history"):
            for item in history.history:
                act_descs = []
                if hasattr(item, "model_output") and item.model_output:
                    actions = getattr(item.model_output, "action", [])
                    for a in actions:
                        if hasattr(a, "model_dump"):
                            act_descs.append(a.model_dump(exclude_none=True))
                        else:
                            act_descs.append(str(a))
                steps.append({
                    "url":    getattr(getattr(item, "state", None), "url", "") or "",
                    "actions": act_descs[:3],
                })
        return steps[-10:]
    except Exception:
        return []


async def get_connection_status() -> dict:
    """現在のブラウザ接続状況を返す（UI表示用）。"""
    cdp_alive = await _is_cdp_alive()
    return {
        "cdp_available": cdp_alive,
        "cdp_url": CDP_URL_DEFAULT,
        "mode": "cdp" if cdp_alive else "new_profile",
        "instruction": (
            "[OK] Chromeに接続中（既存ログイン状態を使用）"
            if cdp_alive else
            "[WARN] Chromeを次のコマンドで起動してください:\n"
            '  open -a "Google Chrome" --args --remote-debugging-port=9222\n'
            "起動していない場合は credentials.enc ベースで動きます。"
        ),
    }
