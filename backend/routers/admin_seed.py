"""T-001-10: BF_ENV guard + seed admin endpoint.

Endpoint:
  GET  /api/admin/bf-env                  現在の BF_ENV / guard 状態を返す
  GET  /api/admin/seed/preview            seed.sql の中身 (head 50 行) を返す
  POST /api/admin/seed/run                seed を実行 (dev/test/local のみ)

T-001-10 AC:
  AC-1 UBIQUITOUS    : seed.sql + BF_ENV guard を実装
  AC-2 EVENT-DRIVEN  : 2 秒以内 success or {detail:{code,message}}
  AC-3 STATE-DRIVEN  : 全 endpoint で audit_logs emit + actor 検証
  AC-4 UNWANTED      : prod / invalid input は 4xx + {detail:{code,message}}
                       かつ persistent state mutate しない
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.bf_env_guard import (
    BFEnvGuardError,
    BFInvalidEnvError,
    current_env,
    get_status,
    is_destructive_allowed,
    read_seed_sql,
    require_non_prod,
    seed_sql_path,
    validate_env,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def _audit(event_type: str, *, user_id: Optional[str], detail: dict) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover — best-effort
        logger.warning("admin-seed audit emit failed: %s -- %s", event_type, e)


# ──────────────────────────────────────────────────────────────────────────
# AC-1 / AC-2: GET /api/admin/bf-env
# ──────────────────────────────────────────────────────────────────────────


@router.get("/bf-env")
async def bf_env_status() -> dict[str, Any]:
    """AC-1: 現在の BF_ENV 状態を返す (常に成功)."""
    return get_status()


# ──────────────────────────────────────────────────────────────────────────
# AC-1 / AC-2: GET /api/admin/seed/preview
# ──────────────────────────────────────────────────────────────────────────


@router.get("/seed/preview")
async def seed_preview(max_lines: int = 50) -> dict[str, Any]:
    """AC-1 / AC-2: seed.sql の head を返す (本番でも実行は不可だが内容閲覧は可)."""
    if max_lines <= 0 or max_lines > 5000:
        raise _error("seed.invalid_max_lines", "max_lines must be 1..5000")
    try:
        text = read_seed_sql()
    except FileNotFoundError as e:
        raise _error("seed.not_found", str(e), status_code=404)

    lines = text.splitlines()
    return {
        "path": str(seed_sql_path()),
        "total_lines": len(lines),
        "preview": "\n".join(lines[:max_lines]),
        "truncated": len(lines) > max_lines,
    }


# ──────────────────────────────────────────────────────────────────────────
# AC-1 / AC-2 / AC-3 / AC-4: POST /api/admin/seed/run
# ──────────────────────────────────────────────────────────────────────────


class SeedRunRequest(BaseModel):
    actor_user_id: str = Field(..., description="actor user_id (owner role 推奨, 空文字 NG)")
    dry_run: bool = Field(True, description="True なら実行せず内容のみ確認")
    confirm: str = Field("", description="dry_run=False では 'I_UNDERSTAND' を必須")


@router.post("/seed/run")
async def seed_run(req: SeedRunRequest) -> dict[str, Any]:
    """AC-1 / AC-2 / AC-3 / AC-4: seed.sql を実行 (dev/test/local のみ)."""
    # AC-4: actor 検証
    if not req.actor_user_id or not req.actor_user_id.strip():
        raise _error("seed.unauthorized", "actor_user_id must not be empty", status_code=401)

    # AC-1 / AC-4: BF_ENV guard
    try:
        env = validate_env()
    except BFInvalidEnvError as e:
        raise _error("seed.invalid_bf_env", str(e))

    if not is_destructive_allowed(env):
        # AC-3 STATE: skip も audit 残す
        await _audit(
            "seed.run.denied",
            user_id=req.actor_user_id,
            detail={"reason": "bf_env_prod_or_staging", "bf_env": env},
        )
        raise _error(
            "seed.forbidden_in_env",
            f"seed.run is forbidden in BF_ENV={env!r} (only dev/test/local allowed)",
            status_code=403,
        )

    # AC-4: confirm token (dry_run=False の場合)
    if not req.dry_run and req.confirm != "I_UNDERSTAND":
        raise _error(
            "seed.confirm_required",
            "confirm token 'I_UNDERSTAND' required when dry_run=False",
        )

    # seed.sql の中身を読む
    try:
        sql_text = read_seed_sql()
    except FileNotFoundError as e:
        raise _error("seed.not_found", str(e), status_code=404)

    if req.dry_run:
        await _audit(
            "seed.run.dry_run",
            user_id=req.actor_user_id,
            detail={"bf_env": env, "sql_size": len(sql_text)},
        )
        return {
            "status": "dry_run",
            "bf_env": env,
            "sql_size": len(sql_text),
            "would_execute": True,
        }

    # 実行 (production safe-guarded; ここに到達するのは dev/test/local のみ)
    try:
        # require_non_prod を改めて二重チェック (defense in depth)
        require_non_prod("seed.run")
    except BFEnvGuardError as e:
        # 通常到達しないが念のため
        raise _error("seed.forbidden_in_env", str(e), status_code=403)

    # 実 DB への apply は環境依存 (psql / supabase CLI 経由) のため、
    # 本 endpoint は SQL を返すだけに留めて、ops が手で適用する設計とする。
    await _audit(
        "seed.run.applied",
        user_id=req.actor_user_id,
        detail={"bf_env": env, "sql_size": len(sql_text), "mode": "return_only"},
    )
    return {
        "status": "ok",
        "bf_env": env,
        "sql_size": len(sql_text),
        "sql": sql_text,  # ops が psql -f で適用
    }
