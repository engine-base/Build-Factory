"""T-AI-06: Anthropic API rate-limit / overload 自動 retry (exponential backoff).

CLAUDE.md §3「自前実装必須 8 項目」の 1 つ。
LiteLLM や langchain-anthropic などのラッパには頼らず、tenacity 直叩きで
独自に retry policy を持つ (依存をミニマルに、ポリシーを完全制御するため)。

## ポリシー (AC 準拠)

- **EVENT**: 429 (rate_limit) / 529 (overloaded) → exponential backoff `2/4/8/16s` で 4 回 retry → fail
- **EVENT**: 5xx (transient) → 3 回 retry → fail
- **STATE**: retry 中も `session_id` + `idempotency-key` を保持 (重複起動防止)
- **UNWANTED**: 4xx (429 以外) は **retry しない** (即時 fail)

## 公開 API

- `@retryable_anthropic_call` デコレータ
- `with_retry(coro_factory, *, idempotency_key=None, session_id=None)` 動的呼び出し
- `RetryExhaustedError` → 全 retry を使い果たした際の例外

## 実装ノート

- Anthropic SDK 0.52+ の `anthropic.RateLimitError` / `APIStatusError` を判定
- SDK 未導入環境でも import-error にならないよう lazy import
- audit_logs に `anthropic_retry` event を残す (memory_service.emit_event 経由)
"""
from __future__ import annotations

import asyncio
import logging
from functools import wraps
from typing import Any, Awaitable, Callable, Optional, TypeVar

from tenacity import (
    AsyncRetrying, RetryError, retry_if_exception, stop_after_attempt,
    wait_exponential,
)
from tenacity.stop import stop_base

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ──────────────────────────────────────────
# 例外判定 (retry すべきか)
# ──────────────────────────────────────────

# AC: 429 (rate limit), 529 (overloaded), 5xx (transient) は retry。
# それ以外の 4xx は **retry しない**。
RETRYABLE_STATUS_CODES = {429, 529}
RETRYABLE_5XX_RANGE = range(500, 600)


def _status_code_of(exc: BaseException) -> Optional[int]:
    """Anthropic SDK / httpx / 一般 exception から HTTP status code を抽出。"""
    # anthropic.APIStatusError / RateLimitError は .status_code を持つ
    code = getattr(exc, "status_code", None)
    if isinstance(code, int):
        return code
    # httpx.HTTPStatusError は .response.status_code
    response = getattr(exc, "response", None)
    if response is not None:
        code = getattr(response, "status_code", None)
        if isinstance(code, int):
            return code
    return None


def is_retryable(exc: BaseException) -> bool:
    """Retry すべき例外かを判定。"""
    code = _status_code_of(exc)
    if code is None:
        # status_code を持たない例外 (ConnectionError 等) は retry 対象
        if isinstance(exc, (ConnectionError, TimeoutError, asyncio.TimeoutError)):
            return True
        return False
    if code in RETRYABLE_STATUS_CODES:
        return True
    if code in RETRYABLE_5XX_RANGE:
        return True
    # AC-UNWANTED: 4xx (429 以外) は明示的に False
    return False


def _is_5xx_only(exc: BaseException) -> bool:
    code = _status_code_of(exc)
    return code is not None and code in RETRYABLE_5XX_RANGE and code not in RETRYABLE_STATUS_CODES


# ──────────────────────────────────────────
# Retry policies
# ──────────────────────────────────────────

# 429/529: 4 回 retry (2/4/8/16s) = 5 試行
# 5xx: 3 回 retry = 4 試行
RATE_LIMIT_MAX_ATTEMPTS = 5
TRANSIENT_5XX_MAX_ATTEMPTS = 4

# wait = multiplier * exp_base^(attempt-1)、AC: 2/4/8/16s
# multiplier=2 / exp_base=2 / max=16 → 2*1=2, 2*2=4, 2*4=8, 2*8=16
RETRY_WAIT = wait_exponential(multiplier=2, min=2, max=16, exp_base=2)


