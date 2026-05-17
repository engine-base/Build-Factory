/**
 * T-V3-C-58 / F-007 / S-028: Typed client for the workspace task-list endpoints
 * backing the タスクリスト (task_list) screen.
 *
 * Backend contract (T-V3-B-11 / backend/routers/workspaces.py):
 *   GET  /api/workspaces/{id}/tasks
 *   POST /api/workspaces/{id}/tasks/bulk-play
 *   POST /api/workspaces/{id}/tasks/bulk-archive
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml
 *          #/api/workspaces/{id}/tasks (GET)
 *          #/api/workspaces/{id}/tasks/bulk-play (POST)
 *          #/api/workspaces/{id}/tasks/bulk-archive (POST)
 *
 * Auth model: bearerAuth (workspace member; bulk-archive requires
 * workspace_admin role server-side per features.json#F-007).
 *
 * 3-tier AC mapping (docs/audit/2026-05-16_v3/T-V3-C-58.md):
 *   functional.AC-F1 → getWorkspaceTasks(workspaceId, opts) GETs the task list payload.
 *   functional.AC-F2 → 4xx / 401 surfaces as TaskListApiError so the page can
 *                      route unauthenticated callers to /login (S-001) and
 *                      render an inline error toast + empty state on other 4xx.
 *   functional.AC-F3 → getWorkspaceTasks(workspaceId, { group_by: "feature" })
 *                      returns tasks grouped by feature_id with accordion-friendly
 *                      `groups` metadata.
 *
 * The client follows the project-wide FastAPI {detail: {code, message}} envelope
 * and never forwards a raw stack trace to the UI.
 */

import { env } from "@/env";

// --------------------------------------------------------------------------
// Endpoint helpers — exposed so callers/tests can assert on canonical paths.
// --------------------------------------------------------------------------

export const TASK_LIST_ENDPOINT_PATTERN =
  "/api/workspaces/{id}/tasks";
export const TASK_BULK_PLAY_ENDPOINT_PATTERN =
  "/api/workspaces/{id}/tasks/bulk-play";
export const TASK_BULK_ARCHIVE_ENDPOINT_PATTERN =
  "/api/workspaces/{id}/tasks/bulk-archive";

/** Build the canonical workspace-tasks endpoint path (optional query). */
export function workspaceTasksEndpoint(
  workspaceId: number | string,
  query: { group_by?: TaskGroupBy; filter?: string } = {},
): string {
  const base = `/api/workspaces/${encodeURIComponent(
    String(workspaceId),
  )}/tasks`;
  const params: string[] = [];
  if (query.group_by) {
    params.push(`group_by=${encodeURIComponent(query.group_by)}`);
  }
  if (query.filter) {
    params.push(`filter=${encodeURIComponent(query.filter)}`);
  }
  return params.length ? `${base}?${params.join("&")}` : base;
}

/** Build the canonical bulk-play endpoint path. */
export function workspaceBulkPlayEndpoint(
  workspaceId: number | string,
): string {
  return `/api/workspaces/${encodeURIComponent(
    String(workspaceId),
  )}/tasks/bulk-play`;
}

/** Build the canonical bulk-archive endpoint path. */
export function workspaceBulkArchiveEndpoint(
  workspaceId: number | string,
): string {
  return `/api/workspaces/${encodeURIComponent(
    String(workspaceId),
  )}/tasks/bulk-archive`;
}

// --------------------------------------------------------------------------
// Wire types — mirror backend/services + openapi.yaml schemas.
// --------------------------------------------------------------------------

/** Supported `group_by` values for the list endpoint. */
export type TaskGroupBy = "feature" | "status" | "assignee";

/**
 * Single task projection. Mirrors `#/components/schemas/Task` in openapi.yaml
 * but keeps every field optional so partial server responses keep rendering.
 */
export interface TaskListItem {
  id: number | string;
  task_id?: string | null;
  title?: string | null;
  feature_id?: string | null;
  status?: string | null;
  assignee?: string | null;
  assignee_name?: string | null;
  estimate_hours?: number | null;
  cost?: number | null;
  updated_at?: string | null;
  workspace_id?: number | string | null;
}

