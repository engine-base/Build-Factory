"""T-V3-D-14: AuditLog unified model.

ADR-018 で audit_logs と auth_audit_log を `audit_logs` 単一テーブル + `source`
列に統合した. 本 module はその schema を Python 型で表現する.

設計境界:
  - 本 repo は raw SQL + `backend/db/async_db.py` パターンで ORM を使わない.
    そのため SQLAlchemy declarative class ではなく **frozen dataclass + Enum**
    で行表現と enum 値を提供する.
  - migration 真実源: `supabase/migrations/20260516210000_audit_log_unification.sql`.
  - 既存 read service `backend/services/audit_logs.py` (T-V3-B-24 / F-018) は
    本 module の `AuditLogSource` enum を import せず string literal で動く
    実装だが、新規 service (`backend/services/audit_service.py`) は本 module
    の `AuditLogSource` 経由で write する.

Public API:
  - AuditLogSource          : Enum of valid `source` values (CHECK constraint)
  - AuditLogRow             : frozen dataclass representing a row
  - AUDIT_LOGS_TABLE        : str — table name
  - AUTH_AUDIT_LOG_VIEW     : str — backward-compat VIEW name

ADR-018 §Decision 2 で「auth_audit_log は VIEW に置換され、新規 write は
audit_logs(source='auth') にする」と決定された.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


AUDIT_LOGS_TABLE = "audit_logs"
AUTH_AUDIT_LOG_VIEW = "auth_audit_log"  # backward-compat VIEW (AC-F4)


class AuditLogSource(str, enum.Enum):
    """`audit_logs.source` の CHECK 制約 enum.

    migration `20260516210000_audit_log_unification.sql` で
    `CHECK (source IN ('generic', 'auth', 'workspace', 'system', 'cost', 'red_line'))`
    と宣言されている. 本 enum はその真実源を Python 側で reflect する.

    値の意味:
      - GENERIC   : 旧 audit_logs 由来の default. classify されていない event.
      - AUTH      : auth event (login / 2FA / OAuth). 旧 auth_audit_log 互換.
      - WORKSPACE : workspace 操作 (member 追加/削除 / setting 変更 等).
      - SYSTEM    : system event (background job / migration / cron 等).
      - COST      : cost tracking / billing event.
      - RED_LINE  : red_line violation event.
    """

    GENERIC = "generic"
    AUTH = "auth"
    WORKSPACE = "workspace"
    SYSTEM = "system"
    COST = "cost"
    RED_LINE = "red_line"

    @classmethod
    def values(cls) -> list[str]:
        """CHECK constraint 検証用 — 全 enum 値の list."""
        return [m.value for m in cls]


@dataclass(frozen=True)
class AuditLogRow:
    """`audit_logs` 行の型表現.

    migration `20260510000001_bf_project_tables.sql` の column 順 +
    `20260516210000_audit_log_unification.sql` で追加された `source` 列を含む.

    Fields:
      - id            : BIGSERIAL PRIMARY KEY
      - workspace_id  : workspace FK (NULL 許容 — system event 用)
      - actor_user_id : TEXT (auth.uid()::text or service identifier)
      - actor_persona : TEXT (mary / devon / quinn 等 — BMAD 10 ペルソナ識別)
      - action        : TEXT NOT NULL ('login.success', 'task.create' 等)
      - resource_type : TEXT (resource entity 名 — 'bf_task' / 'auth' 等)
      - resource_id   : BIGINT (resource の id)
      - payload       : JSONB (event detail)
      - success       : BOOLEAN NOT NULL DEFAULT TRUE
      - source        : TEXT NOT NULL DEFAULT 'generic' (T-V3-D-14)
      - created_at    : TIMESTAMPTZ DEFAULT NOW()
    """

    id: Optional[int]
    workspace_id: Optional[int]
    actor_user_id: Optional[str]
    actor_persona: Optional[str]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[int]
    payload: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    source: AuditLogSource = AuditLogSource.GENERIC
    created_at: Optional[datetime] = None


__all__ = [
    "AUDIT_LOGS_TABLE",
    "AUTH_AUDIT_LOG_VIEW",
    "AuditLogSource",
    "AuditLogRow",
]
