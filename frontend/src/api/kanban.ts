/**
 * T-V3-C-57-1 / F-007: Typed client for the workspace tasks endpoint backing
 * the S-027 タスク Kanban screen.
 *
 * Backend contract (T-V3-B-11 / T-V3-B-12 merged on earlier waves):
 *   GET /api/workspaces/{id}/tasks?group_by=feature
 *     — backend/routers/workspaces.py::get_workspaces_by_id_tasks
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml#/paths/~1api~1workspaces~1{id}~1tasks
 *
 * Errors follow the project-wide `{detail: {code, message}}` contract. The
 * thrown {@link KanbanApiError} surfaces a non-technical, endpoint-tagged
 * message for UI toasts and never leaks server stack traces.
 *
 * Auth-redirect awareness (AC-F2 UNWANTED on S-027): the page layer is
 * responsible for redirecting unauthenticated visitors to /login (S-001). The
 * client surfaces 401 with `status === 401` so the page can detect and route.
 * Likewise 403 is surfaced separately so the page can render the S-046 403
 * page instead of partial data (AC-F4 UNWANTED).
 *
 * Drag & drop / filter network calls are out of scope for T-V3-C-57-1 (they
 * are handled in T-V3-C-57-2 / T-V3-C-57-3 respectively). This module only
 * exposes the GET read path required by the core layout/data-fetch task.
 */

// --------------------------------------------------------------------------
// Endpoint constants
// --------------------------------------------------------------------------

/** Build the workspace tasks endpoint path (no host). */
export function kanbanTasksEndpoint(
  workspaceId: string | number,
  groupBy: "feature" | "status" | "assignee" = "feature",
): string {
  return `/api/workspaces/${encodeURIComponent(
    String(workspaceId),
  )}/tasks?group_by=${encodeURIComponent(groupBy)}`;
}

// --------------------------------------------------------------------------
// Domain types — mirror OpenAPI components/schemas (Task / TaskGroup).
//
// Backend `Task` schema lists `status` as a free-form string. The S-027 Kanban
// only renders 4 buckets (Todo / In Progress / Review / Done — see CLAUDE.md
// §5.5), so we project the raw API string onto a closed union via
// {@link normaliseKanbanStatus}. Anything we cannot classify is bucketed into
// "todo" to avoid silently dropping tasks.
// --------------------------------------------------------------------------

/** Closed kanban column union — must remain in lock-step with CLAUDE.md §5.5. */
export type KanbanColumn = "todo" | "in_progress" | "review" | "done";

/** Raw task object as returned by GET /api/workspaces/{id}/tasks. */
export interface KanbanTask {
  id: string;
  workspace_id?: string;
  phase_id?: string;
  title: string;
  description?: string;
  status?: string;
  priority?: string;
  assigned_employee_id?: string;
  assigned_user_id?: string;
  feature_id?: string;
  screen_id?: string;
  // Backend may attach a few accordion-friendly hints (estimate / cost) that
  // the v3 mock shows. They are optional — the page renders without them.
  estimate_hours?: number;
  cost_yen?: number;
  [extra: string]: unknown;
}

/** A feature_id-keyed group as returned by the backend `groups` array. */
export interface KanbanTaskGroup {
  /** feature_id (e.g. "F-001") or "ungrouped" when feature_id is missing. */
  id: string;
  /** Human-readable feature name (e.g. "Supabase 基盤 + 認証"). */
  name?: string;
  /** Total task count for the feature (optional, fall back to len(tasks)). */
  count?: number;
}

export interface KanbanTasksResponse {
  tasks: KanbanTask[];
  groups: KanbanTaskGroup[];
}

// --------------------------------------------------------------------------
// Status normalisation (raw backend string → 4-column kanban bucket)
// --------------------------------------------------------------------------

