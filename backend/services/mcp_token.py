"""T-010a-04: MCP token scope (workspace 単位) サービス.

MCP server を呼ぶクライアントを workspace 単位で認可するためのトークン管理.
JWT ではなく opaque random token (rotation 容易性 + revocation 即時化 を優先).

スコープ:
  - "spec:read"        bf_get_spec
  - "progress:write"   bf_post_progress
  - "artifact:write"   bf_attach_artifact
  - "review:request"   bf_request_review
  - "review:read"      bf_get_review_feedback
  - "db:read"          query_company_db / get_kpi / list_records
  - "*"                すべて

公開 API:
  - issue_token(workspace_id, scopes, *, expires_in_days, issued_by) -> dict
  - verify_token(token, *, required_scope, workspace_id) -> dict
  - revoke_token(token_id) -> bool
  - list_tokens(workspace_id) -> list[dict]
"""
from __future__ import annotations

import logging
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


class MCPTokenError(RuntimeError):
    pass


VALID_SCOPES = (
    "spec:read", "progress:write", "artifact:write",
    "review:request", "review:read", "db:read", "*",
)


@dataclass
class TokenRecord:
    id: int
    token: str
    workspace_id: int
    scopes: list[str] = field(default_factory=list)
    issued_by: Optional[str] = None
    expires_at: str = ""
    revoked_at: Optional[str] = None
    created_at: str = ""


# in-memory store
_lock = threading.Lock()
_tokens: dict[int, TokenRecord] = {}
_by_token_value: dict[str, int] = {}
_next_id = 1


def reset_store() -> None:
    """test 用 reset."""
    global _next_id
    with _lock:
        _tokens.clear()
        _by_token_value.clear()
        _next_id = 1


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(rec: TokenRecord, *, mask_token: bool = False) -> dict:
    t = rec.token
    if mask_token and len(t) > 12:
        t = t[:6] + "..." + t[-4:]
    return {
        "id": rec.id,
        "token": t,
        "workspace_id": rec.workspace_id,
        "scopes": list(rec.scopes),
        "issued_by": rec.issued_by,
        "expires_at": rec.expires_at,
        "revoked_at": rec.revoked_at,
        "created_at": rec.created_at,
    }


def issue_token(
    workspace_id: int,
    scopes: Iterable[str],
    *,
    expires_in_days: int = 30,
    issued_by: Optional[str] = None,
) -> dict:
    """新規 MCP token を発行 (workspace 単位)."""
    if not isinstance(workspace_id, int) or workspace_id <= 0:
        raise MCPTokenError(f"workspace_id must be > 0, got {workspace_id}")
    scope_list = list(scopes)
    if not scope_list:
        raise MCPTokenError("scopes must not be empty")
    if len(scope_list) > len(VALID_SCOPES):
        raise MCPTokenError(f"too many scopes (max {len(VALID_SCOPES)})")
    for s in scope_list:
        if s not in VALID_SCOPES:
            raise MCPTokenError(
                f"unknown scope {s!r}; allowed {VALID_SCOPES}"
            )
    if len(set(scope_list)) != len(scope_list):
        raise MCPTokenError("scopes must be unique")
    if expires_in_days <= 0 or expires_in_days > 365:
        raise MCPTokenError("expires_in_days must be 1..365")
    if issued_by is not None and not str(issued_by).strip():
        raise MCPTokenError("issued_by must not be empty when provided")

    global _next_id
    token = "mcp_" + secrets.token_urlsafe(32)
    expires_at = (_now() + timedelta(days=expires_in_days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    with _lock:
        rec = TokenRecord(
            id=_next_id,
            token=token,
            workspace_id=workspace_id,
            scopes=scope_list,
            issued_by=issued_by,
            expires_at=expires_at,
            created_at=_now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        _tokens[_next_id] = rec
        _by_token_value[token] = _next_id
        _next_id += 1
    return _serialize(rec)


def verify_token(
    token: str,
    *,
    required_scope: Optional[str] = None,
    workspace_id: Optional[int] = None,
) -> dict:
    """token を検証. valid = True なら claims を返す.

    Returns: {"valid": bool, "reason": str, "claims": dict | None}
    """
    if not isinstance(token, str) or not token.strip():
        return {"valid": False, "reason": "empty_token", "claims": None}
    with _lock:
        tid = _by_token_value.get(token.strip())
        rec = _tokens.get(tid) if tid is not None else None
    if rec is None:
        return {"valid": False, "reason": "not_found", "claims": None}
    if rec.revoked_at:
        return {"valid": False, "reason": "revoked", "claims": None}
    # expiry
    try:
        if datetime.strptime(rec.expires_at, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        ) < _now():
            return {"valid": False, "reason": "expired", "claims": None}
    except Exception:
        pass
    # workspace scope
    if workspace_id is not None and rec.workspace_id != workspace_id:
        return {"valid": False, "reason": "workspace_mismatch", "claims": None}
    # required scope
    if required_scope is not None:
        if required_scope not in rec.scopes and "*" not in rec.scopes:
            return {"valid": False, "reason": "scope_denied", "claims": None}
    return {
        "valid": True,
        "reason": "ok",
        "claims": {
            "workspace_id": rec.workspace_id,
            "scopes": list(rec.scopes),
            "expires_at": rec.expires_at,
            "issued_by": rec.issued_by,
        },
    }


def revoke_token(token_id: int) -> bool:
    """token を revoke. 存在しなければ False."""
    if not isinstance(token_id, int) or token_id <= 0:
        return False
    with _lock:
        rec = _tokens.get(token_id)
        if rec is None or rec.revoked_at:
            return False
        rec.revoked_at = _now().strftime("%Y-%m-%dT%H:%M:%SZ")
    return True


def list_tokens(workspace_id: int, *, include_revoked: bool = False) -> list[dict]:
    if not isinstance(workspace_id, int) or workspace_id <= 0:
        return []
    with _lock:
        recs = [r for r in _tokens.values() if r.workspace_id == workspace_id]
        if not include_revoked:
            recs = [r for r in recs if not r.revoked_at]
    # token 値はマスクして返す (PII 保護)
    return [_serialize(r, mask_token=True) for r in recs]
