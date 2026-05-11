"""T-AI-06: tenacity retry wrapper の AC テスト.

AC:
  - EVENT 429/529 → 2/4/8/16s で 4 retry → fail (5 attempts)
  - EVENT 5xx → 3 retry → fail (4 attempts)
  - STATE retry 中も session_id + idempotency-key 保持
  - UNWANTED 4xx (429 以外) → retry **しない**
"""
from __future__ import annotations

from typing import Optional
from unittest.mock import patch

import pytest

from services.anthropic_retry import (
    RETRY_WAIT, RetryExhaustedError, _status_code_of, is_retryable,
    retryable_anthropic_call, with_retry,
)


class _FakeAPIError(Exception):
    """Anthropic SDK の APIStatusError 相当 (status_code 属性のみ)。"""
    def __init__(self, status_code: int) -> None:
        super().__init__(f"status={status_code}")
        self.status_code = status_code


# ──────────────────────────────────────────
# 例外判定
# ──────────────────────────────────────────

def test_status_code_extraction_from_attribute() -> None:
    assert _status_code_of(_FakeAPIError(429)) == 429


def test_status_code_extraction_from_response() -> None:
    class WithResponse(Exception):
        def __init__(self) -> None:
            class R: status_code = 503
            self.response = R()
    assert _status_code_of(WithResponse()) == 503


def test_is_retryable_429() -> None:
    assert is_retryable(_FakeAPIError(429)) is True


def test_is_retryable_529() -> None:
    assert is_retryable(_FakeAPIError(529)) is True


def test_is_retryable_500() -> None:
    assert is_retryable(_FakeAPIError(500)) is True


def test_is_retryable_503() -> None:
    assert is_retryable(_FakeAPIError(503)) is True


def test_is_NOT_retryable_400() -> None:
    """AC-UNWANTED: 4xx (429 以外) は retry しない。"""
    assert is_retryable(_FakeAPIError(400)) is False


def test_is_NOT_retryable_401() -> None:
    assert is_retryable(_FakeAPIError(401)) is False


def test_is_NOT_retryable_404() -> None:
    assert is_retryable(_FakeAPIError(404)) is False


def test_is_retryable_connection_error() -> None:
    assert is_retryable(ConnectionError("network")) is True


# ──────────────────────────────────────────
# Retry 動作 (with_retry)
# ──────────────────────────────────────────

@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """テストでは指数バックオフの sleep をスキップ (高速化)。"""
    import asyncio
    async def _instant(*a, **k):
        return None
    monkeypatch.setattr(asyncio, "sleep", _instant)


@pytest.mark.asyncio
async def test_429_retries_4_times_then_fails() -> None:
    """AC-EVENT: 429 → 4 retry (2/4/8/16s) → fail。総試行 5 回。"""
    counter = {"n": 0}
    async def call():
        counter["n"] += 1
        raise _FakeAPIError(429)
    with pytest.raises(RetryExhaustedError):
        await with_retry(call)
    assert counter["n"] == 5  # 1 初回 + 4 retry


@pytest.mark.asyncio
async def test_529_overloaded_same_as_429() -> None:
    counter = {"n": 0}
    async def call():
        counter["n"] += 1
        raise _FakeAPIError(529)
    with pytest.raises(RetryExhaustedError):
        await with_retry(call)
    assert counter["n"] == 5


@pytest.mark.asyncio
async def test_5xx_retries_3_times_then_fails() -> None:
    """AC-EVENT: 5xx → 3 retry → fail。総試行 4 回。"""
    counter = {"n": 0}
    async def call():
        counter["n"] += 1
        raise _FakeAPIError(503)
    with pytest.raises(RetryExhaustedError):
        await with_retry(call)
    assert counter["n"] == 4  # 1 初回 + 3 retry


@pytest.mark.asyncio
async def test_400_does_not_retry_at_all() -> None:
    """AC-UNWANTED: 4xx (429 以外) は retry **しない**。"""
    counter = {"n": 0}
    async def call():
        counter["n"] += 1
        raise _FakeAPIError(400)
    with pytest.raises(_FakeAPIError):
        await with_retry(call)
    assert counter["n"] == 1  # retry なし


@pytest.mark.asyncio
async def test_401_does_not_retry() -> None:
    counter = {"n": 0}
    async def call():
        counter["n"] += 1
        raise _FakeAPIError(401)
    with pytest.raises(_FakeAPIError):
        await with_retry(call)
    assert counter["n"] == 1


@pytest.mark.asyncio
async def test_succeeds_on_2nd_attempt() -> None:
    """1 回目 429 → 2 回目成功 → return value。"""
    counter = {"n": 0}
    async def call():
        counter["n"] += 1
        if counter["n"] < 2:
            raise _FakeAPIError(429)
        return "ok"
    result = await with_retry(call)
    assert result == "ok"
    assert counter["n"] == 2


@pytest.mark.asyncio
async def test_succeeds_first_time_no_retry() -> None:
    counter = {"n": 0}
    async def call():
        counter["n"] += 1
        return 42
    result = await with_retry(call)
    assert result == 42
    assert counter["n"] == 1


# ──────────────────────────────────────────
# Decorator
# ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_decorator_passes_through_args_and_retries() -> None:
    counter = {"n": 0}

    @retryable_anthropic_call(label="test.call")
    async def call(x: int, *, y: int) -> int:
        counter["n"] += 1
        if counter["n"] < 2:
            raise _FakeAPIError(429)
        return x + y

    result = await call(10, y=5)
    assert result == 15
    assert counter["n"] == 2


@pytest.mark.asyncio
async def test_decorator_strips_internal_kwargs() -> None:
    """_session_id / _idempotency_key / _user_id は wrapped fn に渡らない。"""
    captured: dict = {}

    @retryable_anthropic_call()
    async def call(**kw):
        captured.update(kw)
        return "ok"

    await call(payload="x", _session_id=42, _user_id="u1", _idempotency_key="k1")
    assert captured == {"payload": "x"}


# ──────────────────────────────────────────
# Backoff schedule (2/4/8/16s)
# ──────────────────────────────────────────

def test_wait_schedule_starts_at_2_seconds() -> None:
    """初回 retry の wait は 2s であるべき (AC: '2s, 4s, 8s, 16s')。"""
    from tenacity import RetryCallState
    # tenacity の wait はカスタム RetryCallState を渡すと評価可能
    class _S:
        attempt_number = 1  # = 1 回目失敗後 → retry #1 = 2s
    # wait_exponential(multiplier=1, min=2, max=16, exp_base=2)
    # → wait = min(max(2^attempt_number * 1, 2), 16)
    # attempt_number=1 → 2^1=2 → 2s
    # attempt_number=2 → 2^2=4 → 4s
    # attempt_number=3 → 2^3=8 → 8s
    # attempt_number=4 → 2^4=16 → 16s
    assert RETRY_WAIT(_S()) == 2.0  # type: ignore[arg-type]


def test_wait_schedule_doubles_each_attempt() -> None:
    class _S:
        def __init__(self, n: int) -> None:
            self.attempt_number = n
    assert RETRY_WAIT(_S(1)) == 2.0   # type: ignore[arg-type]
    assert RETRY_WAIT(_S(2)) == 4.0   # type: ignore[arg-type]
    assert RETRY_WAIT(_S(3)) == 8.0   # type: ignore[arg-type]
    assert RETRY_WAIT(_S(4)) == 16.0  # type: ignore[arg-type]
