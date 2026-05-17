/**
 * T-V3-C-12 / C-13 — Typed client for the ai_employees router endpoints.
 *
 * Consolidated module backing the S-036 (組織図) and S-037 (詳細) screens.
 * (Phase 1.0-fix Wave 0 D: reconciles two concurrent vertical-slice merges
 * that previously left the file with stacked duplicate declarations and a
 * missing comment opener that broke `next build` type-check.)
 *
 * Backend contracts:
 *   GET    /api/ai-employees/org-chart              — S-036 tree view.
 *   POST   /api/ai-employees                        — S-036 create persona.
 *   POST   /api/ai-employees/{id}/clone-from-user   — S-036 / S-037 clone.
 *   GET    /api/ai-employees/{id}                   — S-037 detail.
 *   PUT    /api/ai-employees/{id}                   — S-037 update.
 *   POST   /api/ai-employees/{id}/test              — S-037 test (rate-limited).
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml (F-003 group)
 *
 * Errors follow the project-wide {detail: {code, message}} contract used by
 * the FastAPI backend. `AiEmployeesApiError` surfaces a non-technical message
 * tagged with the failing endpoint and never leaks server stack traces
 * (AC-F4 on S-036/S-037). Back-compat alias `AIEmployeeApiError` is exported
 * for S-037 importers.
 */

// ---------------------------------------------------------------------------
// Endpoint constants.
// ---------------------------------------------------------------------------

export const AI_EMPLOYEES_ORG_CHART_ENDPOINT = "/api/ai-employees/org-chart";
export const AI_EMPLOYEES_CREATE_ENDPOINT = "/api/ai-employees";
export const AI_EMPLOYEES_CLONE_FROM_USER_ENDPOINT = (
  id: string | number,
): string => `/api/ai-employees/${encodeURIComponent(String(id))}/clone-from-user`;

export function aiEmployeeGetEndpoint(id: string): string {
  return `/api/ai-employees/${encodeURIComponent(id)}`;
}

export function aiEmployeeUpdateEndpoint(id: string): string {
  return `/api/ai-employees/${encodeURIComponent(id)}`;
}

export function aiEmployeeTestEndpoint(id: string): string {
  return `/api/ai-employees/${encodeURIComponent(id)}/test`;
}

export function aiEmployeeCloneFromUserEndpoint(id: string): string {
  return `/api/ai-employees/${encodeURIComponent(id)}/clone-from-user`;
}

// ---------------------------------------------------------------------------
// Domain types — S-036 (org chart) + S-037 (detail).
// ---------------------------------------------------------------------------

/** A single tree node returned by GET /api/ai-employees/org-chart. */
export interface AiEmployeeNode {
  id: string;
  name: string;
  persona: string;
  hierarchy_level: number;
  parent_id?: string | null;
  department?: string | null;
  /** Recursively-nested direct reports. */
  children?: AiEmployeeNode[];
  /** Server may include extra metadata (avatar, role label, etc.). */
  [extra: string]: unknown;
}

export interface AiEmployeesOrgChartResponse {
  tree: AiEmployeeNode[];
  total: number;
}

/** Payload for POST /api/ai-employees (persona definition). */
export interface AiEmployeeCreatePayload {
  name: string;
  persona: string;
  /** Backend enforces 1..3 (BMAD + leader + member). */
  hierarchy_level: number;
  parent_id?: string | null;
  department: string;
}

export interface AiEmployeeCreateResponse {
  id: string;
  name: string;
  [extra: string]: unknown;
}

/** Payload for POST /api/ai-employees/{id}/clone-from-user. */
export interface AiEmployeeCloneFromUserPayload {
  /** User id of the source. Backend verifies opt-in flag → 403 otherwise. */
  source_user_id: string;
}

export interface AiEmployeeCloneFromUserResponse {
  id: string;
  source_user_id: string;
  [extra: string]: unknown;
}

// --- S-037 detail surface -------------------------------------------------

export interface AIEmployeeSkill {
  id: string;
  name: string;
  category?: string | null;
}

export interface AIEmployeeExecution {
  session_id: string;
  task_id?: string | null;
  status: "running" | "done" | "failed" | string;
  cost_jpy?: number | null;
  ran_at?: string | null;
}

