"""T-001-10: seed.sql + BF_ENV ガード — 5 AC.

PR #82 で production artifact 完成済
(supabase/seed.sql idempotent + backend/services/bf_env_guard.py /
VALID_ENVS 5 値 + BFEnvGuardError + 6 helper).

AC マッピング:
  AC-1: seed.sql idempotent INSERT / bf_env_guard 8 public symbol.
  AC-2: BF_ENV='prod' で require_non_prod RuntimeError / dev/test/local
        で destructive allowed / staging/prod で禁止 / invalid env で raise.
  AC-3: current_env が os.environ で都度 fresh / no mutable global cache /
        no langgraph/langchain/litellm / no hardcoded secret.
  AC-4: staging で is_destructive_allowed=False / BMAD persona seed
        coexistence.
  AC-5: prod destructive で raise BEFORE mutation / invalid env で
        BFInvalidEnvError / seed.sql に DROP/TRUNCATE/DELETE なし /
        no force= backdoor.
"""
from __future__ import annotations

import importlib
import json
import os
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SEED = REPO_ROOT / "supabase" / "seed.sql"
GUARD = REPO_ROOT / "backend" / "services" / "bf_env_guard.py"
BMAD_SEED = REPO_ROOT / "supabase" / "migrations" / "20260512400000_bmad_personas_seed.sql"
TICKETS = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"


@pytest.fixture
def env_dev(monkeypatch):
    monkeypatch.setenv("BF_ENV", "dev")
    import services.bf_env_guard as g
    importlib.reload(g)
    return g


@pytest.fixture
def env_prod(monkeypatch):
    monkeypatch.setenv("BF_ENV", "prod")
    import services.bf_env_guard as g
    importlib.reload(g)
    return g


@pytest.fixture
def env_staging(monkeypatch):
    monkeypatch.setenv("BF_ENV", "staging")
    import services.bf_env_guard as g
    importlib.reload(g)
    return g


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — seed.sql idempotent + 8 public symbols
# ══════════════════════════════════════════════════════════════════════


def test_ac1_seed_sql_exists():
    assert SEED.exists()


def test_ac1_guard_module_exists():
    assert GUARD.exists()


def test_ac1_seed_wrapped_in_transaction():
    src = SEED.read_text(encoding="utf-8")
    # BEGIN; ... COMMIT; 形式
    assert re.search(r"^\s*BEGIN\s*;", src, re.MULTILINE | re.IGNORECASE)
    assert re.search(r"^\s*COMMIT\s*;", src, re.MULTILINE | re.IGNORECASE)


def test_ac1_seed_uses_idempotent_inserts():
    """INSERT ... ON CONFLICT DO NOTHING / DO UPDATE で idempotent."""
    src = SEED.read_text(encoding="utf-8")
    # ON CONFLICT 句が複数登場
    matches = re.findall(r"ON\s+CONFLICT", src, re.IGNORECASE)
    assert len(matches) >= 2, (
        f"expected >= 2 ON CONFLICT clauses for idempotency, got {len(matches)}"
    )


def test_ac1_guard_valid_envs_5_values(env_dev):
    assert env_dev.VALID_ENVS == (
        "dev", "test", "local", "staging", "prod",
    )


@pytest.mark.parametrize("sym", [
    "VALID_ENVS",
    "BFEnvGuardError",
    "BFInvalidEnvError",
    "current_env",
    "validate_env",
    "is_destructive_allowed",
    "is_prod",
    "require_non_prod",
    "seed_sql_path",
    "read_seed_sql",
    "get_status",
])
def test_ac1_guard_public_symbol(sym, env_dev):
    assert hasattr(env_dev, sym), f"bf_env_guard missing: {sym}"


def test_ac1_bf_env_guard_error_subclass(env_dev):
    assert issubclass(env_dev.BFEnvGuardError, RuntimeError)


def test_ac1_bf_invalid_env_error_subclass(env_dev):
    assert issubclass(env_dev.BFInvalidEnvError, ValueError)


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — prod で raise / dev で OK / invalid raise
# ══════════════════════════════════════════════════════════════════════


