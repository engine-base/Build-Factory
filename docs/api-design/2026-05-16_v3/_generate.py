#!/usr/bin/env python3
"""
Build-Factory v3 api-design generator.

Reads:
  docs/functional-breakdown/2026-05-16_v3/features.json
  docs/functional-breakdown/2026-05-16_v3/entities.json
  docs/functional-breakdown/2026-05-16_v3/roles.json
  docs/functional-breakdown/2026-05-16_v3/api-drift-summary.md

Writes:
  docs/api-design/2026-05-16_v3/openapi.yaml
  docs/api-design/2026-05-16_v3/ears-ac-seed.json
  docs/api-design/2026-05-16_v3/lint-mapping.json
  docs/api-design/2026-05-16_v3/decision-log.json

(types.ts and api-spec.md are written by hand / via separate templates.)
"""
from __future__ import annotations

import json
import re
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
FB_DIR = ROOT / "docs" / "functional-breakdown" / "2026-05-16_v3"
OUT_DIR = ROOT / "docs" / "api-design" / "2026-05-16_v3"

CREATED_AT = "2026-05-16"
VERSION = "v3"


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

# v3 features.json declares ad-hoc type strings on inputs/outputs.
# Map them to OpenAPI / JSON Schema fragments.
TYPE_MAP: dict[str, dict[str, Any]] = {
    "string": {"type": "string"},
    "string?": {"type": "string", "nullable": True},
    "int": {"type": "integer"},
    "int?": {"type": "integer", "nullable": True},
    "integer": {"type": "integer"},
    "number": {"type": "number"},
    "boolean": {"type": "boolean"},
    "boolean?": {"type": "boolean", "nullable": True},
    "uuid": {"type": "string", "format": "uuid"},
    "uuid?": {"type": "string", "format": "uuid", "nullable": True},
    "timestamptz": {"type": "string", "format": "date-time"},
    "timestamp": {"type": "string", "format": "date-time"},
    "date": {"type": "string", "format": "date"},
    "json": {"type": "object", "additionalProperties": True},
    "jsonb": {"type": "object", "additionalProperties": True},
    "string[]": {"type": "array", "items": {"type": "string"}},
    "uuid[]": {"type": "array", "items": {"type": "string", "format": "uuid"}},
    "uuid[]?": {"type": "array", "items": {"type": "string", "format": "uuid"}, "nullable": True},
    "int[]": {"type": "array", "items": {"type": "integer"}},
}


def descriptor_to_schema(desc: str) -> dict[str, Any]:
    """Convert a v3 type descriptor like 'string?' or 'Skill[]' to an OpenAPI schema fragment."""
    if not isinstance(desc, str):
        # nested object descriptor — render as free-form object
        return {"type": "object", "additionalProperties": True}
    d = desc.strip()

    # Enum-like descriptor: "anthropic|github|slack|google"
    if "|" in d and not d.endswith("[]"):
        enum_vals = [s.strip() for s in d.split("|")]
        return {"type": "string", "enum": enum_vals}

    if d in TYPE_MAP:
        return TYPE_MAP[d]

    # Entity array reference, e.g. "Skill[]"
    if d.endswith("[]"):
        inner = d[:-2]
        if inner in TYPE_MAP:
            return {"type": "array", "items": TYPE_MAP[inner]}
        # Treat capitalized inner as $ref to component schema
        if inner and inner[0].isupper():
            return {"type": "array", "items": {"$ref": f"#/components/schemas/{inner}"}}
        return {"type": "array", "items": {"type": "string"}}

    # Entity reference (Capitalized)
    if d and d[0].isupper():
        # strip optional suffix
        if d.endswith("?"):
            return {"$ref": f"#/components/schemas/{d[:-1]}"}
        return {"$ref": f"#/components/schemas/{d}"}

    # Fallback
    return {"type": "string", "description": f"v3 descriptor: {d}"}


def extract_path_params(path: str) -> list[str]:
    return re.findall(r"\{([^}]+)\}", path)


def operation_id(method: str, path: str) -> str:
    # Strip leading /api/
    p = re.sub(r"^/api/", "", path)
    p = re.sub(r"^/ws/", "ws/", p)
    # Replace {param} with by_param
    p = re.sub(r"\{(\w+)\}", r"by_\1", p)
    # Slashes / hyphens -> underscores
    p = re.sub(r"[/\-]", "_", p)
    p = re.sub(r"_+", "_", p).strip("_")
    return f"{method.lower()}_{p}"


def status_to_error_ref(status: int) -> str:
    return {
        401: "#/components/responses/Unauthorized",
        403: "#/components/responses/Forbidden",
        404: "#/components/responses/NotFound",
        409: "#/components/responses/Conflict",
        422: "#/components/responses/ValidationError",
        429: "#/components/responses/RateLimited",
        500: "#/components/responses/InternalServerError",
    }.get(status, "#/components/responses/InternalServerError")


def status_to_code(status: int) -> str:
    return {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMITED",
        500: "INTERNAL_SERVER_ERROR",
    }.get(status, "ERROR")


def status_to_ears_form(status: int, trigger: str) -> str:
    """Compose a UNWANTED EARS form. status 429 uses EVENT-DRIVEN per v3-core convention."""
    if status == 429:
        return f"EVENT-DRIVEN: When {trigger}, the system shall return 429 (rate limited)."
    return f"UNWANTED: If {trigger}, the system shall return {status}."


def role_to_auth(role: str) -> dict[str, Any]:
    """Map features.json 'auth' string to OpenAPI security + x-bf-auth.role metadata."""
    if role == "public":
        return {"required": False, "role": "public", "middleware": []}
    middleware: list[str] = ["require_auth"]
    return {"required": True, "role": role, "middleware": middleware}


