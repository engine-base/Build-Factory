"""auth domain — public barrel (T-001-01b AC-2).

責務: OAuth / 認証 / 認証情報 store / user lifecycle.
"""
from __future__ import annotations

from services.oauth_providers import (
    PROVIDERS as OAUTH_PROVIDERS,
    build_authorize_url,
    exchange_code,
    list_providers,
)
from services.user_lifecycle import (
    set_clone_optin,
    get_clone_optin,
    request_deletion,
)

__all__ = [
    "OAUTH_PROVIDERS",
    "build_authorize_url",
    "exchange_code",
    "list_providers",
    "set_clone_optin",
    "get_clone_optin",
    "request_deletion",
]
