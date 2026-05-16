/**
 * T-V3-C-12 / F-003: Typed client for the AI employees router endpoints backing
 * the S-036 (AI 社員 組織図) screen and adjacent S-037 / S-038 screens.
 *
 * Backend contracts (REUSE — implemented by T-V3-B-04 / T-V3-B-AI-01):
 *   GET    /api/ai-employees/org-chart                — backend/routers/ai_employees.py
 *   POST   /api/ai-employees                          — backend/routers/ai_employees.py
 *   POST   /api/ai-employees/{id}/clone-from-user     — backend/routers/ai_employees.py
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml (F-003 group)
 *
 * The typed client emits the failing endpoint inside `AiEmployeesApiError` so
 * the UI toast can satisfy AC-F4 (no stack-trace leak, endpoint-referenced).
 */

export const AI_EMPLOYEES_ORG_CHART_ENDPOINT = "/api/ai-employees/org-chart";
export const AI_EMPLOYEES_CREATE_ENDPOINT = "/api/ai-employees";
export const AI_EMPLOYEES_CLONE_FROM_USER_ENDPOINT = (id: string | number) =>
  `/api/ai-employees/${encodeURIComponent(String(id))}/clone-from-user`;

// --------------------------------------------------------------------------
// Types — match the OpenAPI components/schemas/AIEmployee + AIEmployeeNode.
// --------------------------------------------------------------------------

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

// --------------------------------------------------------------------------
// Error class
// --------------------------------------------------------------------------

const USER_MESSAGES: Record<number | "default", string> = {
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
   * AC-F4 (S-036 UNWANTED): produce a non-technical, user-facing message that
   * references the failing endpoint without leaking server stack traces.
   */
  toUserMessage(): string {
    const friendly = USER_MESSAGES[this.status] ?? USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------

interface ClientOptions {
  apiBase?: string;
  signal?: AbortSignal;
  authToken?: string | null;
}

function resolveApiBase(opts: ClientOptions): string {
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
): Promise<AiEmployeesApiError> {
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
    // embed the raw body to avoid leaking server stack traces (AC-F4).
  }
  return new AiEmployeesApiError(code, message, response.status, endpoint);
}

async function request<T>(
  method: "GET" | "POST",
  endpoint: string,
  body: unknown,
  opts: ClientOptions,
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
    throw new AiEmployeesApiError(
      "ai_employees.network_error",
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
// Typed API surface (S-036 AC-F1 / AC-F2 / AC-F3)
// --------------------------------------------------------------------------

/** AC-F1 (S-036): GET /api/ai-employees/org-chart via the typed client. */
export function getAiEmployeesOrgChart(
  opts: ClientOptions = {},
): Promise<AiEmployeesOrgChartResponse> {
  return request<AiEmployeesOrgChartResponse>(
    "GET",
    AI_EMPLOYEES_ORG_CHART_ENDPOINT,
    undefined,
    opts,
  );
}

/** AC-F2 (S-036): POST /api/ai-employees via the typed client. */
export function createAiEmployee(
  body: AiEmployeeCreatePayload,
  opts: ClientOptions = {},
): Promise<AiEmployeeCreateResponse> {
  return request<AiEmployeeCreateResponse>(
    "POST",
    AI_EMPLOYEES_CREATE_ENDPOINT,
    body,
    opts,
  );
}

/** AC-F3 (S-036): POST /api/ai-employees/{id}/clone-from-user via the typed client. */
export function cloneAiEmployeeFromUser(
  employeeId: string | number,
  body: AiEmployeeCloneFromUserPayload,
  opts: ClientOptions = {},
): Promise<AiEmployeeCloneFromUserResponse> {
  return request<AiEmployeeCloneFromUserResponse>(
    "POST",
    AI_EMPLOYEES_CLONE_FROM_USER_ENDPOINT(employeeId),
    body,
    opts,
  );
}
