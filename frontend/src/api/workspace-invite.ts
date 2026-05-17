/**
 * T-V3-C-64 / F-004 / S-015: Typed client for the workspace member invitation
 * endpoints backing the メンバー招待 (workspace_invite) screen.
 *
 * Backend contract (T-V3-B-04 / T-V3-B-05 / T-V3-B-06):
 *   POST   /api/workspaces/{id}/invitations            — create invitation (T-004-03)
 *   GET    /api/workspaces/{id}/invitations            — list pending invitations (F-004 spec; impl drift T-V3-DRIFT-F-004-07)
 *   DELETE /api/workspaces/{id}/invitations/{token}    — revoke invitation (T-V3-B-06)
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml
 *          #/api/workspaces/{id}/invitations              (POST + GET)
 *          #/api/workspaces/{id}/invitations/{token}      (DELETE)
 *
 * Auth model: bearerAuth (workspace_admin per features.json#F-004).
 *
 * 3-tier AC mapping (docs/audit/2026-05-16_v3/T-V3-C-64.md):
 *   functional.AC-F1 → createWorkspaceInvitation(workspaceId, body) POSTs the
 *                      payload; 2xx renders, 4xx surfaces as
 *                      WorkspaceInviteApiError so the page can show an inline
 *                      error toast + empty state.
 *   functional.AC-F2 → 401 surfaces with status === 401 so the page can
 *                      redirect unauthenticated callers to /login (S-001) and
 *                      withhold workspace-scoped data.
 *   functional.AC-F3 → updateAccountPlan(accountId, body) PUTs the plan upgrade
 *                      payload for the owner; mirrors the F-004 PUT /accounts
 *                      contract referenced by the audit MD.
 *
 * The client follows the project-wide FastAPI {detail: {code, message}}
 * envelope and never forwards a raw stack trace to the UI.
 */

// --------------------------------------------------------------------------
// Endpoint helpers — exposed so callers / tests can assert canonical paths.
// --------------------------------------------------------------------------

export const WORKSPACE_INVITATIONS_ENDPOINT_PATTERN =
  "/api/workspaces/{id}/invitations";
export const WORKSPACE_INVITATION_REVOKE_ENDPOINT_PATTERN =
  "/api/workspaces/{id}/invitations/{token}";
export const ACCOUNT_PLAN_ENDPOINT_PATTERN = "/api/accounts/{id}";

/** Build the canonical workspace invitations endpoint path. */
export function workspaceInvitationsEndpoint(
  workspaceId: number | string,
): string {
  return `/api/workspaces/${encodeURIComponent(
    String(workspaceId),
  )}/invitations`;
}

/** Build the canonical revoke endpoint path. */
export function workspaceInvitationRevokeEndpoint(
  workspaceId: number | string,
  token: string,
): string {
  return `/api/workspaces/${encodeURIComponent(
    String(workspaceId),
  )}/invitations/${encodeURIComponent(token)}`;
}

/** Build the canonical account update endpoint path. */
export function accountPlanEndpoint(accountId: number | string): string {
  return `/api/accounts/${encodeURIComponent(String(accountId))}`;
}

// --------------------------------------------------------------------------
// Wire types — mirror backend/routers/workspaces.py + openapi.yaml schemas.
// --------------------------------------------------------------------------

/** Roles selectable from the S-015 form (matches mock <select>). */
export type WorkspaceInviteRole =
  | "owner"
  | "ws_admin"
  | "admin"
  | "contributor"
  | "viewer"
  | "monitor"
  | "client"
  | "reviewer"
  | "guest";

export type WorkspaceInviteStatus =
  | "pending"
  | "accepted"
  | "expired"
  | "revoked";

/** POST /api/workspaces/{id}/invitations request body. */
export interface CreateWorkspaceInvitationRequest {
  email: string;
  role?: WorkspaceInviteRole | string;
  expires_in_days?: number;
  invited_by?: string;
  message?: string | null;
}

/** POST /api/workspaces/{id}/invitations response body. */
export interface CreateWorkspaceInvitationResponse {
  token?: string;
  invitation_token?: string;
  invitation_url?: string;
  expires_at?: string;
  email?: string;
  role?: string;
}

