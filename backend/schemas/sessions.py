"""T-V3-B-15 / F-010: Sessions backend Pydantic schemas.

OpenAPI 仕様: docs/api-design/2026-05-16_v3/openapi.yaml#Session
Entity: E-024 Session, E-025 SessionLog

このモジュールは sessions backend の list / detail / kill / kill-all
endpoint の request / response shape を定義する.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# T-V3-B-15: AC-F4 / AC-F7 — Session DTO (OpenAPI #Session に対応)
# ─────────────────────────────────────────────────────────────────────────────


class SessionOut(BaseModel):
    """Entity E-024 Session の serialize 形 (OpenAPI #Session に整合).

    DB の sessions テーブル + ClaudeAgentRunner.SessionRecord と相互運用する.
    """

    id: int = Field(..., description="DB primary key (BIGSERIAL).")
    sdk_session_id: Optional[str] = Field(
        None, description="claude-agent-sdk が発行する session id."
    )
    workspace_id: Optional[int] = Field(None, description="所属 workspace id.")
    project_id: Optional[int] = Field(None, description="所属 bf_project id.")
    bf_task_id: Optional[int] = Field(None, description="所属 bf_task id.")
    agent_persona: Optional[str] = Field(
        None, description="mary / devon / quinn 等の BMAD persona."
    )
    skill_name: Optional[str] = Field(None, description="呼び出した skill 名.")
    prompt: str = Field("", description="初期 prompt (initial_prompt).")
    status: str = Field(
        "running",
        description="running / done / crashed / cancelled / paused (DDL CHECK).",
    )
    resume_choice: Optional[str] = Field(
        None,
        description="from_checkpoint / rerun_full / manual_fix / cancel.",
    )
    crash_reason: Optional[str] = Field(None, description="crash 時の理由.")
    started_at: Optional[Any] = Field(None, description="開始タイムスタンプ.")
    completed_at: Optional[Any] = Field(None, description="完了タイムスタンプ.")


class SessionListResponse(BaseModel):
    """GET /api/workspaces/{id}/sessions の response shape.

    OpenAPI yaml:
        type: object
        properties:
          sessions: array of #/components/schemas/Session
    """

    sessions: list[SessionOut] = Field(default_factory=list)


class SessionDetailResponse(BaseModel):
    """GET /api/sessions/{id} の response shape.

    OpenAPI yaml:
        type: object
        properties:
          session: #/components/schemas/Session
          logs_tail_url: string
    """

    session: SessionOut
    logs_tail_url: str = Field(
        ...,
        description="WS /ws/sessions/{id}/log の URL (S-032 で stream する).",
    )


class KillSessionResponse(BaseModel):
    """POST /api/sessions/{id}/kill の response shape.

    OpenAPI yaml:
        type: object
        properties:
          killed_at: string format date-time
    """

    killed_at: str = Field(..., description="kill 実行時刻 (ISO-8601).")


class KillAllSessionsResponse(BaseModel):
    """POST /api/workspaces/{id}/sessions/kill-all の response shape.

    OpenAPI yaml:
        type: object
        properties:
          killed_count: integer
    """

    killed_count: int = Field(..., ge=0, description="kill された session 件数.")


# Status filter (GET /api/workspaces/{id}/sessions?status=...).
VALID_SESSION_STATUS_FILTER: tuple[str, ...] = (
    "running", "paused", "crashed", "completed",
)


__all__ = (
    "SessionOut",
    "SessionListResponse",
    "SessionDetailResponse",
    "KillSessionResponse",
    "KillAllSessionsResponse",
    "VALID_SESSION_STATUS_FILTER",
)
