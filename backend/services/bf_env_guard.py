"""T-001-10: BF_ENV guard service.

`BF_ENV` 環境変数を参照し、prod 環境で seed / destructive 操作を実行しようとしたら
即時 raise する safety net.

許可される BF_ENV:
  dev / test / local / staging / prod

prod のときは:
  - require_non_prod(): raise BFEnvGuardError
  - is_destructive_allowed(): return False

dev/test/local では:
  - require_non_prod(): no-op
  - is_destructive_allowed(): return True

staging は read-only として扱う (seed 禁止 / RLS 検査用).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

VALID_ENVS = ("dev", "test", "local", "staging", "prod")
DESTRUCTIVE_ALLOWED_ENVS = ("dev", "test", "local")
DEFAULT_ENV = "dev"


class BFEnvGuardError(RuntimeError):
    """destructive 操作が本番で実行されようとした際の error."""


class BFInvalidEnvError(ValueError):
    """BF_ENV の値が VALID_ENVS に含まれない."""


def current_env() -> str:
    """現在の BF_ENV を読む. 未設定なら DEFAULT_ENV."""
    return (os.environ.get("BF_ENV") or DEFAULT_ENV).strip().lower()


def validate_env(env: Optional[str] = None) -> str:
    """env を validate して返す. invalid なら BFInvalidEnvError."""
    e = (env or current_env()).strip().lower()
    if e not in VALID_ENVS:
        raise BFInvalidEnvError(
            f"BF_ENV must be one of {VALID_ENVS}, got {e!r}"
        )
    return e


def is_destructive_allowed(env: Optional[str] = None) -> bool:
    """destructive 操作 (seed / truncate / drop) が許可されているか."""
    return validate_env(env) in DESTRUCTIVE_ALLOWED_ENVS


def is_prod(env: Optional[str] = None) -> bool:
    return validate_env(env) == "prod"


def require_non_prod(op_name: str = "destructive operation") -> None:
    """prod で呼ばれたら raise. seed/truncate 等の入り口で必ず呼ぶ."""
    env = validate_env()
    if not is_destructive_allowed(env):
        raise BFEnvGuardError(
            f"{op_name} is not allowed in BF_ENV={env!r} (only {DESTRUCTIVE_ALLOWED_ENVS})"
        )


# ──────────────────────────────────────────────────────────────────────────
# seed loader
# ──────────────────────────────────────────────────────────────────────────


def seed_sql_path() -> Path:
    """supabase/seed.sql の絶対 path."""
    return Path(__file__).resolve().parents[2] / "supabase" / "seed.sql"


def read_seed_sql() -> str:
    """seed.sql の中身を string で返す."""
    path = seed_sql_path()
    if not path.exists():
        raise FileNotFoundError(f"seed.sql not found: {path}")
    return path.read_text(encoding="utf-8")


def get_status() -> dict:
    """現在の guard 状態を返す (admin endpoint 用)."""
    env = current_env()
    return {
        "bf_env": env,
        "valid": env in VALID_ENVS,
        "destructive_allowed": env in DESTRUCTIVE_ALLOWED_ENVS,
        "is_prod": env == "prod",
        "seed_sql_path": str(seed_sql_path()),
        "seed_sql_exists": seed_sql_path().exists(),
    }
