/**
 * T-V3-C-62 / F-004 / S-013: Typed client for the workspace settings endpoints
 * backing the 案件設定 (workspace_settings) screen.
 *
 * Backend contract (T-V3-B-05 / backend/routers/workspaces.py):
 *   GET    /api/workspaces/{id}
 *   PUT    /api/workspaces/{id}
 *   DELETE /api/workspaces/{id}
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml
 *          #/api/workspaces/{id} (GET / PUT / DELETE)
 *
 * Auth model: bearerAuth (workspace member for GET; workspace_admin for
 * PUT / DELETE per features.json#F-004).
 *
 * 3-tier AC mapping (docs/audit/2026-05-16_v3/T-V3-C-62.md):
 *   functional.AC-F1 → getWorkspace(id) GETs the workspace payload; non-2xx
 *                      surfaces as WorkspaceSettingsApiError so the page can
 *                      render the inline error toast + empty state.
 *   functional.AC-F2 → 401 surfaces as WorkspaceSettingsApiError with status
 *                      401 so the page can router.replace("/login") and not
 *                      render any workspace-scoped data.
 *   functional.AC-F3 → updateWorkspace(id, body) PUTs the settings; on 2xx
 *                      the server emits an account_updated audit log.
 *
 * The client follows the project-wide FastAPI {detail: {code, message}}
 * envelope and never forwards a raw stack trace to the UI.
 */

import { env } from "@/env";

// --------------------------------------------------------------------------
// Endpoint helpers — exposed so callers/tests can assert on canonical paths.
// --------------------------------------------------------------------------

export const WORKSPACE_ENDPOINT_PATTERN = "/api/workspaces/{id}";

/** Build the canonical workspace endpoint path. */
export function workspaceEndpoint(workspaceId: number | string): string {
  return `/api/workspaces/${encodeURIComponent(String(workspaceId))}`;
}

// --------------------------------------------------------------------------
// Wire types — mirror backend/services + openapi.yaml#components/schemas/Workspace.
// --------------------------------------------------------------------------

/** Project type — 内製 / 受託 / OSS. */
export type WorkspaceProjectType = "internal" | "client" | "oss";

/**
 * External integration link projected from `WorkspaceSetting.integration_links`
 * JSONB. Each entry corresponds to one of the badges rendered under "外部連携".
 */
export interface WorkspaceIntegrationLink {
  /** Integration kind — "github" | "slack" | "obsidian" | ... */
  kind: string;
  /** Human-friendly display label (e.g. "engine-base/Build-Factory"). */
  label?: string | null;
  /** "connected" | "disconnected" | "pending" | ... */
  status?: string | null;
  /** Optional opaque external resource URL / path. */
  url?: string | null;
}

/**
 * Single workspace projection. Mirrors `#/components/schemas/Workspace` in
 * openapi.yaml but keeps every field optional so partial server responses
 * keep rendering.
 */
export interface Workspace {
  id: number | string;
  account_id?: number | string | null;
  name?: string | null;
  project_meta?: string | null;
  project_type?: WorkspaceProjectType | string | null;
  is_confidential?: boolean | null;
  /** Monthly token cap (tokens). */
  token_limit?: number | null;
  /** Monthly cost budget (JPY). */
  cost_budget?: number | null;
  /** Maximum concurrent sessions. */
  max_parallel_sessions?: number | null;
  integration_links?: WorkspaceIntegrationLink[] | null;
  status?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

/** GET /api/workspaces/{id} response. */
export interface GetWorkspaceResponse {
  workspace: Workspace;
}

/** PUT /api/workspaces/{id} request body. */
export interface UpdateWorkspaceRequest {
  name?: string | null;
  project_meta?: string | null;
  project_type?: WorkspaceProjectType | string | null;
  is_confidential?: boolean | null;
  token_limit?: number | null;
  cost_budget?: number | null;
  max_parallel_sessions?: number | null;
  status?: string | null;
}

/** PUT /api/workspaces/{id} response body. */
export interface UpdateWorkspaceResponse {
  id: number | string;
  updated_at?: string | null;
}

/** DELETE /api/workspaces/{id} response body. */
export interface DeleteWorkspaceResponse {
  soft_deleted_at?: string | null;
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

/** Thrown for any non-2xx response from a workspace-settings endpoint. */
export class WorkspaceSettingsApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly endpoint: string;

