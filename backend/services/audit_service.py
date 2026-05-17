"""T-V3-D-14: AuditLog 統一 writer service.

ADR-018 で audit_logs と auth_audit_log を `audit_logs` 単一テーブル + `source`
列に統合した. 旧 auth_audit_log への直接 INSERT は廃止し、本 service の
`emit_auth_event` 経由で `audit_logs(source='auth')` に書き込む.

公開 API:
  - emit_audit_event(action, source, ...) -> Optional[int]
        汎用 emitter. source は AuditLogSource enum で指定. id を返却.
  - emit_auth_event(event_type, user_id, success, ...) -> Optional[int]
        auth 専用 backward-compat wrapper. 内部で source='auth' に固定して
        emit_audit_event を呼ぶ. 旧 auth_audit_log writer 相当.

設計境界:
  - 本 module は **write 専用**. read は services.audit_logs (T-V3-B-24).
  - failure は silent fail (log.warning) でアプリ本体を止めない. audit_logs
    は best-effort sink で、書き込み失敗は service 機能の停止を意味しない.
  - workspace_id / actor_user_id 等の context は呼び出し側が渡す.
  - CHECK constraint (`audit_logs_source_check`) を Python 側でも先行
    バリデーションし、不正 source は ValueError で reject する (DB ラウンド
    トリップ削減).

Public dependency:
  - backend.app.models.audit_log : AuditLogSource enum / table name
  - backend.db.async_db          : DB connect helper (既存 pattern と同じ)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional, Union

from backend.app.models.audit_log import (
    AUDIT_LOGS_TABLE,
    AuditLogSource,
)

logger = logging.getLogger(__name__)


class AuditServiceError(RuntimeError):
    """Input validation error — caller 側で 422 にマップする (任意)."""


def _coerce_source(source: Union[str, AuditLogSource]) -> AuditLogSource:
    """source 値を AuditLogSource enum に正規化. 不正は AuditServiceError."""
    if isinstance(source, AuditLogSource):
        return source
    if not isinstance(source, str):
        raise AuditServiceError(
            f"source must be AuditLogSource or str, got {type(source).__name__}"
        )
    try:
        return AuditLogSource(source)
    except ValueError as e:
        valid = ", ".join(AuditLogSource.values())
        raise AuditServiceError(
            f"invalid audit_logs.source value {source!r}; must be one of [{valid}]"
        ) from e


def _serialize_payload(payload: Optional[dict[str, Any]]) -> str:
    """payload を JSON string にシリアライズ. None → '{}'."""
    if payload is None:
        return "{}"
    if not isinstance(payload, dict):
        raise AuditServiceError(
            f"payload must be dict, got {type(payload).__name__}"
        )
    try:
        return json.dumps(payload, default=str, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        raise AuditServiceError(f"payload not JSON-serializable: {e}") from e


def _db():
    """既存 services.audit_logs と同じ pattern で db module を遅延 import."""
    from backend.db import async_db  # type: ignore[import-not-found]
    return async_db


async def emit_audit_event(
    *,
    action: str,
    source: Union[str, AuditLogSource] = AuditLogSource.GENERIC,
    workspace_id: Optional[int] = None,
    actor_user_id: Optional[str] = None,
    actor_persona: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[int] = None,
    payload: Optional[dict[str, Any]] = None,
    success: bool = True,
    created_at: Optional[datetime] = None,
) -> Optional[int]:
    """audit_logs に 1 row INSERT し id を返す.

    AC-F1 / AC-F3: source は AuditLogSource enum で型保証 + DB CHECK 制約で
    重ねて enforce する.

    失敗時は silent fail で None を返す (logger.warning). アプリ本体は停止
    させない (audit_logs は best-effort sink).

    Args:
      action       : "<table>.<op>" 形式の event 名 (REQUIRED)
      source       : AuditLogSource enum or str (default 'generic')
      workspace_id : workspace FK (NULL 許容 — system event 用)
      actor_user_id: TEXT (auth.uid()::text or service identifier)
      actor_persona: BMAD persona name
      resource_type: resource entity 名
      resource_id  : resource の id
      payload      : event detail (dict, JSON serializable)
      success      : 成否 (default True)
      created_at   : 明示指定 (default DB-side NOW())

    Returns:
      INSERT 成功時は id (BIGINT), 失敗時は None.
    """
    if not isinstance(action, str) or not action.strip():
        raise AuditServiceError("action must be non-empty str")

    src = _coerce_source(source)
    payload_json = _serialize_payload(payload)

    sql = (
        f"INSERT INTO {AUDIT_LOGS_TABLE} ("
        "workspace_id, actor_user_id, actor_persona, action, resource_type, "
        "resource_id, payload, success, source"
    )
    params: list[Any] = [
        workspace_id,
        actor_user_id,
        actor_persona,
        action,
        resource_type,
        resource_id,
        payload_json,
        success,
        src.value,
    ]
    if created_at is not None:
        sql += ", created_at"
        params.append(_to_iso(created_at))
        sql += ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id"
    else:
        sql += ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id"

    try:
        db_mod = _db()
        # 既存 services.audit_logs._db_path() と同等 (env か default).
        import os
        path = os.environ.get("BF_DB_PATH", "build_factory.db")
        async with db_mod.connect(path) as db:
            cur = await db.execute(sql, params)
            row = await cur.fetchone()
            if row is None:
                return None
            return int(row[0]) if not isinstance(row, dict) else int(row.get("id", 0))
    except Exception as e:  # noqa: BLE001 — silent best-effort
        logger.warning(
            "audit_service.emit_audit_event silent fail: action=%s source=%s err=%s",
            action,
            src.value,
            e,
        )
        return None


async def emit_auth_event(
    *,
    event_type: str,
    user_id: Optional[str] = None,
    success: bool = True,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> Optional[int]:
    """auth event backward-compat writer (旧 auth_audit_log INSERT 相当).

    AC-F2 / AC-F4 互換: 旧 auth_audit_log の column shape を受け取り、
    audit_logs(source='auth') に書き込む. legacy_id は付与しない (新規
    write なので backward-compat view 経由で UUID 復元される).

    Args:
      event_type : 'login_attempt' / 'login_success' / 'login_failure' /
                   '2fa_challenge' / '2fa_success' / '2fa_failure' /
                   'oauth_link' / 'oauth_unlink' / 'oauth_refresh' /
                   'session_revoke' / 'password_reset' / 'recovery_code_used'
      user_id    : auth.uid() (UUID text). 失敗 login は None.
      success    : 成否
      ip_address : INET (str representation)
      user_agent : User-Agent string
      metadata   : extra detail (e.g. {'failure_reason': '...', 'provider': '...'})

    Returns:
      audit_logs.id (BIGINT) or None on failure.
    """
    if not isinstance(event_type, str) or not event_type.strip():
        raise AuditServiceError("event_type must be non-empty str")

    merged_payload: dict[str, Any] = dict(metadata or {})
    if ip_address is not None:
        merged_payload["ip_address"] = ip_address
    if user_agent is not None:
        merged_payload["user_agent"] = user_agent

    return await emit_audit_event(
        action=event_type,
        source=AuditLogSource.AUTH,
        actor_user_id=user_id,
        resource_type="auth",
        payload=merged_payload,
        success=success,
    )


def _to_iso(dt: datetime) -> str:
    """datetime → ISO-8601 UTC str. naive は UTC とみなす."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


__all__ = [
    "AuditServiceError",
    "emit_audit_event",
    "emit_auth_event",
]
