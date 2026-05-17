/**
 * T-V3-C-63 / F-004 / S-014: Typed client for the workspace_members endpoints
 * backing the 案件メンバー (workspace_members) screen.
 *
 * Backend contracts (T-V3-B-06 / backend/routers/workspaces.py):
 *   GET    /api/workspaces/{id}/members
 *   PUT    /api/workspaces/{id}/members/{user_id}/role
 *   DELETE /api/workspaces/{id}/members/{user_id}
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml
 *          #/api/workspaces/{id}/members (GET)
 *          #/api/workspaces/{id}/members/{user_id}/role (PUT)
 *          #/api/workspaces/{id}/members/{user_id} (DELETE)
 *
 * Auth model: bearerAuth — GET requires workspace member; PUT / DELETE
 * require workspace_admin (server-side enforced via F-021 OR-policy across
 * role default_permissions + member custom_permissions).
 *
 * 3-tier AC mapping (docs/audit/2026-05-16_v3/T-V3-C-63.md):
 *   functional.AC-F1 -> listWorkspaceMembers() GETs and returns members[].
 *                       4xx surfaces as WorkspaceMembersApiError so the page
 *                       can render an inline error toast + empty state.
 *   functional.AC-F2 -> 401 surfaces as WorkspaceMembersApiError.status === 401
 *                       so the page can redirect to /login (S-001) without
 *                       rendering any workspace-scoped data.
 *   functional.AC-F3 -> updateMemberRole() PUTs role + emits the
 *                       account_updated audit log server-side (T-V3-B-06).
 *   functional.AC-F4 -> The OR-policy across role default_permissions and
 *                       member custom_permissions is enforced server-side
 *                       (F-021); this client surfaces 403 as a friendly toast.
 *
 * The client follows the project-wide FastAPI {detail: {code, message}}
 * envelope and never forwards a raw stack trace to the UI.
 */

// --------------------------------------------------------------------------
// Endpoint helpers — exported so tests can assert on canonical paths.
// --------------------------------------------------------------------------

export const WORKSPACE_MEMBERS_ENDPOINT_PATTERN =
  "/api/workspaces/{id}/members";
export const WORKSPACE_MEMBER_ROLE_ENDPOINT_PATTERN =
  "/api/workspaces/{id}/members/{user_id}/role";
export const WORKSPACE_MEMBER_DETAIL_ENDPOINT_PATTERN =
  "/api/workspaces/{id}/members/{user_id}";

/** Build the canonical workspace-members endpoint path. */
export function workspaceMembersEndpoint(
  workspaceId: number | string,
): string {
  return `/api/workspaces/${encodeURIComponent(String(workspaceId))}/members`;
}

/** Build the canonical workspace-member role-mutation endpoint path. */
export function workspaceMemberRoleEndpoint(
  workspaceId: number | string,
  userId: string,
): string {
  return `/api/workspaces/${encodeURIComponent(
    String(workspaceId),
  )}/members/${encodeURIComponent(userId)}/role`;
}

/** Build the canonical workspace-member detail (DELETE) endpoint path. */
export function workspaceMemberDetailEndpoint(
  workspaceId: number | string,
  userId: string,
): string {
  return `/api/workspaces/${encodeURIComponent(
    String(workspaceId),
  )}/members/${encodeURIComponent(userId)}`;
}

// --------------------------------------------------------------------------
// Wire types — mirror backend/services + openapi.yaml schemas.
// --------------------------------------------------------------------------

/**
 * Supported workspace role values (server-side enum). Mirrors
 * openapi.yaml#/paths/...members/{user_id}/role.put.requestBody.schema.role.
 */
export type WorkspaceRole =
  | "owner"
  | "admin"
  | "member"
  | "viewer"
  | "guest"
  // The legacy v2 6-role taxonomy is also accepted by the existing backend
  // (services/roles.py) and surfaces as-is from the GET response. We keep the
  // type open so the UI does not throw on legacy payloads.
  | "ws_admin"
  | "workspace_admin"
  | "contributor"
  | "client"
  | "monitor";

/**
 * Single workspace member projection. Mirrors
 * `#/components/schemas/WorkspaceMember` in openapi.yaml but keeps every
 * field optional so partial server responses keep rendering.
 *
 * Extra optional fields (display_name / email / last_active_at / visible_tabs
 * / custom_permissions) are surfaced by the v2 services and consumed by the
 * mock — they are included here so the UI can render the full row without a
 * second round-trip.
 */
export interface WorkspaceMember {
  workspace_id?: string;
  user_id: string;
  role: WorkspaceRole | string;
  display_name?: string | null;
  email?: string | null;
  custom_permissions?: Record<string, boolean> | string | null;
  visible_tabs?: string[] | string | null;
  last_active_at?: string | null;
}

export interface ListWorkspaceMembersResponse {
  members: WorkspaceMember[];
}

export interface UpdateMemberRoleRequest {
  role: WorkspaceRole;
}

export interface UpdateMemberRoleResponse {
  role: string;
  updated_at: string;
}

