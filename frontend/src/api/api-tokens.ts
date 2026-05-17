/**
 * T-V3-C-25 / F-030: Typed client for /api/me/api-tokens (Personal Access Tokens).
 *
 * Backend contracts (T-V3-B-TOKEN-01 / backend/routers/me.py):
 *   GET    /api/me/api-tokens         — backend/routers/me.py::get_me_api_tokens
 *   POST   /api/me/api-tokens         — backend/routers/me.py::post_me_api_tokens
 *   DELETE /api/me/api-tokens/{id}    — backend/routers/me.py::delete_me_api_tokens_by_id
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml#/paths/~1api~1me~1api-tokens
 *
 * EARS AC mapping (S-064 / T-V3-C-25):
 *   AC-F1: backing API 4xx/5xx -> non-technical toast referencing the failing
 *          endpoint without leaking server stack traces -> {@link ApiTokensApiError}
 *   AC-F2: POST /api/me/api-tokens returns plaintext_token_shown_once exactly once,
 *          server stores only hashed form -> {@link postApiToken}
 *   AC-F3: GET /api/me/api-tokens response surfaces only masked (prefix-only) form
 *          (no plaintext exposure) -> see {@link ApiTokenSummary}
 *
 * Error envelope follows the project-wide FastAPI contract:
 *   { detail: { code: string; message: string } }
 */

import { env } from "@/env";

export const API_TOKENS_ENDPOINT = "/api/me/api-tokens";
export function apiTokensItemEndpoint(id: string): string {
  return `/api/me/api-tokens/${encodeURIComponent(id)}`;
}

// --------------------------------------------------------------------------
// Types
// --------------------------------------------------------------------------

/**
 * Server-returned token summary (AC-F3): never includes the plaintext secret.
 * `prefix` is the short, non-sensitive identifier (e.g. `bf_pat_*****vRyM`)
 * used for display only.
 */
export interface ApiTokenSummary {
  id: string;
  name: string;
  /** Masked display prefix (last 4 chars only, never the plaintext token). */
  prefix?: string | null;
  scopes?: string[] | null;
  created_at?: string | null;
  expires_at?: string | null;
  last_used_at?: string | null;
}

export interface GetApiTokensResponse {
  tokens: ApiTokenSummary[];
}

export interface PostApiTokenRequest {
  name: string;
  scopes: string[];
  /** ISO 8601 timestamp or null for non-expiring tokens. */
  expires_at: string | null;
}

/**
 * Plaintext token is returned exactly once (AC-F2). Callers MUST display it
 * to the user immediately and discard it from memory; subsequent GET responses
 * will surface only {@link ApiTokenSummary}.
 */
export interface PostApiTokenResponse {
  token_id: string;
  plaintext_token_shown_once: string;
}

export interface DeleteApiTokenResponse {
  revoked_at: string;
}

// --------------------------------------------------------------------------
// Error class (AC-F1)
// --------------------------------------------------------------------------

interface BackendErrorEnvelope {
  detail?: { code?: string; message?: string } | string;
}

/**
 * Thrown for any non-2xx response from the /api/me/api-tokens endpoints.
 *
 * `.toUserMessage()` returns a non-technical, end-user friendly message that
 * references the failing endpoint without embedding raw server stack traces,
 * backend exception class names, or SQL details (AC-F1).
 */
export class ApiTokensApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly endpoint: string;

  constructor(code: string, message: string, status: number, endpoint: string) {
    super(message);
    this.name = "ApiTokensApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  toUserMessage(): string {
    const friendly = friendlyMessageForStatus(this.status);
    return `${friendly} (${this.endpoint})`;
  }
}

const USER_MESSAGES: Record<number | "default", string> = {
  400: "入力内容を確認してください",
  401: "サインインが必要です",
  403: "この操作を実行する権限がありません",
  404: "対象のトークンが見つかりませんでした",
  409: "状態が競合しています",
  422: "入力フォーマットが正しくありません",
  429: "リクエストが多すぎます。しばらく待って再試行してください",
  500: "サーバーエラーが発生しました。時間をおいて再試行してください",
  default: "通信に失敗しました",
};

function friendlyMessageForStatus(status: number): string {
  return USER_MESSAGES[status] ?? USER_MESSAGES.default;
}

// --------------------------------------------------------------------------
// Internal HTTP helper
// --------------------------------------------------------------------------

export interface ApiTokensRequestOptions {
  apiBase?: string;
  signal?: AbortSignal;
  /** Bearer token (Authorization: Bearer ...) required for authenticated role. */
  authToken?: string | null;
  /** Test seam — defaults to global fetch. */
  fetchImpl?: typeof fetch;
}

function resolveApiBase(opts: ApiTokensRequestOptions): string {
  if (opts.apiBase) return opts.apiBase;
  const fromEnv = env.NEXT_PUBLIC_API_URL;
  return (fromEnv ?? "http://localhost:8001").replace(/\/$/, "");
}

async function parseError(
  response: Response,
  endpoint: string,
): Promise<ApiTokensApiError> {
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
  return new ApiTokensApiError(code, message, response.status, endpoint);
}

async function request<TOut>(
  endpoint: string,
  init: RequestInit,
  opts: ApiTokensRequestOptions,
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
    throw new ApiTokensApiError("NETWORK_ERROR", "network error", 0, endpoint);
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
 * AC-F3 surface: GET /api/me/api-tokens — returns only masked summaries; the
 * server is responsible for never exposing plaintext via this endpoint.
 */
export function getApiTokens(
  opts: ApiTokensRequestOptions = {},
): Promise<GetApiTokensResponse> {
  return request<GetApiTokensResponse>(
    API_TOKENS_ENDPOINT,
    { method: "GET" },
    opts,
  );
}

/**
 * AC-F2: POST /api/me/api-tokens — server returns the plaintext token exactly
 * once via `plaintext_token_shown_once`. The caller is expected to display the
 * value to the user immediately and discard it; subsequent GETs will only ever
 * return the masked {@link ApiTokenSummary} form.
 */
export function postApiToken(
  body: PostApiTokenRequest,
  opts: ApiTokensRequestOptions = {},
): Promise<PostApiTokenResponse> {
  return request<PostApiTokenResponse>(
    API_TOKENS_ENDPOINT,
    { method: "POST", body: JSON.stringify(body) },
    opts,
  );
}

/** DELETE /api/me/api-tokens/{id} — revokes the token immediately. */
export function deleteApiToken(
  id: string,
  opts: ApiTokensRequestOptions = {},
): Promise<DeleteApiTokenResponse> {
  return request<DeleteApiTokenResponse>(
    apiTokensItemEndpoint(id),
    { method: "DELETE" },
    opts,
  );
}