# Map auth role -> AuthSession / RLS access_control_policies notation (BF profile rule)
def access_policies_for(role: str, related_entities: list[str]) -> list[str]:
    """Build a list of <table>:<policy_name> pseudo-references using BF naming convention.

    Since features.json does not enumerate per-endpoint RLS policies, we surface the
    workspace_member_read / account_owner_write convention by role + related_entities tables.
    """
    if role == "public":
        return []
    # Strip "E-NNN " prefix
    tables: list[str] = []
    for re_ent in related_entities or []:
        if " " in re_ent:
            ent_name = re_ent.split(" ", 1)[1].strip()
        else:
            ent_name = re_ent
        # Crude snake_case
        snake = re.sub(r"(?<!^)(?=[A-Z])", "_", ent_name).lower()
        tables.append(snake)
    suffix = {
        "authenticated": "authenticated_select",
        "member": "workspace_member_rw",
        "workspace_admin": "workspace_admin_rw",
        "account_owner": "account_owner_all",
    }.get(role, "authenticated_select")
    return [f"{t}:{suffix}" for t in tables]


# -----------------------------------------------------------------------------
# Implementation path resolution
# -----------------------------------------------------------------------------

# Map path leading segment to backend router file name
ROUTER_BY_PREFIX = [
    ("/api/auth/", "auth"),
    ("/api/skills/", "skills"),
    ("/api/skills", "skills"),
    ("/api/ai-employees/", "ai_employees"),
    ("/api/ai-employees", "ai_employees"),
    ("/api/accounts/", "accounts"),
    ("/api/accounts", "accounts"),
    ("/api/workspaces/", "workspaces"),
    ("/api/workspaces", "workspaces"),
    ("/api/invitations/", "invitations"),
    ("/api/tasks/", "tasks"),
    ("/api/tasks", "tasks"),
    ("/api/sessions/", "sessions"),
    ("/api/sessions", "sessions"),
    ("/api/violations/", "violations"),
    ("/api/prs/", "prs"),
    ("/api/prs", "prs"),
    ("/api/client/", "client_portal"),
    ("/api/comments/", "comments"),
    ("/api/me/", "me"),
    ("/api/me", "me"),
    ("/api/search", "search"),
    ("/api/audit-logs", "audit_logs"),
    ("/api/notifications", "notifications"),
    ("/api/observability/", "observability"),
    ("/api/email/", "email"),
    ("/api/design-system/", "design_system"),
    ("/api/llm-providers/", "llm_providers"),
    ("/api/mcp/", "mcp"),
    ("/api/slack/", "slack"),
    ("/api/reports/", "reports"),
    ("/api/system/", "system"),
    ("/api/ai/", "ai_review"),
    ("/api/exports/", "exports"),
    ("/ws/", "ws"),
]


def router_file_for(path: str) -> str:
    for prefix, fname in ROUTER_BY_PREFIX:
        if path.startswith(prefix):
            return fname
    return "misc"


def implementation_path_for(method: str, path: str) -> str:
    router = router_file_for(path)
    fn = operation_id(method, path)
    if path.startswith("/ws/"):
        return f"backend/routers/{router}.py::{fn}"
    return f"backend/routers/{router}.py::{fn}"


# -----------------------------------------------------------------------------
# Schema collection: build {req,res} schema components per endpoint
# -----------------------------------------------------------------------------

def build_request_body_schema(ep: dict[str, Any], path: str) -> dict[str, Any] | None:
    """Build a JSON Schema object from `inputs`, excluding path params."""
    inputs = ep.get("inputs") or {}
    if not isinstance(inputs, dict):
        return None
    path_params = set(extract_path_params(path))
    props: dict[str, dict[str, Any]] = {}
    required: list[str] = []
    for k, v in inputs.items():
        if k in path_params:
            continue
        # GET /ws path: keep all body — but methods like GET shouldn't have bodies; handled later
        schema = descriptor_to_schema(v)
        props[k] = schema
        if isinstance(v, str) and not v.endswith("?"):
            required.append(k)
    if not props:
        return None
    out: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        out["required"] = required
    return out


def build_query_params(ep: dict[str, Any], path: str) -> list[dict[str, Any]]:
    """For GET / DELETE methods, inputs (minus path params) become query params."""
    method = ep["method"]
    inputs = ep.get("inputs") or {}
    if not isinstance(inputs, dict):
        return []
    if method not in {"GET", "DELETE"}:
        return []
    path_params = set(extract_path_params(path))
    out: list[dict[str, Any]] = []
    for k, v in inputs.items():
        if k in path_params:
            continue
        required = isinstance(v, str) and not v.endswith("?")
        # strip ? before mapping
        clean = v[:-1] if isinstance(v, str) and v.endswith("?") else v
        schema = descriptor_to_schema(clean)
        out.append({
            "name": k,
            "in": "query",
            "required": required,
            "schema": schema,
        })
    return out


def build_path_params(path: str, ep_inputs: dict[str, Any] | None) -> list[dict[str, Any]]:
    params = extract_path_params(path)
    out: list[dict[str, Any]] = []
    inputs = ep_inputs or {}
    for p in params:
        # find type from inputs if present
        desc = inputs.get(p)
        schema: dict[str, Any]
        if isinstance(desc, str):
            clean = desc[:-1] if desc.endswith("?") else desc
            schema = descriptor_to_schema(clean)
        else:
            # default uuid for {id}, {user_id}, etc.
            schema = {"type": "string", "format": "uuid"} if (p == "id" or p.endswith("_id")) else {"type": "string"}
        out.append({
            "name": p,
            "in": "path",
            "required": True,
            "schema": schema,
        })
    return out


def build_response_2xx_schema(ep: dict[str, Any]) -> dict[str, Any]:
    """Build a JSON Schema object from `outputs_2xx`. Empty -> empty object."""
    outputs = ep.get("outputs_2xx") or {}
    if not isinstance(outputs, dict):
        return {"type": "object"}
    props: dict[str, dict[str, Any]] = {}
    for k, v in outputs.items():
        props[k] = descriptor_to_schema(v)
    return {"type": "object", "properties": props} if props else {"type": "object"}


