"""T-V3-B-29 / F-027: Onboarding flow service.

3 steps の onboarding (welcome → workspace_setup → ai_employee_intro) を
SQLite ローカル DB (`user_onboarding_state`) で永続化する。

- get_state(user_id)        → 現在の onboarding 状態
- advance(user_id, step, payload) → 次の step へ進める / 完了マーク
- skip(user_id, step, reason) → optional step を skip (required step は 409)

Spec link: docs/functional-breakdown/2026-05-16_v3/features.json#F-027
Audit: docs/audit/2026-05-16_v3/T-V3-B-29.md
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── 定義 ────────────────────────────────────────────
# 3 step 固定. step ID の集合 + required flag を service 層が知る.
ONBOARDING_STEPS: list[dict[str, Any]] = [
    {"id": "welcome",            "required": True,  "screen": "S-048"},
    {"id": "workspace_setup",    "required": True,  "screen": "S-049"},
    {"id": "ai_employee_intro",  "required": False, "screen": "S-050"},
]
STEP_IDS: list[str] = [s["id"] for s in ONBOARDING_STEPS]


class OnboardingError(Exception):
    """ロジックエラーの基底クラス. router 層で 4xx に変換される."""


class StepOutOfOrderError(OnboardingError):
    """無効な step transition. 409 にマップ."""


class RequiredStepSkipError(OnboardingError):
    """required=True の step を skip しようとした. 409 にマップ."""


class UnknownStepError(OnboardingError):
    """STEP_IDS に含まれない step ID. 422 にマップ."""


# ── DB helpers ──────────────────────────────────────────

def _db():
    from db import async_db as aiosqlite
    return aiosqlite


def _db_path():
    from db.queries import DB_PATH
    return DB_PATH


async def _ensure_table() -> None:
    """テーブルが無ければ作る (alembic 未実行環境向け graceful)."""
    try:
        async with _db().connect(_db_path()) as db:
            await db.execute(
                """CREATE TABLE IF NOT EXISTS user_onboarding_state (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id         TEXT NOT NULL UNIQUE,
                    current_step    TEXT NOT NULL DEFAULT 'welcome',
                    completed_steps TEXT NOT NULL DEFAULT '[]',
                    skipped_steps   TEXT NOT NULL DEFAULT '[]',
                    completed_at    TEXT,
                    skipped_at      TEXT,
                    payload         TEXT NOT NULL DEFAULT '{}',
                    updated_at      TEXT DEFAULT (datetime('now','localtime')),
                    created_at      TEXT DEFAULT (datetime('now','localtime'))
                )"""
            )
            await db.commit()
    except Exception as e:  # pragma: no cover (defensive)
        logger.warning("onboarding._ensure_table failed: %s", e)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _next_step(current: str, completed: list[str]) -> Optional[str]:
    """current が完了したと仮定して次の step を返す. 全完了なら None."""
    for s in STEP_IDS:
        if s in completed:
            continue
        if s == current:
            # current は完了予定. 次の未完を探す
            idx = STEP_IDS.index(s)
            for nxt in STEP_IDS[idx + 1:]:
                if nxt not in completed:
                    return nxt
            return None
        return s
    return None


# ── public API ──────────────────────────────────────────

async def get_state(user_id: str) -> dict:
    """user の onboarding 状態を返す. 行が無ければ default (welcome / not completed)."""
    if not user_id:
        raise UnknownStepError("user_id must not be empty")
    await _ensure_table()
    try:
        async with _db().connect(_db_path()) as db:
            cur = await db.execute(
                "SELECT * FROM user_onboarding_state WHERE user_id = ?",
                (user_id,),
            )
            row = await cur.fetchone()
    except Exception as e:
        logger.warning("onboarding.get_state failed: %s", e)
        return _default_state(user_id)
    if not row:
        return _default_state(user_id)
    return _row_to_state(dict(row))


def _default_state(user_id: str) -> dict:
    return {
        "user_id":         user_id,
        "current_step":    STEP_IDS[0],
        "completed_steps": [],
        "skipped_steps":   [],
        "completed":       False,
        "completed_at":    None,
        "skipped_at":      None,
        "state":           {"steps": ONBOARDING_STEPS},
    }


def _row_to_state(row: dict) -> dict:
    completed_steps = json.loads(row.get("completed_steps") or "[]")
    skipped_steps = json.loads(row.get("skipped_steps") or "[]")
    completed = row.get("completed_at") is not None
    return {
        "user_id":         row["user_id"],
        "current_step":    row.get("current_step") or STEP_IDS[0],
        "completed_steps": completed_steps,
        "skipped_steps":   skipped_steps,
        "completed":       completed,
        "completed_at":    row.get("completed_at"),
        "skipped_at":      row.get("skipped_at"),
        "state":           {"steps": ONBOARDING_STEPS},
    }


async def advance(user_id: str, step: str, payload: Optional[dict] = None) -> dict:
    """step を完了マークし、次の step へ進める.

    AC:
      - EVENT-DRIVEN: valid な step transition なら persist + return next_step
      - UNWANTED: STEP_IDS に無い step → UnknownStepError (422)
      - UNWANTED: 既に skip 済みでない既完了 step を再度 advance → StepOutOfOrderError (409)
    """
    if not user_id:
        raise UnknownStepError("user_id must not be empty")
    if step not in STEP_IDS:
        raise UnknownStepError(f"unknown step: {step}")
    payload = payload or {}

    await _ensure_table()
    cur_state = await get_state(user_id)
    completed = list(cur_state["completed_steps"])
    skipped = list(cur_state["skipped_steps"])

    if step in completed:
        raise StepOutOfOrderError(f"step already completed: {step}")

    # 進行順序チェック: 前 step が完了 or skip されているか
    idx = STEP_IDS.index(step)
    for prev in STEP_IDS[:idx]:
        if prev not in completed and prev not in skipped:
            raise StepOutOfOrderError(
                f"step out of order: cannot advance to {step} before {prev}"
            )

    completed.append(step)
    nxt = _next_step(step, completed)
    is_completed = nxt is None
    completed_at = _now_iso() if is_completed else None
    current_step = nxt or step

    await _upsert(
        user_id,
        current_step=current_step,
        completed_steps=completed,
        skipped_steps=skipped,
        completed_at=completed_at,
        skipped_at=cur_state.get("skipped_at"),
        payload=payload,
    )
    await _audit(
        "onboarding.completed" if is_completed else "onboarding.advanced",
        user_id,
        {"step": step, "next_step": nxt, "completed": is_completed},
    )
    return {
        "next_step": nxt,
        "completed": is_completed,
        "current_step": current_step,
    }


async def skip(user_id: str, step: Optional[str] = None, reason: Optional[str] = None) -> dict:
    """optional step を skip する.

    step 引数が省略された場合は現在の current_step を skip 対象とする.

    AC:
      - EVENT-DRIVEN: valid な optional step を skip → skipped_at を返す
      - UNWANTED: required=True の step を skip → RequiredStepSkipError (409)
    """
    if not user_id:
        raise UnknownStepError("user_id must not be empty")
    await _ensure_table()
    cur_state = await get_state(user_id)

    target = step or cur_state["current_step"]
    if target not in STEP_IDS:
        raise UnknownStepError(f"unknown step: {target}")

    meta = next(s for s in ONBOARDING_STEPS if s["id"] == target)
    if meta["required"]:
        raise RequiredStepSkipError(
            f"step '{target}' is required and cannot be skipped"
        )
    if target in cur_state["completed_steps"]:
        raise StepOutOfOrderError(f"step already completed: {target}")
    if target in cur_state["skipped_steps"]:
        raise StepOutOfOrderError(f"step already skipped: {target}")

    skipped = list(cur_state["skipped_steps"]) + [target]
    completed = list(cur_state["completed_steps"])
    nxt = _next_step(target, completed + skipped)
    is_completed = nxt is None
    now = _now_iso()
    completed_at = _now_iso() if is_completed else cur_state.get("completed_at")
    current_step = nxt or target

    await _upsert(
        user_id,
        current_step=current_step,
        completed_steps=completed,
        skipped_steps=skipped,
        completed_at=completed_at,
        skipped_at=now,
        payload={"skip_reason": reason} if reason else {},
    )
    await _audit(
        "onboarding.skipped",
        user_id,
        {"step": target, "reason": reason, "next_step": nxt},
    )
    return {
        "skipped_at": now,
        "next_step": nxt,
        "completed": is_completed,
    }


# ── DB writer ──────────────────────────────────────────

async def _upsert(
    user_id: str,
    *,
    current_step: str,
    completed_steps: list[str],
    skipped_steps: list[str],
    completed_at: Optional[str],
    skipped_at: Optional[str],
    payload: dict,
) -> None:
    try:
        async with _db().connect(_db_path()) as db:
            await db.execute(
                """INSERT INTO user_onboarding_state
                    (user_id, current_step, completed_steps, skipped_steps,
                     completed_at, skipped_at, payload, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'))
                   ON CONFLICT(user_id) DO UPDATE SET
                     current_step    = excluded.current_step,
                     completed_steps = excluded.completed_steps,
                     skipped_steps   = excluded.skipped_steps,
                     completed_at    = excluded.completed_at,
                     skipped_at      = excluded.skipped_at,
                     payload         = excluded.payload,
                     updated_at      = excluded.updated_at""",
                (
                    user_id,
                    current_step,
                    json.dumps(completed_steps),
                    json.dumps(skipped_steps),
                    completed_at,
                    skipped_at,
                    json.dumps(payload),
                ),
            )
            await db.commit()
    except Exception as e:  # pragma: no cover (defensive)
        logger.warning("onboarding._upsert failed: %s", e)


async def _audit(event_type: str, user_id: str, detail: dict) -> None:
    """audit_logs へ event を emit する. failure は silent (本処理は止めない)."""
    try:
        from services.memory_service import emit_event
        await emit_event(event_type, user_id=user_id, detail=detail)
    except Exception as e:  # pragma: no cover (defensive)
        logger.warning("onboarding audit emit failed: %s — %s", event_type, e)