/** Single invitation record returned by GET /workspaces/{id}/invitations. */
export interface WorkspaceInvitation {
  token: string;
  email: string;
  role?: WorkspaceInviteRole | string | null;
  status?: WorkspaceInviteStatus | string | null;
  invited_by?: string | null;
  invited_at?: string | null;
  created_at?: string | null;
  expires_at?: string | null;
  workspace_id?: number | string | null;
}

/** GET /api/workspaces/{id}/invitations response shape. */
export interface ListWorkspaceInvitationsResponse {
  invitations: WorkspaceInvitation[];
}

/** DELETE /api/workspaces/{id}/invitations/{token} response shape. */
export interface RevokeWorkspaceInvitationResponse {
  revoked_at: string;
}

/** PUT /api/accounts/{id} request body for AC-F3 plan upgrade. */
export interface UpdateAccountPlanRequest {
  plan: string;
  name?: string;
  account_type?: string;
}

/** PUT /api/accounts/{id} response body for AC-F3 plan upgrade. */
export interface UpdateAccountPlanResponse {
  id?: number | string;
  plan?: string;
  updated_at?: string;
}

// --------------------------------------------------------------------------
// Error envelope — matches the project-wide FastAPI contract.
// --------------------------------------------------------------------------

interface BackendErrorEnvelope {
  detail?:
    | string
    | {
        code?: string;
        message?: string;
        errors?: unknown;
      };
}

