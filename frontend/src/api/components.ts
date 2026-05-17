/**
 * T-V3-C-50 / F-005b: Typed client for the workspace component-catalog
 * endpoints backing the S-024 (コンポーネントカタログ) screen.
 *
 * Backend contracts (T-V3-B-09 / drift T-V3-DRIFT-F-005b-06..07):
 *   GET /api/workspaces/{id}/components                 (member)
 *   GET /api/workspaces/{id}/components/{id}/usage      (member)
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml
 *   #/paths/~1api~1workspaces~1{id}~1components
 *   #/paths/~1api~1workspaces~1{id}~1components~1{id}~1usage
 *
 * Errors follow the project-wide `{detail: {code, message}}` envelope. The
 * thrown {@link ComponentsApiError} surfaces a non-technical user message
 * (with the failing endpoint tagged) so AC-F1 on T-V3-C-50 never leaks
 * server stack traces.
 */

import { env } from "@/env";

// --------------------------------------------------------------------------
// Endpoint constants
// --------------------------------------------------------------------------

export function workspaceComponentsEndpoint(workspaceId: string): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/components`;
}

export function workspaceComponentUsageEndpoint(
  workspaceId: string,
  componentId: string,
): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/components/${encodeURIComponent(componentId)}/usage`;
}

// --------------------------------------------------------------------------
// Types — narrow to what S-024 renders. Backend may include extra fields.
// --------------------------------------------------------------------------

/** Entity E-023 Component (table components). */
export interface Component {
  id: string;
  workspace_id?: string;
  name: string;
  /** e.g. "button" / "card" / "input" — free-form. */
  type?: string | null;
  description?: string | null;
  mock_artifact_id?: string | null;
  /** Backend may include arbitrary extras (variants/uses counts/etc.). */
  [extra: string]: unknown;
}

export interface GetComponentsResponse {
  components: Component[];
}

/** Entity ComponentUsage — where a component is referenced. */
export interface ComponentUsage {
  screen_id: string;
  screen_name?: string | null;
  instance_count?: number | null;
  [extra: string]: unknown;
}

export interface GetComponentUsageResponse {
  usages: ComponentUsage[];
}

// --------------------------------------------------------------------------
// Error class
// --------------------------------------------------------------------------

const USER_MESSAGES: Record<number | "default", string> = {
  0: "ネットワークに接続できませんでした",
  400: "リクエストが不正です",
  401: "サインインが必要です",
  403: "この操作を実行する権限がありません",
  404: "対象のコンポーネントが見つかりませんでした",
  409: "コンポーネントが競合しています",
  422: "入力フォーマットが正しくありません",
  429: "リクエストが多すぎます。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "通信に失敗しました",
};

interface BackendErrorEnvelope {
  detail?: { code?: string; message?: string } | string;
}

/** Thrown for any non-2xx response from the components endpoints. */
export class ComponentsApiError extends Error {
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
    this.name = "ComponentsApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * AC-F1 (S-024 UNWANTED): produce a non-technical user-facing message that
   * tags the failing endpoint without leaking server stack traces or
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

export interface ComponentsRequestOptions {
  apiBase?: string;
  signal?: AbortSignal;
  /** Bearer token (Authorization: Bearer ...). */
  authToken?: string | null;
  /** Test seam — defaults to global fetch. */
  fetchImpl?: typeof fetch;
}

function resolveApiBase(opts: ComponentsRequestOptions): string {
  if (opts.apiBase) return opts.apiBase;
  const fromEnv = env.NEXT_PUBLIC_API_URL;
  return (fromEnv ?? "http://localhost:8001").replace(/\/$/, "");
}

async function parseError(
  response: Response,
  endpoint: string,
): Promise<ComponentsApiError> {
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
  return new ComponentsApiError(code, message, response.status, endpoint);
}

async function request<TOut>(
  endpoint: string,
  init: RequestInit,
  opts: ComponentsRequestOptions,
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
    throw new ComponentsApiError("NETWORK_ERROR", "network error", 0, endpoint);
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
 * GET /api/workspaces/{id}/components — returns the workspace's design-system
 * component catalog (E-023 rows).
 *
 * AC-F1 surface: 4xx/5xx normalised to {@link ComponentsApiError}.
 * Backend role: member.
 */
export function getComponents(
  workspaceId: string,
  opts: ComponentsRequestOptions = {},
): Promise<GetComponentsResponse> {
  return request<GetComponentsResponse>(
    workspaceComponentsEndpoint(workspaceId),
    { method: "GET" },
    opts,
  );
}

/**
 * GET /api/workspaces/{id}/components/{id}/usage — returns the screens that
 * reference a given component (E-024 ScreenComponent join rows projected to
 * a flat list).
 *
 * Backend role: member.
 */
export function getComponentUsage(
  workspaceId: string,
  componentId: string,
  opts: ComponentsRequestOptions = {},
): Promise<GetComponentUsageResponse> {
  return request<GetComponentUsageResponse>(
    workspaceComponentUsageEndpoint(workspaceId, componentId),
    { method: "GET" },
    opts,
  );
}
