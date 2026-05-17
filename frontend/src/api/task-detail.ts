/**
 * T-V3-C-60 / F-006 + F-007 / S-030: Typed client for the task-detail endpoints
 * backing the タスク詳細 (task_detail) screen.
 *
 * Backend contracts (T-V3-B-11 + T-V3-B-12):
 *   GET  /api/tasks/{id}                 — get_tasks_by_id (member)
 *   PUT  /api/tasks/{id}                 — put_tasks_by_id (member)
 *   POST /api/tasks/{id}/play            — post_tasks_by_id_play (member)
 *   POST /api/tasks/{id}/comments        — post_tasks_by_id_comments (member)
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml
 *          #/api/tasks/{id}
 *          #/api/tasks/{id}/play
 *          #/api/tasks/{id}/comments
 *
 * Auth model: bearerAuth (workspace member).
 *
 * 3-tier AC mapping (docs/audit/2026-05-16_v3/T-V3-C-60.md):
 *   functional.AC-F1 → getTaskDetail(id) GETs the task payload; 4xx → typed error.
 *   functional.AC-F2 → 401 surfaces as TaskDetailApiError(status=401) so the
 *                       page can redirect to /login (S-001) without rendering
 *                       workspace-scoped data.
 *   functional.AC-F5 → validateEarsForm() asserts every AC matches one of the
 *                       5 EARS forms before persisting through PUT.
 *
 * The client follows the project-wide FastAPI {detail: {code, message}} envelope
 * and never forwards a raw stack trace to the UI.
 */

import { env } from "@/env";

// --------------------------------------------------------------------------
// Endpoint helpers — exposed so callers/tests can assert on canonical paths.
// --------------------------------------------------------------------------

export const TASK_DETAIL_ENDPOINT_PATTERN = "/api/tasks/{id}";
export const TASK_PLAY_ENDPOINT_PATTERN = "/api/tasks/{id}/play";
export const TASK_COMMENTS_ENDPOINT_PATTERN = "/api/tasks/{id}/comments";

/** Build the canonical task-detail endpoint path. */
export function taskDetailEndpoint(taskId: number | string): string {
  return `/api/tasks/${encodeURIComponent(String(taskId))}`;
}

/** Build the canonical task-play endpoint path. */
export function taskPlayEndpoint(taskId: number | string): string {
  return `/api/tasks/${encodeURIComponent(String(taskId))}/play`;
}

/** Build the canonical task-comments endpoint path. */
export function taskCommentsEndpoint(taskId: number | string): string {
  return `/api/tasks/${encodeURIComponent(String(taskId))}/comments`;
}

// --------------------------------------------------------------------------
// Wire types — mirror backend/services + openapi.yaml schemas.
// --------------------------------------------------------------------------

/** Single acceptance-criteria item (EARS-form). */
export interface AcceptanceCriterion {
  id?: string | null;
  text: string;
  ears_form?: EarsForm | null;
}

/** EARS notation forms (the only 5 allowed by Build-Factory). */
export type EarsForm =
  | "UBIQUITOUS"
  | "EVENT-DRIVEN"
  | "STATE-DRIVEN"
  | "OPTIONAL"
  | "UNWANTED";

/** Task projection — mirrors `#/components/schemas/Task` in openapi.yaml. */
export interface TaskView {
  id: number | string;
  task_id?: string | null;
  title?: string | null;
  description?: string | null;
  status?: string | null;
  feature_id?: string | null;
  workspace_id?: number | string | null;
  assignee?: string | null;
  assignee_name?: string | null;
  estimate_hours?: number | null;
  cost?: number | null;
  cost_jpy?: number | null;
  tokens?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  /** Linked screens / dependencies (free shape — server may evolve). */
  related_screens?: Array<{ id: string; label?: string | null }> | null;
  dependencies?: Array<{
    task_id: string;
    title?: string | null;
    status?: string | null;
  }> | null;
  /** Files predicted to change when this task runs. */
  changed_files?: Array<{ path: string; change_type?: string | null }> | null;
}

/** Compact session summary shown in the right rail / history. */
export interface SessionSummary {
  id: string | number;
  status?: string | null;
  assignee?: string | null;
  cost_jpy?: number | null;
  tokens?: number | null;
  elapsed_label?: string | null;
  created_at?: string | null;
}

/** Comment thread item. */
export interface TaskComment {
  id: string | number;
  body: string;
  author?: string | null;
  author_name?: string | null;
  created_at?: string | null;
}

/** GET /api/tasks/{id} response. */
export interface TaskDetailResponse {
  task: TaskView;
  acceptance_criteria?: AcceptanceCriterion[] | null;
  sessions?: SessionSummary[] | null;
  comments?: TaskComment[] | null;
}

export interface PlayTaskRequest {
  /** Optional context for the play session (free text). */
  note?: string | null;
}

export interface PlayTaskResponse {
  session_id: string;
}

export interface PostTaskCommentRequest {
  body: string;
}

export interface PostTaskCommentResponse {
  comment_id: string;
}

export interface PutTaskRequest {
  title?: string | null;
  status?: string | null;
  description?: string | null;
  assignee_id?: string | null;
  acceptance_criteria?: AcceptanceCriterion[] | null;
}

export interface PutTaskResponse {
  id: string;
  updated_at: string;
}

// --------------------------------------------------------------------------
// EARS validation — AC-F5.
// --------------------------------------------------------------------------

