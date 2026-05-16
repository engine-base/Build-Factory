/**
 * T-V3-C-05 / F-001: Typed client for GET /api/auth/oauth/{provider}/callback.
 *
 * Backend contract: backend/routers/auth.py::get_auth_oauth_by_provider_callback
 * (implemented by T-V3-B-02, public endpoint, no Authorization header required).
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml#/api/auth/oauth/{provider}/callback
 *
 * Errors follow the project-wide {detail: {code, message}} contract used by the
 * FastAPI backend. The thrown OAuthCallbackApiError surfaces a non-technical
 * message for the UI toast while preserving the failing endpoint reference,
 * never leaking server stack traces (AC-F2).
 */
import { env } from "@/env";

export const OAUTH_CALLBACK_ENDPOINT_PATTERN =
  "/api/auth/oauth/{provider}/callback";

/** OAuth providers accepted by the backend (auth.py oauth_supported_providers). */
export const OAUTH_PROVIDERS = [
  "anthropic",
  "github",
  "slack",
  "google",
] as const;
export type OAuthProvider = (typeof OAUTH_PROVIDERS)[number];

export interface OAuthCallbackResponse {
  /** Short-lived JWT access token (Authorization: Bearer ...). */
  access_token: string;
  /** Long-lived refresh token used to mint new access tokens. */
  refresh_token: string;
  /** Authenticated user id (UUID). */
  user_id: string;
}

/** Backend FastAPI error envelope: `{detail: {code, message, errors?}}`. */
interface BackendErrorEnvelope {
  detail?: {
    code?: string;
    message?: string;
    errors?: unknown;
  };
}

/** Thrown for any non-2xx response from the OAuth callback endpoint. */
export class OAuthCallbackApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly endpoint: string;
  readonly provider: string;

  constructor(
    code: string,
    message: string,
    status: number,
    endpoint: string,
    provider: string
  ) {
    super(message);
    this.name = "OAuthCallbackApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
    this.provider = provider;
  }

  /**
   * Build a non-technical, end-user friendly message that references the
   * failing endpoint (AC-F2). Never embeds raw stack traces or backend
   * exception class names.
   */
  toUserMessage(): string {
    const friendly = friendlyMessageForStatus(this.status, this.code);
    return `${friendly} (${this.endpoint})`;
  }
}

function friendlyMessageForStatus(status: number, code: string): string {
  // AC-F2 mandates non-technical, no stack-trace leakage.
  if (status === 401) {
    return "認証情報の検証に失敗しました。もう一度ログインしてください。";
  }
  if (status === 404) {
    return "選択した OAuth プロバイダは現在ご利用いただけません。";
  }
  if (status === 422) {
    return "OAuth のリクエストパラメータが不正です。";
  }
  if (status >= 500) {
    return "OAuth サーバーで問題が発生しました。しばらくしてから再度お試しください。";
  }
  if (code) {
    return "OAuth 認証中にエラーが発生しました。";
  }
  return "認証中にエラーが発生しました。";
}

/**
 * Build the canonical OAuth callback endpoint path for the given provider.
 *
 * Note: the path includes the `provider` segment but never the `code` /
 * `state` query params — those are added by `completeOAuthCallback`.
 */
export function oauthCallbackEndpoint(provider: string): string {
  // We do not validate the provider against OAUTH_PROVIDERS here; the backend
  // returns 422 for unknown providers, and we want callers (including the UI)
  // to be able to render the canonical endpoint path in error toasts.
  return `/api/auth/oauth/${encodeURIComponent(provider)}/callback`;
}

export interface OAuthCallbackInput {
  /** Provider segment (anthropic | github | slack | google). */
  provider: string;
  /** Authorization code returned by the OAuth provider. */
  code: string;
  /** CSRF state token issued during the /authorize step. */
  state: string;
  /** Optional AbortSignal — wired to React effect cleanup. */
  signal?: AbortSignal;
}

/**
 * GET /api/auth/oauth/{provider}/callback (T-V3-B-02 backend contract).
 *
 * AC-F1: typed API client.
 * AC-F3: returns access_token + refresh_token when state is valid (handshake).
 * AC-F2: throws OAuthCallbackApiError with `.toUserMessage()` on 4xx/5xx.
 */
export async function completeOAuthCallback(
  input: OAuthCallbackInput
): Promise<OAuthCallbackResponse> {
  const endpoint = oauthCallbackEndpoint(input.provider);
  const baseUrl =
    (env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001").replace(/\/$/, "");
  const url = new URL(`${baseUrl}${endpoint}`);
  url.searchParams.set("code", input.code);
  url.searchParams.set("state", input.state);

  let response: Response;
  try {
    response = await fetch(url.toString(), {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: input.signal,
    });
  } catch (err) {
    // Network / abort / DNS — translate to a typed error w/o stack trace leak.
    const msg = err instanceof Error ? err.message : "network error";
    throw new OAuthCallbackApiError(
      "NETWORK_ERROR",
      msg,
      0,
      endpoint,
      input.provider
    );
  }

  if (!response.ok) {
    let envelope: BackendErrorEnvelope = {};
    try {
      envelope = (await response.json()) as BackendErrorEnvelope;
    } catch {
      // ignore body parse failure — keep envelope empty.
    }
    const code = envelope.detail?.code ?? "UNKNOWN_ERROR";
    const message = envelope.detail?.message ?? "request failed";
    throw new OAuthCallbackApiError(
      code,
      message,
      response.status,
      endpoint,
      input.provider
    );
  }

  const payload = (await response.json()) as OAuthCallbackResponse;
  return payload;
}
