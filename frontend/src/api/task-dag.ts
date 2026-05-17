/**
 * T-V3-C-59 / F-007: Typed client for the workspace task-DAG endpoints
 * backing the S-029 タスク DAG screen.
 *
 * Backend contracts:
 *   GET    /api/workspaces/{id}/tasks/dag                     — T-V3-B-007 (workspaces router)
 *   GET    /api/workspaces/{id}/tasks?group_by=feature        — F-007 list endpoint
 *   POST   /api/workspaces/{id}/dependencies                  — T-V3-B-009 / T-V3-B-014
 *   POST   /api/workspaces/{id}/dependencies/impact-analysis  — T-V3-B-014
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml
 *   #/paths/~1api~1workspaces~1{id}~1tasks~1dag
 *   #/components/schemas/TaskNode
 *   #/components/schemas/DAGEdge
 *
 * Errors follow the project-wide `{detail: {code, message}}` contract. The
 * thrown {@link TaskDagApiError} surfaces a non-technical, endpoint-tagged
 * message for UI toasts and never leaks server stack traces (AC-F1 on S-029).
 *
 * Auth-redirect awareness (AC-F2 UNWANTED on S-029): the page layer is
 * responsible for redirecting unauthenticated visitors to /login (S-001). The
 * client surfaces 401 with `status === 401` so the page can detect and route.
 */

// --------------------------------------------------------------------------
// Endpoint constants
// --------------------------------------------------------------------------

export function taskDagEndpoint(workspaceId: string | number): string {
  return `/api/workspaces/${encodeURIComponent(String(workspaceId))}/tasks/dag`;
}

export function tasksByFeatureEndpoint(workspaceId: string | number): string {
  return `/api/workspaces/${encodeURIComponent(
    String(workspaceId),
  )}/tasks?group_by=feature`;
}

export function dependencyCreateEndpoint(
  workspaceId: string | number,
): string {
  return `/api/workspaces/${encodeURIComponent(
    String(workspaceId),
  )}/dependencies`;
}

export function impactAnalysisEndpoint(
  workspaceId: string | number,
): string {
  return `/api/workspaces/${encodeURIComponent(
    String(workspaceId),
  )}/dependencies/impact-analysis`;
}

// --------------------------------------------------------------------------
// Domain types — mirror OpenAPI components/schemas (TaskNode / DAGEdge).
// --------------------------------------------------------------------------

/** A single node of the task DAG (one task). */
export interface TaskDagNode {
  id: string;
  title?: string;
  status?: string;
  wave?: number | null;
  phase?: string | null;
  feature_id?: string | null;
  [extra: string]: unknown;
}

/** A single edge of the task DAG (task → task). */
export interface TaskDagEdge {
  from_task_id: string;
  to_task_id: string;
  /** "blocks" | "informs" | "soft" (OpenAPI enum, optional). */
  type?: "blocks" | "informs" | "soft" | string | null;
  [extra: string]: unknown;
}

export interface TaskDagResponse {
  nodes: TaskDagNode[];
  edges: TaskDagEdge[];
}

/** Tasks grouped by feature (AC-F3 — accordion-friendly metadata). */
export interface TasksByFeatureGroup {
  feature_id: string;
  feature_title?: string | null;
  tasks: TaskDagNode[];
  /** Count for accordion badge ("3 / 12" shape). */
  done_count?: number | null;
  total_count?: number | null;
}

export interface TasksByFeatureResponse {
  groups: TasksByFeatureGroup[];
}

export interface DependencyCreatePayload {
  from_task_id: string;
  to_task_id: string;
  /** "blocks" | "informs" | "soft" (OpenAPI enum). */
  type?: "blocks" | "informs" | "soft" | null;
}

export interface DependencyCreateResponse {
  dependency_id?: string;
  [extra: string]: unknown;
}

export interface ImpactAnalysisPayload {
  /** Task whose change should be propagated through the DAG. */
  changed_task_id: string;
}

export interface ImpactAnalysisAffectedTask {
  id: string;
  title?: string | null;
  status?: string | null;
}

