"""T-001-08: クローン opt-in service helper.

T-001-03 で実装した `bf_enforce_clone_opt_in` trigger を caller 層から扱いやすくする
service wrapper. Python 側で opt-in 状態を pre-check して 4xx 化、 また DB trigger
の CheckViolation を {code: 'clone_opt_in_required'} エラーに変換する.

公開 API:
  - check_opt_in(user_id) -> bool        # ai_clones.is_opted_in
  - set_opt_in(user_id, opted_in, consent_version) -> dict  # opt-in 切替 + audit
  - log_interaction(user_id, clone_id, interaction_type, ...) -> int | raise
       opt-in OFF → CloneOptInRequiredError raise (caller 400)
       opt-in ON  → user_interaction_log に INSERT
  - revoke_opt_in_and_delete_data(user_id) -> dict
       AC-OPTIONAL (M-22): opt-out 時に全 interaction log を削除

AC マッピング:
  AC-1 UBIQUITOUS: opt-in 切替 / 学習データ INSERT / opt-out delete の 3 API
  AC-2 EVENT:     {code, message} 構造化 response
  AC-3 STATE:     全 INSERT は ai_clones.is_opted_in と整合
  AC-4 UNWANTED:  opt-in OFF → CloneOptInRequiredError (caller 400)
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _db():
    from db import async_db as aiosqlite
    return aiosqlite


def _db_path():
    from db.queries import DB_PATH
    return DB_PATH


class CloneOptInRequiredError(ValueError):
    """opt-in OFF user に interaction log を INSERT しようとした (M-22 違反)."""


class CloneNotFoundError(ValueError):
    """ai_clones に該当 user の row が存在しない."""


# ──────────────────────────────────────────────────────────────────────────
# opt-in state lookup
# ──────────────────────────────────────────────────────────────────────────


async def check_opt_in(user_id: str) -> bool:
    """ai_clones.is_opted_in を返す. row 不在 / opt-in OFF は False."""
    try:
        async with _db().connect(_db_path()) as db:
            db.row_factory = _db().Row
            cur = await db.execute(
                "SELECT is_opted_in FROM ai_clones WHERE user_id = ?",
                (user_id,),
            )
            row = await cur.fetchone()
    except Exception as e:
        logger.warning("check_opt_in failed: %s", e)
        return False
    if row is None:
        return False
    val = dict(row).get("is_opted_in")
    return bool(val)


# ──────────────────────────────────────────────────────────────────────────
# opt-in toggle (set / revoke)
# ──────────────────────────────────────────────────────────────────────────


async def set_opt_in(
    user_id: str, *,
    opted_in: bool,
    consent_version: Optional[str] = None,
    workspace_id: Optional[int] = None,
) -> dict:
    """ai_clones の opt-in 状態を切替.

    既存 row 無ければ INSERT、 あれば UPDATE.
    opt-in TRUE 時は opted_in_at 自動セット、 FALSE 時は opted_out_at セット.
    """
    now_kw = "datetime('now','localtime')"
    try:
        async with _db().connect(_db_path()) as db:
            db.row_factory = _db().Row
            # 既存 row 確認
            cur = await db.execute(
                "SELECT id FROM ai_clones WHERE user_id = ?",
                (user_id,),
            )
            existing = await cur.fetchone()
            if existing is None:
                # 新規 INSERT
                await db.execute(
                    f"""INSERT INTO ai_clones
                        (user_id, workspace_id, is_opted_in, opted_in_at,
                         opted_out_at, consent_version)
                        VALUES (?, ?, ?,
                                CASE WHEN ? THEN {now_kw} ELSE NULL END,
                                CASE WHEN ? THEN NULL ELSE {now_kw} END,
                                ?)""",
                    (user_id, workspace_id, opted_in, opted_in, opted_in,
                     consent_version),
                )
            else:
                # 既存 row UPDATE
                if opted_in:
                    await db.execute(
                        f"""UPDATE ai_clones
                              SET is_opted_in = TRUE,
                                  opted_in_at = COALESCE(opted_in_at, {now_kw}),
                                  opted_out_at = NULL,
                                  consent_version = COALESCE(?, consent_version),
                                  updated_at = {now_kw}
                            WHERE user_id = ?""",
                        (consent_version, user_id),
                    )
                else:
                    await db.execute(
                        f"""UPDATE ai_clones
                              SET is_opted_in = FALSE,
                                  opted_out_at = {now_kw},
                                  updated_at = {now_kw}
                            WHERE user_id = ?""",
                        (user_id,),
                    )
            await db.commit()
    except Exception as e:
        raise ValueError(f"opt-in toggle failed: {e}") from e

    await _emit_audit(
        "clone_opt_in_changed",
        user_id=user_id,
        detail={
            "is_opted_in": opted_in,
            "consent_version": consent_version,
            "workspace_id": workspace_id,
        },
    )
    return {
        "user_id": user_id,
        "is_opted_in": opted_in,
        "consent_version": consent_version,
    }


# ──────────────────────────────────────────────────────────────────────────
# interaction log INSERT (opt-in 強制 / AC-4)
# ──────────────────────────────────────────────────────────────────────────


VALID_INTERACTION_TYPES = (
    "decision", "correction", "preference", "rejection", "approval", "annotation",
)


async def log_interaction(
    user_id: str, *,
    clone_id: Optional[int] = None,
    interaction_type: str,
    context_summary: Optional[str] = None,
    raw_payload: Optional[dict] = None,
) -> int:
    """opt-in 強制で user_interaction_log に INSERT.

    Raises:
      CloneOptInRequiredError: opt-in OFF user の INSERT 試行
      ValueError: interaction_type が enum 外
    """
    if interaction_type not in VALID_INTERACTION_TYPES:
        raise ValueError(
            f"interaction_type must be one of {VALID_INTERACTION_TYPES}, got {interaction_type!r}"
        )

    # AC-4 Python 側 pre-check: trigger より早く reject
    is_opted = await check_opt_in(user_id)
    if not is_opted:
        raise CloneOptInRequiredError(
            f"user_id={user_id!r} has not opted in to clone training (M-22)"
        )

    payload_json = json.dumps(raw_payload or {}, ensure_ascii=False)
    try:
        async with _db().connect(_db_path()) as db:
            cur = await db.execute(
                """INSERT INTO user_interaction_log
                   (user_id, clone_id, interaction_type, context_summary, raw_payload)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, clone_id, interaction_type, context_summary, payload_json),
            )
            await db.commit()
            return cur.lastrowid or 0
    except Exception as e:
        msg = str(e).lower()
        if "clone_opt_in_required" in msg or "check_violation" in msg:
            # DB trigger 経由で reject (race condition / 多重 check)
            raise CloneOptInRequiredError(
                f"trigger rejected: user_id={user_id!r} (race vs opt-out)"
            ) from e
        raise


