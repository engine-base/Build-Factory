"""T-S0-12: Better Stack uptime monitor (heartbeat push + /health 連携).

## 目的

Build-Factory backend が生きていることを Better Stack に通知する uptime monitor.
2 通りの方式を併用する:

  1. **Pull モード** (Better Stack → backend):
     Better Stack が `/health` (既存 endpoint, backend/main.py L248) を 30 秒ごとに
     ping. ステータスコード 200 で alive 判定. **設定は Better Stack ダッシュボード**
     で行うため本 module はコード変更不要 (運用文書化のみ).

  2. **Push モード** (backend → Better Stack heartbeat URL):
     backend が `BETTER_STACK_HEARTBEAT_URL` に定期的に POST. 5 分以内に ping が
     来ないと Better Stack 側で down 判定 + Slack/email/PagerDuty alert.
     本 module で push 関数を提供し APScheduler から呼ぶ.

両方式を併用することで「外部 ping unreachable」と「backend 自身が異常」の
両方を検出できる.

## 4 層 observability の役割分担 (前 PR の 3 層 + 本 PR)

| 機構           | 目的            | 担当                                |
|----------------|-----------------|-------------------------------------|
| structlog/pino | 全ログ          | T-S0-11                             |
| audit_logs DB  | 監査 trail      | memory_service.emit_event           |
| Sentry         | error / perf    | T-S0-10                             |
| **Better Stack** | **uptime / SLO** | **T-S0-12 (this) + /health + heartbeat** |

4 機構は独立 (どれが落ちても他は動く).

## Graceful degradation

httpx は backend 既存依存 (requirements.txt 既存) なので新規依存追加なし.
`BETTER_STACK_HEARTBEAT_URL` 未設定の場合, send_heartbeat() は no-op で False
を返す. APScheduler 側で本関数を呼んでも crash しない.

## AC マッピング

  AC-1 UBIQUITOUS    : send_heartbeat() / is_configured() / get_heartbeat_url()
                       公開. /health endpoint は既存活用 (無改変).
  AC-2 EVENT-DRIVEN  : APScheduler 連携で 1 分ごとに送信 (運用文書).
                       send_heartbeat() の戻り値で成功/失敗が分かる.
  AC-3 STATE-DRIVEN  : BETTER_STACK_HEARTBEAT_URL 未設定で no-op (graceful) /
                       HTTP failure で log warning, 既存 audit_logs に書込まない.
  AC-4 UNWANTED      : invalid URL (non-https / 空) で ValueError /
                       network failure で例外 raise しない (return False) /
                       hardcoded secret なし.
"""
from __future__ import annotations

import logging
import os
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────

DEFAULT_TIMEOUT_SEC = 10
ALLOWED_SCHEMES = ("https", "http")  # http は dev only


def _validate_url(url: str) -> str:
    """Better Stack heartbeat URL の form 検証 (network call しない)."""
    if not isinstance(url, str):
        raise ValueError("url must be string")
    url = url.strip()
    if not url:
        raise ValueError("url must not be empty")
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError(
            f"url scheme must be one of {ALLOWED_SCHEMES}, got {parsed.scheme!r}"
        )
    if not parsed.netloc:
        raise ValueError(f"url netloc missing: {url!r}")
    return url


def get_heartbeat_url() -> Optional[str]:
    """Return BETTER_STACK_HEARTBEAT_URL env var or None."""
    raw = os.environ.get("BETTER_STACK_HEARTBEAT_URL")
    if not raw or not raw.strip():
        return None
    return raw.strip()


def is_configured() -> bool:
    """Heartbeat URL が設定されているか (graceful flag)."""
    return get_heartbeat_url() is not None


# ──────────────────────────────────────────────────────────────────────
# Heartbeat send (graceful: never raises on network errors)
# ──────────────────────────────────────────────────────────────────────


def send_heartbeat(
    *,
    url: Optional[str] = None,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    extra_payload: Optional[dict] = None,
) -> bool:
    """Send a heartbeat to Better Stack.

    Args:
        url: heartbeat URL. None なら BETTER_STACK_HEARTBEAT_URL env 参照.
        timeout_sec: HTTP timeout. invalid (<=0 or >60) で ValueError.
        extra_payload: 任意の JSON payload (status='healthy' 等を Better Stack
                       UI に表示できる). dict 以外なら ValueError.

    Returns:
        bool: 成功時 True, no-op / network 失敗時 False.

    Note: 任意の network/import 失敗で例外を raise しない (graceful).
          意図的 ValueError (invalid input) のみ raise.
    """
    if not isinstance(timeout_sec, (int, float)):
        raise ValueError("timeout_sec must be a number")
    if timeout_sec <= 0 or timeout_sec > 60:
        raise ValueError(
            f"timeout_sec must be in (0, 60], got {timeout_sec}"
        )
    if extra_payload is not None and not isinstance(extra_payload, dict):
        raise ValueError("extra_payload must be dict or None")

    # explicit url: 必ず validate (空文字 / 非 str も raise)
    # env fallback: 未設定なら no-op で False
    if url is not None:
        target_url = _validate_url(url)
    else:
        target_url = get_heartbeat_url()
        if not target_url:
            logger.debug(
                "BETTER_STACK_HEARTBEAT_URL not configured; skip heartbeat"
            )
            return False
        target_url = _validate_url(target_url)

    try:
        import httpx
    except ImportError:  # pragma: no cover (backend deps に httpx あり)
        logger.warning(
            "httpx not installed; cannot send Better Stack heartbeat"
        )
        return False

    try:
        # Better Stack heartbeat は POST or GET どちらでも OK
        if extra_payload:
            r = httpx.post(target_url, json=extra_payload, timeout=timeout_sec)
        else:
            r = httpx.get(target_url, timeout=timeout_sec)
        if r.status_code >= 400:
            logger.warning(
                "Better Stack heartbeat returned %d: %s",
                r.status_code, target_url,
            )
            return False
        logger.debug("Better Stack heartbeat OK (status=%d)", r.status_code)
        return True
    except Exception as e:
        # network failure: 例外を raise せず False 返却 (uptime monitor 自身が
        # システム crash の原因になってはいけない)
        logger.warning(
            "Better Stack heartbeat send failed: %s -- %s",
            type(e).__name__, str(e)[:200],
        )
        return False


# ──────────────────────────────────────────────────────────────────────
# APScheduler 連携 (運用文書 / docstring only)
# ──────────────────────────────────────────────────────────────────────

APSCHEDULER_INTEGRATION_GUIDE = """\
APScheduler を使った定期送信例 (lifespan 内):

    from backend.uptime_heartbeat import send_heartbeat, is_configured
    if is_configured():
        scheduler.add_job(
            send_heartbeat,
            "interval",
            minutes=1,
            id="better_stack_heartbeat",
            replace_existing=True,
        )

Better Stack 側で「heartbeat received within 90 seconds」の閾値を設定し,
ping が止まったら Slack/email/PagerDuty に alert.
"""
