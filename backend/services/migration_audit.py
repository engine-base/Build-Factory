"""T-024-04: schema migration audit (ADR-012 Decision 5 cascade).

alembic / supabase migration が適用された事実を audit_logs に記録する
helper. Postgres 側は migration SQL 内で `INSERT INTO audit_logs` で
直接記録するが, SQLite (Phase 1 dev / test) では memory_service.emit_event
経由で application 層から発火する.

AC マッピング (T-024-04 AC-2):
  When the migration is applied, the system shall ... emit an audit_logs
  entry ('schema.migration_applied' with migration_id, rows_backfilled,
  duration_ms).

公開 API:
  - EVENT_MIGRATION_APPLIED: str
  - record_migration_applied(migration_id, *, rows_backfilled, duration_ms,
                              detail=None, actor_user_id='system')
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


EVENT_MIGRATION_APPLIED = "schema.migration_applied"


class MigrationAuditError(RuntimeError):
    """入力 / 不変条件違反."""


def _validate_migration_id(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MigrationAuditError("migration_id must not be empty")
    s = value.strip()
    if len(s) > 200:
        raise MigrationAuditError("migration_id must be <= 200 chars")
    return s


def _validate_non_negative_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MigrationAuditError(f"{field} must be int")
    if value < 0:
        raise MigrationAuditError(f"{field} must be >= 0")
    return value


async def record_migration_applied(
    migration_id: str,
    *,
    rows_backfilled: int = 0,
    duration_ms: int = 0,
    detail: Optional[dict[str, Any]] = None,
    actor_user_id: str = "system",
) -> Optional[int]:
    """audit_logs に 'schema.migration_applied' event を書く.

    Returns audit row id (or None if backend が無効環境).
    """
    mid = _validate_migration_id(migration_id)
    rb = _validate_non_negative_int(rows_backfilled, field="rows_backfilled")
    dm = _validate_non_negative_int(duration_ms, field="duration_ms")
    if detail is not None and not isinstance(detail, dict):
        raise MigrationAuditError("detail must be dict or null")

    payload: dict[str, Any] = {
        "migration_id": mid,
        "rows_backfilled": rb,
        "duration_ms": dm,
    }
    if detail:
        payload.update(detail)

    try:
        from services.memory_service import emit_event
        return await emit_event(
            EVENT_MIGRATION_APPLIED,
            user_id=actor_user_id,
            detail=payload,
        )
    except Exception as e:  # pragma: no cover (sqlite 未配備環境)
        logger.warning(
            "migration audit emit failed migration_id=%s: %s", mid, e,
        )
        return None
