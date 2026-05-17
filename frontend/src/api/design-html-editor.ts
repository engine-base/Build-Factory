/**
 * T-V3-C-52 / F-005b: Typed client for the workspace HTML-editor endpoints
 * backing the S-026 (HTML エディタ) screen.
 *
 * Backend contracts (T-V3-B-09 already merged for ai-edit; html GET/PUT live
 * under the same `mocks` router used by S-023 / T-V3-C-49):
 *   GET    /api/workspaces/{id}/mocks/{screen_id}/html      (member)
 *   PUT    /api/workspaces/{id}/mocks/{screen_id}/html      (workspace_admin)
 *   POST   /api/workspaces/{id}/mocks/{screen_id}/ai-edit   (member)
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml
 *   #/paths/~1api~1workspaces~1{id}~1mocks~1{screen_id}~1html
 *   #/paths/~1api~1workspaces~1{id}~1mocks~1{screen_id}~1ai-edit
 *
 * Errors follow the project-wide {detail: {code, message}} contract. The
 * thrown {@link DesignHtmlEditorApiError} surfaces a non-technical, endpoint-
 * tagged user message and never leaks server stack traces (AC-F1 on S-026 /
 * T-V3-C-52).
 *
 * Auth-redirect awareness (AC-F2 UNWANTED on S-026): the page layer is
 * responsible for redirecting unauthenticated visitors to /login (S-001). The
 * client surfaces 401 with `status === 401` so the page can detect and route.
 */

// --------------------------------------------------------------------------
// Endpoint constants — matched 逐語 against the OpenAPI paths.
// --------------------------------------------------------------------------

export function htmlEditorGetEndpoint(
  workspaceId: string | number,
  screenId: string,
): string {
  return `/api/workspaces/${encodeURIComponent(
    String(workspaceId),
  )}/mocks/${encodeURIComponent(screenId)}/html`;
}

export function htmlEditorPutEndpoint(
  workspaceId: string | number,
  screenId: string,
): string {
  // PUT shares the same path as GET; kept as a named helper to avoid mis-typed
  // string concatenation at call sites.
  return htmlEditorGetEndpoint(workspaceId, screenId);
}

export function htmlEditorAiEditEndpoint(
  workspaceId: string | number,
  screenId: string,
): string {
  return `/api/workspaces/${encodeURIComponent(
    String(workspaceId),
  )}/mocks/${encodeURIComponent(screenId)}/ai-edit`;
}

// --------------------------------------------------------------------------
// Domain types — narrow to what S-026 renders. Backend may include extras.
// --------------------------------------------------------------------------

/** Response of GET /api/workspaces/{id}/mocks/{screen_id}/html (AC-F1/F3). */
export interface DesignHtmlEditorHtmlResponse {
  html: string;
  /** Backend may include version, updated_at, etc. */
  [extra: string]: unknown;
}

/** Request body of PUT /api/workspaces/{id}/mocks/{screen_id}/html. */
export interface DesignHtmlEditorSaveRequest {
  html: string;
}

/** Response of PUT /api/workspaces/{id}/mocks/{screen_id}/html. */
export interface DesignHtmlEditorSaveResponse {
  new_version?: number;
  updated_at?: string;
  [extra: string]: unknown;
}

/** Request body of POST /api/workspaces/{id}/mocks/{screen_id}/ai-edit. */
export interface DesignHtmlEditorAiEditRequest {
  prompt: string;
}

/** Response of POST /api/workspaces/{id}/mocks/{screen_id}/ai-edit. */
export interface DesignHtmlEditorAiEditResponse {
  diff?: string;
  new_html?: string;
  tokens_used?: number;
  [extra: string]: unknown;
}

// --------------------------------------------------------------------------
// Error class — uniform with @/api/mocks + @/api/screen-flow.
// --------------------------------------------------------------------------

const USER_MESSAGES: Record<number | "default", string> = {
  0: "ネットワークに接続できませんでした",
  400: "リクエストが不正です",
  401: "サインインが必要です",
  403: "このモックを編集する権限がありません",
  404: "対象のモックが見つかりませんでした",
  409: "モックの状態が競合しました",
  422: "入力フォーマットが正しくありません",
  429: "リクエストが多すぎます。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "通信に失敗しました",
};

