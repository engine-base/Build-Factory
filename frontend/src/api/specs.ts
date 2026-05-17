/**
 * T-V3-C-48 / F-005: Typed client for the workspace spec viewer endpoints
 * backing the S-022 (仕様書ビューア) screen.
 *
 * Backend contracts (T-V3-B-07):
 *   GET    /api/workspaces/{id}/specs                                (member)
 *   GET    /api/workspaces/{id}/specs/{spec_id}/comments             (member)
 *   POST   /api/workspaces/{id}/specs/{spec_id}/comments             (member)
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml
 *   #/paths/~1api~1workspaces~1{id}~1specs
 *   #/paths/~1api~1workspaces~1{id}~1specs~1{spec_id}~1comments
 *
 * Errors follow the project-wide {detail: {code, message}} contract used by
 * the FastAPI backend. The thrown {@link SpecsApiError} surfaces a
 * non-technical message (with the failing endpoint tagged) for UI toasts,
 * never leaking server stack traces (AC-F1 on S-022 / T-V3-C-48).
 */

import { env } from "@/env";

// --------------------------------------------------------------------------
// Endpoint constants
// --------------------------------------------------------------------------

export function workspaceSpecsEndpoint(workspaceId: string): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/specs`;
}

export function workspaceSpecCommentsEndpoint(
  workspaceId: string,
  specId: string,
): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/specs/${encodeURIComponent(specId)}/comments`;
}

// --------------------------------------------------------------------------
// Types — narrow to what S-022 renders. Backend may include extra fields.
// --------------------------------------------------------------------------

/** A single spec row returned by GET /api/workspaces/{id}/specs. */
export interface Spec {
  id: string;
  workspace_id?: string;
  title: string;
  version?: number | string;
  html_path?: string | null;
  status?: string;
  body_md?: string | null;
  /** Server may include arbitrary extras. */
  [extra: string]: unknown;
}

export interface GetSpecsResponse {
  specs: Spec[];
  count?: number;
}

/** A single comment row returned by GET /specs/{spec_id}/comments. */
export interface SpecComment {
  id: string;
  body: string;
  author_id?: string | null;
  author_name?: string | null;
  created_at: string;
  /** Server may include arbitrary extras (anchor, etc.). */
  [extra: string]: unknown;
}

export interface GetSpecCommentsResponse {
  comments: SpecComment[];
  count?: number;
}

export interface CreateCommentPayload {
  body: string;
  anchor?: string | null;
}

export interface CreateCommentResponse {
  comment_id: string;
  created_at: string;
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
  404: "対象の仕様書が見つかりませんでした",
  409: "競合が発生しました",
  422: "入力フォーマットが正しくありません",
  429: "リクエストが多すぎます。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "通信に失敗しました",
};

interface BackendErrorEnvelope {
  detail?: { code?: string; message?: string } | string;
}

/** Thrown for any non-2xx response from the specs endpoints. */
export class SpecsApiError extends Error {
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
    this.name = "SpecsApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * AC-F1 (S-022 UNWANTED): produce a non-technical user-facing message that
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

export interface SpecsRequestOptions {
  apiBase?: string;
  signal?: AbortSignal;
  /** Bearer token (Authorization: Bearer ...) required for authenticated role. */
  authToken?: string | null;
  /** Test seam — defaults to global fetch. */
  fetchImpl?: typeof fetch;
}

function resolveApiBase(opts: SpecsRequestOptions): string {
  if (opts.apiBase) return opts.apiBase;
  const fromEnv = env.NEXT_PUBLIC_API_URL;
  return (fromEnv ?? "http://localhost:8001").replace(/\/$/, "");
}

async function parseError(
  response: Response,
  endpoint: string,
): Promise<SpecsApiError> {
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
  return new SpecsApiError(code, message, response.status, endpoint);
}

async function request<TOut>(
  endpoint: string,
  init: RequestInit,
  opts: SpecsRequestOptions,
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
    throw new SpecsApiError("NETWORK_ERROR", "network error", 0, endpoint);
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
 * GET /api/workspaces/{id}/specs — returns the workspace's spec list.
 *
 * AC-F1 surface: 4xx/5xx is normalised into a {@link SpecsApiError}.
 * Backend role: member (any workspace member may read).
 */
export function getSpecs(
  workspaceId: string,
  opts: SpecsRequestOptions = {},
): Promise<GetSpecsResponse> {
  return request<GetSpecsResponse>(
    workspaceSpecsEndpoint(workspaceId),
    { method: "GET" },
    opts,
  );
}

/**
 * GET /api/workspaces/{id}/specs/{spec_id}/comments — list spec comments.
 * Backend role: member.
 */
export function getSpecComments(
  workspaceId: string,
  specId: string,
  opts: SpecsRequestOptions = {},
): Promise<GetSpecCommentsResponse> {
  return request<GetSpecCommentsResponse>(
    workspaceSpecCommentsEndpoint(workspaceId, specId),
    { method: "GET" },
    opts,
  );
}

/**
 * POST /api/workspaces/{id}/specs/{spec_id}/comments — add a comment to a spec.
 * Backend role: member. Body max length 10000 chars (server enforced; 422 on
 * overflow surfaced via {@link SpecsApiError.toUserMessage}).
 */
export function createSpecComment(
  workspaceId: string,
  specId: string,
  body: CreateCommentPayload,
  opts: SpecsRequestOptions = {},
): Promise<CreateCommentResponse> {
  return request<CreateCommentResponse>(
    workspaceSpecCommentsEndpoint(workspaceId, specId),
    { method: "POST", body: JSON.stringify(body) },
    opts,
  );
}
