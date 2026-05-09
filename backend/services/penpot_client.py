"""
Penpot RPC API クライアント。

Penpot は GraphQL ではなく独自の RPC エンドポイントを公開している:
    POST /api/rpc/command/{command-name}    (mutating)
    POST /api/rpc/query/{query-name}        (read-only)

認証: クッキー (auth-token) または Bearer access-token。
Build-Factory は Phase 1 では admin アカウントの永続トークンで全 RPC を叩く。

使い方:
    client = PenpotClient(base_url=..., admin_token=...)
    project = await client.create_project(team_id=..., name="新規プロジェクト")
    file = await client.create_file(project_id=project["id"], name="ログイン画面")
"""
from __future__ import annotations

import os
from typing import Any, Optional

import httpx

PENPOT_BASE_URL = os.environ.get("PENPOT_BASE_URL", "http://localhost:9001")
PENPOT_ADMIN_EMAIL = os.environ.get("PENPOT_ADMIN_EMAIL", "admin@buildfactory.local")
PENPOT_ADMIN_PASSWORD = os.environ.get("PENPOT_ADMIN_PASSWORD", "buildfactory123")


class PenpotClient:
    """Penpot RPC のシン薄いラッパ。"""

    def __init__(
        self,
        base_url: str = PENPOT_BASE_URL,
        access_token: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self._access_token = access_token
        self._cookies: dict[str, str] = {}
        self._client: Optional[httpx.AsyncClient] = None

    # ──────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0, base_url=self.base_url)
        return self._client

    async def aclose(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _rpc(
        self, kind: str, name: str, payload: Optional[dict[str, Any]] = None,
    ) -> Any:
        client = self._get_client()
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",  # JSON で返してもらう (transit+json をスキップ)
        }
        if self._access_token:
            headers["Authorization"] = f"Token {self._access_token}"
        r = await client.post(
            f"/api/rpc/{kind}/{name}",
            headers=headers,
            cookies=self._cookies,
            json=payload or {},
        )
        # Penpot は失敗時に 4xx + JSON ボディを返す
        if r.status_code >= 400:
            raise PenpotError(
                f"Penpot RPC {kind}/{name} failed: {r.status_code} {r.text[:300]}"
            )
        # 成功時 cookie を保持 (login 用)
        if r.cookies:
            self._cookies.update(dict(r.cookies))
        if not r.content:
            return None
        try:
            return r.json()
        except Exception:
            return r.text

    # ──────────────────────────────────────
    # Auth
    # ──────────────────────────────────────

    async def login_with_password(
        self, email: str = PENPOT_ADMIN_EMAIL, password: str = PENPOT_ADMIN_PASSWORD,
    ) -> dict:
        """パスワードログイン。成功時にクッキーが保持される。"""
        return await self._rpc(
            "command",
            "login-with-password",
            {"email": email, "password": password},
        )

    async def register_profile(
        self,
        email: str = PENPOT_ADMIN_EMAIL,
        password: str = PENPOT_ADMIN_PASSWORD,
        fullname: str = "Build-Factory Admin",
    ) -> dict:
        """初回起動時の admin アカウント自動作成 (prepare → register の 2 段階)。"""
        # Step 1: prepare で token 取得
        prepared = await self._rpc(
            "command",
            "prepare-register-profile",
            {
                "email": email,
                "password": password,
                "fullname": fullname,
            },
        )
        token = (prepared or {}).get("token") if isinstance(prepared, dict) else None
        if not token:
            raise PenpotError(f"prepare-register-profile returned no token: {prepared!r}")
        # Step 2: token を使って register
        result = await self._rpc(
            "command",
            "register-profile",
            {
                "token": token,
                "accept-terms-and-privacy": True,
                "accept-newsletter-subscription": False,
            },
        )
        return result

    async def skip_onboarding(self) -> Any:
        """admin user の profile にオンボーディング完了フラグを設定 (modal をスキップ)。
        Penpot 2.x の正規 prop 名 (frontend/src/app/main/data/profile.cljs より):
          - onboarding-viewed
          - onboarding-questions-answered
          - release-notes-viewed
        """
        try:
            return await self._rpc(
                "command",
                "update-profile-props",
                {
                    "props": {
                        "onboarding-viewed": True,
                        "onboarding-questions-answered": True,
                        "release-notes-viewed": "2.14",
                        "v2-info-shown": True,
                    }
                },
            )
        except Exception as e:
            print(f"[penpot] skip_onboarding failed (non-fatal): {e}")
            return None

    async def get_profile(self) -> dict:
        return await self._rpc("command", "get-profile")

    # ──────────────────────────────────────
    # Teams / Projects / Files
    # ──────────────────────────────────────

    async def get_teams(self) -> list[dict]:
        return await self._rpc("command", "get-teams") or []

    async def get_default_team_id(self) -> str:
        teams = await self.get_teams()
        # default team は is-default: true
        default = next(
            (t for t in teams if t.get("is-default") or t.get("isDefault")),
            None,
        )
        if default:
            return default["id"]
        # フォールバック: 最初の team
        if teams:
            return teams[0]["id"]
        raise PenpotError("No teams available")

    async def create_project(self, team_id: str, name: str) -> dict:
        return await self._rpc(
            "command",
            "create-project",
            {"team-id": team_id, "name": name},
        )

    async def get_projects(self, team_id: str) -> list[dict]:
        return (
            await self._rpc(
                "command",
                "get-projects",
                {"team-id": team_id},
            )
            or []
        )

    async def create_file(
        self,
        project_id: str,
        name: str,
        is_shared: bool = False,
    ) -> dict:
        return await self._rpc(
            "command",
            "create-file",
            {
                "project-id": project_id,
                "name": name,
                "is-shared": is_shared,
            },
        )

    async def get_file(self, file_id: str) -> dict:
        return await self._rpc("command", "get-file", {"id": file_id})

    async def delete_file(self, file_id: str) -> Any:
        return await self._rpc("command", "delete-file", {"id": file_id})

    async def get_file_thumbnail(self, file_id: str) -> Optional[dict]:
        try:
            return await self._rpc(
                "command",
                "get-file-thumbnail",
                {"file-id": file_id},
            )
        except Exception:
            return None


class PenpotError(RuntimeError):
    pass


# ──────────────────────────────────────
# Module-level singleton (lazy login)
# ──────────────────────────────────────

_singleton: Optional[PenpotClient] = None


async def get_penpot_client() -> PenpotClient:
    """共有 admin セッションでログイン済みのクライアントを返す。"""
    global _singleton
    if _singleton is None:
        client = PenpotClient()
        # 初回: 登録 → ログイン (既に登録済なら register が失敗するのでスキップ)
        try:
            await client.register_profile()
        except PenpotError:
            pass
        await client.login_with_password()
        # オンボーディング modal をスキップ
        await client.skip_onboarding()
        _singleton = client
    return _singleton
