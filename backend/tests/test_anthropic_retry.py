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


# ──────────────────────────────────────────
# AC 全網羅 補完 + cov 100% (missing lines 76 / 86-87 / 114 / 121 / 189)
# ──────────────────────────────────────────

import sys
import types
from services import anthropic_retry as ar


# ----------------- missing 76: status_code なし & 非ConnectionError → False ----


def test_is_retryable_generic_exception_returns_false() -> None:
    """status_code が抽出できない一般例外 (ConnectionError 系でもない) は retry しない."""
    assert is_retryable(ValueError("bad")) is False
    assert is_retryable(KeyError("missing")) is False


# ----------------- missing 86-87: _is_5xx_only -------------------------------


def test_is_5xx_only_distinguishes_from_429_529() -> None:
    """5xx の中で 429/529 を除外する内部判定 (内部関数だが retry policy で参照)."""
    assert ar._is_5xx_only(_FakeAPIError(500)) is True
    assert ar._is_5xx_only(_FakeAPIError(503)) is True
    assert ar._is_5xx_only(_FakeAPIError(429)) is False
    assert ar._is_5xx_only(_FakeAPIError(529)) is False  # 529 は 5xx だが 429 系扱い


# ----------------- missing 114: StopByExceptionType outcome=None -------------


def test_stop_by_exception_type_returns_false_when_no_exception() -> None:
    """outcome.exception() が None の retry_state では stop=False (続行)."""

    class _Outcome:
        def exception(self): return None

    class _State:
        outcome = _Outcome()
        attempt_number = 1

    assert ar.RETRY_STOP(_State()) is False


# ----------------- missing 121: ConnectionError は 5xx と同じ 3 retry --------


@pytest.mark.asyncio
async def test_connection_error_uses_5xx_retry_count() -> None:
    """AC: 接続系例外は 3 retry (5xx と同じ)、 総試行 4 回."""
    counter = {"n": 0}

    async def call():
        counter["n"] += 1
        raise ConnectionError("network down")

    with pytest.raises(RetryExhaustedError):
        await with_retry(call)
    assert counter["n"] == 4  # 1 + 3 retry


# ----------------- AC-STATE: idempotency_key / session_id 維持 ---------------