# -----------------------------------------------------------------------------
# Entity schemas: minimal envelopes
# -----------------------------------------------------------------------------

def build_entity_schemas(entities: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for e in entities:
        name = e["name"]
        props: dict[str, Any] = {}
        required: list[str] = []
        for fd in e.get("fields", []) or []:
            fname = fd.get("name")
            if not fname:
                continue
            # Guess type from name
            if fname == "id" or fname.endswith("_id"):
                schema = {"type": "string", "format": "uuid"}
            elif fname in {"created_at", "updated_at", "deleted_at"} or fname.endswith("_at"):
                schema = {"type": "string", "format": "date-time", "nullable": fname == "deleted_at"}
            elif fname.startswith("is_") or fname.startswith("has_") or fname.endswith("_enabled"):
                schema = {"type": "boolean"}
            elif fname.endswith("_count") or fname.endswith("_ms") or fname.endswith("_seconds") or fname in {"version", "hierarchy_level"}:
                schema = {"type": "integer"}
            elif fname.endswith("_json") or fname.endswith("_jsonb") or fname == "metadata":
                schema = {"type": "object", "additionalProperties": True}
            else:
                schema = {"type": "string"}
            props[fname] = schema
            if fname == "id":
                required.append("id")
        schema_obj: dict[str, Any] = {
            "type": "object",
            "description": f"Entity {e['id']} {name} (table {e.get('table_name')}).",
            "properties": props or {"id": {"type": "string", "format": "uuid"}},
        }
        if required:
            schema_obj["required"] = required
        out[name] = schema_obj

    # Helper alias schemas for nested types referenced in features.json output_2xx
    helper_aliases = {
        "AIEmployeeNode": {
            "type": "object",
            "description": "AI employee org-chart node.",
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "name": {"type": "string"},
                "persona": {"type": "string"},
                "hierarchy_level": {"type": "integer"},
                "parent_id": {"type": "string", "format": "uuid", "nullable": True},
                "children": {"type": "array", "items": {"$ref": "#/components/schemas/AIEmployeeNode"}},
            },
            "required": ["id", "name"],
        },
        "Member": {"$ref": "#/components/schemas/AccountMember"},
        "AccountMember": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "format": "uuid"},
                "role": {"type": "string"},
                "joined_at": {"type": "string", "format": "date-time"},
            },
        },
        "Invitation": {"$ref": "#/components/schemas/WorkspaceInvitation"},
        "Phase": {"$ref": "#/components/schemas/Phase"},
        "Comment": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "body": {"type": "string"},
                "author_id": {"type": "string", "format": "uuid"},
                "created_at": {"type": "string", "format": "date-time"},
            },
        },
        "Dependency": {"$ref": "#/components/schemas/TaskDependency"},
        "Edge": {
            "type": "object",
            "properties": {
                "from": {"type": "string"},
                "to": {"type": "string"},
                "type": {"type": "string"},
            },
        },
        "Node": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "label": {"type": "string"},
                "kind": {"type": "string"},
            },
        },
        "PRComment": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "author": {"type": "string"},
                "body": {"type": "string"},
                "created_at": {"type": "string", "format": "date-time"},
            },
        },
        "Mock": {"$ref": "#/components/schemas/BFMock"},
        "Component": {"$ref": "#/components/schemas/Component"},
        "Usage": {
            "type": "object",
            "properties": {
                "screen_id": {"type": "string"},
                "count": {"type": "integer"},
            },
        },
        "Requirement": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "section": {"type": "string"},
                "body_md": {"type": "string"},
            },
        },
        "SpecDoc": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "title": {"type": "string"},
                "version": {"type": "integer"},
                "html_path": {"type": "string"},
            },
        },
        "Skill": {"$ref": "#/components/schemas/Skill"},
        "AIEmployee": {"$ref": "#/components/schemas/AIEmployee"},
        "EARSCriterion": {
            "type": "object",
            "properties": {
                "form": {"type": "string", "enum": ["UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED"]},
                "text": {"type": "string"},
            },
            "required": ["form", "text"],
        },
        "ErrorBody": {
            "type": "object",
            "properties": {
                "error": {"type": "string"},
                "code": {"type": "string"},
                "message": {"type": "string"},
                "details": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                "retry_after_sec": {"type": "integer"},
            },
            "required": ["error"],
        },
        # Loose nested types referenced from features.json outputs_2xx — stub objects.
        "AC": {
            "type": "object",
            "description": "Acceptance criterion (EARS-form).",
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "form": {"type": "string", "enum": ["UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED"]},
                "text": {"type": "string"},
                "tier": {"type": "string", "enum": ["structural", "functional", "regression"]},
            },
            "required": ["form", "text"],
        },
        "ApiToken": {
            "type": "object",
            "description": "Personal / workspace-scoped API token (Bearer JWT alternative).",
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "name": {"type": "string"},
                "prefix": {"type": "string"},
                "scopes": {"type": "array", "items": {"type": "string"}},
                "created_at": {"type": "string", "format": "date-time"},
                "expires_at": {"type": "string", "format": "date-time", "nullable": True},
                "last_used_at": {"type": "string", "format": "date-time", "nullable": True},
            },
            "required": ["id", "name"],
        },
        "ComponentUsage": {
            "type": "object",
            "description": "Where a UI component is used across screens.",
            "properties": {
                "screen_id": {"type": "string"},
                "screen_name": {"type": "string"},
                "instance_count": {"type": "integer"},
            },
        },
        "DAGEdge": {
            "type": "object",
            "description": "DAG edge between two tasks (dependency).",
            "properties": {
                "from_task_id": {"type": "string", "format": "uuid"},
                "to_task_id": {"type": "string", "format": "uuid"},
                "type": {"type": "string", "enum": ["blocks", "informs", "soft"]},
            },
            "required": ["from_task_id", "to_task_id"],
        },
        "Delivery": {
            "type": "object",
            "description": "Workspace delivery package metadata.",
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "workspace_id": {"type": "string", "format": "uuid"},
                "status": {"type": "string", "enum": ["draft", "approved", "sent", "accepted"]},
                "approved_at": {"type": "string", "format": "date-time", "nullable": True},
                "sent_at": {"type": "string", "format": "date-time", "nullable": True},
                "artifact_urls": {"type": "array", "items": {"type": "string", "format": "uri"}},
            },
        },
        "DesignToken": {
            "type": "object",
            "description": "Design system token (color / typography / spacing).",
            "properties": {
                "key": {"type": "string"},
                "value": {"type": "string"},
                "category": {"type": "string"},
            },
            "required": ["key", "value"],
        },
        "EmailTemplate": {
            "type": "object",
            "description": "Outbound email template (Resend / Postmark).",
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "subject": {"type": "string"},
                "body_html": {"type": "string"},
                "body_text": {"type": "string"},
                "variables": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["id", "name"],
        },
        "Export": {
            "type": "object",
            "description": "Export job (spec PDF / delivery report).",
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "kind": {"type": "string", "enum": ["spec_pdf", "delivery_report", "task_csv", "audit_csv"]},
                "status": {"type": "string", "enum": ["queued", "running", "succeeded", "failed"]},
                "url": {"type": "string", "format": "uri", "nullable": True},
                "created_at": {"type": "string", "format": "date-time"},
            },
        },
        "KnowledgeHit": {
            "type": "object",
            "description": "Vector / fulltext search hit from knowledge base.",
            "properties": {
                "id": {"type": "string"},
                "title": {"type": "string"},
                "snippet": {"type": "string"},
                "score": {"type": "number"},
                "source": {"type": "string"},
            },
        },
        "KnowledgeItem": {
            "type": "object",
            "description": "Knowledge-base item (Obsidian Vault entry).",
            "properties": {
                "id": {"type": "string"},
                "title": {"type": "string"},
                "path": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "updated_at": {"type": "string", "format": "date-time"},
            },
        },
        "McpToken": {
            "type": "object",
            "description": "MCP server access token (for AI employee tool access).",
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "scopes": {"type": "array", "items": {"type": "string"}},
                "expires_at": {"type": "string", "format": "date-time"},
            },
        },
        "PublicComment": {
            "type": "object",
            "description": "Comment posted via public client-portal token (no auth).",
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "author_name": {"type": "string"},
                "body": {"type": "string"},
                "created_at": {"type": "string", "format": "date-time"},
                "resolved": {"type": "boolean"},
            },
        },
        "PublicWorkspaceView": {
            "type": "object",
            "description": "Redacted workspace view exposed to client portal (token-gated).",
            "properties": {
                "workspace_id": {"type": "string", "format": "uuid"},
                "name": {"type": "string"},
                "status": {"type": "string"},
                "spec_url": {"type": "string", "format": "uri"},
                "delivery": {"$ref": "#/components/schemas/Delivery"},
            },
        },
        "PullRequest": {
            "type": "object",
            "description": "Github pull request mirror.",
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "github_pr_number": {"type": "integer"},
                "title": {"type": "string"},
                "state": {"type": "string", "enum": ["open", "merged", "closed"]},
                "author": {"type": "string"},
                "created_at": {"type": "string", "format": "date-time"},
            },
        },
        "Report": {
            "type": "object",
            "description": "HTML report metadata (7 kinds).",
            "properties": {
                "id": {"type": "string"},
                "kind": {"type": "string"},
                "title": {"type": "string"},
                "html_url": {"type": "string", "format": "uri"},
                "generated_at": {"type": "string", "format": "date-time"},
            },
        },
        "RequirementItem": {
            "type": "object",
            "description": "Single requirement entry inside spec.",
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "section": {"type": "string"},
                "label": {"type": "string", "enum": ["Must", "Should", "Could", "Wont"]},
                "body_md": {"type": "string"},
            },
        },
        "ReviewTurn": {
            "type": "object",
            "description": "One turn of the leader-AI Plan/Gen/Eval review loop.",
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "phase": {"type": "string", "enum": ["plan", "gen", "eval"]},
                "agent": {"type": "string"},
                "output": {"type": "string"},
                "score": {"type": "number"},
                "created_at": {"type": "string", "format": "date-time"},
            },
        },
        "ScreenFlowEdge": {
            "type": "object",
            "description": "Edge of the screen-flow graph (S → S transition).",
            "properties": {
                "from_screen_id": {"type": "string"},
                "to_screen_id": {"type": "string"},
                "trigger": {"type": "string"},
            },
        },
        "ScreenFlowNode": {
            "type": "object",
            "description": "Node of the screen-flow graph (one screen).",
            "properties": {
                "screen_id": {"type": "string"},
                "name": {"type": "string"},
                "kind": {"type": "string"},
            },
        },
        "SearchHit": {
            "type": "object",
            "description": "Global search hit (Cmd+K).",
            "properties": {
                "id": {"type": "string"},
                "kind": {"type": "string", "enum": ["workspace", "task", "spec", "mock", "ai_employee", "skill", "audit_log"]},
                "title": {"type": "string"},
                "snippet": {"type": "string"},
                "url": {"type": "string", "format": "uri"},
                "score": {"type": "number"},
            },
        },
        "Spec": {
            "type": "object",
            "description": "Project specification document.",
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "workspace_id": {"type": "string", "format": "uuid"},
                "title": {"type": "string"},
                "version": {"type": "integer"},
                "html_path": {"type": "string"},
                "status": {"type": "string"},
            },
        },
        "TaskGroup": {
            "type": "object",
            "description": "Task group (Group A/B-1/B-2/C/D per task-decomposition).",
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "count": {"type": "integer"},
            },
        },
        "TaskNode": {
            "type": "object",
            "description": "Task DAG node.",
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "title": {"type": "string"},
                "status": {"type": "string"},
                "wave": {"type": "integer"},
            },
        },
        "UserSettings": {
            "type": "object",
            "description": "User personal settings (preferences / locale).",
            "properties": {
                "user_id": {"type": "string", "format": "uuid"},
                "locale": {"type": "string"},
                "theme": {"type": "string"},
                "notification_prefs": {"type": "object", "additionalProperties": True},
            },
        },
        "WorkspaceSummary": {
            "type": "object",
            "description": "Workspace summary for dashboard.",
            "properties": {
                "id": {"type": "string", "format": "uuid"},
                "name": {"type": "string"},
                "task_count": {"type": "integer"},
                "active_session_count": {"type": "integer"},
                "delivery_status": {"type": "string"},
            },
        },
    }
    for k, v in helper_aliases.items():
        out.setdefault(k, v)
    return out