# ──────────────────────────────────────────────────────────────────────────
# opt-out + 全データ削除 (M-22 / AC-OPTIONAL)
# ──────────────────────────────────────────────────────────────────────────


async def revoke_opt_in_and_delete_data(user_id: str) -> dict:
    """M-22 完全準拠: opt-out → 既存 interaction_log を全削除 + audit.

    Returns:
      {user_id, deleted_count, opted_in: False}
    """
    deleted_count = 0
    try:
        async with _db().connect(_db_path()) as db:
            cur = await db.execute(
                "DELETE FROM user_interaction_log WHERE user_id = ?",
                (user_id,),
            )
            deleted_count = cur.rowcount or 0
            await db.commit()
    except Exception as e:
        logger.warning("delete interaction log failed: %s", e)
    # opt-out 状態に切替
    await set_opt_in(user_id, opted_in=False)
    await _emit_audit(
        "clone_opt_out_and_data_deleted",
        user_id=user_id,
        detail={"deleted_count": deleted_count},
    )
    return {
        "user_id": user_id,
        "opted_in": False,
        "deleted_count": deleted_count,
    }


# ──────────────────────────────────────────────────────────────────────────
# Audit helper
# ──────────────────────────────────────────────────────────────────────────


async def _emit_audit(event_type: str, *, user_id: Optional[str] = None,
                       detail: Optional[dict] = None) -> None:
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail or {})
    except Exception as e:
        logger.warning("audit emit failed: %s", e)