/** Regex covering the 5 EARS forms accepted by Build-Factory. */
const EARS_PATTERNS: ReadonlyArray<{ form: EarsForm; pattern: RegExp }> = [
  { form: "EVENT-DRIVEN", pattern: /^\s*when\b[^.]*?\bthe system shall\b/i },
  { form: "STATE-DRIVEN", pattern: /^\s*while\b[^.]*?\bthe system shall\b/i },
  { form: "OPTIONAL", pattern: /^\s*where\b[^.]*?\bthe system shall\b/i },
  { form: "UNWANTED", pattern: /^\s*if\b[^.]*?\bthe system shall not\b/i },
  { form: "UBIQUITOUS", pattern: /^\s*the system shall\b/i },
];

/**
 * Returns the EARS form for `text` or `null` when it does not match any of
 * the 5 allowed forms. AC-F5: every persisted AC must validate.
 */
export function detectEarsForm(text: string): EarsForm | null {
  if (!text) return null;
  for (const { form, pattern } of EARS_PATTERNS) {
    if (pattern.test(text)) return form;
  }
  return null;
}

/** Validate an array of AC items; throw if any one fails EARS. */
export function assertAllEarsValid(items: AcceptanceCriterion[]): void {
  for (let i = 0; i < items.length; i++) {
    const it = items[i];
    if (!it || typeof it.text !== "string" || !detectEarsForm(it.text)) {
      throw new TaskDetailApiError(
        "ears_validation_failed",
        `acceptance_criteria[${i}] does not match any of the 5 EARS forms`,
        422,
        TASK_DETAIL_ENDPOINT_PATTERN,
      );
    }
  }
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

/** Thrown for any non-2xx response from a task-detail endpoint. */
export class TaskDetailApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly endpoint: string;

  constructor(code: string, message: string, status: number, endpoint: string) {
    super(message);
    this.name = "TaskDetailApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * Non-technical, end-user friendly message tagged with the failing endpoint.
   * Never embeds stack traces / SQL / raw exception class names (AC-F1 tail).
   */
  toUserMessage(): string {
    const friendly =
      TASK_DETAIL_USER_MESSAGES[this.status] ??
      TASK_DETAIL_USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

const TASK_DETAIL_USER_MESSAGES: Record<number | "default", string> = {
  400: "リクエストに問題があります",
  401: "ログインが必要です",
  403: "この操作を実行する権限がありません",
  404: "タスクが見つかりませんでした",
  409: "依存タスクが未完了です",
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
): Promise<TaskDetailApiError> {
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
    /* swallow — keep generic fallback */
  }
  return new TaskDetailApiError(code, message, response.status, endpoint);
}

export interface TaskDetailRequestOptions {
  apiBase?: string;
  signal?: AbortSignal;
  /** Optional bearer token forwarded as `Authorization: Bearer <token>`. */
  authToken?: string | null;
  /** Test seam — defaults to the global `fetch`. */
  fetchImpl?: typeof fetch;
}

function buildHeaders(
  opts: TaskDetailRequestOptions,
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
 * AC-F1: GET /api/tasks/{id} via the typed client.
 *
 * Throws {@link TaskDetailApiError} on non-2xx so the page can:
 *  - redirect to /login (S-001) on 401 (AC-F2)
 *  - render the inline error toast + empty state on other 4xx (AC-F1 tail).
 */
export async function getTaskDetail(
  taskId: number | string,
  opts: TaskDetailRequestOptions = {},
): Promise<TaskDetailResponse> {
  const endpoint = taskDetailEndpoint(taskId);
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
    throw new TaskDetailApiError("network_error", "network error", 0, endpoint);
  }

  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  return (await response.json()) as TaskDetailResponse;
}

/** POST /api/tasks/{id}/play via the typed client (single-task play). */
export async function playTask(
  taskId: number | string,
  body: PlayTaskRequest = {},
  opts: TaskDetailRequestOptions = {},
): Promise<PlayTaskResponse> {
  const endpoint = taskPlayEndpoint(taskId);
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
    throw new TaskDetailApiError("network_error", "network error", 0, endpoint);
  }

  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  return (await response.json()) as PlayTaskResponse;
}

/** POST /api/tasks/{id}/comments via the typed client. */
export async function postTaskComment(
  taskId: number | string,
  body: PostTaskCommentRequest,
  opts: TaskDetailRequestOptions = {},
): Promise<PostTaskCommentResponse> {
  const endpoint = taskCommentsEndpoint(taskId);
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
    throw new TaskDetailApiError("network_error", "network error", 0, endpoint);
  }

  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  return (await response.json()) as PostTaskCommentResponse;
}

/**
 * AC-F5: PUT /api/tasks/{id} — validates every acceptance_criteria item against
 * one of the 5 EARS forms BEFORE sending the request. On EARS failure the call
 * throws a {@link TaskDetailApiError}(status=422) without contacting the server.
 */
export async function putTask(
  taskId: number | string,
  body: PutTaskRequest,
  opts: TaskDetailRequestOptions = {},
): Promise<PutTaskResponse> {
  if (Array.isArray(body.acceptance_criteria)) {
    assertAllEarsValid(body.acceptance_criteria);
  }
  const endpoint = taskDetailEndpoint(taskId);
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
    throw new TaskDetailApiError("network_error", "network error", 0, endpoint);
  }

  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  return (await response.json()) as PutTaskResponse;
}
