"""T-V3-B-06 / F-004: Workspace member role + invitation revocation schemas.

EARS AC seed (T-V3-B-06 functional Tier):
  - EVENT-DRIVEN: PUT /api/workspaces/{id}/members/{user_id}/role updates the
                  member's workspace role and returns {role, updated_at}.
  - EVENT-DRIVEN: DELETE /api/workspaces/{id}/invitations/{token} marks a
                  pending invitation as revoked and returns {revoked_at}.

Consumed by S-013 workspace_settings / S-014 workspace_members / S-015
workspace_invite. Role enum mirrors openapi.yaml#/paths/.../members/{user_id}/role
and is validated by Pydantic with a clear 422 field-level error map.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Role enum is the union of OpenAPI spec roles (owner / admin / member /
# viewer / guest) plus workspace-internal aliases (ws_admin / contributor /
# reviewer) that the existing roles registry recognizes. The 6-role v2.1 set
# is the canonical source — see services.roles.ROLE_KEYS.
WorkspaceRole = Literal[
    "owner",
    "admin",
    "ws_admin",
    "member",
    "contributor",
    "viewer",
    "reviewer",
    "guest",
]


class WorkspaceMemberRoleUpdate(BaseModel):
    """T-V3-B-06 AC-F7 / AC-F9: PUT /api/workspaces/{id}/members/{user_id}/role.

    AC-F9 UNWANTED: invalid role → 422 with field-level error map (Pydantic).
    """

    role: WorkspaceRole = Field(..., description="new workspace member role")
    actor_user_id: str | None = Field(
        None,
        description="caller user_id (self-strip / owner protection guard)",
        max_length=255,
    )


class WorkspaceMemberRoleResponse(BaseModel):
    """T-V3-B-06 AC-F7: 2xx contract per features.json#F-004 / openapi.yaml."""

    role: WorkspaceRole
    updated_at: str


class WorkspaceInvitationRevokeResponse(BaseModel):
    """T-V3-B-06 AC-F10: 2xx contract per features.json#F-004 / openapi.yaml.

    revoked_at is an ISO-8601 timestamp captured at service-layer revocation
    time. token_prefix is included for audit log cross-reference but not the
    full token (PII / replay-safety).
    """

    revoked_at: str
    workspace_id: int
    token_prefix: str
