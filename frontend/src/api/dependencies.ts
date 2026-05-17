/**
 * T-V3-C-38 / F-009: Typed client for the workspace dependency-graph endpoints
 * backing the S-017 依存グラフ (DAG) screen.
 *
 * Backend contracts (REUSE — implemented by T-V3-B-009 / T-V3-B-14):
 *   GET    /api/workspaces/{id}/dependencies                  — backend/routers/workspaces.py
 *   POST   /api/workspaces/{id}/dependencies                  — backend/routers/workspaces.py
 *   POST   /api/workspaces/{id}/dependencies/impact-analysis  — backend/routers/workspaces.py
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml#/paths/~1api~1workspaces~1{id}~1dependencies
 *
 * Errors follow the project-wide `{detail: {code, message}}` contract used by
 * the FastAPI backend. {@link DependenciesApiError} surfaces a non-technical
 * message (with the failing endpoint tagged) for UI toasts, never leaking
 * server stack traces (AC-F1 / AC-F4 on S-017 — non-technical message).
 *
 * Auth-redirect awareness (AC-F2 UNWANTED on S-017): the page layer is
 * responsible for redirecting unauthenticated visitors to /login (S-001). The
 * client surfaces 401 with `status === 401` so the page can detect and route.
 */

// --------------------------------------------------------------------------
// Endpoint constants
// --------------------------------------------------------------------------

export function dependenciesListEndpoint(workspaceId: string | number): string {
  return `/api/workspaces/${encodeURIComponent(String(workspaceId))}/dependencies`;
}

export function dependenciesCreateEndpoint(
  workspaceId: string | number,
): string {
  return `/api/workspaces/${encodeURIComponent(String(workspaceId))}/dependencies`;
}

export function dependenciesImpactAnalysisEndpoint(
  workspaceId: string | number,
): string {
  return `/api/workspaces/${encodeURIComponent(
    String(workspaceId),
  )}/dependencies/impact-analysis`;
}

// --------------------------------------------------------------------------
// Domain types — mirror OpenAPI components/schemas (TaskDependency, Task).
// --------------------------------------------------------------------------

/** A single edge of the dependency DAG. */
export interface TaskDependency {
  id: string;
  from_task_id: string;
  to_task_id: string;
  /** "hard" (blocking) or "soft" (informational). Optional — server default = "hard". */
  kind?: "hard" | "soft" | string | null;
  /** Optional metadata propagated to UI tooltips. */
  status?: string | null;
  created_at?: string | null;
  [extra: string]: unknown;
}

/** Minimal Task projection used by the right-rail / node tooltips. */
export interface DependencyTaskNode {
  id: string;
  title: string;
  status: string;
  phase?: string | null;
  feature_id?: string | null;
  assignee?: string | null;
  [extra: string]: unknown;
}

export interface DependenciesListResponse {
  dependencies: TaskDependency[];
  /** Optional task projection: backend may include tasks for node rendering. */
  tasks?: DependencyTaskNode[] | null;
}

export interface DependencyCreatePayload {
  from_task_id: string;
  to_task_id: string;
  kind?: "hard" | "soft" | null;
}

export interface DependencyCreateResponse {
  dependency_id: string;
  [extra: string]: unknown;
}

export interface DependencyImpactAnalysisPayload {
  /** Task whose change should be propagated through the DAG. */
  changed_task_id: string;
}

export interface DependencyImpactAnalysisResponse {
  affected_tasks: DependencyTaskNode[];
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
  404: "対象の依存関係が見つかりませんでした",
  409: "依存関係に循環が検出されました",
  422: "入力フォーマットが正しくありません",
  429: "リクエストが多すぎます。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "通信に失敗しました",
};

/** Thrown for any non-2xx response from the dependencies endpoints. */
export class DependenciesApiError extends Error {
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
    this.name = "DependenciesApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * AC-F1 (S-017): produce a non-technical, user-facing message that references
   * the failing endpoint without leaking server stack traces (no traceback /
   * file paths / SQL ever embedded in the surfaced string).
   */
  toUserMessage(): string {
    const friendly = USER_MESSAGES[this.status] ?? USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

// --------------------------------------------------------------------------
// Internal helpers
// --------------------------------------------------------------------------

export interface DependenciesClientOptions {
  apiBase?: string;
  signal?: AbortSignal;
  authToken?: string | null;
  /** Test seam — overrides global fetch. */
  fetchImpl?: typeof fetch;
}

function resolveApiBase(opts: DependenciesClientOptions): string {
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
): Promise<DependenciesApiError> {
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
  return new DependenciesApiError(code, message, response.status, endpoint);
}

async function request<T>(
  method: "GET" | "POST",
  endpoint: string,
  body: unknown,
  opts: DependenciesClientOptions,
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
    throw new DependenciesApiError(
      "dependencies.network_error",
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
// Typed API surface (S-017 AC-F1 / AC-F3 + impact-analysis)
// --------------------------------------------------------------------------

/** AC-F1 (S-017): GET /api/workspaces/{id}/dependencies. */
export function getDependencies(
  workspaceId: string | number,
  opts: DependenciesClientOptions = {},
): Promise<DependenciesListResponse> {
  return request<DependenciesListResponse>(
    "GET",
    dependenciesListEndpoint(workspaceId),
    undefined,
    opts,
  );
}

/** AC-F3 (S-017): POST /api/workspaces/{id}/dependencies. */
export function createDependency(
  workspaceId: string | number,
  body: DependencyCreatePayload,
  opts: DependenciesClientOptions = {},
): Promise<DependencyCreateResponse> {
  return request<DependencyCreateResponse>(
    "POST",
    dependenciesCreateEndpoint(workspaceId),
    body,
    opts,
  );
}

/** Impact analysis: POST /api/workspaces/{id}/dependencies/impact-analysis. */
export function runImpactAnalysis(
  workspaceId: string | number,
  body: DependencyImpactAnalysisPayload,
  opts: DependenciesClientOptions = {},
): Promise<DependencyImpactAnalysisResponse> {
  return request<DependencyImpactAnalysisResponse>(
    "POST",
    dependenciesImpactAnalysisEndpoint(workspaceId),
    body,
    opts,
  );
}