/**
 * Accordion-friendly grouping metadata. When `group_by=feature` is requested
 * the backend returns one entry per feature with the member task ids so the UI
 * can render `<details>` accordions without re-grouping client-side.
 */
export interface TaskGroup {
  key: string;
  label?: string | null;
  count?: number | null;
  task_ids?: Array<number | string> | null;
}

/** GET /api/workspaces/{id}/tasks response. */
export interface WorkspaceTasksResponse {
  tasks: TaskListItem[];
  groups?: TaskGroup[] | null;
}

export interface BulkPlayRequest {
  task_ids: Array<number | string>;
}

export interface BulkPlayResponse {
  session_ids?: string[];
  queued?: number;
}

export interface BulkArchiveRequest {
  task_ids: Array<number | string>;
}

export interface BulkArchiveResponse {
  archived_count?: number;
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

/** Thrown for any non-2xx response from a task-list endpoint. */
export class TaskListApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly endpoint: string;

  constructor(code: string, message: string, status: number, endpoint: string) {
    super(message);
    this.name = "TaskListApiError";
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
      TASK_LIST_USER_MESSAGES[this.status] ??
      TASK_LIST_USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

const TASK_LIST_USER_MESSAGES: Record<number | "default", string> = {
  400: "リクエストに問題があります",
  401: "ログインが必要です",
  403: "この操作を実行する権限がありません",
  404: "タスクが見つかりませんでした",
  409: "並列実行の上限に達しています",
  422: "入力内容を確認してください",
  429: "リクエストが多すぎます。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "タスクの読み込みに失敗しました",
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
): Promise<TaskListApiError> {
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
  return new TaskListApiError(code, message, response.status, endpoint);
}

export interface TaskListRequestOptions {
  apiBase?: string;
  signal?: AbortSignal;
  /** Optional bearer token forwarded as `Authorization: Bearer <token>`. */
  authToken?: string | null;
  /** Test seam — defaults to the global `fetch`. */
  fetchImpl?: typeof fetch;
}

function buildHeaders(
  opts: TaskListRequestOptions,
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

export interface GetWorkspaceTasksParams {
  group_by?: TaskGroupBy;
  filter?: string;
}

/**
 * AC-F1 / AC-F3: GET /api/workspaces/{id}/tasks via the typed client.
 *
 * Throws {@link TaskListApiError} on non-2xx so the page can:
 *  - redirect to /login (S-001) on 401 (AC-F2)
 *  - render the inline error toast + empty state on other 4xx (AC-F1 tail).
 *
 * When `group_by="feature"` is passed the response includes an accordion-friendly
 * `groups` array keyed by feature_id (AC-F3).
 */
export async function getWorkspaceTasks(
  workspaceId: number | string,
  params: GetWorkspaceTasksParams = {},
  opts: TaskListRequestOptions = {},
): Promise<WorkspaceTasksResponse> {
  const endpoint = workspaceTasksEndpoint(workspaceId, params);
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
    throw new TaskListApiError(
      "network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  return (await response.json()) as WorkspaceTasksResponse;
}

/**
 * POST /api/workspaces/{id}/tasks/bulk-play.
 *
 * Queues each task id as a session run (workspace member). Returns the queued
 * `session_ids`; on 409 the response indicates max_parallel reached.
 */
export async function bulkPlayTasks(
  workspaceId: number | string,
  body: BulkPlayRequest,
  opts: TaskListRequestOptions = {},
): Promise<BulkPlayResponse> {
  const endpoint = workspaceBulkPlayEndpoint(workspaceId);
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
    throw new TaskListApiError(
      "network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  return (await response.json()) as BulkPlayResponse;
}

/**
 * POST /api/workspaces/{id}/tasks/bulk-archive (workspace_admin).
 *
 * The backend enforces workspace_admin via RLS; the UI surfaces 403 as a
 * friendly toast tagged with the failing endpoint.
 */
export async function bulkArchiveTasks(
  workspaceId: number | string,
  body: BulkArchiveRequest,
  opts: TaskListRequestOptions = {},
): Promise<BulkArchiveResponse> {
  const endpoint = workspaceBulkArchiveEndpoint(workspaceId);
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
    throw new TaskListApiError(
      "network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  return (await response.json()) as BulkArchiveResponse;
}
