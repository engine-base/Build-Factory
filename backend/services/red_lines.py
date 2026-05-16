"""T-V3-B-17: Red-lines backend service (F-012).

Provides CRUD + pattern-test logic for ``red_lines`` and lifecycle management
for ``red_line_violations``. Builds on the pure-Python pattern detector in
``services.red_line_detector`` (T-012-02) and exposes process-local persistence
so the router layer is fully testable without a Postgres / Supabase backend.

設計:
  - In-process store (process-scoped) で workspace 単位の red_lines / violations を保持
  - ``red_line_detector.detect_patterns`` を再利用し、新規に regex を増やさない
    (drift guard / T-012-02 invariant)
  - Workspace admin がワークスペース固有 rule を追加でき、`test` で
    sample text に対する一致集合を返す
  - Violation 状態遷移: ``pending`` -> ``approved`` | ``rejected``
    再遷移は 409 conflict (router 層で変換)

AC マッピング (T-V3-B-17 audit MD と 1:1):
  AC-F1 UBIQUITOUS          : evaluate() で全 AI action を pattern check
  AC-F2 EVENT-DRIVEN(block) : block 一致時に pending violation を生成
  AC-F3 UNWANTED(pending)   : pending 中の session を resume させない
  AC-F4 EVENT-DRIVEN(approve): approve_violation() で resolved + resume signal
  AC-F5 UNWANTED(409)       : 既 resolved を approve すると VIOLATION_ALREADY_RESOLVED
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from services import red_line_detector as rld


# ──────────────────────────────────────────────────────────────────────
# Errors
# ──────────────────────────────────────────────────────────────────────


class RedLineServiceError(Exception):
    """Base error. router 層が HTTPException に変換する."""

    code = "red_lines.error"
    status_code = 400


class InvalidRedLineInput(RedLineServiceError):
    code = "red_lines.invalid_input"
    status_code = 422


class WorkspaceNotFound(RedLineServiceError):
    code = "red_lines.workspace_not_found"
    status_code = 404


class ViolationNotFound(RedLineServiceError):
    code = "red_lines.violation_not_found"
    status_code = 404


class ViolationAlreadyResolved(RedLineServiceError):
    code = "red_lines.violation_already_resolved"
    status_code = 409


# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────


VIOLATION_PENDING = "pending"
VIOLATION_APPROVED = "approved"
VIOLATION_REJECTED = "rejected"

VALID_ACTIONS = ("block", "warn", "log")
VALID_CATEGORIES = frozenset(rld.DEFAULT_CATEGORIES)

MAX_PATTERN_LEN = 4096
MAX_SAMPLE_LEN = rld.MAX_TARGET_LEN  # 200KB


# ──────────────────────────────────────────────────────────────────────
# Datamodel
# ──────────────────────────────────────────────────────────────────────


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RedLine:
    """Per-workspace red-line rule (E-031)."""

    red_line_id: str
    workspace_id: str
    category: str
    pattern: str
    action: str
    description: str = ""
    is_enabled: bool = True
    created_at: str = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "red_line_id": self.red_line_id,
            "workspace_id": self.workspace_id,
            "category": self.category,
            "pattern": self.pattern,
            "action": self.action,
            "description": self.description,
            "is_enabled": self.is_enabled,
            "created_at": self.created_at,
        }


@dataclass
class RedLineViolation:
    """Per-action violation record (E-032)."""

    violation_id: str
    workspace_id: str
    red_line_id: str
    session_id: Optional[str]
    matched_text: str
    action_taken: str  # blocked | warned | logged
    status: str = VIOLATION_PENDING  # pending | approved | rejected
    resolution_reason: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[str] = None
    created_at: str = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "violation_id": self.violation_id,
            "workspace_id": self.workspace_id,
            "red_line_id": self.red_line_id,
            "session_id": self.session_id,
            "matched_text": self.matched_text,
            "action_taken": self.action_taken,
            "status": self.status,
            "resolution_reason": self.resolution_reason,
            "resolved_by": self.resolved_by,
            "resolved_at": self.resolved_at,
            "created_at": self.created_at,
        }


# ──────────────────────────────────────────────────────────────────────
# Storage (process-scoped, thread-safe)
# ──────────────────────────────────────────────────────────────────────


_LOCK = threading.RLock()
_RED_LINES: dict[str, RedLine] = {}
_VIOLATIONS: dict[str, RedLineViolation] = {}
# Sessions known to be blocked by a pending violation. AC-F3.
_BLOCKED_SESSIONS: set[str] = set()


def reset_store() -> None:
    """Clear process-local stores. tests only."""
    with _LOCK:
        _RED_LINES.clear()
        _VIOLATIONS.clear()
        _BLOCKED_SESSIONS.clear()


# ──────────────────────────────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────────────────────────────


def _validate_workspace_id(value: Any) -> str:
    if value is None or not isinstance(value, str) or not value.strip():
        raise InvalidRedLineInput("workspace_id must be a non-empty string")
    return value.strip()


def _validate_category(category: Any) -> str:
    if not isinstance(category, str) or not category.strip():
        raise InvalidRedLineInput("category must be a non-empty string")
    c = category.strip()
    if c not in VALID_CATEGORIES:
        raise InvalidRedLineInput(
            f"category must be one of {sorted(VALID_CATEGORIES)}, got {c!r}"
        )
    return c


def _validate_action(action: Any) -> str:
    if not isinstance(action, str):
        raise InvalidRedLineInput("action must be a string")
    a = action.strip()
    if a not in VALID_ACTIONS:
        raise InvalidRedLineInput(
            f"action must be one of {list(VALID_ACTIONS)}, got {a!r}"
        )
    return a


def _validate_pattern(pattern: Any) -> str:
    if not isinstance(pattern, str) or not pattern.strip():
        raise InvalidRedLineInput("pattern must be a non-empty string")
    p = pattern.strip()
    if len(p) > MAX_PATTERN_LEN:
        raise InvalidRedLineInput(
            f"pattern too long: {len(p)} > {MAX_PATTERN_LEN}"
        )
    # try to compile the regex so callers get a 422 instead of 500
    import re as _re
    try:
        _re.compile(p)
    except _re.error as e:
        raise InvalidRedLineInput(f"pattern is not a valid regex: {e}") from None
    return p


def _validate_sample_text(text: Any) -> str:
    if not isinstance(text, str):
        raise InvalidRedLineInput("sample_text must be a string")
    if len(text) == 0:
        raise InvalidRedLineInput("sample_text must not be empty")
    if len(text) > MAX_SAMPLE_LEN:
        raise InvalidRedLineInput(
            f"sample_text too long: {len(text)} > {MAX_SAMPLE_LEN}"
        )
    return text


# ──────────────────────────────────────────────────────────────────────
# CRUD: red_lines
# ──────────────────────────────────────────────────────────────────────


def list_red_lines(workspace_id: str) -> list[dict[str, Any]]:
    """Return red_lines for the workspace + the global defaults.

    Backs AC-F6 (GET /api/workspaces/{id}/red-lines returns red_lines).
    """
    ws = _validate_workspace_id(workspace_id)
    with _LOCK:
        ws_rules = [r for r in _RED_LINES.values() if r.workspace_id == ws]
    # default seeded categories (action mapped from rule severity)
    defaults = [
        {
            "red_line_id": f"default::{r.rule_key}",
            "workspace_id": ws,
            "category": r.category,
            "pattern": r.pattern,
            "action": rld.severity_to_action(r.severity),
            "description": r.description,
            "is_enabled": True,
            "created_at": "1970-01-01T00:00:00+00:00",
            "is_default": True,
        }
        for r in rld.DEFAULT_RULES
    ]
    custom = [{**r.to_dict(), "is_default": False} for r in ws_rules]
    # deterministic order: defaults first, then custom by created_at
    custom.sort(key=lambda r: (r["category"], r["created_at"]))
    return defaults + custom


def create_red_line(
    workspace_id: str,
    *,
    category: str,
    pattern: str,
    action: str,
    description: str = "",
) -> dict[str, Any]:
    """Create a workspace-specific red_line. Backs AC-F9.

    Returns the persisted record. `red_line_id` is a generated UUID.
    """
    ws = _validate_workspace_id(workspace_id)
    cat = _validate_category(category)
    pat = _validate_pattern(pattern)
    act = _validate_action(action)
    if description is not None and not isinstance(description, str):
        raise InvalidRedLineInput("description must be a string when provided")

    rid = str(uuid.uuid4())
    rl = RedLine(
        red_line_id=rid,
        workspace_id=ws,
        category=cat,
        pattern=pat,
        action=act,
        description=description or "",
    )
    with _LOCK:
        _RED_LINES[rid] = rl
    return rl.to_dict()


def test_red_line(workspace_id: str, *, sample_text: str) -> dict[str, Any]:
    """Match sample_text against active red_lines + defaults. Backs AC-F12.

    Returns {matched: [...], would_block: bool}.
    """
    ws = _validate_workspace_id(workspace_id)
    text = _validate_sample_text(sample_text)

    matched: list[dict[str, Any]] = []
    # 1. default rules (delegated to detect_patterns for invariants)
    default_hits = rld.detect_patterns(text)
    for hit in default_hits:
        matched.append({
            "red_line_id": f"default::{hit['rule_key']}",
            "workspace_id": ws,
            "category": hit["category"],
            "pattern_type": hit["pattern_type"],
            "severity": hit["severity"],
            "action": hit["action"],
            "description": hit["description"],
            "is_default": True,
        })

    # 2. workspace-specific custom rules
    with _LOCK:
        ws_rules = [r for r in _RED_LINES.values()
                    if r.workspace_id == ws and r.is_enabled]
    import re as _re
    for rl in ws_rules:
        try:
            if _re.search(rl.pattern, text, _re.IGNORECASE):
                matched.append({
                    "red_line_id": rl.red_line_id,
                    "workspace_id": ws,
                    "category": rl.category,
                    "pattern": rl.pattern,
                    "severity": "block" if rl.action == "block" else "warn"
                                if rl.action == "warn" else "log",
                    "action": rl.action,
                    "description": rl.description,
                    "is_default": False,
                })
        except _re.error:
            # 不正 regex はスキップ (create_red_line 側で弾いているはず)
            continue

    would_block = any(m["action"] == "block" for m in matched)
    return {"matched": matched, "would_block": would_block}


# ──────────────────────────────────────────────────────────────────────
# Evaluation + violation lifecycle (F-012 core)
# ──────────────────────────────────────────────────────────────────────


def evaluate_action(
    workspace_id: str,
    *,
    target_text: str,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    """AC-F1 / AC-F2: evaluate text + side effect (pending violation on block).

    Returns:
      {
        "allowed": bool,            # False iff block hit
        "action": "block"|"warn"|"log"|"pass",
        "violations": [...],        # newly created violation dicts (block only)
      }
    """
    ws = _validate_workspace_id(workspace_id)
    if not isinstance(target_text, str) or not target_text:
        raise InvalidRedLineInput("target_text must be a non-empty string")

    matches = test_red_line(ws, sample_text=target_text)["matched"]
    has_block = any(m["action"] == "block" for m in matches)
    has_warn = any(m["action"] == "warn" for m in matches)

    created: list[dict[str, Any]] = []
    if has_block:
        # AC-F2: create pending violation per block hit
        with _LOCK:
            for m in matches:
                if m["action"] != "block":
                    continue
                vid = str(uuid.uuid4())
                v = RedLineViolation(
                    violation_id=vid,
                    workspace_id=ws,
                    red_line_id=m["red_line_id"],
                    session_id=session_id,
                    matched_text=target_text[:1000],
                    action_taken="blocked",
                    status=VIOLATION_PENDING,
                )
                _VIOLATIONS[vid] = v
                created.append(v.to_dict())
                if session_id:
                    # AC-F3: block this session from resuming
                    _BLOCKED_SESSIONS.add(session_id)

    if has_block:
        action = "block"
    elif has_warn:
        action = "warn"
    elif matches:
        action = "log"
    else:
        action = "pass"

    return {
        "allowed": not has_block,
        "action": action,
        "violations": created,
        "matched_count": len(matches),
    }


def is_session_blocked(session_id: str) -> bool:
    """AC-F3 query helper: session 中に pending violation があるか."""
    if not isinstance(session_id, str) or not session_id:
        return False
    with _LOCK:
        return session_id in _BLOCKED_SESSIONS


def list_violations(
    workspace_id: str,
    *,
    status: Optional[str] = None,
) -> list[dict[str, Any]]:
    ws = _validate_workspace_id(workspace_id)
    if status is not None and status not in (
        VIOLATION_PENDING, VIOLATION_APPROVED, VIOLATION_REJECTED,
    ):
        raise InvalidRedLineInput(f"unknown status: {status!r}")
    with _LOCK:
        items = [v for v in _VIOLATIONS.values() if v.workspace_id == ws]
    if status is not None:
        items = [v for v in items if v.status == status]
    items.sort(key=lambda v: v.created_at, reverse=True)
    return [v.to_dict() for v in items]


def get_violation(violation_id: str) -> dict[str, Any]:
    if not isinstance(violation_id, str) or not violation_id:
        raise InvalidRedLineInput("violation_id must be a non-empty string")
    with _LOCK:
        v = _VIOLATIONS.get(violation_id)
    if v is None:
        raise ViolationNotFound(f"violation not found: {violation_id}")
    return v.to_dict()


def approve_violation(
    violation_id: str,
    *,
    actor_user_id: str,
    reason: str,
) -> dict[str, Any]:
    """AC-F4 / AC-F5: resolve a pending violation as approved.

    Returns the updated violation dict, including ``resumed_session_id``
    (None if no session was tied to the violation).
    """
    if not isinstance(violation_id, str) or not violation_id:
        raise InvalidRedLineInput("violation_id must be a non-empty string")
    if not isinstance(actor_user_id, str) or not actor_user_id.strip():
        raise InvalidRedLineInput("actor_user_id must be a non-empty string")
    if not isinstance(reason, str) or not reason.strip():
        raise InvalidRedLineInput("reason must be a non-empty string")

    with _LOCK:
        v = _VIOLATIONS.get(violation_id)
        if v is None:
            raise ViolationNotFound(f"violation not found: {violation_id}")
        if v.status != VIOLATION_PENDING:
            # AC-F5
            raise ViolationAlreadyResolved(
                f"violation already resolved: {v.status}"
            )
        v.status = VIOLATION_APPROVED
        v.resolution_reason = reason.strip()
        v.resolved_by = actor_user_id.strip()
        v.resolved_at = _utcnow()
        resumed = v.session_id
        if resumed:
            _BLOCKED_SESSIONS.discard(resumed)
        out = v.to_dict()
    out["resumed_session_id"] = resumed
    out["approved_at"] = out["resolved_at"]
    return out


def reject_violation(
    violation_id: str,
    *,
    actor_user_id: str,
    reason: str,
) -> dict[str, Any]:
    if not isinstance(violation_id, str) or not violation_id:
        raise InvalidRedLineInput("violation_id must be a non-empty string")
    if not isinstance(actor_user_id, str) or not actor_user_id.strip():
        raise InvalidRedLineInput("actor_user_id must be a non-empty string")
    if not isinstance(reason, str) or not reason.strip():
        raise InvalidRedLineInput("reason must be a non-empty string")

    with _LOCK:
        v = _VIOLATIONS.get(violation_id)
        if v is None:
            raise ViolationNotFound(f"violation not found: {violation_id}")
        if v.status != VIOLATION_PENDING:
            raise ViolationAlreadyResolved(
                f"violation already resolved: {v.status}"
            )
        v.status = VIOLATION_REJECTED
        v.resolution_reason = reason.strip()
        v.resolved_by = actor_user_id.strip()
        v.resolved_at = _utcnow()
        # rejected: session は依然 block 状態のままで良い (admin が許可しなかった)
        out = v.to_dict()
    out["rejected_at"] = out["resolved_at"]
    return out


__all__ = [
    # errors
    "RedLineServiceError",
    "InvalidRedLineInput",
    "WorkspaceNotFound",
    "ViolationNotFound",
    "ViolationAlreadyResolved",
    # constants
    "VIOLATION_PENDING",
    "VIOLATION_APPROVED",
    "VIOLATION_REJECTED",
    "VALID_ACTIONS",
    "VALID_CATEGORIES",
    # data
    "RedLine",
    "RedLineViolation",
    # public api
    "reset_store",
    "list_red_lines",
    "create_red_line",
    "test_red_line",
    "evaluate_action",
    "is_session_blocked",
    "list_violations",
    "get_violation",
    "approve_violation",
    "reject_violation",
]
