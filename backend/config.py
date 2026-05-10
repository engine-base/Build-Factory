"""
Application 起動時設定バリデーション。

T-001-01 AC-3 を満たすため、main.py の lifespan startup で
`validate_required_env()` を呼び、必須 env が欠けていれば fail fast する。

呼び出し例:
    from config import validate_required_env
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        validate_required_env()
        yield
"""
from __future__ import annotations

import os
import sys
from typing import Iterable

REQUIRED_SUPABASE = (
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_KEY",
    "SUPABASE_JWT_SECRET",
)


def _missing(keys: Iterable[str]) -> list[str]:
    return [k for k in keys if not os.environ.get(k)]


def validate_required_env(*, exit_on_failure: bool = True) -> list[str]:
    """必須 env vars の存在を確認。欠けがあればエラーメッセージを stderr に出して
    `SystemExit(1)` する (テスト用に exit_on_failure=False で list 返却のみ可)。
    """
    missing = _missing(REQUIRED_SUPABASE)
    if not missing:
        return []
    msg = (
        "Build-Factory: 必須環境変数が未設定です。\n"
        f"  欠けている: {', '.join(missing)}\n"
        "  対処: .env を作成し SUPABASE_URL / SUPABASE_ANON_KEY / "
        "SUPABASE_SERVICE_KEY / SUPABASE_JWT_SECRET を設定してください\n"
        "  参考: .env.example / docs/SUPABASE_MIGRATION.md"
    )
    print(msg, file=sys.stderr)
    if exit_on_failure:
        raise SystemExit(1)
    return missing
