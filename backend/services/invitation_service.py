"""
invitation_service.py — F-004 / T-V3-B-05 共通ヘルパ.

主な役割:
  - account-level invitation lookup (account_service へ delegate)
  - workspace-level invitation lookup (workspace_service へ delegate)
  - in-memory rate-limit (20/hour/account) for POST /api/accounts/{id}/invitations

将来的に Redis sliding-window へ差し替え可能な、ピュアな抽象。
"""
from __future__ import annotations

import time
from collections import deque
from threading import Lock
from typing import Deque, Dict, Optional

# ──────────────────────────────────────────────────────────────────────
# AC-F2 / AC-F10: rate limit (20 invitations / 1 hour / account)
# ──────────────────────────────────────────────────────────────────────

_RATE_LIMIT_WINDOW_SECONDS: float = 3600.0
_RATE_LIMIT_MAX_REQUESTS: int = 20

_buckets: Dict[int, Deque[float]] = {}
_lock = Lock()


def reset_rate_limit() -> None:
    """tests 用. プロセス内 state をクリア."""
    with _lock:
        _buckets.clear()


def configure_rate_limit(
    *, max_requests: int = 20, window_seconds: float = 3600.0
) -> None:
    """tests / config override 用。プロセス global を更新する。"""
    global _RATE_LIMIT_MAX_REQUESTS, _RATE_LIMIT_WINDOW_SECONDS
    _RATE_LIMIT_MAX_REQUESTS = max_requests
    _RATE_LIMIT_WINDOW_SECONDS = float(window_seconds)


def check_invitation_rate_limit(account_id: int) -> tuple[bool, int]:
    """T-V3-B-05 AC-F2 / AC-F10.

    Returns:
      (allowed, remaining)
      allowed=False の場合 429 を返すこと.
    """
    now = time.monotonic()
    threshold = now - _RATE_LIMIT_WINDOW_SECONDS
    with _lock:
        bucket = _buckets.setdefault(account_id, deque())
        # evict expired
        while bucket and bucket[0] < threshold:
            bucket.popleft()
        if len(bucket) >= _RATE_LIMIT_MAX_REQUESTS:
            return False, 0
        bucket.append(now)
        remaining = _RATE_LIMIT_MAX_REQUESTS - len(bucket)
    return True, remaining


# ──────────────────────────────────────────────────────────────────────
# AC-F3 / AC-F13: public lookup (mutate-free)
# ──────────────────────────────────────────────────────────────────────


async def public_lookup(token: str) -> Optional[dict]:
    """T-V3-B-05 AC-F13.

    GET /api/invitations/{token} の core. account-level → workspace-level
    の順に解決する。is_expired / status を返す。
    """
    # account-level 優先
    from services import account_service as acc

    acc_inv = await acc.lookup_account_invitation(token)
    if acc_inv:
        return {"scope": "account", **acc_inv}

    # fallback: workspace-level
    from services import workspace_service as ws

    ws_inv = await ws.lookup_invitation(token)
    if ws_inv:
        return {"scope": "workspace", **ws_inv}

    return None
