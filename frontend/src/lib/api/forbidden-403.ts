/**
 * T-V3-C-55 / S-046 — Typed client for the 403 Forbidden screen.
 *
 * Backend contracts:
 *   GET  /api/me                                — current actor (role, workspace_id)
 *   POST /api/workspaces/{workspace_id}/role-requests
 *                                                — issue a "request access" event
 *
 * Backend router (existing):
 *   - backend/routers/me.py::get_me        (returns {role, workspace_id, ...})
 *
 * Error contract  : `{detail: {code, message}}` (FastAPI project-wide).
 *                   Thrown as ForbiddenApiError so the UI can surface a
 *                   non-technical toast referencing the failing endpoint
 *                   without leaking server stack traces.
 *
 * Auth: any authenticated session. Unauthenticated (401) callers are
 * redirected to /login (S-001) by the page-level guard — see
 * use-forbidden-403.ts (AC-F1). This screen itself never renders any
 * workspace-scoped data; it only renders the user's own role string so the
 * 403 explanation can name "what you have" vs "what is required" (per the
 * S-046 mock: 現在のロール / 必要なロール).
 *
 * EARS AC mapping (S-046 / T-V3-C-55):
 *   functional.AC-F1: UNWANTED unauthenticated visitor -> 401 surfaces here
 *     so the page redirects to /login (S-001) without leaking workspace data.
 *   functional.AC-F2: STATE-DRIVEN data fetching surface — the typed client
 *     is the boundary between fetch state and the page's skeleton/loaded swap.
 */

export const ME_ENDPOINT = "/api/me";
export const ROLE_REQUEST_ENDPOINT_PREFIX = "/api/workspaces"; // + /{id}/role-requests

// ---------------------------------------------------------------------------
// Wire types — match openapi.yaml verbatim.
// ---------------------------------------------------------------------------

/** Role keys defined by docs/functional-breakdown/2026-05-16_v3 (6 roles). */
export type RoleKey =
  | "owner"
  | "workspace_admin"
  | "developer"
  | "pm"
  | "monitor"
  | "guest"
  | string;

export interface MeResponse {
  /** Current authenticated role key. */
  role: RoleKey;
  /** Active workspace id (number). May be null on a global-scoped session. */
  workspace_id?: number | null;
  /** Display name (optional, surfaced for the role card). */
  display_name?: string | null;
}

export interface RoleRequestPayload {
  /** Optional message the requester can supply to the workspace admin. */
  message?: string | null;
  /** The role the requester wants to be promoted to. */
  requested_role: RoleKey;
}

export interface RoleRequestResponse {
  /** ISO-8601 timestamp the request was recorded at. */
  requested_at: string;
}

// ---------------------------------------------------------------------------
// Error envelope — mirrors the FastAPI project-wide {detail:{code,message}}.
// ---------------------------------------------------------------------------

/** Thrown for any non-2xx response from S-046 client calls. */
export class ForbiddenApiError extends Error {
  code: string;
  status: number;
  endpoint: string;

  constructor(code: string, message: string, status: number, endpoint: string) {
    super(message);
    this.name = "ForbiddenApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }
}

interface ErrorEnvelope {
  detail?: {
    code?: string;
    message?: string;
  };
}

async function parseError(
  res: Response,
  endpoint: string,
): Promise<ForbiddenApiError> {
  let code = "UNKNOWN";
  let message = `${endpoint} failed with HTTP ${res.status}`;
  try {
    const body = (await res.json()) as ErrorEnvelope;
    if (body?.detail?.code) code = body.detail.code;
    if (body?.detail?.message) message = body.detail.message;
  } catch {
    // body was not JSON — keep the default message.
  }
  return new ForbiddenApiError(code, message, res.status, endpoint);
}

// ---------------------------------------------------------------------------
// GET /api/me — surface the current actor (role + workspace_id).
// ---------------------------------------------------------------------------
export async function fetchMe(
  fetchImpl: typeof fetch = globalThis.fetch.bind(globalThis),
): Promise<MeResponse> {
  const res = await fetchImpl(ME_ENDPOINT, {
    method: "GET",
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw await parseError(res, ME_ENDPOINT);
  }
  return (await res.json()) as MeResponse;
}

// ---------------------------------------------------------------------------
// POST /api/workspaces/{workspace_id}/role-requests — "request access" CTA.
// ---------------------------------------------------------------------------
export async function postRoleRequest(
  workspaceId: number,
  payload: RoleRequestPayload,
  fetchImpl: typeof fetch = globalThis.fetch.bind(globalThis),
): Promise<RoleRequestResponse> {
  const endpoint = `${ROLE_REQUEST_ENDPOINT_PREFIX}/${workspaceId}/role-requests`;
  const res = await fetchImpl(endpoint, {
    method: "POST",
    credentials: "include",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw await parseError(res, endpoint);
  }
  return (await res.json()) as RoleRequestResponse;
}
