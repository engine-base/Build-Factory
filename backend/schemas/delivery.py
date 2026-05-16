"""T-V3-B-21 / F-013: Delivery schemas (Pydantic).

Public schemas for the 3 delivery endpoints exposed on /api/workspaces/{id}/delivery:

    GET  /api/workspaces/{id}/delivery               -> {delivery: Delivery}
    POST /api/workspaces/{id}/delivery/approve       -> {approved_at}
    POST /api/workspaces/{id}/delivery/send-client   -> {sent_at, delivery_token}

The wire shapes follow ``docs/api-design/2026-05-16_v3/openapi.yaml``
components.schemas.Delivery (workspace_id / status / approved_at / sent_at /
artifact_urls).
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# RFC 5322 ライト互換 email pattern (避ける: pydantic[email]).
_EMAIL_PATTERN = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"

DeliveryStatus = Literal["draft", "approved", "sent", "accepted"]


class Delivery(BaseModel):
    """Workspace delivery package metadata (openapi.yaml#components.schemas.Delivery)."""

    id: str
    workspace_id: str
    status: DeliveryStatus
    approved_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    artifact_urls: List[str] = Field(default_factory=list)


class GetDeliveryResponse(BaseModel):
    delivery: Delivery


class ApproveDeliveryResponse(BaseModel):
    approved_at: datetime


class SendClientRequest(BaseModel):
    """Body for POST /api/workspaces/{id}/delivery/send-client.

    ``client_email`` is required by features.json#F-013.api_endpoints. ``ttl_days``
    is an optional override (default 14) for the public token's expiry.
    """

    client_email: str = Field(..., pattern=_EMAIL_PATTERN, description="client email")
    ttl_days: Optional[int] = Field(default=None, ge=1, le=365)


class SendClientResponse(BaseModel):
    sent_at: datetime
    delivery_token: str