export interface AIEmployee {
  id: string;
  name: string;
  role: string;
  department?: string | null;
  parent_employee?: string | null;
  /** "active" | "inactive" — kept open-ended so unknown server states render. */
  status: string;
  persona?: string | null;
  system_prompt?: string | null;
  model?: string | null;
  /** When the AI 社員 was cloned from a user — null for canonical BMAD personas. */
  cloned_from_user_id?: string | null;
  /** Aggregate cost summary surfaced on the S-037 right rail. */
  cost_summary?: {
    monthly_total_jpy?: number | null;
    tasks_done?: number | null;
    avg_per_task_jpy?: number | null;
    tokens_used?: number | null;
    cache_hit_rate?: number | null;
  } | null;
  /** Latest execution history (server caps at small N). */
  execution_history?: AIEmployeeExecution[] | null;
}

export interface AIEmployeeDetailResponse {
  employee: AIEmployee;
  skills: AIEmployeeSkill[];
}

export interface AIEmployeeUpdateRequest {
  name?: string | null;
  skill_ids?: string[] | null;
  constitution_version?: number | null;
}

export interface AIEmployeeUpdateResponse {
  id: string;
  updated_at: string;
}

export interface AIEmployeeTestRequest {
  input_prompt: string;
}

export interface AIEmployeeTestResponse {
  output: string;
  tokens_used: number;
  cost_usd: number;
}

export interface AIEmployeeCloneRequest {
  user_id: string;
  opt_in_acknowledged: boolean;
}

export interface AIEmployeeCloneResponse {
  clone_id: string;
  namespace: string;
}

// ---------------------------------------------------------------------------
// Error envelope + class.
// ---------------------------------------------------------------------------

interface BackendErrorEnvelope {
  detail?:
    | { code?: string; message?: string; errors?: unknown }
    | string;
}

const USER_MESSAGES: Record<number | "default", string> = {
  0: "ネットワークに接続できませんでした",
  400: "リクエストが不正です",
  401: "サインインが必要です",
  403: "この操作を実行する権限がありません",
  404: "AI 社員が見つかりませんでした",
  409: "親子関係が循環しています",
  422: "入力内容を確認してください",
  429: "リクエストが多すぎます。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "通信に失敗しました",
};