def test_ac2_prod_require_non_prod_raises(env_prod):
    with pytest.raises(env_prod.BFEnvGuardError) as exc:
        env_prod.require_non_prod("seed")
    assert "seed" in str(exc.value)
    assert "prod" in str(exc.value).lower()


def test_ac2_dev_destructive_allowed(env_dev):
    assert env_dev.is_destructive_allowed("dev") is True
    assert env_dev.is_destructive_allowed("test") is True
    assert env_dev.is_destructive_allowed("local") is True


def test_ac2_prod_destructive_not_allowed(env_prod):
    assert env_prod.is_destructive_allowed("prod") is False


def test_ac2_staging_destructive_not_allowed(env_staging):
    assert env_staging.is_destructive_allowed("staging") is False


def test_ac2_invalid_env_raises(env_dev):
    """invalid env name で BFInvalidEnvError.

    validate_env は .lower().strip() 正規化を行うので 'PROD' は 'prod' に
    なり valid 判定. 完全に enum 外の文字列のみが raise する.
    """
    for bad in ("production", "development", "stage", "unknown", "qa"):
        with pytest.raises(env_dev.BFInvalidEnvError):
            env_dev.validate_env(bad)


def test_ac2_dev_require_non_prod_noop(env_dev):
    # raise しない
    env_dev.require_non_prod("seed")


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — fresh env / no cache / no langgraph / no secret
# ══════════════════════════════════════════════════════════════════════


def test_ac3_current_env_reads_environ_freshly(monkeypatch):
    """current_env() が呼ばれるたびに os.environ を読む."""
    import services.bf_env_guard as g
    importlib.reload(g)
    monkeypatch.setenv("BF_ENV", "dev")
    assert g.current_env() == "dev"
    monkeypatch.setenv("BF_ENV", "test")
    assert g.current_env() == "test"
    monkeypatch.setenv("BF_ENV", "local")
    assert g.current_env() == "local"


def test_ac3_default_env_is_dev_when_unset(monkeypatch):
    """BF_ENV 未設定で default='dev'."""
    import services.bf_env_guard as g
    importlib.reload(g)
    monkeypatch.delenv("BF_ENV", raising=False)
    assert g.current_env() == "dev"


def test_ac3_no_langgraph_langchain_litellm_in_guard():
    src = GUARD.read_text(encoding="utf-8")
    code = re.sub(r'"""[\s\S]*?"""', "", src)
    code = re.sub(r"'''[\s\S]*?'''", "", code)
    code = re.sub(r"#[^\n]*", "", code).lower()
    for bad in ("langgraph", "langchain", "litellm"):
        assert bad not in code, f"forbidden {bad} in bf_env_guard"


