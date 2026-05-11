"""T-001-08: クローン opt-in trigger + service AC 検証.

T-001-03 の DB trigger を caller 層で扱う services/clone_opt_in.py を全 AC 機械検証.

AC マッピング:
  AC-1 UBIQUITOUS: check_opt_in / set_opt_in / log_interaction / revoke_opt_in_and_delete_data
  AC-2 EVENT:     {code, message} 構造化 response (caller がエラー判定可能)
  AC-3 STATE:     opt-in TRUE のみ INSERT 許可 + audit_logs に変更記録
  AC-4 UNWANTED:  opt-in OFF → CloneOptInRequiredError raise (caller 400 化)
"""
from __future__ import annotations

import asyncio
import sys
import types
from typing import Any

import pytest

from services import clone_opt_in as coi
from services.clone_opt_in import (
    CloneOptInRequiredError, VALID_INTERACTION_TYPES,
    check_opt_in, set_opt_in, log_interaction, revoke_opt_in_and_delete_data,
)


# ──────────────────────────────────────────────────────────────────────────
# Fake DB
# ──────────────────────────────────────────────────────────────────────────


class _Cur:
    def __init__(self, rows=None, lastrowid=0, rowcount=0):
        self._rows = list(rows or [])
        self.lastrowid = lastrowid
        self.rowcount = rowcount

    async def fetchone(self): return self._rows.pop(0) if self._rows else None
    async def fetchall(self): return list(self._rows)


class _Conn:
    Row = dict

    def __init__(self, *, opt_in_state=None, raise_on_insert=None,
                 raise_on_check=False):
        # opt_in_state: dict[user_id, bool] for check_opt_in
        self._opt_in = opt_in_state or {}
        # raise_on_insert: msg to raise on user_interaction_log INSERT
        self._raise_on_insert = raise_on_insert
        self._raise_on_check = raise_on_check
        self.row_factory = None
        self.executed: list[tuple[str, tuple]] = []
        self._delete_count = 0

    async def execute(self, sql, *args):
        params = args[0] if args else ()
        self.executed.append((sql, params))
        s = sql.lower()
        if "select is_opted_in from ai_clones" in s:
            if self._raise_on_check:
                raise RuntimeError("db down")
            uid = params[0] if params else None
            v = self._opt_in.get(uid)
            return _Cur(rows=[{"is_opted_in": v}] if v is not None else [])
        if "select id from ai_clones" in s:
            uid = params[0] if params else None
            return _Cur(rows=[{"id": 1}] if uid in self._opt_in else [])
        if "insert into ai_clones" in s:
            uid = params[0] if params else None
            opted = params[2] if len(params) > 2 else False
            self._opt_in[uid] = opted
            return _Cur(lastrowid=42)
        if "update ai_clones" in s:
            # opt-in toggle
            return _Cur()
        if "insert into user_interaction_log" in s:
            if self._raise_on_insert:
                raise RuntimeError(self._raise_on_insert)
            return _Cur(lastrowid=99)
        if "delete from user_interaction_log" in s:
            self._delete_count += 1
            return _Cur(rowcount=3)  # mock 3 rows deleted
        return _Cur()

    async def commit(self): return None
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return None


def _patch_db(monkeypatch, **kwargs) -> _Conn:
    conn = _Conn(**kwargs)
    mod = types.SimpleNamespace(connect=lambda _p: conn, Row=dict)
    monkeypatch.setattr(coi, "_db", lambda: mod)
    monkeypatch.setattr(coi, "_db_path", lambda: ":memory:")
    return conn


