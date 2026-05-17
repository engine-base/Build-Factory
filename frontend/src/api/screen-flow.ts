/**
 * T-V3-C-51 / F-005b: Typed client for the workspace screen-flow endpoint
 * backing the S-025 画面遷移マップ screen.
 *
 * Backend contracts (T-V3-B-09 / merged via earlier wave):
 *   GET /api/workspaces/{id}/screen-flow                — backend/routers/screen_flow.py
 *   GET /api/workspaces/{id}/mocks/{screen_id}/html     — backend/routers/screens.py
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml#/paths/~1api~1workspaces~1{id}~1screen-flow
 *
 * Errors follow the project-wide `{detail: {code, message}}` contract. The
 * thrown {@link ScreenFlowApiError} surfaces a non-technical, endpoint-tagged
 * message for UI toasts and never leaks server stack traces (AC-F1 on S-025).
 *
 * Auth-redirect awareness (AC-F2 UNWANTED on S-025): the page layer is
 * responsible for redirecting unauthenticated visitors to /login (S-001). The
 * client surfaces 401 with `status === 401` so the page can detect and route.
 */

// --------------------------------------------------------------------------
// Endpoint constants
// --------------------------------------------------------------------------

export function screenFlowEndpoint(workspaceId: string | number): string {
  return `/api/workspaces/${encodeURIComponent(String(workspaceId))}/screen-flow`;
}

export function mockHtmlEndpoint(
  workspaceId: string | number,
  screenId: string,
): string {
  return `/api/workspaces/${encodeURIComponent(
    String(workspaceId),
  )}/mocks/${encodeURIComponent(screenId)}/html`;
}

// --------------------------------------------------------------------------
// Domain types — mirror OpenAPI components/schemas (ScreenFlowNode / ScreenFlowEdge).
// --------------------------------------------------------------------------

/** One node of the screen-flow graph (one screen). */
export interface ScreenFlowNode {
  screen_id: string;
  name?: string;
  kind?: string;
  [extra: string]: unknown;
}

/** One edge of the screen-flow graph (S → S transition). */
export interface ScreenFlowEdge {
  from_screen_id: string;
  to_screen_id: string;
  trigger?: string;
  [extra: string]: unknown;
}

export interface ScreenFlowResponse {
  nodes: ScreenFlowNode[];
  edges: ScreenFlowEdge[];
}

export interface MockHtmlResponse {
  html: string;
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
  404: "対象の画面遷移マップが見つかりませんでした",
  422: "入力フォーマットが正しくありません",
  429: "リクエストが多すぎます。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "通信に失敗しました",
};

/** Thrown for any non-2xx response from the screen-flow endpoints. */
export class ScreenFlowApiError extends Error {
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
    this.name = "ScreenFlowApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * AC-F1 (S-025): produce a non-technical, user-facing message that
   * references the failing endpoint without leaking server stack traces
   * (no traceback / file paths / SQL ever embedded in the surfaced string).
   */
  toUserMessage(): string {
    const friendly = USER_MESSAGES[this.status] ?? USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

// --------------------------------------------------------------------------
// Internal helpers
// --------------------------------------------------------------------------

export interface ScreenFlowClientOptions {
  apiBase?: string;
  signal?: AbortSignal;
  authToken?: string | null;
  /** Test seam — overrides global fetch. */
  fetchImpl?: typeof fetch;
}

function resolveApiBase(opts: ScreenFlowClientOptions): string {
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
): Promise<ScreenFlowApiError> {
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
  return new ScreenFlowApiError(code, message, response.status, endpoint);
}

async function request<T>(
  method: "GET",
  endpoint: string,
  opts: ScreenFlowClientOptions,
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
    throw new ScreenFlowApiError(
      "screen_flow.network_error",
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
// Typed API surface (S-025 AC-F1 GET screen-flow / AC-F3 GET mock html)
// --------------------------------------------------------------------------

/** AC-F1 (S-025): GET /api/workspaces/{id}/screen-flow. */
export function getScreenFlow(
  workspaceId: string | number,
  opts: ScreenFlowClientOptions = {},
): Promise<ScreenFlowResponse> {
  return request<ScreenFlowResponse>(
    "GET",
    screenFlowEndpoint(workspaceId),
    opts,
  );
}

/** AC-F3 (S-025): GET /api/workspaces/{id}/mocks/{screen_id}/html. */
export function getMockHtml(
  workspaceId: string | number,
  screenId: string,
  opts: ScreenFlowClientOptions = {},
): Promise<MockHtmlResponse> {
  return request<MockHtmlResponse>(
    "GET",
    mockHtmlEndpoint(workspaceId, screenId),
    opts,
  );
}