  constructor(code: string, message: string, status: number, endpoint: string) {
    super(message);
    this.name = "WorkspaceSettingsApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * Non-technical, end-user friendly message tagged with the failing endpoint.
   * Never embeds stack traces / SQL / raw exception class names.
   */
  toUserMessage(): string {
    const friendly =
      WORKSPACE_SETTINGS_USER_MESSAGES[this.status] ??
      WORKSPACE_SETTINGS_USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

const WORKSPACE_SETTINGS_USER_MESSAGES: Record<number | "default", string> = {
  400: "リクエストに問題があります",
  401: "ログインが必要です",
  403: "この操作を実行する権限がありません",
  404: "案件が見つかりませんでした",
  409: "他のユーザーが先に更新しました",
  422: "入力内容を確認してください",
  429: "リクエストが多すぎます。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "案件設定の読み込みに失敗しました",
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
  try {
    if (env?.NEXT_PUBLIC_API_URL) return env.NEXT_PUBLIC_API_URL;
  } catch {
    /* swallow — env is not always defined in test contexts */
  }
  return "http://localhost:8001";
}

async function parseErrorEnvelope(
  response: Response,
  endpoint: string,
): Promise<WorkspaceSettingsApiError> {
  let code = "UNKNOWN_ERROR";
  let message = response.statusText || "request failed";
  try {
    const envelope = (await response.json()) as BackendErrorEnvelope;
    if (envelope && typeof envelope.detail === "object" && envelope.detail) {
      if (typeof envelope.detail.code === "string") code = envelope.detail.code;
      if (typeof envelope.detail.message === "string") {
        message = envelope.detail.message;
      }
    } else if (typeof envelope?.detail === "string") {
      message = envelope.detail;
    }
  } catch {
    // intentionally ignore parse failure — never forward raw HTML / stack traces.
  }
  return new WorkspaceSettingsApiError(
    code,
    message,
    response.status,
    endpoint,
  );
}

export interface WorkspaceSettingsRequestOptions {
  apiBase?: string;
  signal?: AbortSignal;
  /** Optional bearer token forwarded as `Authorization: Bearer <token>`. */
  authToken?: string | null;
  /** Test seam — defaults to the global `fetch`. */
  fetchImpl?: typeof fetch;
}

function buildHeaders(
  opts: WorkspaceSettingsRequestOptions,
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
 * AC-F1: GET /api/workspaces/{id} via the typed client.
 *
 * Throws {@link WorkspaceSettingsApiError} on non-2xx so the page can:
 *  - redirect to /login (S-001) on 401 (AC-F2)
 *  - render the inline error toast + empty state on other 4xx (AC-F1 tail).
 */
export async function getWorkspace(
  workspaceId: number | string,
  opts: WorkspaceSettingsRequestOptions = {},
): Promise<GetWorkspaceResponse> {
  const endpoint = workspaceEndpoint(workspaceId);
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
    throw new WorkspaceSettingsApiError(
      "network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  return (await response.json()) as GetWorkspaceResponse;
}

/**
 * AC-F3: PUT /api/workspaces/{id} via the typed client (workspace_admin).
 *
 * The backend enforces workspace_admin via RLS; on a successful update the
 * backend emits an `account_updated` audit log entry (see
 * backend/services/workspaces.py). The UI surfaces 403 as a friendly toast
 * tagged with the failing endpoint.
 */
export async function updateWorkspace(
  workspaceId: number | string,
  body: UpdateWorkspaceRequest,
  opts: WorkspaceSettingsRequestOptions = {},
): Promise<UpdateWorkspaceResponse> {
  const endpoint = workspaceEndpoint(workspaceId);
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
    throw new WorkspaceSettingsApiError(
      "network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  return (await response.json()) as UpdateWorkspaceResponse;
}

/**
 * DELETE /api/workspaces/{id} via the typed client (workspace_admin).
 *
 * Soft-delete — the server marks the workspace `soft_deleted_at` and returns
 * the timestamp.
 */
export async function deleteWorkspace(
  workspaceId: number | string,
  opts: WorkspaceSettingsRequestOptions = {},
): Promise<DeleteWorkspaceResponse> {
  const endpoint = workspaceEndpoint(workspaceId);
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
    throw new WorkspaceSettingsApiError(
      "network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  return (await response.json()) as DeleteWorkspaceResponse;
}
