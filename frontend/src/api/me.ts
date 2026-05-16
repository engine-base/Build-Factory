/**
 * T-V3-C-09 / F-023: Typed client for /api/me, /api/me/api-keys,
 * /api/me/oauth/{provider}.
 *
 * Backend contracts (T-V3-B-26 PROFILE-01 実装済):
 *   GET    /api/me                    — backend/routers/me.py::get_me
 *   PUT    /api/me                    — backend/routers/me.py::put_me
 *   POST   /api/me/api-keys           — backend/routers/me.py::post_me_api_keys
 *   DELETE /api/me/oauth/{provider}   — backend/routers/me.py::delete_me_oauth_by_provider
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml#/paths/~1api~1me
 *
 * EARS AC mapping (S-009 / T-V3-C-09):
 *   AC-F1: GET /api/me                via typed client     → {@link getMe}
 *   AC-F2: PUT /api/me                via typed client     → {@link putMe}
 *   AC-F3: POST /api/me/api-keys      via typed client     → {@link postMeApiKey}
 *   AC-F4: DELETE /api/me/oauth/...   via typed client     → {@link deleteMeOAuth}
 *   AC-F5: 4xx/5xx surfaces non-technical toast referencing the failing
 *          endpoint without leaking server stack traces → {@link MeApiError}
 *
 * Error envelope follows the project-wide FastAPI contract:
 *   { detail: { code: string; message: string } }
 */

import { env } from "@/env";

export const ME_ENDPOINT = "/api/me";
export const ME_API_KEYS_ENDPOINT = "/api/me/api-keys";
/** Build the canonical OAuth unlink endpoint path for the given provider. */
export function meOAuthEndpoint(provider: string): string {
  return `/api/me/oauth/${encodeURIComponent(provider)}`;
}

// --------------------------------------------------------------------------
// Types
// --------------------------------------------------------------------------

export interface MeUser {
  id: string;
  email: string;
  name: string | null;
  avatar_url: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface MeSettings {
  theme?: "light" | "dark" | "system" | null;
  language?: string | null;
  timezone?: string | null;
  notifications?: Record<string, boolean> | null;
  default_llm_provider?: string | null;
  clone_opt_in?: boolean | null;
}

export interface GetMeResponse {
  user: MeUser;
  settings: MeSettings;
}

export interface PutMeRequest {
  name?: string | null;
  avatar_url?: string | null;
  settings?: MeSettings | null;
}

export interface PutMeResponse {
  updated_at: string;
}

export interface PostMeApiKeyRequest {
  /** Provider identifier: "anthropic" | "openai" | "google" | ... */
  provider: string;
  /** Raw API key (encrypted at rest server-side, never returned again). */
  api_key: string;
  /** Optional label for the key (display only). */
  label?: string | null;
}

export interface PostMeApiKeyResponse {
  key_id: string;
  masked_key: string;
}

export interface DeleteMeOAuthResponse {
  unlinked_at: string;
}

// --------------------------------------------------------------------------
// Error class (AC-F5)
// --------------------------------------------------------------------------

interface BackendErrorEnvelope {
  detail?: { code?: string; message?: string } | string;
}

/**
 * Thrown for any non-2xx response from the /api/me endpoints.
 *
 * `.toUserMessage()` returns a non-technical, end-user friendly message that
 * references the failing endpoint without embedding raw server stack traces,
 * backend exception class names, or SQL details (AC-F5).
 */
export class MeApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly endpoint: string;

  constructor(code: string, message: string, status: number, endpoint: string) {
    super(message);
    this.name = "MeApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  toUserMessage(): string {
    const friendly = friendlyMessageForStatus(this.status);
    return `${friendly} (${this.endpoint})`;
  }
}

const ME_USER_MESSAGES: Record<number | "default", string> = {
  400: "入力内容を確認してください",
  401: "サインインが必要です",
  403: "この操作を実行する権限がありません",
  404: "対象が見つかりませんでした",
  409: "状態が競合しています",
  422: "入力フォーマットが正しくありません",
  429: "リクエストが多すぎます。しばらく待って再試行してください",
  500: "サーバーエラーが発生しました。時間をおいて再試行してください",
  default: "通信に失敗しました",
};

function friendlyMessageForStatus(status: number): string {
  return ME_USER_MESSAGES[status] ?? ME_USER_MESSAGES.default;
}

// --------------------------------------------------------------------------
// Internal HTTP helper
// --------------------------------------------------------------------------

export interface MeRequestOptions {
  apiBase?: string;
  signal?: AbortSignal;
  /** Bearer token (Authorization: Bearer ...) required for authenticated role. */
  authToken?: string | null;
  /** Test seam — defaults to global fetch. */
  fetchImpl?: typeof fetch;
}

function resolveApiBase(opts: MeRequestOptions): string {
  if (opts.apiBase) return opts.apiBase;
  const fromEnv = env.NEXT_PUBLIC_API_URL;
  return (fromEnv ?? "http://localhost:8001").replace(/\/$/, "");
}

async function parseError(
  response: Response,
  endpoint: string,
): Promise<MeApiError> {
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
    // Non-JSON body — keep the synthesised message. AC-F5: don't leak raw body.
  }
  return new MeApiError(code, message, response.status, endpoint);
}

async function request<TOut>(
  endpoint: string,
  init: RequestInit,
  opts: MeRequestOptions,
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
    throw new MeApiError(
      "NETWORK_ERROR",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseError(response, endpoint);
  }
  // 204 No Content – return {} for type alignment.
  if (response.status === 204) return {} as TOut;
  return (await response.json()) as TOut;
}

// --------------------------------------------------------------------------
// Public API
// --------------------------------------------------------------------------

/** AC-F1: GET /api/me. */
export function getMe(opts: MeRequestOptions = {}): Promise<GetMeResponse> {
  return request<GetMeResponse>(ME_ENDPOINT, { method: "GET" }, opts);
}

/** AC-F2: PUT /api/me. */
export function putMe(
  body: PutMeRequest,
  opts: MeRequestOptions = {},
): Promise<PutMeResponse> {
  return request<PutMeResponse>(
    ME_ENDPOINT,
    { method: "PUT", body: JSON.stringify(body) },
    opts,
  );
}

/** AC-F3: POST /api/me/api-keys. */
export function postMeApiKey(
  body: PostMeApiKeyRequest,
  opts: MeRequestOptions = {},
): Promise<PostMeApiKeyResponse> {
  return request<PostMeApiKeyResponse>(
    ME_API_KEYS_ENDPOINT,
    { method: "POST", body: JSON.stringify(body) },
    opts,
  );
}

/** AC-F4: DELETE /api/me/oauth/{provider}. */
export function deleteMeOAuth(
  provider: string,
  opts: MeRequestOptions = {},
): Promise<DeleteMeOAuthResponse> {
  return request<DeleteMeOAuthResponse>(
    meOAuthEndpoint(provider),
    { method: "DELETE" },
    opts,
  );
}
