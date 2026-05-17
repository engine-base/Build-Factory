/**
 * T-V3-C-49 / F-005b: Typed client for the workspace mocks endpoints backing
 * the S-023 (画面モックビューア) screen.
 *
 * Backend contracts (T-V3-B-08 / T-V3-B-09 already merged):
 *   GET    /api/workspaces/{id}/mocks                          (member)
 *   GET    /api/workspaces/{id}/mocks/{screen_id}              (member)
 *   GET    /api/workspaces/{id}/mocks/{screen_id}/html         (member)
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml
 *   #/paths/~1api~1workspaces~1{id}~1mocks
 *   #/paths/~1api~1workspaces~1{id}~1mocks~1{screen_id}
 *   #/paths/~1api~1workspaces~1{id}~1mocks~1{screen_id}~1html
 *
 * Errors follow the project-wide {detail: {code, message}} contract used by
 * the FastAPI backend. The thrown {@link MocksApiError} surfaces a
 * non-technical message (with the failing endpoint tagged) for UI toasts,
 * never leaking server stack traces (AC-F1 on S-023 / T-V3-C-49).
 */

import { env } from "@/env";

// --------------------------------------------------------------------------
// Endpoint constants
// --------------------------------------------------------------------------

export function workspaceMocksEndpoint(workspaceId: string): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/mocks`;
}

export function workspaceMockDetailEndpoint(
  workspaceId: string,
  screenId: string,
): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/mocks/${encodeURIComponent(screenId)}`;
}

export function workspaceMockHtmlEndpoint(
  workspaceId: string,
  screenId: string,
): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/mocks/${encodeURIComponent(screenId)}/html`;
}

// --------------------------------------------------------------------------
// Types — narrow to what S-023 renders. Backend may include extra fields.
// --------------------------------------------------------------------------

/** A single mock row returned by GET /api/workspaces/{id}/mocks. */
export interface Mock {
  /** Stable screen id, e.g. "S-006". */
  screen_id: string;
  /** Human-readable screen name. */
  name?: string | null;
  /** Optional logical category (e.g. "Account", "Workspace", "Task"). */
  category?: string | null;
  /** Mock version (monotonic non-negative). */
  version?: number | null;
  updated_at?: string | null;
  /** Server may include arbitrary extras (locked, owner, etc.). */
  [extra: string]: unknown;
}

export interface GetMocksResponse {
  mocks: Mock[];
  total?: number | null;
}

export interface GetMockHtmlResponse {
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
  403: "このモックを閲覧する権限がありません",
  404: "モックが見つかりませんでした",
  409: "モックの状態が競合しました",
  422: "入力フォーマットが正しくありません",
  429: "リクエストが多すぎます。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "通信に失敗しました",
};

interface BackendErrorEnvelope {
  detail?: { code?: string; message?: string } | string;
}

/** Thrown for any non-2xx response from the mocks endpoints. */
export class MocksApiError extends Error {
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
    this.name = "MocksApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * AC-F1 (S-023 UNWANTED): produce a non-technical user-facing message that
   * references the failing endpoint without leaking server stack traces or
   * internal exception class names.
   */
  toUserMessage(): string {
    const friendly = USER_MESSAGES[this.status] ?? USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

// --------------------------------------------------------------------------
// Internal HTTP helper
// --------------------------------------------------------------------------

export interface MocksRequestOptions {
  apiBase?: string;
  signal?: AbortSignal;
  /** Bearer token (Authorization: Bearer ...) required for authenticated role. */
  authToken?: string | null;
  /** Test seam — defaults to global fetch. */
  fetchImpl?: typeof fetch;
}

function resolveApiBase(opts: MocksRequestOptions): string {
  if (opts.apiBase) return opts.apiBase;
  const fromEnv = env.NEXT_PUBLIC_API_URL;
  return (fromEnv ?? "http://localhost:8001").replace(/\/$/, "");
}

async function parseError(
  response: Response,
  endpoint: string,
): Promise<MocksApiError> {
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
    // Non-JSON body — keep the synthesised message. AC-F1: don't leak raw body.
  }
  return new MocksApiError(code, message, response.status, endpoint);
}

async function request<TOut>(
  endpoint: string,
  init: RequestInit,
  opts: MocksRequestOptions,
): Promise<TOut> {
  const base = resolveApiBase(opts);
  const fetchImpl = opts.fetchImpl ?? fetch;
  const url = `${base}${endpoint}`;

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
    throw new MocksApiError("NETWORK_ERROR", "network error", 0, endpoint);
  }

  if (!response.ok) {
    throw await parseError(response, endpoint);
  }
  if (response.status === 204) return {} as TOut;
  return (await response.json()) as TOut;
}

// --------------------------------------------------------------------------
// Public API
// --------------------------------------------------------------------------

/**
 * GET /api/workspaces/{id}/mocks — returns the workspace's available mocks.
 *
 * AC-F1 surface: 4xx/5xx is normalised into a {@link MocksApiError}.
 * Backend role: member (any workspace member may read).
 */
export function getMocks(
  workspaceId: string,
  opts: MocksRequestOptions = {},
): Promise<GetMocksResponse> {
  return request<GetMocksResponse>(
    workspaceMocksEndpoint(workspaceId),
    { method: "GET" },
    opts,
  );
}

/**
 * GET /api/workspaces/{id}/mocks/{screen_id}/html — returns the latest mock
 * HTML for a given screen (AC-F3). The returned `html` string is dropped into
 * the preview iframe via `srcdoc`.
 */
export function getMockHtml(
  workspaceId: string,
  screenId: string,
  opts: MocksRequestOptions = {},
): Promise<GetMockHtmlResponse> {
  return request<GetMockHtmlResponse>(
    workspaceMockHtmlEndpoint(workspaceId, screenId),
    { method: "GET" },
    opts,
  );
}