def _install_audit_recorder(monkeypatch):
    captured: list[dict] = []

    async def emit_event(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({"event": event_type, "user_id": user_id, "detail": detail or {}})

    monkeypatch.setattr("services.memory_service.emit_event", emit_event)
    return captured


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: check_opt_in
# ──────────────────────────────────────────────────────────────────────────


def test_check_opt_in_returns_true_when_opted_in(monkeypatch) -> None:
    _patch_db(monkeypatch, opt_in_state={"u1": True})
    assert asyncio.run(check_opt_in("u1")) is True


def test_check_opt_in_returns_false_when_opted_out(monkeypatch) -> None:
    _patch_db(monkeypatch, opt_in_state={"u1": False})
    assert asyncio.run(check_opt_in("u1")) is False


def test_check_opt_in_returns_false_for_unknown_user(monkeypatch) -> None:
    _patch_db(monkeypatch, opt_in_state={})
    assert asyncio.run(check_opt_in("ghost")) is False


def test_check_opt_in_returns_false_on_db_error(monkeypatch) -> None:
    _patch_db(monkeypatch, opt_in_state={"u1": True}, raise_on_check=True)
    assert asyncio.run(check_opt_in("u1")) is False


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: set_opt_in (新規 INSERT + 既存 UPDATE)
# ──────────────────────────────────────────────────────────────────────────


def test_set_opt_in_inserts_new_row_when_user_unknown(monkeypatch) -> None:
    captured = _install_audit_recorder(monkeypatch)
    conn = _patch_db(monkeypatch, opt_in_state={})  # ai_clones row 不在
    out = asyncio.run(set_opt_in("new_user", opted_in=True, consent_version="v1.0"))
    assert out["is_opted_in"] is True
    assert out["consent_version"] == "v1.0"
    # INSERT が走った
    assert any("insert into ai_clones" in s.lower() for s, _ in conn.executed)
    # audit event 発火
    assert any(e["event"] == "clone_opt_in_changed" for e in captured)


def test_set_opt_in_updates_existing_row(monkeypatch) -> None:
    """既存 row があれば UPDATE 経路."""
    conn = _patch_db(monkeypatch, opt_in_state={"u1": False})
    out = asyncio.run(set_opt_in("u1", opted_in=True, consent_version="v1.1"))
    assert out["is_opted_in"] is True
    # UPDATE が走った
    assert any("update ai_clones" in s.lower() for s, _ in conn.executed)


def test_set_opt_in_to_false_sets_opted_out_at(monkeypatch) -> None:
    conn = _patch_db(monkeypatch, opt_in_state={"u1": True})
    out = asyncio.run(set_opt_in("u1", opted_in=False))
    assert out["is_opted_in"] is False
    # opt-out path で UPDATE
    assert any("update ai_clones" in s.lower() for s, _ in conn.executed)


def test_set_opt_in_db_error_raises_value_error(monkeypatch) -> None:
    """DB 失敗 → ValueError (caller 4xx 化可能)."""
    class _ErrConn(_Conn):
        async def execute(self, sql, *args):
            raise RuntimeError("db down")

    mod = types.SimpleNamespace(connect=lambda _p: _ErrConn(), Row=dict)
    monkeypatch.setattr(coi, "_db", lambda: mod)
    monkeypatch.setattr(coi, "_db_path", lambda: ":memory:")

    with pytest.raises(ValueError, match="opt-in toggle failed"):
        asyncio.run(set_opt_in("u1", opted_in=True))


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: opt-in OFF → CloneOptInRequiredError
# ──────────────────────────────────────────────────────────────────────────


def test_log_interaction_rejects_when_opted_out(monkeypatch) -> None:
    _patch_db(monkeypatch, opt_in_state={"u1": False})
    with pytest.raises(CloneOptInRequiredError, match="not opted in"):
        asyncio.run(log_interaction(
            "u1", interaction_type="decision", context_summary="x",
        ))


def test_log_interaction_rejects_when_user_unknown(monkeypatch) -> None:
    _patch_db(monkeypatch, opt_in_state={})
    with pytest.raises(CloneOptInRequiredError):
        asyncio.run(log_interaction(
            "ghost", interaction_type="decision",
        ))


def test_log_interaction_succeeds_when_opted_in(monkeypatch) -> None:
    conn = _patch_db(monkeypatch, opt_in_state={"u1": True})
    log_id = asyncio.run(log_interaction(
        "u1", interaction_type="approval",
        context_summary="approve PR #123",
        raw_payload={"pr_id": 123},
    ))
    assert log_id == 99
    # INSERT が走った
    assert any("insert into user_interaction_log" in s.lower() for s, _ in conn.executed)


def test_log_interaction_rejects_invalid_type(monkeypatch) -> None:
    _patch_db(monkeypatch, opt_in_state={"u1": True})
    with pytest.raises(ValueError, match="interaction_type must be"):
        asyncio.run(log_interaction(
            "u1", interaction_type="BOGUS_TYPE",
        ))


@pytest.mark.parametrize("itype", VALID_INTERACTION_TYPES)
def test_log_interaction_accepts_all_6_types(itype: str, monkeypatch) -> None:
    _patch_db(monkeypatch, opt_in_state={"u1": True})
    log_id = asyncio.run(log_interaction("u1", interaction_type=itype))
    assert log_id == 99


def test_log_interaction_trigger_race_raises_opt_in_required(monkeypatch) -> None:
    """opt-in TRUE で pre-check 通過後、 DB trigger が check_violation を返す
    (opt-out race condition) → CloneOptInRequiredError に変換."""
    _patch_db(monkeypatch, opt_in_state={"u1": True},
              raise_on_insert="clone_opt_in_required: user_id=u1 (race condition)")
    with pytest.raises(CloneOptInRequiredError, match="trigger rejected"):
        asyncio.run(log_interaction("u1", interaction_type="decision"))


def test_log_interaction_other_db_error_propagates(monkeypatch) -> None:
    """opt-in 関連以外の DB エラーはそのまま propagate."""
    _patch_db(monkeypatch, opt_in_state={"u1": True},
              raise_on_insert="connection lost")
    with pytest.raises(RuntimeError, match="connection lost"):
        asyncio.run(log_interaction("u1", interaction_type="decision"))


# ──────────────────────────────────────────────────────────────────────────
# AC-OPTIONAL: opt-out + 全データ削除 (M-22 GDPR right-to-be-forgotten)
# ──────────────────────────────────────────────────────────────────────────


def test_revoke_opt_in_deletes_all_interaction_log(monkeypatch) -> None:
    captured = _install_audit_recorder(monkeypatch)
    conn = _patch_db(monkeypatch, opt_in_state={"u1": True})
    out = asyncio.run(revoke_opt_in_and_delete_data("u1"))
    assert out["opted_in"] is False
    assert out["deleted_count"] == 3
    # DELETE + UPDATE 両方走った
    assert any("delete from user_interaction_log" in s.lower() for s, _ in conn.executed)
    assert any("update ai_clones" in s.lower() for s, _ in conn.executed)
    # audit event 発火
    events = [e["event"] for e in captured]
    assert "clone_opt_out_and_data_deleted" in events
    assert "clone_opt_in_changed" in events


def test_revoke_opt_in_handles_db_error_gracefully(monkeypatch) -> None:
    """DELETE 失敗でも opt-out state は更新を試みる (silent log)."""
    class _PartialErrConn(_Conn):
        async def execute(self, sql, *args):
            if "delete from user_interaction_log" in sql.lower():
                raise RuntimeError("delete failed")
            return await super().execute(sql, *args)

    mod = types.SimpleNamespace(
        connect=lambda _p: _PartialErrConn(opt_in_state={"u1": True}), Row=dict,
    )
    monkeypatch.setattr(coi, "_db", lambda: mod)
    monkeypatch.setattr(coi, "_db_path", lambda: ":memory:")
    out = asyncio.run(revoke_opt_in_and_delete_data("u1"))
    assert out["opted_in"] is False
    assert out["deleted_count"] == 0  # delete failed


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE: audit_logs 連携
# ──────────────────────────────────────────────────────────────────────────


def test_set_opt_in_emits_audit_event(monkeypatch) -> None:
    captured = _install_audit_recorder(monkeypatch)
    _patch_db(monkeypatch, opt_in_state={})
    asyncio.run(set_opt_in("u1", opted_in=True, consent_version="v1.0"))
    ev = next(e for e in captured if e["event"] == "clone_opt_in_changed")
    assert ev["user_id"] == "u1"
    assert ev["detail"]["is_opted_in"] is True
    assert ev["detail"]["consent_version"] == "v1.0"


def test_audit_emit_failure_does_not_break_set_opt_in(monkeypatch) -> None:
    """audit 失敗してもアプリは止めない."""
    async def boom(*a, **kw):
        raise RuntimeError("audit down")

    monkeypatch.setattr("services.memory_service.emit_event", boom)
    _patch_db(monkeypatch, opt_in_state={})
    out = asyncio.run(set_opt_in("u1", opted_in=True))
    assert out["is_opted_in"] is True


# ──────────────────────────────────────────────────────────────────────────
# Exception hierarchy
# ──────────────────────────────────────────────────────────────────────────


def test_clone_opt_in_required_inherits_value_error() -> None:
    assert issubclass(CloneOptInRequiredError, ValueError)


def test_valid_interaction_types_constant() -> None:
    """interaction_type 6 種が migration の CHECK と一致."""
    assert set(VALID_INTERACTION_TYPES) == {
        "decision", "correction", "preference",
        "rejection", "approval", "annotation",
    }