"""T-AI-06: Rate limit auto-retry — 5 AC.

Production artifact 完成済
(backend/services/anthropic_retry.py with_retry + retryable_anthropic_call
decorator + tenacity AsyncRetrying + StopByExceptionType + RETRY_WAIT).
本 module は **spec contract layer**.

AC マッピング:
  AC-1 UBIQUITOUS    : with_retry + retryable_anthropic_call +
                       RetryExhaustedError + is_retryable / tenacity
                       AsyncRetrying with reraise=True / no langgraph.
  AC-2 EVENT-DRIVEN  : 429/529 → 5 attempts (2/4/8/16s) /
                       5xx + ConnectionError/TimeoutError → 4 attempts
                       / exhaustion → RetryExhaustedError chain +
                       audit 'anthropic_retry_exhausted'.
  AC-3 STATE-DRIVEN  : idempotency_key + session_id + user_id
                       preserved across attempts / StopByExceptionType
                       inherits stop_base + status-aware decision.
  AC-4 OPTIONAL      : _status_code_of fallback to
                       exc.response.status_code / audit emit failure
                       logged but does not break retry path.
  AC-5 UNWANTED      : non-retryable 4xx → is_retryable False +
                       immediate reraise + 'anthropic_non_retryable'
                       audit / no langgraph / no hardcoded secret.
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
RETRY_PY = REPO_ROOT / "backend" / "services" / "anthropic_retry.py"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — public API + tenacity AsyncRetrying + reraise=True
# ══════════════════════════════════════════════════════════════════════


def test_ac1_module_exists():
    assert RETRY_PY.exists()


def test_ac1_with_retry_callable():
    from services.anthropic_retry import with_retry
    assert callable(with_retry)
    assert inspect.iscoroutinefunction(with_retry)


def test_ac1_with_retry_signature():
    from services.anthropic_retry import with_retry
    sig = inspect.signature(with_retry)
    params = sig.parameters
    assert "coro_factory" in params
    for name in ("idempotency_key", "session_id", "user_id", "label"):
        assert name in params
        assert params[name].kind == inspect.Parameter.KEYWORD_ONLY


def test_ac1_retryable_decorator_signature():
    from services.anthropic_retry import retryable_anthropic_call
    assert callable(retryable_anthropic_call)
    sig = inspect.signature(retryable_anthropic_call)
    p = sig.parameters.get("label")
    assert p is not None
    assert p.default == "anthropic_call"


def test_ac1_retry_exhausted_error_is_runtime_error():
    from services.anthropic_retry import RetryExhaustedError
    assert issubclass(RetryExhaustedError, RuntimeError)


def test_ac1_is_retryable_helper_exists():
    from services.anthropic_retry import is_retryable
    assert callable(is_retryable)


def test_ac1_uses_async_retrying_with_reraise_true():
    src = RETRY_PY.read_text(encoding="utf-8")
    assert "AsyncRetrying" in src
    assert re.search(
        r"AsyncRetrying\([\s\S]+?reraise\s*=\s*True",
        src,
    )
    assert "retry_if_exception(is_retryable)" in src


def test_ac1_no_langgraph_langchain_litellm():
    """Check actual import / from statements, not docstring mentions."""
    src = RETRY_PY.read_text(encoding="utf-8")
    # strip module + class + function docstrings (triple-quoted) and # comments
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"'''[\s\S]*?'''", "", src)
    src = re.sub(r"#[^\n]*", "", src)
    src = src.lower()
    for bad in ("langgraph", "langchain", "litellm"):
        assert f"import {bad}" not in src, f"forbidden import {bad}"
        assert f"from {bad}" not in src, f"forbidden from {bad}"


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — backoff 2/4/8/16s + max attempts + retry exhausted
# ══════════════════════════════════════════════════════════════════════


def test_ac2_retryable_status_codes_429_529():
    from services.anthropic_retry import RETRYABLE_STATUS_CODES
    assert 429 in RETRYABLE_STATUS_CODES
    assert 529 in RETRYABLE_STATUS_CODES


def test_ac2_max_attempts_constants():
    from services.anthropic_retry import (
        RATE_LIMIT_MAX_ATTEMPTS, TRANSIENT_5XX_MAX_ATTEMPTS,
    )
    assert RATE_LIMIT_MAX_ATTEMPTS == 5  # 4 retries (2/4/8/16s) + 1 initial
    assert TRANSIENT_5XX_MAX_ATTEMPTS == 4  # 3 retries + 1 initial


def test_ac2_wait_exponential_2_to_16():
    src = RETRY_PY.read_text(encoding="utf-8")
    assert re.search(
        r"wait_exponential\(\s*multiplier\s*=\s*2[\s\S]+?min\s*=\s*2[\s\S]+?max\s*=\s*16[\s\S]+?exp_base\s*=\s*2",
        src,
    )


def test_ac2_5xx_or_conn_timeout_retried():
    """ConnectionError / TimeoutError / asyncio.TimeoutError + 5xx も retry."""
    import asyncio
    from services.anthropic_retry import is_retryable

    class _Resp:
        def __init__(self, code: int):
            self.status_code = code

    class _Err(Exception):
        def __init__(self, code: int):
            self.status_code = code

    # 5xx
    assert is_retryable(_Err(500)) is True
    assert is_retryable(_Err(503)) is True
    assert is_retryable(_Err(599)) is True
    # ConnectionError / TimeoutError
    assert is_retryable(ConnectionError("conn fail")) is True
    assert is_retryable(TimeoutError("slow")) is True
    assert is_retryable(asyncio.TimeoutError()) is True


def test_ac2_exhaustion_raises_retry_exhausted_with_chain():
    src = RETRY_PY.read_text(encoding="utf-8")
    # raise RetryExhaustedError(e, attempts) from e
    assert re.search(
        r"raise\s+RetryExhaustedError\(e,\s*attempts\)\s+from\s+e",
        src,
    )
    assert "anthropic_retry_exhausted" in src


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — idempotency_key preserved + StopByExceptionType
# ══════════════════════════════════════════════════════════════════════


def test_ac3_stop_by_exception_type_inherits_stop_base():
    from services.anthropic_retry import StopByExceptionType
    from tenacity.stop import stop_base
    assert issubclass(StopByExceptionType, stop_base)


def test_ac3_stop_picks_rate_limit_vs_5xx_max():
    """StopByExceptionType.__call__ should branch on status_code."""
    src = RETRY_PY.read_text(encoding="utf-8")
    m = re.search(
        r"class StopByExceptionType[\s\S]+?(?=\n\nclass |\nRETRY_STOP|\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "RATE_LIMIT_MAX_ATTEMPTS" in body
    assert "TRANSIENT_5XX_MAX_ATTEMPTS" in body
    assert "RETRYABLE_STATUS_CODES" in body
    assert "attempt_number" in body


def test_ac3_decorator_routes_idempotency_session_user_id():
    """retryable_anthropic_call extracts _session_id / _user_id /
    _idempotency_key kwargs and passes them to with_retry."""
    src = RETRY_PY.read_text(encoding="utf-8")
    m = re.search(
        r"def retryable_anthropic_call[\s\S]+?(?=\n\n#|\nasync def _audit|\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert re.search(r"_session_id", body)
    assert re.search(r"_user_id", body)
    assert re.search(r"_idempotency_key", body)
    assert "with_retry(" in body
    assert "idempotency_key=idem" in body


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — status_code fallback via response + audit failure log
# ══════════════════════════════════════════════════════════════════════


def test_ac4_status_code_fallback_to_response_attr():
    from services.anthropic_retry import _status_code_of

    class _Resp:
        def __init__(self, code: int):
            self.status_code = code

    class _HttpxStyle(Exception):
        def __init__(self, code: int):
            self.response = _Resp(code)

    err = _HttpxStyle(503)
    assert _status_code_of(err) == 503


def test_ac4_status_code_direct_attr_takes_precedence():
    from services.anthropic_retry import _status_code_of

    class _Direct(Exception):
        def __init__(self):
            self.status_code = 429
    assert _status_code_of(_Direct()) == 429


def test_ac4_audit_emit_failure_logged_not_raised():
    src = RETRY_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def _audit[\s\S]+?(?=\n(?:async )?def |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    assert "try:" in body
    assert "except Exception as audit_err" in body
    assert "logger.warning" in body


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — non-retryable 4xx returns False + immediate raise + audit
# ══════════════════════════════════════════════════════════════════════


def test_ac5_non_retryable_4xx_returns_false():
    from services.anthropic_retry import is_retryable

    class _Err(Exception):
        def __init__(self, code: int):
            self.status_code = code

    for code in (400, 401, 403, 404, 422):
        assert is_retryable(_Err(code)) is False, (
            f"status {code} should NOT be retryable"
        )


def test_ac5_non_retryable_immediate_reraise_and_audit():
    """with_retry の except 経路で is_retryable False → raise + audit."""
    src = RETRY_PY.read_text(encoding="utf-8")
    m = re.search(
        r"async def with_retry[\s\S]+?(?=\n\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    # if not is_retryable(e): emit audit; raise
    assert "anthropic_non_retryable" in body
    assert re.search(
        r"if\s+not\s+is_retryable\(e\)[\s\S]+?raise\b",
        body,
    )


def test_ac5_no_hardcoded_supabase_or_anthropic_key():
    src = RETRY_PY.read_text(encoding="utf-8")
    assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_ai_06_canonical_ears():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-AI-06"), None)
    assert t is not None
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == [
        "UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED",
    ]


def test_tickets_t_ai_06_has_adr_link_and_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-AI-06"), None)
    assert t.get("adr_link") is not None
    assert "ADR-010" in t["adr_link"]
    files = t.get("existing_files", [])
    assert "backend/services/anthropic_retry.py" in files


def test_tickets_t_ai_06_ac_mentions_concrete_symbols():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-AI-06"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "with_retry",
        "retryable_anthropic_call",
        "RetryExhaustedError",
        "is_retryable",
        "AsyncRetrying",
        "wait_exponential",
        "StopByExceptionType",
        "RATE_LIMIT_MAX_ATTEMPTS",
        "TRANSIENT_5XX_MAX_ATTEMPTS",
        "anthropic_retry_exhausted",
        "anthropic_non_retryable",
        "ADR-010",
    ):
        assert sym in full, f"T-AI-06 AC missing: {sym}"