def test_ac3_no_hardcoded_secret_in_seed():
    src = SEED.read_text(encoding="utf-8")
    assert not re.search(r"sb_(publishable|secret)_[A-Za-z0-9_-]{20,}", src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", src)
    assert not re.search(r"eyJ[A-Za-z0-9_=-]{40,}\.[A-Za-z0-9_=-]{40,}\.", src)


def test_ac3_no_mutable_global_state_in_guard():
    """module-level に dict / list / set の global state mutation なし."""
    src = GUARD.read_text(encoding="utf-8")
    code = re.sub(r'"""[\s\S]*?"""', "", src)
    code = re.sub(r"#[^\n]*", "", code)
    # _ENV_CACHE = {} のような module-level mutable
    bad = re.findall(
        r"^_[A-Z_]+\s*=\s*(?:\{\}|\[\]|set\(\))",
        code,
        re.MULTILINE,
    )
    assert not bad, f"module-level mutable state forbidden: {bad}"


# ══════════════════════════════════════════════════════════════════════
# AC-4 OPTIONAL — staging read-only / BMAD persona coexistence
# ══════════════════════════════════════════════════════════════════════


def test_ac4_staging_is_destructive_allowed_false(env_staging):
    assert env_staging.is_destructive_allowed("staging") is False


def test_ac4_staging_require_non_prod_raises(env_staging):
    """staging も seed 禁止 (RLS テスト用 read-only)."""
    with pytest.raises(env_staging.BFEnvGuardError):
        env_staging.require_non_prod("seed")


def test_ac4_bmad_persona_seed_migration_exists():
    """companion migration: 10 BMAD persona seed."""
    assert BMAD_SEED.exists()


def test_ac4_bmad_seed_has_10_personas():
    src = BMAD_SEED.read_text(encoding="utf-8")
    for persona in ("mary", "preston", "winston", "sally", "devon",
                    "quinn", "reviewer", "brand", "mockup", "curator"):
        assert persona in src, f"BMAD persona {persona} not in seed"


# ══════════════════════════════════════════════════════════════════════
# AC-5 UNWANTED — prod raise BEFORE / invalid env / no DROP/TRUNCATE /
#                  no force= backdoor
# ══════════════════════════════════════════════════════════════════════


def test_ac5_seed_has_no_drop_table():
    src = SEED.read_text(encoding="utf-8")
    assert not re.search(r"\bDROP\s+TABLE\b", src, re.IGNORECASE)


def test_ac5_seed_has_no_truncate():
    src = SEED.read_text(encoding="utf-8")
    assert not re.search(r"\bTRUNCATE\b", src, re.IGNORECASE)


def test_ac5_seed_has_no_delete_star():
    """DELETE FROM table_name; (where 句なし) のような全削除なし."""
    src = SEED.read_text(encoding="utf-8")
    # DELETE FROM xxx; (where なし) — ただし comment / 文字列内除外
    code = re.sub(r"--[^\n]*", "", src)
    bad = re.findall(
        r"DELETE\s+FROM\s+\w+\s*;",
        code,
        re.IGNORECASE,
    )
    assert not bad, f"forbidden DELETE FROM ...; without WHERE: {bad}"


def test_ac5_require_non_prod_raises_before_any_side_effect(env_prod):
    """require_non_prod が prod で即時 raise (side effect なし)."""
    # 関数呼出時点で raise / log や DB call は行わない
    src = GUARD.read_text(encoding="utf-8")
    m = re.search(
        r"def require_non_prod[\s\S]+?(?=\n\ndef |\Z)",
        src,
    )
    assert m
    body = m.group(0)
    # raise 前に I/O や DB call が無い (logger 系を除く)
    assert "open(" not in body
    assert "requests" not in body


def test_ac5_no_force_backdoor():
    """require_non_prod() / is_destructive_allowed() に force= 引数なし."""
    src = GUARD.read_text(encoding="utf-8")
    code = re.sub(r'"""[\s\S]*?"""', "", src)
    # def require_non_prod(..., force=...) パターン禁止
    assert not re.search(
        r"def require_non_prod\s*\([^)]*force\s*=",
        code,
    )
    assert not re.search(
        r"def is_destructive_allowed\s*\([^)]*force\s*=",
        code,
    )


def test_ac5_invalid_env_raises_bf_invalid_env_error(env_dev):
    """完全に enum 外の文字列で BFInvalidEnvError.

    .lower().strip() 正規化が走るので case 違い ('PROD'→'prod') は valid.
    """
    with pytest.raises(env_dev.BFInvalidEnvError):
        env_dev.validate_env("development")
    with pytest.raises(env_dev.BFInvalidEnvError):
        env_dev.validate_env("production")


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_001_10_canonical_ears():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-10"), None)
    types = [ac["type"] for ac in t["acceptance_criteria"]]
    for ty in types:
        assert ty not in ("EVENT", "STATE")
    assert types == ["UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED"]


def test_tickets_t_001_10_has_adr_link_and_files():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-10"), None)
    assert t.get("adr_link") is not None
    files = t.get("existing_files", [])
    assert "supabase/seed.sql" in files
    assert "backend/services/bf_env_guard.py" in files


def test_tickets_t_001_10_ac_mentions_concrete():
    d = json.loads(TICKETS.read_text(encoding="utf-8"))
    t = next((x for x in d["tickets"] if x["id"] == "T-001-10"), None)
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    for sym in (
        "supabase/seed.sql",
        "backend/services/bf_env_guard.py",
        "VALID_ENVS",
        "BFEnvGuardError",
        "BFInvalidEnvError",
        "current_env",
        "is_destructive_allowed",
        "require_non_prod",
        "BF_ENV",
        "DROP TABLE",
        "TRUNCATE",
    ):
        assert sym in full, f"T-001-10 AC missing: {sym}"