/** Thrown for any non-2xx response from the ai-employees endpoints. */
export class AiEmployeesApiError extends Error {
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
    this.name = "AiEmployeesApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * AC-F4 (S-036 / S-037 UNWANTED): produce a non-technical, user-facing
   * message that references the failing endpoint without leaking server
   * stack traces.
   */
  toUserMessage(): string {
    const friendly = USER_MESSAGES[this.status] ?? USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

/** Back-compat alias for S-037 callers that imported the old class name. */
export const AIEmployeeApiError = AiEmployeesApiError;
export type AIEmployeeApiError = AiEmployeesApiError;

// ---------------------------------------------------------------------------
// Helpers.
// ---------------------------------------------------------------------------

export interface AIEmployeeRequestOptions {
  apiBase?: string;
  signal?: AbortSignal;
  /** Bearer token (workspace_admin scope is enforced server-side). */
  authToken?: string | null;
  /** Test seam — overrides global fetch. */
  fetchImpl?: typeof fetch;
}

function resolveApiBase(opts: AIEmployeeRequestOptions): string {
  if (opts.apiBase) return opts.apiBase;
  if (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  if (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_BASE) {
    return process.env.NEXT_PUBLIC_API_BASE;
  }
  return "http://localhost:8001";
}

async function parseError(
  response: Response,
  endpoint: string,
): Promise<AiEmployeesApiError> {
  let code = "UNKNOWN";
  let message = response.statusText || "request failed";
  try {
    const payload = (await response.json()) as BackendErrorEnvelope;
    if (payload && typeof payload.detail === "object" && payload.detail) {
      if (typeof payload.detail.code === "string") code = payload.detail.code;
      if (typeof payload.detail.message === "string") {
        message = payload.detail.message;
      }
    } else if (typeof payload?.detail === "string") {
      message = payload.detail;
    }
  } catch {
    // Non-JSON body — keep the synthesised message. AC-F4: never embed raw body.
  }
  return new AiEmployeesApiError(code, message, response.status, endpoint);
}

async function request<TOut>(
  endpoint: string,
  init: RequestInit,
  opts: AIEmployeeRequestOptions,
): Promise<TOut> {
  const base = resolveApiBase(opts);
  const fetchImpl = opts.fetchImpl ?? fetch;
  const url = endpoint.startsWith("http") ? endpoint : `${base}${endpoint}`;

  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  if (init.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  if (opts.authToken) {
    headers.Authorization = `Bearer ${opts.authToken}`;
  }

  let response: Response;
  try {
    response = await fetchImpl(url, {
      ...init,
      headers,
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as { name?: string }).name === "AbortError") throw err;
    throw new AiEmployeesApiError(
      "NETWORK_ERROR",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseError(response, endpoint);
  }
  if (response.status === 204) return undefined as unknown as TOut;
  try {
    return (await response.json()) as TOut;
  } catch {
    return undefined as unknown as TOut;
  }
}

// ---------------------------------------------------------------------------
// S-036 endpoint functions.
// ---------------------------------------------------------------------------

/** AC-F1 (S-036): GET /api/ai-employees/org-chart via the typed client. */
export function getAiEmployeesOrgChart(
  opts: AIEmployeeRequestOptions = {},
): Promise<AiEmployeesOrgChartResponse> {
  return request<AiEmployeesOrgChartResponse>(
    AI_EMPLOYEES_ORG_CHART_ENDPOINT,
    { method: "GET" },
    opts,
  );
}

/** AC-F2 (S-036): POST /api/ai-employees via the typed client. */
export function createAiEmployee(
  body: AiEmployeeCreatePayload,
  opts: AIEmployeeRequestOptions = {},
): Promise<AiEmployeeCreateResponse> {
  return request<AiEmployeeCreateResponse>(
    AI_EMPLOYEES_CREATE_ENDPOINT,
    { method: "POST", body: JSON.stringify(body) },
    opts,
  );
}

/** AC-F3 (S-036): POST /api/ai-employees/{id}/clone-from-user. */
export function cloneAiEmployeeFromUser(
  employeeId: string | number,
  body: AiEmployeeCloneFromUserPayload,
  opts: AIEmployeeRequestOptions = {},
): Promise<AiEmployeeCloneFromUserResponse> {
  return request<AiEmployeeCloneFromUserResponse>(
    AI_EMPLOYEES_CLONE_FROM_USER_ENDPOINT(employeeId),
    { method: "POST", body: JSON.stringify(body) },
    opts,
  );
}

// ---------------------------------------------------------------------------
// S-037 endpoint functions.
// ---------------------------------------------------------------------------

/** AC-F1 (S-037): GET /api/ai-employees/{id} via the typed client. */
export function getAIEmployee(
  id: string,
  opts: AIEmployeeRequestOptions = {},
): Promise<AIEmployeeDetailResponse> {
  return request<AIEmployeeDetailResponse>(
    aiEmployeeGetEndpoint(id),
    { method: "GET" },
    opts,
  );
}

/** AC-F2 (S-037): PUT /api/ai-employees/{id} via the typed client. */
export function updateAIEmployee(
  id: string,
  body: AIEmployeeUpdateRequest,
  opts: AIEmployeeRequestOptions = {},
): Promise<AIEmployeeUpdateResponse> {
  return request<AIEmployeeUpdateResponse>(
    aiEmployeeUpdateEndpoint(id),
    { method: "PUT", body: JSON.stringify(body) },
    opts,
  );
}

/**
 * AC-F3 + AC-F6 (S-037): POST /api/ai-employees/{id}/test via the typed client.
 *
 * Server-side rate limit is 20/min/workspace. The client preserves the 429
 * status so the UI can render a polite, non-technical wait message.
 */
export function testAIEmployee(
  id: string,
  body: AIEmployeeTestRequest,
  opts: AIEmployeeRequestOptions = {},
): Promise<AIEmployeeTestResponse> {
  return request<AIEmployeeTestResponse>(
    aiEmployeeTestEndpoint(id),
    { method: "POST", body: JSON.stringify(body) },
    opts,
  );
}

/**
 * AC-F5 (S-037): POST /api/ai-employees/{id}/clone-from-user via the typed
 * client. When the source user has clone opt-in FALSE the backend returns
 * 403; the thrown AiEmployeesApiError carries the original status so the
 * caller can render a non-technical permission message without leaking
 * server traces.
 */
export function cloneAIEmployeeFromUser(
  id: string,
  body: AIEmployeeCloneRequest,
  opts: AIEmployeeRequestOptions = {},
): Promise<AIEmployeeCloneResponse> {
  return request<AIEmployeeCloneResponse>(
    aiEmployeeCloneFromUserEndpoint(id),
    { method: "POST", body: JSON.stringify(body) },
    opts,
  );
}