def _install_audit_recorder():
    """services.memory_service.emit_event を fake 化、 呼び出しを記録."""
    captured: list[dict] = []

    fake_mod = types.ModuleType("services.memory_service")

    async def fake_emit_event(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({
            "event_type": event_type,
            "session_id": session_id,
            "user_id": user_id,
            "detail": detail or {},
        })

    fake_mod.emit_event = fake_emit_event
    sys.modules["services.memory_service"] = fake_mod
    return captured


@pytest.mark.asyncio
async def test_retry_preserves_idempotency_key_through_all_attempts() -> None:
    """AC-STATE: 429 retry 中、 idempotency_key と session_id が保持され、
    最終 audit log に同じ値が記録される."""
    captured = _install_audit_recorder()

    counter = {"n": 0}

    async def call():
        counter["n"] += 1
        raise _FakeAPIError(429)

    try:
        with pytest.raises(RetryExhaustedError):
            await with_retry(
                call,
                idempotency_key="key-fixed-001",
                session_id=42,
                user_id="masato",
                label="messages.create",
            )
        # exhausted event が emit され、 detail に idempotency_key が含まれる
        assert len(captured) == 1
        ev = captured[0]
        assert ev["event_type"] == "anthropic_retry_exhausted"
        assert ev["session_id"] == 42
        assert ev["user_id"] == "masato"
        assert ev["detail"]["idempotency_key"] == "key-fixed-001"
        assert ev["detail"]["label"] == "messages.create"
        assert ev["detail"]["status_code"] == 429
        assert ev["detail"]["attempts"] == 5
    finally:
        sys.modules.pop("services.memory_service", None)


@pytest.mark.asyncio
async def test_non_retryable_audit_emits_with_idempotency_key() -> None:
    """AC-STATE inverse: 非 retryable (400) でも audit に idempotency_key が記録."""
    captured = _install_audit_recorder()

    async def call():
        raise _FakeAPIError(400)

    try:
        with pytest.raises(_FakeAPIError):
            await with_retry(
                call,
                idempotency_key="key-noretry-002",
                session_id=7,
                user_id="alice",
                label="messages.create",
            )
        assert len(captured) == 1
        ev = captured[0]
        assert ev["event_type"] == "anthropic_non_retryable"
        assert ev["detail"]["idempotency_key"] == "key-noretry-002"
        assert ev["detail"]["status_code"] == 400
    finally:
        sys.modules.pop("services.memory_service", None)


@pytest.mark.asyncio
async def test_audit_failure_does_not_break_caller() -> None:
    """audit 経路で例外が出てもアプリは止めない (log warning のみ)."""
    fake_mod = types.ModuleType("services.memory_service")

    async def boom(*a, **kw):
        raise RuntimeError("audit DB down")

    fake_mod.emit_event = boom
    sys.modules["services.memory_service"] = fake_mod

    async def call():
        raise _FakeAPIError(400)

    try:
        # audit が失敗しても _FakeAPIError が伝播する (audit エラーで上書きされない)
        with pytest.raises(_FakeAPIError):
            await with_retry(call, idempotency_key="x")
    finally:
        sys.modules.pop("services.memory_service", None)


@pytest.mark.asyncio
async def test_5xx_recovery_no_audit_emit() -> None:
    """途中で復旧した場合 (5xx → 200) は audit emit されない (成功 path)."""
    captured = _install_audit_recorder()

    counter = {"n": 0}

    async def call():
        counter["n"] += 1
        if counter["n"] < 3:
            raise _FakeAPIError(503)
        return "recovered"

    try:
        result = await with_retry(call, idempotency_key="key-recover")
        assert result == "recovered"
        assert counter["n"] == 3
        # 成功時は audit を emit しない
        assert captured == []
    finally:
        sys.modules.pop("services.memory_service", None)


# ----------------- decorator + _idempotency_key 統合 -------------------------


@pytest.mark.asyncio
async def test_decorator_propagates_idempotency_key_to_audit() -> None:
    """retryable_anthropic_call デコレータ経由でも idempotency_key が audit に乗る."""
    captured = _install_audit_recorder()

    @retryable_anthropic_call(label="messages.create")
    async def call(prompt: str) -> str:
        raise _FakeAPIError(529)

    try:
        with pytest.raises(RetryExhaustedError):
            await call(
                "hi",
                _idempotency_key="key-deco-003",
                _session_id=99,
                _user_id="bob",
            )
        assert len(captured) == 1
        assert captured[0]["detail"]["idempotency_key"] == "key-deco-003"
        assert captured[0]["session_id"] == 99
    finally:
        sys.modules.pop("services.memory_service", None)


# ----------------- timeout / asyncio.TimeoutError も retryable --------------


def test_is_retryable_timeout_error() -> None:
    """TimeoutError は retry 対象."""
    assert is_retryable(TimeoutError("slow")) is True
    import asyncio as _a
    assert is_retryable(_a.TimeoutError()) is True


@pytest.mark.asyncio
async def test_timeout_error_retries_3_times() -> None:
    counter = {"n": 0}

    async def call():
        counter["n"] += 1
        raise TimeoutError("slow")

    with pytest.raises(RetryExhaustedError):
        await with_retry(call)
    assert counter["n"] == 4  # 5xx と同じ retry 戦略


# ----------------- response.status_code が int でない場合 -------------------


def test_status_code_extraction_returns_none_when_non_int() -> None:
    """status_code が int でないなら None を返す (status を持たない場合)."""

    class _NoneCode:
        status_code = "not-an-int"
        response = None

    assert _status_code_of(_NoneCode()) is None  # type: ignore[arg-type]
