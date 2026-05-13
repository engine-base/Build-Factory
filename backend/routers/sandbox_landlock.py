"""T-012-03: Landlock + seccomp red-line policy REST endpoint.

Endpoint:
  POST /api/sandbox/landlock/evaluate         cmd + policy + sandbox_cfg を check
  GET  /api/sandbox/landlock/availability     kernel 対応状況
  GET  /api/sandbox/landlock/default-policy   default red-line policy

REUSE invariant: T-S0-09 backend/sandbox/{config,exec,__init__}.py 完全無改変.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from sandbox import landlock_policy as lp
from sandbox.config import SandboxConfig

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/sandbox/landlock",
    tags=["sandbox-landlock"],
)


def _error(code: str, message: str, *, status_code: int = 400) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def _map_service_error(e: lp.LandlockPolicyError) -> HTTPException:
    return _error("landlock_policy.invalid_input", str(e), status_code=400)


def _check_actor(actor: Optional[str]) -> Optional[str]:
    if actor is not None and not actor.strip():
        raise _error(
            "landlock_policy.unauthorized",
            "actor_user_id must not be empty when provided",
            status_code=401,
        )
    return actor.strip() if actor else None


class PolicyPayload(BaseModel):
    read_paths: list[str] = Field(default_factory=list)
    write_paths: list[str] = Field(default_factory=list)
    exec_paths: list[str] = Field(default_factory=list)
    denied_syscalls: Optional[list[str]] = None
    network_allowed: bool = False
    description: str = ""


class SandboxCfgPayload(BaseModel):
    allow_paths: list[str] = Field(default_factory=list)
    allow_hosts: list[str] = Field(default_factory=list)
    timeout_sec: int = 300


class EvaluateRequest(BaseModel):
    cmd: list[str]
    policy: Optional[PolicyPayload] = None  # None → DEFAULT_RED_LINE_POLICY
    sandbox_cfg: Optional[SandboxCfgPayload] = None
    actor_user_id: Optional[str] = None


def _build_policy(payload: Optional[PolicyPayload]) -> lp.LandlockPolicy:
    if payload is None:
        return lp.DEFAULT_RED_LINE_POLICY
    try:
        return lp.LandlockPolicy(
            read_paths=tuple(Path(p) for p in payload.read_paths),
            write_paths=tuple(Path(p) for p in payload.write_paths),
            exec_paths=tuple(Path(p) for p in payload.exec_paths),
            denied_syscalls=(
                tuple(payload.denied_syscalls)
                if payload.denied_syscalls is not None
                else lp.DEFAULT_DENIED_SYSCALLS
            ),
            network_allowed=payload.network_allowed,
            description=payload.description,
        )
    except (TypeError, ValueError) as e:
        raise _error(
            "landlock_policy.invalid_input",
            f"failed to construct policy: {e}",
            status_code=400,
        )


def _build_sandbox_cfg(
    payload: Optional[SandboxCfgPayload],
) -> Optional[SandboxConfig]:
    if payload is None:
        return None
    try:
        return SandboxConfig(
            allow_paths=tuple(Path(p) for p in payload.allow_paths),
            allow_hosts=tuple(payload.allow_hosts),
            timeout_sec=payload.timeout_sec,
        )
    except (TypeError, ValueError) as e:
        raise _error(
            "landlock_policy.invalid_input",
            f"failed to construct sandbox_cfg: {e}",
            status_code=400,
        )


@router.post("/evaluate")
async def evaluate_endpoint(body: EvaluateRequest) -> dict[str, Any]:
    _check_actor(body.actor_user_id)
    policy = _build_policy(body.policy)
    sandbox_cfg = _build_sandbox_cfg(body.sandbox_cfg)
    try:
        return lp.evaluate_command(body.cmd, policy, sandbox_cfg)
    except lp.LandlockPolicyError as e:
        raise _map_service_error(e)


@router.get("/availability")
async def availability_endpoint() -> dict[str, Any]:
    return lp.detect_landlock_availability()


@router.get("/default-policy")
async def default_policy_endpoint() -> dict[str, Any]:
    p = lp.DEFAULT_RED_LINE_POLICY
    return {
        "read_paths": [str(x) for x in p.read_paths],
        "write_paths": [str(x) for x in p.write_paths],
        "exec_paths": [str(x) for x in p.exec_paths],
        "denied_syscalls": list(p.denied_syscalls),
        "network_allowed": p.network_allowed,
        "description": p.description,
    }
