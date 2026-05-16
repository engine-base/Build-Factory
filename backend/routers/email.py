"""T-V3-B-30 / F-028: Email backend (templates list + test-send) REST endpoints.

Endpoints:
  GET  /api/email/templates    — list active EmailTemplate rows
                                 (auth: workspace_admin, x-workspace-id optional)
  POST /api/email/test-send    — enqueue a test send (rate-limited 10/hour/ws)

AC mapping (verbatim from docs/audit/2026-05-16_v3/T-V3-B-30.md):
  AC-F1 UNWANTED   : POST /api/email/test-send >10/hour/workspace → 429
  AC-F2 EVENT      : GET  /api/email/templates → 2xx + {templates: [...]}
  AC-F3 UNWANTED   : GET  /api/email/templates 認証無し → 401
  AC-F4 UNWANTED   : GET  /api/email/templates 入力 invalid → 422
  AC-F5 EVENT      : POST /api/email/test-send 正常 → 201 + {delivery_id, queued_at}
  AC-F6 UNWANTED   : POST /api/email/test-send 認証無し → 401
  AC-F7 UNWANTED   : POST /api/email/test-send 入力 invalid → 422
  AC-F8 UNWANTED   : POST /api/email/test-send 上限超 → 429
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, ValidationError

from services import email as email_service
from services.auth_middleware import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/email", tags=["email"])

# When set, the GET /api/email/templates endpoint enforces auth even if the
# global DEV_BYPASS_AUTH=1 toggle is enabled. Tests use this to assert AC-F3.
_STRICT_AUTH_ENV = "EMAIL_API_STRICT_AUTH"


def _error(
    code: str, message: str, *, status_code: int = 400, **extra: Any
) -> HTTPException:
    detail: dict[str, Any] = {"code": code, "message": message}
    detail.update(extra)
    return HTTPException(status_code=status_code, detail=detail)


def _require_user(
    user: Optional[dict] = Depends(get_current_user),
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """Require an authenticated caller.

    Returns the user claims dict on success. Raises 401 otherwise.
    Honours `EMAIL_API_STRICT_AUTH=1` to bypass the dev-mode default user so
    AC-F3 / AC-F6 (401 path) is testable.
    """
    strict = os.environ.get(_STRICT_AUTH_ENV, "0") == "1"
    if strict and not authorization:
        raise _error("email.unauthorized", "missing bearer token", status_code=401)
    if not user:
        raise _error("email.unauthorized", "unauthenticated", status_code=401)
    return user


def _resolve_workspace_id(raw: Optional[str]) -> Optional[int]:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise _error(
            "email.invalid_workspace_id",
            "x-workspace-id must be an integer",
            status_code=422,
            field="x-workspace-id",
        ) from exc


# ──────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────
class TestSendRequest(BaseModel):
    """POST /api/email/test-send request body.

    Mirrors openapi.yaml#components.schemas.test-send requestBody:
      - template_id (uuid, required)
      - recipient   (string, required)
    """
    template_id: str = Field(..., min_length=1, description="EmailTemplate UUID")
    recipient: str = Field(..., min_length=3, description="recipient email address")
    detail: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


# ──────────────────────────────────────────────────────────────────
# GET /api/email/templates
# ──────────────────────────────────────────────────────────────────
@router.get("/templates")
async def list_email_templates(
    user: dict = Depends(_require_user),
    x_workspace_id: Optional[str] = Header(default=None, alias="x-workspace-id"),
) -> dict[str, Any]:
    """List active email templates scoped to the workspace.

    AC-F2 EVENT-DRIVEN: returns `{templates: EmailTemplate[]}`.
    AC-F3 UNWANTED:     unauth → 401 (via _require_user).
    AC-F4 UNWANTED:     invalid x-workspace-id → 422 (via _resolve_workspace_id).
    """
    workspace_id = _resolve_workspace_id(x_workspace_id)
    rows = email_service.list_templates(workspace_id)
    return {
        "templates": rows,
        "workspace_id": workspace_id,
        "count": len(rows),
    }


# ──────────────────────────────────────────────────────────────────
# POST /api/email/test-send
# ──────────────────────────────────────────────────────────────────
@router.post("/test-send", status_code=status.HTTP_201_CREATED)
async def post_email_test_send(
    body: TestSendRequest,
    user: dict = Depends(_require_user),
    x_workspace_id: Optional[str] = Header(default=None, alias="x-workspace-id"),
) -> dict[str, Any]:
    """Enqueue a test email send.

    AC-F5 EVENT-DRIVEN: 201 + `{delivery_id, queued_at}`.
    AC-F1 / AC-F8 UNWANTED: rate-limit overflow → 429 with Retry-After.
    AC-F6 UNWANTED:        unauth → 401 (via _require_user).
    AC-F7 UNWANTED:        invalid body → 422 (FastAPI / Pydantic + manual checks).
    """
    workspace_id = _resolve_workspace_id(x_workspace_id)
    try:
        result = email_service.enqueue_test_send(
            workspace_id=workspace_id,
            template_id=body.template_id,
            recipient=body.recipient,
            detail=body.detail,
        )
    except email_service.InvalidRecipientError as exc:
        raise _error(
            "email.invalid_recipient",
            str(exc),
            status_code=422,
            field="recipient",
        ) from exc
    except email_service.TemplateNotFoundError as exc:
        raise _error("email.template_not_found", str(exc), status_code=404) from exc
    except email_service.RateLimitedError as exc:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "email.rate_limited",
                "message": str(exc),
                "retry_after": exc.retry_after,
                "limit": exc.limit,
                "window_seconds": exc.window_seconds,
            },
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except ValidationError as exc:  # pragma: no cover - FastAPI handles this earlier
        raise _error("email.validation_error", str(exc), status_code=422) from exc

    return {
        "delivery_id": result["delivery_id"],
        "queued_at": result["queued_at"],
        "template_id": result["template_id"],
        "recipient": result["recipient"],
        "status": result["status"],
    }