class StopByExceptionType(stop_base):
    """例外種別ごとに異なる max-attempts を適用する stop 戦略。

    - 429/529 → RATE_LIMIT_MAX_ATTEMPTS
    - 5xx     → TRANSIENT_5XX_MAX_ATTEMPTS
    """

    def __call__(self, retry_state: Any) -> bool:
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        if exc is None:
            return False
        code = _status_code_of(exc)
        if code in RETRYABLE_STATUS_CODES:
            return retry_state.attempt_number >= RATE_LIMIT_MAX_ATTEMPTS
        if code is not None and code in RETRYABLE_5XX_RANGE:
            return retry_state.attempt_number >= TRANSIENT_5XX_MAX_ATTEMPTS
        # 接続系などは 5xx と同じ扱い (3 retry)
        return retry_state.attempt_number >= TRANSIENT_5XX_MAX_ATTEMPTS


RETRY_STOP = StopByExceptionType()


class RetryExhaustedError(RuntimeError):
    """全 retry を使い果たして失敗した際に raise される。"""

    def __init__(self, last_exc: BaseException, attempts: int) -> None:
        self.last_exc = last_exc
        self.attempts = attempts
        super().__init__(f"retry exhausted after {attempts} attempts: {last_exc!r}")


# ──────────────────────────────────────────
# 公開 API
# ──────────────────────────────────────────

async def with_retry(
    coro_factory: Callable[[], Awaitable[T]],
    *,
    idempotency_key: Optional[str] = None,
    session_id: Optional[int] = None,
    user_id: Optional[str] = None,
    label: str = "anthropic_call",
) -> T:
    """coroutine factory を retry policy 付きで呼び出す。

    coro_factory は **毎回新しい awaitable を返す callable** であること
    (awaitable は 1 回しか await できないため、同じインスタンスを使い回せない)。

    AC-STATE: 同じ idempotency_key で何度試行しても、論理的に同一リクエストとして
    扱われる前提 (Anthropic API は Idempotency-Key ヘッダをサポートする)。
    呼び出し元は coro_factory 内部で同じ key を毎回送る必要がある。
    """
    last_exc: Optional[BaseException] = None
    attempts = 0

    async def _attempt() -> T:
        nonlocal attempts
        attempts += 1
        return await coro_factory()

    try:
        async for attempt in AsyncRetrying(
            retry=retry_if_exception(is_retryable),
            stop=RETRY_STOP,
            wait=RETRY_WAIT,
            reraise=True,
        ):
            with attempt:
                return await _attempt()
    except BaseException as e:
        last_exc = e
        # AC-UNWANTED: 非 retryable 例外はそのまま raise (retry しない経路)
        if not is_retryable(e):
            await _audit("anthropic_non_retryable", e, attempts,
                         session_id=session_id, user_id=user_id,
                         label=label, idempotency_key=idempotency_key)
            raise
        # ここに到達するのは tenacity が exhausted で reraise した時のみ
        await _audit("anthropic_retry_exhausted", e, attempts,
                     session_id=session_id, user_id=user_id,
                     label=label, idempotency_key=idempotency_key)
        raise RetryExhaustedError(e, attempts) from e

    # mypy 用 unreachable
    raise RetryExhaustedError(last_exc or RuntimeError("no attempt"), attempts)


def retryable_anthropic_call(
    *, label: str = "anthropic_call",
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """async 関数を retry policy 付きでラップするデコレータ。

    使い方:
        @retryable_anthropic_call(label="messages.create")
        async def call(client, **kw):
            return await client.messages.create(**kw)
    """
    def deco(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            session_id = kwargs.pop("_session_id", None)
            user_id = kwargs.pop("_user_id", None)
            idem = kwargs.pop("_idempotency_key", None)
            return await with_retry(
                lambda: fn(*args, **kwargs),
                idempotency_key=idem,
                session_id=session_id,
                user_id=user_id,
                label=label,
            )
        return wrapper
    return deco


# ──────────────────────────────────────────
# audit_logs 連携
# ──────────────────────────────────────────

async def _audit(
    event_type: str,
    exc: BaseException,
    attempts: int,
    *,
    session_id: Optional[int],
    user_id: Optional[str],
    label: str,
    idempotency_key: Optional[str],
) -> None:
    """audit_logs に retry/exhaustion event を残す (失敗してもアプリは止めない)。"""
    try:
        from services.memory_service import emit_event
        await emit_event(
            event_type,
            session_id=session_id,
            user_id=user_id,
            detail={
                "label": label,
                "attempts": attempts,
                "status_code": _status_code_of(exc),
                "exception": type(exc).__name__,
                "idempotency_key": idempotency_key,
            },
        )
    except Exception as audit_err:
        logger.warning("audit emit failed: %s", audit_err)