export interface RemoveMemberResponse {
  removed_at: string;
}

// --------------------------------------------------------------------------
// Error class — friendly user-facing messages without stack-trace leak.
// --------------------------------------------------------------------------

const USER_MESSAGES: Record<number | "default", string> = {
  400: "リクエストが不正です",
  401: "サインインが必要です",
  403: "この操作を実行する権限がありません",
  404: "メンバーが見つかりませんでした",
  409: "最後の管理者は降格・削除できません",
  422: "入力内容を確認してください",
  429: "リクエストが多すぎます。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "通信に失敗しました",
};

/** Thrown for any non-2xx response from the workspace-members endpoints. */
export class WorkspaceMembersApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly endpoint: string;

  constructor(
    code: string,
    message: string,
    status: number,
    endpoint: string,
  ) {
    super(message);
    this.name = "WorkspaceMembersApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * Produce a non-technical user-facing message that references the failing
   * endpoint without leaking server stack traces (AC-F1 / AC-F2).
   */
  toUserMessage(): string {
    const friendly = USER_MESSAGES[this.status] ?? USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

// --------------------------------------------------------------------------
// HTTP helper — fetch wrapper with auth header + error parsing.
// --------------------------------------------------------------------------

export interface WorkspaceMembersClientOptions {
  apiBase?: string;
  signal?: AbortSignal;
  /** Bearer token for endpoints requiring `authenticated` role. */
  authToken?: string | null;
}

function resolveApiBase(opts: WorkspaceMembersClientOptions): string {
  if (opts.apiBase) return opts.apiBase;
  if (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  return "http://localhost:8001";
}

interface BackendErrorEnvelope {
  detail?: { code?: string; message?: string } | string;
}

async function parseError(
  response: Response,
  endpoint: string,
): Promise<WorkspaceMembersApiError> {
  let code = "UNKNOWN";
  let message = response.statusText || "request failed";
  try {
    const payload = (await response.json()) as BackendErrorEnvelope;
    if (payload && typeof payload.detail === "object" && payload.detail) {
      if (typeof payload.detail.code === "string") code = payload.detail.code;
      if (typeof payload.detail.message === "string")
        message = payload.detail.message;
    } else if (typeof payload?.detail === "string") {
      message = payload.detail;
    }
  } catch {
    // Non-JSON body — keep the synthesised message. We deliberately do not
    // include the raw body to avoid leaking server stack traces.
  }
  return new WorkspaceMembersApiError(code, message, response.status, endpoint);
}

async function request<T>(
  method: "GET" | "PUT" | "DELETE",
  endpoint: string,
  body: unknown,
  opts: WorkspaceMembersClientOptions,
): Promise<T> {
  const base = resolveApiBase(opts);
  const url = `${base}${endpoint}`;

  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (opts.authToken) headers.Authorization = `Bearer ${opts.authToken}`;

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as { name?: string }).name === "AbortError") throw err;
    throw new WorkspaceMembersApiError(
      "workspace_members.network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) throw await parseError(response, endpoint);

  // DELETE / 204 may return empty body.
  if (response.status === 204) return undefined as unknown as T;

  try {
    return (await response.json()) as T;
  } catch {
    return undefined as unknown as T;
  }
}

// --------------------------------------------------------------------------
// Typed API surface — small, exactly what S-014 needs.
// --------------------------------------------------------------------------

/** AC-F1: GET /api/workspaces/{id}/members. */
export async function listWorkspaceMembers(
  workspaceId: number | string,
  opts: WorkspaceMembersClientOptions = {},
): Promise<ListWorkspaceMembersResponse> {
  const endpoint = workspaceMembersEndpoint(workspaceId);
  const payload = await request<unknown>("GET", endpoint, undefined, opts);
  // Backend response may be either { members: [...] } or [...] (legacy).
  if (Array.isArray(payload)) {
    return { members: payload as WorkspaceMember[] };
  }
  if (payload && typeof payload === "object" && "members" in payload) {
    const members = (payload as { members?: unknown }).members;
    if (Array.isArray(members)) {
      return { members: members as WorkspaceMember[] };
    }
  }
  return { members: [] };
}

/** AC-F3: PUT /api/workspaces/{id}/members/{user_id}/role. */
export function updateMemberRole(
  workspaceId: number | string,
  userId: string,
  body: UpdateMemberRoleRequest,
  opts: WorkspaceMembersClientOptions = {},
): Promise<UpdateMemberRoleResponse> {
  return request<UpdateMemberRoleResponse>(
    "PUT",
    workspaceMemberRoleEndpoint(workspaceId, userId),
    body,
    opts,
  );
}

/** DELETE /api/workspaces/{id}/members/{user_id}. */
export function removeWorkspaceMember(
  workspaceId: number | string,
  userId: string,
  opts: WorkspaceMembersClientOptions = {},
): Promise<RemoveMemberResponse> {
  return request<RemoveMemberResponse>(
    "DELETE",
    workspaceMemberDetailEndpoint(workspaceId, userId),
    undefined,
    opts,
  );
}
