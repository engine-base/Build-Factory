"""T-S0-10: Sentry 設定 (Backend / FastAPI).

## 目的

Build-Factory backend で error / performance を Sentry に送信する設定基盤.
構造化ログ (T-S0-11 structlog) は ephemeral, audit_logs (DB) は監査 trail,
Sentry は error/exception reporting に特化した 3 つ目の observability 層.

## 3 層 observability の役割分担

| 機構           | 目的            | 永続     | 対象                           |
|----------------|-----------------|----------|--------------------------------|
| structlog/pino | 人間 / 監視     | ephemeral| 全ログ                         |
| audit_logs     | 監査 trail      | DB 永続  | 重要イベントのみ              |
| Sentry         | error / perf    | Sentry   | 例外 / slow request / release |

3 つは独立: Sentry が落ちても structlog/audit_logs は動く. 逆も真.

## Graceful degradation

sentry-sdk が未インストール / SENTRY_DSN 未設定の場合, 本 module は import OK
で全 API が no-op になる (既存コードに `try-except import sentry` を書く必要なし).

## 環境変数

- SENTRY_DSN          : DSN (省略時は disabled, 起動時 warning)
- SENTRY_ENVIRONMENT  : production / staging / development (default: development)
- SENTRY_TRACES_SAMPLE_RATE : 0.0-1.0 (default 0.1, prod では適切に調整)
- SENTRY_RELEASE      : git sha 等 (CI で auto inject 推奨)

## ADR-010 / structlog 統合

claude-agent-sdk runner (T-S0-08) が発する Anthropic API error は本 Sentry 経由で
捕捉される. T-AI-06 (rate limit retry) と協調: retry 全失敗時のみ Sentry に
送信 (rate limit は通常 retry で回復するため毎回 Sentry 通知は noise).

## AC マッピング

  AC-1 UBIQUITOUS    : init_sentry() / capture_exception() / set_user() / set_tag()
                       を公開. sentry-sdk 未インストール / DSN 未設定で graceful no-op.
  AC-2 EVENT-DRIVEN  : init_sentry() で DSN + env 設定 / capture で event 送信.
  AC-3 STATE-DRIVEN  : sentry-sdk 未インストール時 stub 動作 / 既存 logger 不変.
  AC-4 UNWANTED      : invalid sample_rate (range outside 0-1) で ValueError /
                       PII / secret を default で送らない (send_default_pii=False).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    import sentry_sdk as _sentry_sdk
    _SENTRY_AVAILABLE = True
except ImportError:  # pragma: no cover (CI で sentry-sdk 入れる)
    _sentry_sdk = None
    _SENTRY_AVAILABLE = False


# ──────────────────────────────────────────────────────────────────────
# Public flags / constants
# ──────────────────────────────────────────────────────────────────────


def is_sentry_available() -> bool:
    return _SENTRY_AVAILABLE


VALID_ENVIRONMENTS = ("development", "staging", "production", "ci", "test")
_INITIALIZED = False
_LAST_INIT_RESULT: Optional[bool] = None


# ──────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────


def _validate_sample_rate(value: Any, *, field: str) -> float:
    if not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number (0.0-1.0)")
    rate = float(value)
    if rate < 0.0 or rate > 1.0:
        raise ValueError(
            f"{field} must be in range [0.0, 1.0], got {rate}"
        )
    return rate


def _validate_environment(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("environment must be string")
    s = value.strip().lower()
    if s not in VALID_ENVIRONMENTS:
        raise ValueError(
            f"environment must be one of {VALID_ENVIRONMENTS}, got {value!r}"
        )
    return s


# ──────────────────────────────────────────────────────────────────────
# Initialization (idempotent)
# ──────────────────────────────────────────────────────────────────────


def init_sentry(
    dsn: Optional[str] = None,
    environment: Optional[str] = None,
    traces_sample_rate: float = 0.1,
    release: Optional[str] = None,
    send_default_pii: bool = False,
) -> bool:
    """Initialize Sentry SDK.

    Args:
        dsn: Sentry DSN. None なら SENTRY_DSN env 参照. 両方なし → no-op.
        environment: development / staging / production / ci / test.
                     None なら SENTRY_ENVIRONMENT env または "development".
        traces_sample_rate: 0.0-1.0. perf tracing rate.
        release: git sha 等. None なら SENTRY_RELEASE env.
        send_default_pii: PII (cookie / IP) を default で送るか. **default False**.

    Returns:
        bool: 実際に初期化したか (sentry_sdk 未インストール / DSN なし → False).
    """
    global _INITIALIZED, _LAST_INIT_RESULT
    if _INITIALIZED:
        return bool(_LAST_INIT_RESULT)

    rate = _validate_sample_rate(traces_sample_rate, field="traces_sample_rate")
    # environment が指定済かつ str 以外なら type エラー (env fallback の前に判定)
    if environment is not None and not isinstance(environment, str):
        raise ValueError(
            f"environment must be string or None, got {type(environment).__name__}"
        )
    env_raw = environment or os.environ.get("SENTRY_ENVIRONMENT", "development")
    env = _validate_environment(env_raw)
    if not isinstance(send_default_pii, bool):
        raise ValueError("send_default_pii must be bool")

    dsn = dsn or os.environ.get("SENTRY_DSN")

    if not _SENTRY_AVAILABLE:
        logger.warning(
            "sentry-sdk not installed; skip init (graceful)"
        )
        _INITIALIZED = True
        _LAST_INIT_RESULT = False
        return False

    if not dsn:
        logger.warning(
            "SENTRY_DSN not configured; Sentry disabled (env=%s)", env
        )
        _INITIALIZED = True
        _LAST_INIT_RESULT = False
        return False

    rel = release or os.environ.get("SENTRY_RELEASE")
    _sentry_sdk.init(
        dsn=dsn,
        environment=env,
        traces_sample_rate=rate,
        release=rel,
        send_default_pii=send_default_pii,
        # AC-4: PII 排除 / cookie / authorization header を default で送らない
        # max_breadcrumbs を制限 (memory 効率)
        max_breadcrumbs=50,
    )
    _INITIALIZED = True
    _LAST_INIT_RESULT = True
    logger.info(
        "Sentry initialized (env=%s, sample_rate=%s, release=%s)",
        env, rate, rel,
    )
    return True


# ──────────────────────────────────────────────────────────────────────
# Public API (graceful no-op if sentry-sdk not available)
# ──────────────────────────────────────────────────────────────────────


def capture_exception(error: Optional[BaseException] = None) -> Optional[str]:
    """Capture an exception. Returns event_id or None."""
    if not _SENTRY_AVAILABLE:
        return None
    return _sentry_sdk.capture_exception(error)


def capture_message(message: str, level: str = "info") -> Optional[str]:
    """Capture a message event. Returns event_id or None."""
    if not _SENTRY_AVAILABLE:
        return None
    if not isinstance(message, str) or not message.strip():
        raise ValueError("message must be non-empty string")
    valid_levels = ("debug", "info", "warning", "error", "fatal")
    if level not in valid_levels:
        raise ValueError(f"level must be one of {valid_levels}")
    return _sentry_sdk.capture_message(message, level=level)


def set_user(user_id: Optional[str] = None, **kwargs: Any) -> None:
    """Bind user context to current scope."""
    if not _SENTRY_AVAILABLE:
        return
    if user_id is not None and not isinstance(user_id, str):
        raise ValueError("user_id must be string or None")
    user_dict: dict = {}
    if user_id:
        user_dict["id"] = user_id
    user_dict.update(kwargs)
    if user_dict:
        _sentry_sdk.set_user(user_dict)
    else:
        _sentry_sdk.set_user(None)  # clear


def set_tag(key: str, value: str) -> None:
    """Set a tag on current scope."""
    if not _SENTRY_AVAILABLE:
        return
    if not isinstance(key, str) or not key.strip():
        raise ValueError("tag key must be non-empty string")
    if not isinstance(value, str):
        value = str(value)
    _sentry_sdk.set_tag(key, value)


def add_breadcrumb(
    *,
    category: str,
    message: str,
    level: str = "info",
    data: Optional[dict] = None,
) -> None:
    """Add a breadcrumb to current scope."""
    if not _SENTRY_AVAILABLE:
        return
    if not isinstance(category, str) or not category.strip():
        raise ValueError("category must be non-empty string")
    if not isinstance(message, str):
        raise ValueError("message must be string")
    _sentry_sdk.add_breadcrumb(
        category=category, message=message, level=level, data=data or {},
    )


def reset_for_tests() -> None:
    """Reset initialization flag (test-only)."""
    global _INITIALIZED, _LAST_INIT_RESULT
    _INITIALIZED = False
    _LAST_INIT_RESULT = None