# -----------------------------------------------------------------------------
# Main builder
# -----------------------------------------------------------------------------

def main() -> int:
    with (FB_DIR / "features.json").open() as f:
        features = json.load(f)
    with (FB_DIR / "entities.json").open() as f:
        entities_doc = json.load(f)
    with (FB_DIR / "roles.json").open() as f:
        roles_doc = json.load(f)

    entities = entities_doc["entities"]

    # ------------------------------------------------------------------
    # Build OpenAPI document
    # ------------------------------------------------------------------
    paths: dict[str, dict[str, Any]] = OrderedDict()
    operation_ids_seen: set[str] = set()
    ears_seeds_out: list[dict[str, Any]] = []
    lint_mapping_endpoints: list[dict[str, Any]] = []
    endpoints_total = 0

    # Drift lookup: spec_endpoint -> drift_note
    drift_lookup: dict[str, dict[str, Any]] = {}
    for f in features["items"]:
        for d in f.get("legacy_drift_notes") or []:
            drift_lookup[d.get("spec_endpoint", "")] = d

    for feat in features["items"]:
        fid = feat["id"]
        related_screens = [s.split(" ", 1)[0] for s in feat.get("related_screens", [])]
        # ears_ac_seed of the *feature*; reused across endpoints since features.json
        # attaches them at feature level, not per-endpoint.
        feature_seeds = feat.get("ears_ac_seed", []) or []

        for ep in feat.get("api_endpoints", []) or []:
            endpoints_total += 1
            method = ep["method"]
            path = ep["path"]
            spec_key = f"{method} {path}"
            drift = drift_lookup.get(spec_key)

            # Translate WebSocket to HTTP-style spec (OpenAPI 3.1 supports custom x-)
            if method == "WS":
                # Represent as GET with x-bf-protocol: websocket
                http_method = "get"
                is_ws = True
            else:
                http_method = method.lower()
                is_ws = False

            auth_role = ep.get("auth", "public")
            auth_info = role_to_auth(auth_role)
            related_entities = ep.get("related_entities", [])
            ac_policies = access_policies_for(auth_role, related_entities)

            # operationId uniqueness
            opid = operation_id(method, path)
            base_opid = opid
            ix = 2
            while opid in operation_ids_seen:
                opid = f"{base_opid}_{ix}"
                ix += 1
            operation_ids_seen.add(opid)

            # path params (forced even if not in inputs)
            params: list[dict[str, Any]] = build_path_params(path, ep.get("inputs"))
            # query params for GET / DELETE
            params.extend(build_query_params(ep, path))

            # request body
            request_body = None
            if method in {"POST", "PUT", "PATCH"} and not is_ws:
                body_schema = build_request_body_schema(ep, path)
                if body_schema is not None:
                    request_body = {
                        "required": True,
                        "content": {
                            "application/json": {"schema": body_schema}
                        },
                    }

            # responses
            outputs_2xx_schema = build_response_2xx_schema(ep)
            success_status = "201" if method == "POST" else "200"
            success_desc = {
                "200": "OK",
                "201": "Created",
            }[success_status]
            # Special: WebSocket upgrade
            responses: dict[str, Any] = {}
            if is_ws:
                responses["101"] = {
                    "description": "Switching Protocols (WebSocket upgrade)",
                }
            else:
                responses[success_status] = {
                    "description": success_desc,
                    "content": {
                        "application/json": {"schema": outputs_2xx_schema}
                    },
                }

            outputs_4xx = ep.get("outputs_4xx") or {}
            ep_error_seeds: list[dict[str, Any]] = []
            for status_str, trigger in outputs_4xx.items():
                try:
                    status = int(status_str)
                except (TypeError, ValueError):
                    continue
                responses[str(status)] = {"$ref": status_to_error_ref(status)}
                ep_error_seeds.append({
                    "status": status,
                    "code": status_to_code(status),
                    "trigger": trigger,
                    "ears_form": status_to_ears_form(status, str(trigger)),
                })

            # security
            security: list[dict[str, list[str]]]
            if auth_info["required"]:
                security = [{"bearerAuth": []}]
            else:
                security = []

            # operation object
            op: dict[str, Any] = {
                "operationId": opid,
                "summary": f"{feat['name']} — {method} {path}",
                "description": (
                    f"Feature: {fid} ({feat['name']}). "
                    f"Auth role: {auth_role}. "
                    f"Related entities: {', '.join(related_entities) or '-'}. "
                    f"Related screens: {', '.join(related_screens) or '-'}."
                ),
                "tags": [feat.get("category", "misc")],
                "security": security,
                "responses": responses,
                "x-bf-feature-id": fid,
                "x-bf-screen-ids": related_screens,
                "x-bf-auth-role": auth_role,
                "x-bf-related-entities": related_entities,
                "x-bf-access-control-policies": ac_policies,
                "x-bf-implementation-path": implementation_path_for(method, path),
                "x-bf-error-seeds": ep_error_seeds,
            }
            if ep.get("rate_limit"):
                op["x-bf-rate-limit"] = ep["rate_limit"]
            if is_ws:
                op["x-bf-protocol"] = "websocket"
            if drift:
                op["x-bf-drift"] = {
                    "severity": drift.get("diff_severity"),
                    "task_id": drift.get("task_id"),
                    "recommendation": drift.get("recommendation"),
                    "impl_router_state": drift.get("impl_router"),
                }
            if params:
                op["parameters"] = params
            if request_body is not None:
                op["requestBody"] = request_body

            paths.setdefault(path, OrderedDict())[http_method] = op

            # ears-ac-seed.json entry (per endpoint) — combine feature-level seeds and per-error UNWANTED forms
            seed_for_ep: list[str] = list(feature_seeds)  #逐語移植 (verbatim, not paraphrased)
            for es in ep_error_seeds:
                ears_str = es["ears_form"]
                if ears_str not in seed_for_ep:
                    seed_for_ep.append(ears_str)
            ears_seeds_out.append({
                "endpoint": spec_key,
                "feature_id": fid,
                "feature_name": feat.get("name"),
                "screen_ids": related_screens,
                "auth_role": auth_role,
                "rate_limit": ep.get("rate_limit"),
                "ears_ac_seed": seed_for_ep,
                "outputs_4xx_seeds": ep_error_seeds,
            })

            # lint-mapping.json entry
            lint_mapping_endpoints.append({
                "method": method,
                "path": path,
                "feature_id": fid,
                "auth_role": auth_role,
                "screen_ids_referencing": related_screens,
                "implementation_path": implementation_path_for(method, path),
                "drift_severity": (drift or {}).get("diff_severity"),
                "drift_task_id": (drift or {}).get("task_id"),
                "access_control_policies": ac_policies,
            })

    # ------------------------------------------------------------------
    # Components
    # ------------------------------------------------------------------
    components: dict[str, Any] = {
        "securitySchemes": {
            "bearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "Supabase Auth (GoTrue) issued JWT. Send as `Authorization: Bearer <token>`.",
            }
        },
        "responses": {
            "Unauthorized": {
                "description": "401 Unauthorized — missing or invalid credentials.",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/ErrorBody"},
                        "example": {"error": "unauthorized", "code": "UNAUTHORIZED", "message": "missing or invalid token"},
                    }
                },
            },
            "Forbidden": {
                "description": "403 Forbidden — authenticated but RLS / RBAC denied.",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/ErrorBody"},
                        "example": {"error": "forbidden", "code": "FORBIDDEN", "message": "insufficient role"},
                    }
                },
            },
            "NotFound": {
                "description": "404 Not Found — resource does not exist or is hidden by RLS.",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/ErrorBody"},
                        "example": {"error": "not_found", "code": "NOT_FOUND"},
                    }
                },
            },
            "Conflict": {
                "description": "409 Conflict — uniqueness / state conflict.",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/ErrorBody"},
                        "example": {"error": "conflict", "code": "CONFLICT", "message": "unique constraint violated"},
                    }
                },
            },
            "ValidationError": {
                "description": "422 Validation Error — request body / params failed schema.",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/ErrorBody"},
                        "example": {"error": "validation_failed", "code": "VALIDATION_ERROR", "details": [{"field": "email", "msg": "invalid format"}]},
                    }
                },
            },
            "RateLimited": {
                "description": "429 Too Many Requests — rate limit exceeded.",
                "headers": {
                    "Retry-After": {"schema": {"type": "integer"}},
                },
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/ErrorBody"},
                        "example": {"error": "rate_limited", "code": "RATE_LIMITED", "retry_after_sec": 900},
                    }
                },
            },
            "InternalServerError": {
                "description": "500 Internal Server Error — opaque server failure.",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/ErrorBody"},
                        "example": {"error": "internal_server_error", "code": "INTERNAL_SERVER_ERROR"},
                    }
                },
            },
        },
        "schemas": build_entity_schemas(entities),
    }

    openapi: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {
            "title": "Build-Factory API (v3)",
            "version": "3.0.0",
            "description": (
                "Build-Factory v3 API contract — 140 endpoints derived from "
                "`docs/functional-breakdown/2026-05-16_v3/features.json`. "
                "All paths follow the BF naming convention `/api/<resource>/...`. "
                "Authentication is Supabase Auth (GoTrue) Bearer JWT. "
                "Row-level access control is Supabase Postgres RLS — see x-bf-access-control-policies on each operation. "
                "This document is the **trust source** for `openapi-typescript` (frontend `frontend/src/api/types.ts`) "
                "and `datamodel-code-generator` (backend `backend/schemas.py`) regeneration, plus `Schemathesis` contract test."
            ),
            "contact": {
                "name": "ENGINE BASE — Build-Factory",
                "email": "masato@engine-base.com",
            },
            "x-bf-version": VERSION,
            "x-bf-generated-at": CREATED_AT,
            "x-bf-endpoint-count": endpoints_total,
        },
        "servers": [
            {"url": "https://api.build-factory.engine-base.com", "description": "Production"},
            {"url": "https://api.staging.build-factory.engine-base.com", "description": "Staging"},
            {"url": "http://localhost:8000", "description": "Local dev"},
        ],
        "tags": sorted({feat.get("category", "misc") for feat in features["items"]}),
        "security": [{"bearerAuth": []}],
        "paths": paths,
        "components": components,
    }

    # rewrite tags to objects
    openapi["tags"] = [{"name": t, "description": f"{t} endpoints"} for t in openapi["tags"]]

    # ------------------------------------------------------------------
    # Write outputs
    # ------------------------------------------------------------------
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # YAML write — implement minimal YAML emitter to avoid PyYAML dep ordering issues
    yaml_text = json_to_yaml(openapi)
    (OUT_DIR / "openapi.yaml").write_text(yaml_text)
    print(f"wrote openapi.yaml ({len(yaml_text)} bytes)")

    # ears-ac-seed.json
    ears_doc = {
        "version": VERSION,
        "skill": "api-design",
        "project": "Build-Factory",
        "created_at": CREATED_AT,
        "endpoints_count": len(ears_seeds_out),
        "feature_count": len(features["items"]),
        "note": (
            "feature-level ears_ac_seed[] from features.json are 逐語 (verbatim) copied "
            "to each endpoint of that feature. outputs_4xx triggers are wrapped into "
            "UNWANTED / EVENT-DRIVEN EARS forms. Downstream task-decomposition Tier 2 "
            "(functional AC) MUST verbatim copy these strings — no paraphrasing."
        ),
        "ac_seeds": ears_seeds_out,
    }
    (OUT_DIR / "ears-ac-seed.json").write_text(json.dumps(ears_doc, indent=2, ensure_ascii=False))
    print(f"wrote ears-ac-seed.json ({len(ears_seeds_out)} entries)")

    # lint-mapping.json
    lint_doc = {
        "version": VERSION,
        "skill": "api-design",
        "project": "Build-Factory",
        "created_at": CREATED_AT,
        "lint_consumer": "scripts/lint-screens-api.py (lint #18 screens-API in lint-mock.sh)",
        "endpoints_count": len(lint_mapping_endpoints),
        "endpoints": lint_mapping_endpoints,
    }
    (OUT_DIR / "lint-mapping.json").write_text(json.dumps(lint_doc, indent=2, ensure_ascii=False))
    print(f"wrote lint-mapping.json ({len(lint_mapping_endpoints)} entries)")

    # decision-log.json
    decision_doc = {
        "version": VERSION,
        "skill": "api-design",
        "project": "Build-Factory",
        "created_at": CREATED_AT,
        "decisions": [
            {
                "id": "AD-001",
                "topic": "API style",
                "decision": "RESTful HTTP/JSON + 2 WebSocket streams (hearing / session log).",
                "rationale": "v3 features.json already declares REST verbs and resource paths; consistent with existing 453 backend routers. WebSocket only used for long-running streams (LLM hearing, session log)."
            },
            {
                "id": "AD-002",
                "topic": "URL prefix / versioning",
                "decision": "Keep `/api/<resource>/...` (no `/api/v1/` prefix).",
                "rationale": (
                    "features.json declares 138/140 endpoints under `/api/...` and 2 under `/ws/...`. "
                    "Backend has ~453 existing endpoints under `/api/...` already in production-shape; "
                    "introducing `/api/v1/` would force a wholesale rewrite. BF profile section 'URL pattern' "
                    "specifies `/api/<resource>/...` (kebab-case). Future v2 will introduce `/api/v2/` when "
                    "breaking changes accumulate."
                )
            },
            {
                "id": "AD-003",
                "topic": "Authentication",
                "decision": "Supabase Auth (GoTrue) Bearer JWT. ADR-013 (AUTH strategy).",
                "rationale": "Selected stack mandates Supabase Auth + JWT + 2FA TOTP + OAuth (Anthropic/GitHub/Slack/Google). Bearer is the simplest standard scheme — declared via OpenAPI `securitySchemes.bearerAuth` (http/bearer/JWT)."
            },
            {
                "id": "AD-004",
                "topic": "Access control encoding",
                "decision": "x-bf-access-control-policies per operation, format `<table>:<policy_name>` (BF profile rule).",
                "rationale": "Supabase Postgres RLS is the authoritative authorisation layer. Each operation declares which `(table, policy)` pair gates the row visibility. `scripts/verify-rls-coverage.py` consumes this to ensure every endpoint touches at least one declared policy."
            },
            {
                "id": "AD-005",
                "topic": "Error model",
                "decision": "Standard 4xx components reused via $ref: Unauthorized / Forbidden / NotFound / Conflict / ValidationError / RateLimited / InternalServerError. Body schema = ErrorBody (error/code/message/details/retry_after_sec).",
                "rationale": "DRY for 140 endpoints. Triggers / EARS-UNWANTED forms remain per-endpoint via x-bf-error-seeds so the same response component carries different ears_form text downstream."
            },
            {
                "id": "AD-006",
                "topic": "ears_ac_seed — verbatim vs synthesised",
                "decision": "features.json `ears_ac_seed[]` is the master text; copied verbatim into ears-ac-seed.json. outputs_4xx triggers are wrapped into UNWANTED EARS forms (status 429 → EVENT-DRIVEN per v3-core convention).",
                "rationale": "Task-decomposition Tier 2 functional AC MUST quote api-design verbatim. Synthesising new wording introduces drift and defeats the EARS validator."
            },
            {
                "id": "AD-007",
                "topic": "Rate limiting",
                "decision": "Surface as `x-bf-rate-limit` extension on each operation (format `<count>/<window>/<scope>` from features.json). Enforced by FastAPI middleware (slowapi) per ADR-013.",
                "rationale": "OpenAPI 3.1 has no canonical rate-limit field. `x-bf-rate-limit` is parsed by `scripts/lint-screens-api.py` and Schemathesis 4xx fuzz to ensure 429 is reachable."
            },
            {
                "id": "AD-008",
                "topic": "WebSocket endpoints",
                "decision": "Represent /ws/* as HTTP GET with x-bf-protocol=websocket and response 101 Switching Protocols.",
                "rationale": "OpenAPI 3.1 has no first-class WebSocket support yet (AsyncAPI is separate). The GET + extension shim is the de-facto convention used by openapi-typescript / Schemathesis."
            },
            {
                "id": "AD-009",
                "topic": "Drift carry-over",
                "decision": "Each operation that exists in api-drift-summary.md gets x-bf-drift{severity,task_id,recommendation,impl_router_state}. 104/140 endpoints currently lack backend impl (94 critical + 7 high + 1 medium + 2 low).",
                "rationale": "task-decomposition Group B-1 (vertical slice) will consume x-bf-drift.task_id to materialise T-V3-DRIFT-F-XXX-NN tasks. screens-API lint (#18) blocks merges when an endpoint is referenced from mock but has no implementation_path."
            },
            {
                "id": "AD-010",
                "topic": "Schema generation chain",
                "decision": "openapi.yaml → openapi-typescript → frontend/src/api/types.ts. openapi.yaml → datamodel-code-generator → backend/schemas.py. Schemathesis runs against openapi.yaml in Foundation gate.",
                "rationale": "Per BF profile §型自動生成チェーン. types.ts and schemas.py are committed but generated (edit禁止). Foundation phase CI gate #1 (mock lint #18) + gate #7 (tsc --strict) detect drift."
            },
            {
                "id": "AD-011",
                "topic": "Entity schema fidelity",
                "decision": "Entity schemas in components.schemas are minimal envelopes derived from entities.json field names + name-based type heuristics (id/_id → uuid; _at → date-time; is_/has_ → boolean; etc.).",
                "rationale": "entities.json fields are stored as raw_v1_descriptor strings without strict types. We do not fabricate detailed schemas — backend schemas.py (generated by datamodel-codegen from Pydantic models, which read SQLAlchemy declarative types) is the precise source. types.ts consumers should treat entity types as loose dicts plus `id`."
            },
            {
                "id": "AD-012",
                "topic": "Endpoint count discipline",
                "decision": "Exactly 140 endpoints exported (138 HTTP + 2 WebSocket). No legacy ~340 backend endpoints included.",
                "rationale": "Per session brief: 'legacy は別 audit'. Phase 1.5 will run a separate audit to either lift surviving endpoints into v3 spec or mark them deprecated."
            },
        ],
        "metrics": {
            "endpoint_count": endpoints_total,
            "feature_count": len(features["items"]),
            "entity_count": len(entities),
            "role_count": len(roles_doc["roles"]),
            "drift_critical_endpoints": sum(1 for d in drift_lookup.values() if d.get("diff_severity") == "critical"),
            "drift_high_endpoints": sum(1 for d in drift_lookup.values() if d.get("diff_severity") == "high"),
        },
    }
    (OUT_DIR / "decision-log.json").write_text(json.dumps(decision_doc, indent=2, ensure_ascii=False))
    print(f"wrote decision-log.json")

    print(f"\nTOTAL endpoints emitted: {endpoints_total}")
    print(f"unique operationIds: {len(operation_ids_seen)}")
    return 0