/** Thrown for any non-2xx response from a workspace-invite endpoint. */
export class WorkspaceInviteApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly endpoint: string;

  constructor(code: string, message: string, status: number, endpoint: string) {
    super(message);
    this.name = "WorkspaceInviteApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /** End-user-friendly message tagged with the failing endpoint. */
  toUserMessage(): string {
    const friendly =
      WORKSPACE_INVITE_USER_MESSAGES[this.status] ??
      WORKSPACE_INVITE_USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

const WORKSPACE_INVITE_USER_MESSAGES: Record<number | "default", string> = {
  400: "リクエストに問題があります",
  401: "ログインが必要です",
  403: "この操作を実行する権限がありません",
  404: "ワークスペースが見つかりませんでした",
  409: "招待は既に処理されています",
  422: "入力内容を確認してください",
  429: "招待リクエストが多すぎます。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "招待処理に失敗しました",
};

// --------------------------------------------------------------------------
// Internal helpers
// --------------------------------------------------------------------------

function resolveApiBase(apiBase?: string): string {
  if (apiBase) return apiBase;
  const fromEnv =
    (typeof process !== "undefined" &&
      (process.env?.NEXT_PUBLIC_API_URL ??
        process.env?.NEXT_PUBLIC_API_BASE)) ||
    undefined;
  if (fromEnv) return fromEnv;
  return "http://localhost:8001";
}

async function parseErrorEnvelope(
  response: Response,
  endpoint: string,
): Promise<WorkspaceInviteApiError> {
  let code = "UNKNOWN_ERROR";
  let message = response.statusText || "request failed";
  try {
    const envelope = (await response.json()) as BackendErrorEnvelope;
    if (envelope && typeof envelope.detail === "object" && envelope.detail) {
      if (typeof envelope.detail.code === "string") {
        code = envelope.detail.code;
      }
      if (typeof envelope.detail.message === "string") {
        message = envelope.detail.message;
      }
    } else if (typeof envelope?.detail === "string") {
      message = envelope.detail;
    }
  } catch {
    // intentionally ignore — never forward raw HTML / stack traces.
  }
  return new WorkspaceInviteApiError(code, message, response.status, endpoint);
}

export interface WorkspaceInviteRequestOptions {
  apiBase?: string;
  signal?: AbortSignal;
  authToken?: string | null;
  fetchImpl?: typeof fetch;
}

function buildHeaders(
  opts: WorkspaceInviteRequestOptions,
  hasJsonBody: boolean,
): Record<string, string> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (hasJsonBody) headers["Content-Type"] = "application/json";
  if (opts.authToken) headers.Authorization = `Bearer ${opts.authToken}`;
  return headers;
}

// --------------------------------------------------------------------------
// API functions
// --------------------------------------------------------------------------

/**
 * AC-F1: POST /api/workspaces/{id}/invitations via the typed client.
 *
 * Throws {@link WorkspaceInviteApiError} on non-2xx so the page can:
 *  - redirect to /login (S-001) on 401 (AC-F2),
 *  - render an inline error toast + empty state on other 4xx (AC-F1 tail).
 */
export async function createWorkspaceInvitation(
  workspaceId: number | string,
  body: CreateWorkspaceInvitationRequest,
  opts: WorkspaceInviteRequestOptions = {},
): Promise<CreateWorkspaceInvitationResponse> {
  const endpoint = workspaceInvitationsEndpoint(workspaceId);
  const baseUrl = resolveApiBase(opts.apiBase).replace(/\/$/, "");
  const url = `${baseUrl}${endpoint}`;
  const fetchImpl = opts.fetchImpl ?? fetch;

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "POST",
      headers: buildHeaders(opts, true),
      body: JSON.stringify(body),
      signal: opts.signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") throw err;
    throw new WorkspaceInviteApiError(
      "network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  return (await response.json()) as CreateWorkspaceInvitationResponse;
}

/**
 * AC-F1 (list): GET /api/workspaces/{id}/invitations.
 *
 * The OpenAPI contract (F-004) lists this endpoint and the v3 drift task
 * T-V3-DRIFT-F-004-07 tracks adding the GET handler in router; until that
 * lands, the typed client returns whatever the backend exposes and the page
 * gracefully shows an empty list when the call 4xx-s.
 */
export async function listWorkspaceInvitations(
  workspaceId: number | string,
  opts: WorkspaceInviteRequestOptions = {},
): Promise<ListWorkspaceInvitationsResponse> {
  const endpoint = workspaceInvitationsEndpoint(workspaceId);
  const baseUrl = resolveApiBase(opts.apiBase).replace(/\/$/, "");
  const url = `${baseUrl}${endpoint}`;
  const fetchImpl = opts.fetchImpl ?? fetch;

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "GET",
      headers: buildHeaders(opts, false),
      signal: opts.signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") throw err;
    throw new WorkspaceInviteApiError(
      "network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  const raw = (await response.json()) as
    | ListWorkspaceInvitationsResponse
    | WorkspaceInvitation[]
    | null;
  if (Array.isArray(raw)) return { invitations: raw };
  if (raw && Array.isArray((raw as ListWorkspaceInvitationsResponse).invitations)) {
    return raw as ListWorkspaceInvitationsResponse;
  }
  return { invitations: [] };
}

/**
 * DELETE /api/workspaces/{id}/invitations/{token} (T-V3-B-06).
 *
 * The page surfaces 401 → /login (AC-F2) and 403 / 404 → inline toast.
 */
export async function revokeWorkspaceInvitation(
  workspaceId: number | string,
  token: string,
  opts: WorkspaceInviteRequestOptions = {},
): Promise<RevokeWorkspaceInvitationResponse> {
  const endpoint = workspaceInvitationRevokeEndpoint(workspaceId, token);
  const baseUrl = resolveApiBase(opts.apiBase).replace(/\/$/, "");
  const url = `${baseUrl}${endpoint}`;
  const fetchImpl = opts.fetchImpl ?? fetch;

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "DELETE",
      headers: buildHeaders(opts, false),
      signal: opts.signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") throw err;
    throw new WorkspaceInviteApiError(
      "network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  return (await response.json()) as RevokeWorkspaceInvitationResponse;
}

/**
 * AC-F3: PUT /api/accounts/{id} for owner plan upgrade.
 *
 * Surfaces 4xx via {@link WorkspaceInviteApiError} so the page can render a
 * friendly toast and refuse to render the plan banner on 401.
 */
export async function updateAccountPlan(
  accountId: number | string,
  body: UpdateAccountPlanRequest,
  opts: WorkspaceInviteRequestOptions = {},
): Promise<UpdateAccountPlanResponse> {
  const endpoint = accountPlanEndpoint(accountId);
  const baseUrl = resolveApiBase(opts.apiBase).replace(/\/$/, "");
  const url = `${baseUrl}${endpoint}`;
  const fetchImpl = opts.fetchImpl ?? fetch;

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "PUT",
      headers: buildHeaders(opts, true),
      body: JSON.stringify(body),
      signal: opts.signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") throw err;
    throw new WorkspaceInviteApiError(
      "network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  return (await response.json()) as UpdateAccountPlanResponse;
}