export interface ImpactAnalysisResponse {
  affected_tasks: ImpactAnalysisAffectedTask[];
  blast_radius: number;
  [extra: string]: unknown;
}

// --------------------------------------------------------------------------
// Error class
// --------------------------------------------------------------------------

const USER_MESSAGES: Record<number | "default", string> = {
  0: "ネットワークに接続できませんでした",
  400: "リクエストが不正です",
  401: "サインインが必要です",
  403: "この操作を実行する権限がありません",
  404: "対象のタスク DAG が見つかりませんでした",
  409: "依存関係に循環が検出されました",
  422: "入力フォーマットが正しくありません",
  429: "リクエストが多すぎます。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "通信に失敗しました",
};

/** Thrown for any non-2xx response from the task-DAG endpoints. */
export class TaskDagApiError extends Error {
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
    this.name = "TaskDagApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * AC-F1 (S-029): non-technical, user-facing message referencing the failing
   * endpoint. Never embed server stack traces / file paths / SQL.
   */
  toUserMessage(): string {
    const friendly = USER_MESSAGES[this.status] ?? USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

// --------------------------------------------------------------------------
// Internal helpers
// --------------------------------------------------------------------------

export interface TaskDagClientOptions {
  apiBase?: string;
  signal?: AbortSignal;
  authToken?: string | null;
  /** Test seam — overrides global fetch. */
  fetchImpl?: typeof fetch;
}

function resolveApiBase(opts: TaskDagClientOptions): string {
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
): Promise<TaskDagApiError> {
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
    // leaking server stack traces (AC-F1 non-technical).
  }
  return new TaskDagApiError(code, message, response.status, endpoint);
}

async function request<T>(
  method: "GET" | "POST",
  endpoint: string,
  body: unknown,
  opts: TaskDagClientOptions,
): Promise<T> {
  const base = resolveApiBase(opts);
  const url = `${base}${endpoint}`;
  const fetchImpl = opts.fetchImpl ?? fetch;

  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (opts.authToken) headers.Authorization = `Bearer ${opts.authToken}`;

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as { name?: string }).name === "AbortError") throw err;
    throw new TaskDagApiError(
      "task_dag.network_error",
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
// Typed API surface (S-029 AC-F1 / AC-F3 / AC-F4 + impact-analysis)
// --------------------------------------------------------------------------

/** AC-F1 (S-029): GET /api/workspaces/{id}/tasks/dag. */
export function getTaskDag(
  workspaceId: string | number,
  opts: TaskDagClientOptions = {},
): Promise<TaskDagResponse> {
  return request<TaskDagResponse>(
    "GET",
    taskDagEndpoint(workspaceId),
    undefined,
    opts,
  );
}

/** AC-F3 (S-029): GET /api/workspaces/{id}/tasks?group_by=feature. */
export function getTasksByFeature(
  workspaceId: string | number,
  opts: TaskDagClientOptions = {},
): Promise<TasksByFeatureResponse> {
  return request<TasksByFeatureResponse>(
    "GET",
    tasksByFeatureEndpoint(workspaceId),
    undefined,
    opts,
  );
}

/** AC-F4 (S-029): POST /api/workspaces/{id}/dependencies. */
export function createTaskDependency(
  workspaceId: string | number,
  body: DependencyCreatePayload,
  opts: TaskDagClientOptions = {},
): Promise<DependencyCreateResponse> {
  return request<DependencyCreateResponse>(
    "POST",
    dependencyCreateEndpoint(workspaceId),
    body,
    opts,
  );
}

/** Impact analysis: POST /api/workspaces/{id}/dependencies/impact-analysis. */
export function runImpactAnalysis(
  workspaceId: string | number,
  body: ImpactAnalysisPayload,
  opts: TaskDagClientOptions = {},
): Promise<ImpactAnalysisResponse> {
  return request<ImpactAnalysisResponse>(
    "POST",
    impactAnalysisEndpoint(workspaceId),
    body,
    opts,
  );
}
