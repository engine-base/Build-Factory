"""
invitations.py — F-004 public invitation lookup.

T-V3-B-05 で追加:
  GET /api/invitations/{token}    public (no auth) — lookup invitation by token

既存の `routers.workspaces` 経由 invitations_router (POST /accept, /signup,
GET /lookup/{token}) はそのまま温存し、ここでは F-004 OpenAPI 仕様準拠の
"public token resolve" のみを担う。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from services import invitation_service as inv

router = APIRouter(prefix="/api/invitations", tags=["invitations"])


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code, detail={"code": code, "message": message}
    )


@router.get("/{token}")
async def get_invitation_by_token(token: str) -> dict:
    """T-V3-B-05 AC-F13 / AC-F3.

    EVENT-DRIVEN: valid token → 2xx with {invitation, workspace_name?, inviter_name?}.
    UNWANTED: expires_at 経過 → 409 expired.
    UNWANTED: token が存在しない → 404 not_found.
    """
    token = (token or "").strip()
    if not token:
        raise _error(
            "invitations.invalid_token", "token must not be empty", status_code=400
        )
    if len(token) < 8:
        raise _error(
            "invitations.invalid_token",
            "token must be at least 8 chars",
            status_code=400,
        )
    if len(token) > 200:
        raise _error(
            "invitations.token_too_long", "token too long", status_code=400
        )

    found = await inv.public_lookup(token)
    if not found:
        raise _error(
            "invitations.not_found", "invitation not found", status_code=404
        )

    # AC-F3 UNWANTED: expired → 409
    if found.get("is_expired"):
        raise _error(
            "invitations.expired",
            "invitation expired (past expires_at)",
            status_code=409,
        )

    # status が pending 以外 (accepted / revoked) も 409 で返す
    status = found.get("status")
    if status and status != "pending":
        raise _error(
            "invitations.already_used",
            f"invitation already in state '{status}'",
            status_code=409,
        )

    # response: F-004 OpenAPI 契約に倣う
    response: dict = {
        "invitation": {
            "scope": found.get("scope"),
            "email": found.get("email"),
            "role": found.get("role"),
            "status": found.get("status"),
            "expires_at": found.get("expires_at"),
            "invited_by": found.get("invited_by"),
        }
    }
    if found.get("scope") == "workspace":
        response["invitation"]["workspace_id"] = found.get("workspace_id")
    else:
        response["invitation"]["account_id"] = found.get("account_id")
    return response
