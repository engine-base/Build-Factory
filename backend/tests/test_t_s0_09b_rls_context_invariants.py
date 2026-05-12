"""T-S0-09b: RLS context helper — 5 AC 機械 invariant 検証.

NEW BE module. backend/services/rls_context.py を新規追加して
auth_middleware から PostgreSQL session に user_id を伝播する.

AC マッピング:
  AC-1 UBIQUITOUS    : 6 公開 symbol / DEV_BYPASS_USER_ID = auth_middleware
                       DEV_USER.sub と一致 / SET LOCAL.
  AC-2 EVENT-DRIVEN  : with_request_user CM の success / exception 出口で
                       reset / RESET 使用.
  AC-3 STATE-DRIVEN  : prod で bypass 不可 (bf_env_guard.is_prod 経由) /
                       no langgraph / langchain / litellm.
  AC-4 OPTIONAL      : custom_permissions JSON を SET LOCAL に safe escape
                       で渡す.
  AC-5 UNWANTED      : empty / non-string / over 200 / single-quote /
                       null-byte で RLSContextError BEFORE SET LOCAL /
                       reset 失敗で re-raise / no force_bypass.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import re
from pathlib import Path

import pytest

from services import rls_context as rc


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE = REPO_ROOT / "backend" / "services" / "rls_context.py"
AUTH_MW = REPO_ROOT / "backend" / "services" / "auth_middleware.py"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"


class FakeConn:
    """async DB connection の最小 stub."""

    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []
        self.fail_on_reset = False

    async def execute(self, query: str, *args):
        if self.fail_on_reset and "RESET" in query:
            raise RuntimeError("simulated reset failure")
        self.calls.append((query, args))


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — 6 public symbols + DEV_BYPASS_USER_ID match
# ══════════════════════════════════════════════════════════════════════


def test_ac1_module_exists():
    assert MODULE.exists()


@pytest.mark.parametrize("sym", [
    "set_request_user",
    "reset_request_user",
    "with_request_user",
    "DEV_BYPASS_USER_ID",
    "MAX_USER_ID_LEN",
    "RLSContextError",
    "effective_user_id_for_request",
    "is_bypass_allowed",
])
def test_ac1_public_symbol(sym):
    assert hasattr(rc, sym), f"rls_context missing: {sym}"


def test_ac1_max_user_id_len_200():
    assert rc.MAX_USER_ID_LEN == 200


def test_ac1_dev_bypass_user_id_matches_auth_middleware():
    """cross-module invariant: DEV_BYPASS_USER_ID = auth_middleware DEV_USER.sub."""
    src = AUTH_MW.read_text(encoding="utf-8")
    # DEV_USER の sub = "00000000-..."
    m = re.search(r'"sub"\s*:\s*"([^"]+)"', src)
    assert m
    auth_sub = m.group(1)
    assert rc.DEV_BYPASS_USER_ID == auth_sub, (
        f"DEV_BYPASS_USER_ID drift: rls_context={rc.DEV_BYPASS_USER_ID} "
        f"vs auth_middleware={auth_sub}"
    )


def test_ac1_rls_context_error_is_value_error_subclass():
    assert issubclass(rc.RLSContextError, ValueError)


def test_ac1_set_request_user_is_async():
    assert inspect.iscoroutinefunction(rc.set_request_user)


def test_ac1_reset_request_user_is_async():
    assert inspect.iscoroutinefunction(rc.reset_request_user)


def test_ac1_with_request_user_is_async_context_manager():
    """@asynccontextmanager decorator が使われている."""
    src = MODULE.read_text(encoding="utf-8")
    assert "@asynccontextmanager" in src


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — set / reset / context manager exits
# ══════════════════════════════════════════════════════════════════════


def test_ac2_set_request_user_issues_set_local_for_sub():
    conn = FakeConn()
    asyncio.run(rc.set_request_user(conn, "user-123"))
    # at least one SET LOCAL request.jwt.claim.sub
    joined = " ".join(c[0] for c in conn.calls)
    assert "request.jwt.claim.sub" in joined


def test_ac2_set_request_user_issues_set_local_for_claims():
    conn = FakeConn()
    asyncio.run(rc.set_request_user(conn, "user-123"))
    joined = " ".join(c[0] for c in conn.calls)
    assert "request.jwt.claims" in joined


def test_ac2_reset_request_user_uses_RESET():
    conn = FakeConn()
    asyncio.run(rc.reset_request_user(conn))
    joined = " ".join(c[0] for c in conn.calls)
    assert "RESET request.jwt.claim.sub" in joined
    assert "RESET request.jwt.claims" in joined


def test_ac2_with_request_user_calls_reset_on_success():
    async def _run():
        conn = FakeConn()
        async with rc.with_request_user(conn, "user-success"):
            pass
        return conn
    conn = asyncio.run(_run())
    joined = " ".join(c[0] for c in conn.calls)
    assert "RESET" in joined


def test_ac2_with_request_user_calls_reset_on_exception():
    """exception path でも reset が呼ばれる."""
    async def _run():
        conn = FakeConn()
        try:
            async with rc.with_request_user(conn, "user-err"):
                raise RuntimeError("simulated")
        except RuntimeError:
            pass
        return conn
    conn = asyncio.run(_run())
    joined = " ".join(c[0] for c in conn.calls)
    assert "RESET" in joined


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — prod bypass forbidden / no AI stack import
# ══════════════════════════════════════════════════════════════════════


def test_ac3_is_bypass_allowed_false_in_prod(monkeypatch):
    monkeypatch.setenv("BF_ENV", "prod")
    monkeypatch.setenv("BUILD_FACTORY_DEV_BYPASS_AUTH", "1")
    import importlib
    importlib.reload(rc)
    assert rc.is_bypass_allowed() is False


def test_ac3_is_bypass_allowed_true_in_dev_with_env_flag(monkeypatch):
    monkeypatch.setenv("BF_ENV", "dev")
    monkeypatch.setenv("BUILD_FACTORY_DEV_BYPASS_AUTH", "1")
    import importlib
    importlib.reload(rc)
    assert rc.is_bypass_allowed() is True


def test_ac3_effective_user_id_raises_in_prod_without_user(monkeypatch):
    monkeypatch.setenv("BF_ENV", "prod")
    monkeypatch.setenv("BUILD_FACTORY_DEV_BYPASS_AUTH", "1")
    import importlib
    importlib.reload(rc)
    with pytest.raises(rc.RLSContextError):
        rc.effective_user_id_for_request(None)


def test_ac3_effective_user_id_uses_dev_bypass_in_dev(monkeypatch):
    monkeypatch.setenv("BF_ENV", "dev")
    monkeypatch.setenv("BUILD_FACTORY_DEV_BYPASS_AUTH", "1")
    import importlib
    importlib.reload(rc)
    assert rc.effective_user_id_for_request(None) == rc.DEV_BYPASS_USER_ID


def test_ac3_no_langgraph_langchain_litellm():
    src = MODULE.read_text(encoding="utf-8")
    code = re.sub(r'"""[\s\S]*?"""', "", src)
    code = re.sub(r"'''[\s\S]*?'''", "", code)
    code = re.sub(r"#[^\n]*", "", code).lower()
    for bad in ("langgraph", "langchain", "litellm"):
        assert bad not in code


def test_ac3_imports_bf_env_guard():
    """prod 判定は bf_env_guard 経由."""
    src = MODULE.read_text(encoding="utf-8")
    assert "from services.bf_env_guard import" in src or \
           "import services.bf_env_guard" in src


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — custom_permissions JSON safe escape
# ══════════════════════════════════════════════════════════════════════


def test_ac4_custom_permissions_serialized_into_claims():
    conn = FakeConn()
    perms = {"role": "admin", "scopes": ["read", "write"]}
    asyncio.run(rc.set_request_user(conn, "u-1", custom_permissions=perms))
    # claims SET LOCAL の payload に custom_permissions が含まれる
    claims_call = next(
        c for c in conn.calls if "request.jwt.claims" in c[0]
    )
    # args または query literal に role が含まれる
    args_str = " ".join(str(a) for a in claims_call[1])
    full = claims_call[0] + " " + args_str
    assert "custom_permissions" in full
    assert "admin" in full


def test_ac4_invalid_custom_permissions_raises():
    """non-dict は RLSContextError."""
    conn = FakeConn()
    with pytest.raises(rc.RLSContextError):
        asyncio.run(rc.set_request_user(
            conn, "u-1", custom_permissions="not a dict",  # type: ignore
        ))


def test_ac4_oversized_custom_permissions_raises():
    big = {"x": "y" * 10000}
    conn = FakeConn()
    with pytest.raises(rc.RLSContextError):
        asyncio.run(rc.set_request_user(conn, "u-1", custom_permissions=big))


def test_ac4_sql_literal_escape_doubles_quotes():
    """fallback 経路の _escape_sql_literal が single-quote を doubling."""
    assert rc._escape_sql_literal("hello'world") == "hello''world"
    assert rc._escape_sql_literal("normal") == "normal"


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — validation + reset failure re-raise + no force_bypass
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("bad", ["", "  ", None, 123, [], {}])
def test_ac5_invalid_user_id_raises(bad):
    conn = FakeConn()
    with pytest.raises(rc.RLSContextError):
        asyncio.run(rc.set_request_user(conn, bad))
    # SET LOCAL が発行されていない (validate が先)
    assert not any("SET" in c[0] or "request.jwt" in c[0] for c in conn.calls)


def test_ac5_user_id_over_max_length_raises():
    conn = FakeConn()
    long = "x" * (rc.MAX_USER_ID_LEN + 1)
    with pytest.raises(rc.RLSContextError):
        asyncio.run(rc.set_request_user(conn, long))


@pytest.mark.parametrize("bad_char", ["'", "\x00", "\\", ";", "\n", "\r"])
def test_ac5_user_id_with_injection_char_raises(bad_char):
    conn = FakeConn()
    with pytest.raises(rc.RLSContextError):
        asyncio.run(rc.set_request_user(conn, f"user{bad_char}id"))


def test_ac5_reset_failure_raises_rls_context_error():
    conn = FakeConn()
    conn.fail_on_reset = True
    with pytest.raises(rc.RLSContextError):
        asyncio.run(rc.reset_request_user(conn))


def test_ac5_no_force_bypass_argument():
    """set_request_user / with_request_user / effective_user_id_for_request
    に force_bypass / force= argument なし (backdoor 禁止)."""
    for fn in (rc.set_request_user, rc.reset_request_user, rc.with_request_user,
                rc.effective_user_id_for_request, rc.is_bypass_allowed):
        sig = inspect.signature(fn)
        params = list(sig.parameters.keys())
        for p in params:
            assert "force" not in p.lower(), (
                f"{fn.__name__} has forbidden force* param: {p}"
            )


def test_ac5_with_request_user_resets_even_when_inner_raises():
    """exception path でも reset が呼ばれる (re-raise の前)."""
    async def _run():
        conn = FakeConn()
        try:
            async with rc.with_request_user(conn, "user-x"):
                raise ValueError("inner")
        except ValueError:
            pass
        return conn
    conn = asyncio.run(_run())
    has_reset = any("RESET" in c[0] for c in conn.calls)
    assert has_reset


def test_ac5_no_hardcoded_secret():
    src = MODULE.read_text(encoding="utf-8")
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)
    assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_s0_09b_canonical_ears():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-09b"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == ["UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED"]


def test_tickets_t_s0_09b_has_adr_link_and_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-09b"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert "backend/services/auth_middleware.py" in files


def test_tickets_t_s0_09b_ac_mentions_concrete():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-S0-09b"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "rls_context.py",
        "set_request_user",
        "reset_request_user",
        "with_request_user",
        "DEV_BYPASS_USER_ID",
        "RLSContextError",
        "request.jwt.claim.sub",
        "request.jwt.claims",
        "BUILD_FACTORY_DEV_BYPASS_AUTH",
        "MAX_USER_ID_LEN",
    ):
        assert sym in full, f"T-S0-09b AC missing: {sym}"