const STATUS_TO_COLUMN: Record<string, KanbanColumn> = {
  todo: "todo",
  pending: "todo",
  not_started: "todo",
  open: "todo",
  in_progress: "in_progress",
  wip: "in_progress",
  doing: "in_progress",
  review: "review",
  in_review: "review",
  review_needed: "review",
  done: "done",
  completed: "done",
  closed: "done",
};

/** Map a raw backend status string onto a 4-column kanban bucket. */
export function normaliseKanbanStatus(
  raw: string | undefined | null,
): KanbanColumn {
  if (!raw) return "todo";
  const key = String(raw).toLowerCase();
  return STATUS_TO_COLUMN[key] ?? "todo";
}

// --------------------------------------------------------------------------
// Error class
// --------------------------------------------------------------------------

const USER_MESSAGES: Record<number | "default", string> = {
  0: "ネットワークに接続できませんでした",
  400: "リクエストが不正です",
  401: "サインインが必要です",
  403: "この操作を実行する権限がありません",
  404: "対象のタスクが見つかりませんでした",
  422: "入力フォーマットが正しくありません",
  429: "リクエストが多すぎます。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "通信に失敗しました",
};

/** Thrown for any non-2xx response from the kanban tasks endpoint. */
export class KanbanApiError extends Error {
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
    this.name = "KanbanApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /** Non-technical, user-facing string suitable for toast / banner copy. */
  toUserMessage(): string {
    const friendly = USER_MESSAGES[this.status] ?? USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

// --------------------------------------------------------------------------
// Internal helpers
// --------------------------------------------------------------------------

export interface KanbanClientOptions {
  apiBase?: string;
  signal?: AbortSignal;
  authToken?: string | null;
  /** Test seam — overrides global fetch. */
  fetchImpl?: typeof fetch;
}

function resolveApiBase(opts: KanbanClientOptions): string {
  if (opts.apiBase) return opts.apiBase;
  if (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  if (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_BASE) {
    return process.env.NEXT_PUBLIC_API_BASE;
  }
  return "http://localhost:8001";
}

interface BackendErrorEnvelope {
  detail?: { code?: string; message?: string } | string;
}

async function parseError(
  response: Response,
  endpoint: string,
): Promise<KanbanApiError> {
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
    // Non-JSON body — keep generic fallback. Never embed raw body to avoid
    // leaking server stack traces in surfaced UI strings.
  }
  return new KanbanApiError(code, message, response.status, endpoint);
}

async function request<T>(
  method: "GET",
  endpoint: string,
  opts: KanbanClientOptions,
): Promise<T> {
  const base = resolveApiBase(opts);
  const url = `${base}${endpoint}`;
  const fetchImpl = opts.fetchImpl ?? fetch;

  const headers: Record<string, string> = { Accept: "application/json" };
  if (opts.authToken) headers.Authorization = `Bearer ${opts.authToken}`;

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method,
      headers,
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as { name?: string }).name === "AbortError") throw err;
    throw new KanbanApiError(
      "kanban.network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) throw await parseError(response, endpoint);
  if (response.status === 204) return undefined as unknown as T;

  try {
    return (await response.json()) as T;
  } catch {
    return undefined as unknown as T;
  }
}

// --------------------------------------------------------------------------
// Typed API surface
// --------------------------------------------------------------------------

/**
 * AC-F1 (S-027): GET /api/workspaces/{id}/tasks?group_by=feature.
 *
 * The backend response loosely conforms to {@link KanbanTasksResponse}. Missing
 * `groups` (older backend) is normalised to an empty array.
 */
export async function getKanbanTasks(
  workspaceId: string | number,
  opts: KanbanClientOptions = {},
): Promise<KanbanTasksResponse> {
  const payload = await request<Partial<KanbanTasksResponse>>(
    "GET",
    kanbanTasksEndpoint(workspaceId, "feature"),
    opts,
  );
  return {
    tasks: Array.isArray(payload?.tasks) ? payload!.tasks : [],
    groups: Array.isArray(payload?.groups) ? payload!.groups : [],
  };
}