interface BackendErrorEnvelope {
  detail?: { code?: string; message?: string } | string;
}

/** Thrown for any non-2xx response from the HTML-editor endpoints. */
export class DesignHtmlEditorApiError extends Error {
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
    this.name = "DesignHtmlEditorApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * AC-F1 (S-026): produce a non-technical user-facing message that
   * references the failing endpoint without leaking server stack traces.
   */
  toUserMessage(): string {
    const friendly = USER_MESSAGES[this.status] ?? USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

// --------------------------------------------------------------------------
// Internal helpers
// --------------------------------------------------------------------------

export interface DesignHtmlEditorClientOptions {
  apiBase?: string;
  signal?: AbortSignal;
  /** Bearer token (Authorization: Bearer ...) for authenticated callers. */
  authToken?: string | null;
  /** Test seam — overrides global fetch. */
  fetchImpl?: typeof fetch;
}

function resolveApiBase(opts: DesignHtmlEditorClientOptions): string {
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
): Promise<DesignHtmlEditorApiError> {
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
    // Non-JSON body — keep generic fallback. Never embed raw body (AC-F1).
  }
  return new DesignHtmlEditorApiError(code, message, response.status, endpoint);
}

interface InternalRequestInit {
  method: "GET" | "PUT" | "POST";
  body?: unknown;
}

async function request<T>(
  endpoint: string,
  init: InternalRequestInit,
  opts: DesignHtmlEditorClientOptions,
): Promise<T> {
  const base = resolveApiBase(opts).replace(/\/$/, "");
  const url = `${base}${endpoint}`;
  const fetchImpl = opts.fetchImpl ?? fetch;

  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  if (opts.authToken) headers.Authorization = `Bearer ${opts.authToken}`;

  let bodyText: string | undefined;
  if (init.body !== undefined) {
    headers["Content-Type"] = "application/json";
    bodyText = JSON.stringify(init.body);
  }

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: init.method,
      headers,
      body: bodyText,
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as { name?: string }).name === "AbortError") throw err;
    throw new DesignHtmlEditorApiError(
      "design_html_editor.network_error",
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
 * AC-F1 / AC-F3 (S-026): GET /api/workspaces/{id}/mocks/{screen_id}/html.
 * Returns the latest version of the mock HTML for the given screen.
 */
export function getDesignHtml(
  workspaceId: string | number,
  screenId: string,
  opts: DesignHtmlEditorClientOptions = {},
): Promise<DesignHtmlEditorHtmlResponse> {
  return request<DesignHtmlEditorHtmlResponse>(
    htmlEditorGetEndpoint(workspaceId, screenId),
    { method: "GET" },
    opts,
  );
}

/**
 * PUT /api/workspaces/{id}/mocks/{screen_id}/html — saves a new version of
 * the mock HTML. Role: workspace_admin (server enforces). Used by the page's
 * "新バージョン保存" action.
 */
export function saveDesignHtml(
  workspaceId: string | number,
  screenId: string,
  payload: DesignHtmlEditorSaveRequest,
  opts: DesignHtmlEditorClientOptions = {},
): Promise<DesignHtmlEditorSaveResponse> {
  return request<DesignHtmlEditorSaveResponse>(
    htmlEditorPutEndpoint(workspaceId, screenId),
    { method: "PUT", body: payload },
    opts,
  );
}

/**
 * POST /api/workspaces/{id}/mocks/{screen_id}/ai-edit — sends a natural-
 * language prompt to the AI designer. Backend returns the diff and the
 * resulting HTML (T-V3-B-09 contract).
 */
export function aiEditDesignHtml(
  workspaceId: string | number,
  screenId: string,
  payload: DesignHtmlEditorAiEditRequest,
  opts: DesignHtmlEditorClientOptions = {},
): Promise<DesignHtmlEditorAiEditResponse> {
  return request<DesignHtmlEditorAiEditResponse>(
    htmlEditorAiEditEndpoint(workspaceId, screenId),
    { method: "POST", body: payload },
    opts,
  );
}
