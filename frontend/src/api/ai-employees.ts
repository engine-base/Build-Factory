/**
 * T-V3-C-13 / F-003: Typed client for the ai_employees router endpoints used
 * by the S-037 detail screen.
 *
 * Backend contracts:
 *   GET    /api/ai-employees/{id}              — backend/routers/ai_employees.py
 *   PUT    /api/ai-employees/{id}              — backend/routers/ai_employees.py
 *   POST   /api/ai-employees/{id}/test         — T-V3-B-AI-02 / drift fix queue
 *   POST   /api/ai-employees/{id}/clone-from-user
 *                                              — T-V3-B-04 / drift fix queue
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml#/paths/~1api~1ai-employees~1{id}
 *
 * Errors follow the project-wide {detail: {code, message}} contract used by
 * the FastAPI backend. The thrown {@link AIEmployeeApiError} surfaces a
 * non-technical message (with the failing endpoint tagged) for UI toasts,
 * never leaking server stack traces (AC-F4 on S-037).
 *
 * Rate-limit awareness (AC-F6): /test enforces 20/min/workspace server-side;
 * the client just propagates 429 → toUserMessage().
 *
 * Clone opt-in (AC-F5): when the source user has clone opt-in FALSE the
 * backend returns 403 — the client preserves that signal so the UI can show
 * a non-technical message without leaking server traces.
 */

// --------------------------------------------------------------------------
// Endpoint constants
// --------------------------------------------------------------------------

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

// --------------------------------------------------------------------------
// Domain types (kept narrow — UI only needs what S-037 renders)
// --------------------------------------------------------------------------

export interface AIEmployeeSkill {
  id: string;
  name: string;
  category?: string | null;
}

export interface AIEmployee {
  id: string;
  name: string;
  role: string;
  department?: string | null;
  parent_employee?: string | null;
  /** "active" | "inactive" — keep open-ended so unknown server states render. */
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

export interface AIEmployeeExecution {
  session_id: string;
  task_id?: string | null;
  status: "running" | "done" | "failed" | string;
  cost_jpy?: number | null;
  ran_at?: string | null;
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

// --------------------------------------------------------------------------
// Error envelope + class
// --------------------------------------------------------------------------

interface BackendErrorEnvelope {
  detail?:
    | { code?: string; message?: string; errors?: unknown }
    | string;
}

/** Thrown for any non-2xx response from the ai-employees endpoints. */
export class AIEmployeeApiError extends Error {
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
    this.name = "AIEmployeeApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * AC-F4 (S-037 UNWANTED): produce a user-facing message that references the
   * failing endpoint without leaking server stack traces. The 403 branch is
   * tuned for AC-F5 (clone opt-in FALSE) so the UI can render a clear,
   * non-technical reason for the rejection.
   */
  toUserMessage(): string {
    const friendly =
      AI_EMPLOYEE_USER_MESSAGES[this.status] ??
      AI_EMPLOYEE_USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

const AI_EMPLOYEE_USER_MESSAGES: Record<number | "default", string> = {
  0: "ネットワークに接続できませんでした",
  400: "リクエストが不正です",
  401: "サインインが必要です",
  403: "この操作を実行する権限がありません",
  404: "AI 社員が見つかりませんでした",
  409: "更新の競合が発生しました。最新を再読込してください",
  422: "入力フォーマットが正しくありません",
  429: "テスト呼び出しの上限に達しました。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "通信に失敗しました",
};

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------

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
): Promise<AIEmployeeApiError> {
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
    // leaking server stack traces (AC-F4).
  }
  return new AIEmployeeApiError(code, message, response.status, endpoint);
}

async function request<TOut>(
  endpoint: string,
  init: RequestInit,
  opts: AIEmployeeRequestOptions,
): Promise<TOut> {
  const base = resolveApiBase(opts);
  const url = `${base}${endpoint}`;
  const fetchImpl = opts.fetchImpl ?? fetch;

  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(init.body ? { "Content-Type": "application/json" } : {}),
  };
  if (opts.authToken) headers.Authorization = `Bearer ${opts.authToken}`;

  let response: Response;
  try {
    response = await fetchImpl(url, {
      ...init,
      headers: { ...headers, ...(init.headers ?? {}) },
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as { name?: string }).name === "AbortError") throw err;
    throw new AIEmployeeApiError(
      "NETWORK_ERROR",
      "network error",
      0,
      endpoint,
    );
  }
  if (!response.ok) {
    throw await parseError(response, endpoint);
  }
  return (await response.json()) as TOut;
}

// --------------------------------------------------------------------------
// Endpoint functions
// --------------------------------------------------------------------------

/**
 * AC-F1: GET /api/ai-employees/{id} via the typed client.
 */
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

/**
 * AC-F2: PUT /api/ai-employees/{id} via the typed client.
 */
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
 * AC-F3 + AC-F6: POST /api/ai-employees/{id}/test via the typed client.
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
 * AC-F5: POST /api/ai-employees/{id}/clone-from-user via the typed client.
 *
 * When the source user has clone opt-in FALSE the backend returns 403; the
 * thrown AIEmployeeApiError carries the original status so the caller can
 * render a non-technical permission message without leaking server traces.
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