# -----------------------------------------------------------------------------
# Minimal JSON -> YAML emitter
# -----------------------------------------------------------------------------

def _yaml_str(s: str) -> str:
    """Quote a string for YAML."""
    if s == "":
        return '""'
    # If it contains special yaml chars or starts with reserved tokens, double-quote
    needs_quote = False
    if s != s.strip():
        needs_quote = True
    elif s.lower() in {"true", "false", "yes", "no", "null", "~", "on", "off"}:
        needs_quote = True
    elif re.match(r"^[\-\?:,\[\]\{\}#&*!|>'\"%@`]", s):
        needs_quote = True
    elif ":" in s or "#" in s or "\n" in s or "\t" in s:
        needs_quote = True
    elif re.match(r"^-?\d+(\.\d+)?$", s):
        needs_quote = True

    if needs_quote:
        # Use double-quoted, escape backslash and quote and control chars
        escaped = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")
        return f'"{escaped}"'
    return s


def json_to_yaml(obj: Any, indent: int = 0) -> str:
    """Tiny YAML emitter sufficient for our OpenAPI dict (strings/numbers/bools/lists/dicts)."""
    sp = "  " * indent
    out_lines: list[str] = []

    if isinstance(obj, dict):
        if not obj:
            return "{}"
        lines: list[str] = []
        for k, v in obj.items():
            key = str(k)
            # quote key if it has special chars
            if not re.match(r"^[A-Za-z_][\w\-./]*$", key):
                key = _yaml_str(key)
            if isinstance(v, dict):
                if not v:
                    lines.append(f"{sp}{key}: {{}}")
                else:
                    lines.append(f"{sp}{key}:")
                    lines.append(json_to_yaml(v, indent + 1))
            elif isinstance(v, list):
                if not v:
                    lines.append(f"{sp}{key}: []")
                else:
                    lines.append(f"{sp}{key}:")
                    for item in v:
                        if isinstance(item, (dict, list)):
                            inner = json_to_yaml(item, indent + 2).rstrip("\n")
                            # Convert first line to "- " prefix
                            inner_lines = inner.split("\n")
                            first = inner_lines[0]
                            # find first non-space
                            stripped_first = first.lstrip()
                            lead = first[: len(first) - len(stripped_first)]
                            # Replace last 2 spaces of leading indent with "- "
                            if len(lead) >= 2:
                                new_first = lead[:-2] + "- " + stripped_first
                            else:
                                new_first = "- " + stripped_first
                            lines.append(new_first)
                            for rest in inner_lines[1:]:
                                lines.append(rest)
                        else:
                            lines.append(f"{'  ' * (indent + 1)}- {_yaml_scalar(item)}")
            else:
                lines.append(f"{sp}{key}: {_yaml_scalar(v)}")
        return "\n".join(lines) + "\n"

    if isinstance(obj, list):
        if not obj:
            return "[]"
        lines = []
        for item in obj:
            if isinstance(item, (dict, list)):
                inner = json_to_yaml(item, indent + 1).rstrip("\n")
                inner_lines = inner.split("\n")
                first = inner_lines[0]
                stripped_first = first.lstrip()
                lead = first[: len(first) - len(stripped_first)]
                if len(lead) >= 2:
                    new_first = lead[:-2] + "- " + stripped_first
                else:
                    new_first = "- " + stripped_first
                lines.append(new_first)
                for rest in inner_lines[1:]:
                    lines.append(rest)
            else:
                lines.append(f"{sp}- {_yaml_scalar(item)}")
        return "\n".join(lines) + "\n"

    return _yaml_scalar(obj)


def _yaml_scalar(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        return _yaml_str(v)
    return _yaml_str(str(v))


if __name__ == "__main__":
    sys.exit(main())
