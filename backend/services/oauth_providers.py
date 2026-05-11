"""T-023-04: OAuth 連携 (Slack / GitHub / Anthropic)

各プロバイダの authorize URL 構築 + token 交換 + encrypted_store への保存を
backend-agnostic に提供する。実 token 取引は httpx (既に依存) で同期取得。

## 公開 API

- `build_authorize_url(provider, *, state, redirect_uri) -> str`
- `exchange_code(provider, *, code, redirect_uri) -> dict`
- `save_token(provider, owner_id, token_data) -> None`
- `load_token(provider, owner_id) -> Optional[dict]`

## サポートプロバイダ

| Provider | scope | client_id env | client_secret env |
|---|---|---|---|
| `slack`     | `chat:write,channels:read` | SLACK_CLIENT_ID | SLACK_CLIENT_SECRET |
| `github`    | `repo,read:user`           | GITHUB_CLIENT_ID | GITHUB_CLIENT_SECRET |
| `anthropic` | `claude.read,claude.write` | ANTHROPIC_CLIENT_ID | ANTHROPIC_CLIENT_SECRET |
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

from services import encrypted_store


@dataclass(frozen=True)
class ProviderConfig:
    key: str
    authorize_url: str
    token_url: str
    default_scope: str
    client_id_env: str
    client_secret_env: str


PROVIDERS: dict[str, ProviderConfig] = {
    "slack": ProviderConfig(
        key="slack",
        authorize_url="https://slack.com/oauth/v2/authorize",
        token_url="https://slack.com/api/oauth.v2.access",
        default_scope="chat:write,channels:read",
        client_id_env="SLACK_CLIENT_ID",
        client_secret_env="SLACK_CLIENT_SECRET",
    ),
    "github": ProviderConfig(
        key="github",
        authorize_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        default_scope="repo read:user",
        client_id_env="GITHUB_CLIENT_ID",
        client_secret_env="GITHUB_CLIENT_SECRET",
    ),
    "anthropic": ProviderConfig(
        key="anthropic",
        authorize_url="https://console.anthropic.com/oauth/authorize",
        token_url="https://console.anthropic.com/oauth/token",
        default_scope="claude.read claude.write",
        client_id_env="ANTHROPIC_CLIENT_ID",
        client_secret_env="ANTHROPIC_CLIENT_SECRET",
    ),
}


class UnknownProviderError(ValueError):
    pass


class OAuthConfigError(RuntimeError):
    pass


def _config(provider: str) -> ProviderConfig:
    cfg = PROVIDERS.get(provider)
    if not cfg:
        raise UnknownProviderError(f"unknown provider: {provider}")
    return cfg


def build_authorize_url(
    provider: str, *, state: str, redirect_uri: str, scope: Optional[str] = None,
) -> str:
    """OAuth authorize URL を組み立てる。state は CSRF 防止トークン。"""
    cfg = _config(provider)
    client_id = os.environ.get(cfg.client_id_env)
    if not client_id:
        raise OAuthConfigError(f"{cfg.client_id_env} not set")
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope or cfg.default_scope,
        "state": state,
        "response_type": "code",
    }
    return f"{cfg.authorize_url}?{urlencode(params)}"


async def exchange_code(
    provider: str, *, code: str, redirect_uri: str,
) -> dict:
    """authorization code を access token に交換する。"""
    cfg = _config(provider)
    client_id = os.environ.get(cfg.client_id_env)
    client_secret = os.environ.get(cfg.client_secret_env)
    if not client_id or not client_secret:
        raise OAuthConfigError(f"{cfg.client_id_env}/{cfg.client_secret_env} not set")

    import httpx
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            cfg.token_url,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        try:
            return resp.json()
        except json.JSONDecodeError:
            # GitHub legacy 等は x-www-form-urlencoded で返すこともある
            from urllib.parse import parse_qs
            return {k: v[0] if v else "" for k, v in parse_qs(resp.text).items()}


def save_token(provider: str, owner_id: str, token_data: dict) -> None:
    """token を encrypted_store に保存。"""
    _config(provider)  # validate provider
    value = json.dumps(token_data, ensure_ascii=False)
    encrypted_store.set_secret("oauth", provider, value, owner_id=owner_id)


def load_token(provider: str, owner_id: str) -> Optional[dict]:
    _config(provider)
    raw = encrypted_store.get_secret("oauth", provider, owner_id=owner_id)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def delete_token(provider: str, owner_id: str) -> bool:
    _config(provider)
    return encrypted_store.delete_secret("oauth", provider, owner_id=owner_id)


def list_providers() -> list[str]:
    return list(PROVIDERS.keys())
