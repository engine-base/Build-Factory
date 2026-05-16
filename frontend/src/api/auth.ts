/**
 * T-V3-C-04 / F-001: Typed client for the auth router MFA endpoints.
 *
 * Backend contract:
 *   backend/routers/auth.py (POST /api/auth/mfa/enroll, POST /api/auth/mfa/verify)
 *   backend/schemas/auth.py (MfaEnroll/Verify Request/Response)
 *   docs/api-design/2026-05-16_v3/openapi.yaml#/paths/~1api~1auth~1mfa~1enroll
 *
 * The thrown {@link AuthApiError} surfaces a non-technical message for the UI
 * toast while preserving the failing endpoint reference, never leaking server
 * stack traces (AC-F3).
 */

export const AUTH_MFA_ENROLL_ENDPOINT = "/api/auth/mfa/enroll";
export const AUTH_MFA_VERIFY_ENDPOINT = "/api/auth/mfa/verify";

export interface MfaEnrollRequest {
  /** Base32-encoded TOTP secret (RFC 4648 alphabet, 16-128 chars). */
  totp_secret: string;
}

export interface MfaEnrollResponse {
  /** `otpauth://` URI or QR image URL the UI displays as a scannable code. */
  qr_code_url: string;
  /** Single-use backup codes (>= 8 entries, 8 hex chars each). */
  backup_codes: string[];
}

export interface MfaVerifyRequest {
  /** user_id (UUID v4) issued at signup / mfa enroll. */
  user_id: string;
  /** 6-8 digit numeric TOTP code (current 30s window). */
  totp_code: string;
}

export interface MfaVerifyResponse {
  /** Bearer access token (short-lived). */
  access_token: string;
  /** Long-lived refresh token. */
  refresh_token: string;
}

/** Thrown for any non-2xx response from the auth router. */
 * T-V3-C-02 / F-001 / F-004: Typed clients for auth + invitations endpoints
 * backing the S-002 signup screen.
 *
 * Backend contracts:
 *   POST /api/auth/signup        — backend/routers/auth.py::post_auth_signup
 *   GET  /api/invitations/{token} — backend/routers/invitations.py (T-V3-B-INV-01)
 *   POST /api/auth/login         — backend/routers/auth.py::post_auth_login
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml#/api/auth/signup
 *          docs/api-design/2026-05-16_v3/openapi.yaml#/api/invitations/{token}
 *          docs/api-design/2026-05-16_v3/openapi.yaml#/api/auth/login
 *
 * Errors follow the project-wide {detail: {code, message}} contract used by the
 * FastAPI backend. The thrown AuthApiError surfaces a non-technical message
 * (with the failing endpoint tagged) for UI toasts, never leaking server
 * stack traces (AC-F3 on S-002).
 */

export const SIGNUP_ENDPOINT = "/api/auth/signup";
export const LOGIN_ENDPOINT = "/api/auth/login";
export const INVITATION_ENDPOINT_PREFIX = "/api/invitations";

// --------------------------------------------------------------------------
// Signup
// --------------------------------------------------------------------------

export interface SignupRequest {
  /** RFC 5322 互換 email. backend pattern is enforced by Pydantic. */
  email: string;
  /** >= 8 chars per F-001 outputs_4xx 422. */
  password: string;
  /** Display name (1..128 chars). */
  name: string;
  /** Optional invite token (F-004 連携). */
  invitation_token?: string | null;
}

export interface SignupResponse {
  user_id: string;
  verify_email_sent: boolean;
}

// --------------------------------------------------------------------------
// Login (AC-F5 / AC-F6 — referenced by S-002 spec for auto-login post-signup)
// --------------------------------------------------------------------------

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  user_id: string;
  /** Optional MFA challenge handle when the user has TOTP enrolled. */
  mfa_required?: boolean;
}

// --------------------------------------------------------------------------
// Invitation lookup
// --------------------------------------------------------------------------

export interface InvitationInfo {
  invitation: {
    token: string;
    workspace_id: string;
    role: string;
    expires_at?: string;
    email?: string;
  };
  workspace_name: string;
  inviter_name: string;
}

// --------------------------------------------------------------------------
// Error class
// --------------------------------------------------------------------------

/** Thrown for any non-2xx response from the auth / invitations endpoints. */
export class AuthApiError extends Error {
  code: string;
  status: number;
  endpoint: string;

  constructor(code: string, message: string, status: number, endpoint: string) {
    super(message);
    this.name = "AuthApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * AC-F3 (UNWANTED): produce a user-facing message that references the
   * failing endpoint without leaking server stack traces.
   */
  toUserMessage(): string {
    const friendly = AUTH_USER_MESSAGES[this.status] ?? AUTH_USER_MESSAGES.default;
   * AC-F3 (S-002): produce a non-technical user-facing message that references
   * the failing endpoint without leaking server stack traces.
   */
  toUserMessage(): string {
    const friendly =
      AUTH_USER_MESSAGES[this.status] ?? AUTH_USER_MESSAGES.default;
 * Auth API client (typed) — T-V3-C-03 / S-003 / F-001.
 *
 * @screen-id S-003
 * @feature-id F-001
 * @task-ids T-V3-C-03,T-V3-AUTH-10,T-V3-AUTH-03
 * @entities E-001,E-039
 * @phase Phase 1B
 *
 * 関連 endpoint:
 *   POST /api/auth/password-reset
 *     - request : { email: string }
 *     - response: 2xx (status: 'sent' | string)  ← account enumeration 回避のため、
 *                 アカウント存否に依らず常に 2xx を返す (T-V3-B-01 実装済)
 *     - error   : 4xx/5xx は ApiError として上位 (Toast) に伝播
 */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

export type PasswordResetRequest = {
  email: string;
};

export type PasswordResetResponse = {
  status: string;
};

/**
 * 構造化 API エラー (server stack を露出させないため message は短文に正規化済み).
 *
 * UNWANTED AC: stack trace / SQL / internal path を含まない。
 */
export class ApiError extends Error {
  public readonly endpoint: string;
  public readonly status: number;

  constructor(endpoint: string, status: number, message?: string) {
    super(message ?? `${endpoint} failed (${status})`);
    this.name = "ApiError";
    this.endpoint = endpoint;
    this.status = status;
  }
}

/**
 * POST /api/auth/password-reset — パスワード再設定リンクを送信する.
 *
 * EVENT-DRIVEN: When called with an email, the backend shall always return 2xx
 * (no account enumeration) and send reset email only if the account exists.
 *
 * @throws ApiError 4xx / 5xx / network failure
 */
export async function requestPasswordReset(
  payload: PasswordResetRequest,
  init?: { fetchImpl?: typeof fetch; baseUrl?: string },
): Promise<PasswordResetResponse> {
  const endpoint = "POST /api/auth/password-reset";
  const fetchImpl = init?.fetchImpl ?? fetch;
  const baseUrl = init?.baseUrl ?? BASE;

  let res: Response;
  try {
    res = await fetchImpl(`${baseUrl}/api/auth/password-reset`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    // network-level failure (no response). Don't leak the cause to UI.
    throw new ApiError(endpoint, 0, `${endpoint}: ネットワークに接続できませんでした`);
  }

  if (!res.ok) {
    // 4xx / 5xx — stack trace を漏らさない短文へ正規化.
    const code = res.status;
    const msg =
      code === 429
        ? `${endpoint}: リクエストが多すぎます。しばらく待って再試行してください`
        : code >= 500
          ? `${endpoint}: サーバーで一時的なエラーが発生しました`
          : `${endpoint}: 入力内容を確認してください (${code})`;
    throw new ApiError(endpoint, code, msg);
  }

  // 2xx — backend は { status: "sent" } 等を返す.
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    data = { status: "sent" };
  }
  if (data && typeof data === "object" && "status" in data && typeof (data as { status: unknown }).status === "string") {
    return { status: (data as { status: string }).status };
  }
  return { status: "sent" };
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

const AUTH_USER_MESSAGES: Record<number | "default", string> = {
  400: "入力内容を確認してください",
  401: "サインインが必要です",
  403: "この操作を実行する権限がありません",
  404: "ユーザーが見つかりませんでした",
  409: "MFA は既に有効化されています",
  422: "入力フォーマットが正しくありません",
  429: "試行回数の上限に達しました。しばらく待って再試行してください",
  400: "リクエストが不正です",
  401: "メールアドレスまたはパスワードが正しくありません",
  403: "この操作を実行する権限がありません",
  404: "招待コードが見つかりません",
  409: "このメールアドレスは既に登録されています",
  422: "入力内容を確認してください",
  429: "リクエストが多すぎます。時間をおいて再試行してください",
  500: "サーバーエラーが発生しました。時間をおいて再試行してください",
  default: "通信に失敗しました",
};

function resolveApiBase(opts: { apiBase?: string }): string {
  if (opts.apiBase) return opts.apiBase;
  if (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_BASE) {
    return process.env.NEXT_PUBLIC_API_BASE;
  }
  return "http://localhost:8001";
}

export interface AuthRequestOptions {
  apiBase?: string;
  signal?: AbortSignal;
  /** Bearer token for endpoints requiring `authenticated` role (enroll). */
  authToken?: string | null;
}

async function postJson<TIn, TOut>(
  endpoint: string,
  body: TIn,
  opts: AuthRequestOptions,
): Promise<TOut> {
  const base = resolveApiBase(opts);
  const url = `${base}${endpoint}`;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };
  if (opts.authToken) headers.Authorization = `Bearer ${opts.authToken}`;

  let resp: Response;
  try {
    resp = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal: opts.signal,
      credentials: "include",
    });
  } catch (e) {
    if ((e as { name?: string }).name === "AbortError") {
      throw e;
    }
    throw new AuthApiError("auth.network_error", "network error", 0, endpoint);
  }

  if (!resp.ok) {
    let code = "auth.unknown";
    let message = `HTTP ${resp.status}`;
    try {
      const data = (await resp.json()) as {
        detail?: { code?: string; message?: string } | string;
      };
      if (typeof data?.detail === "string") {
        message = data.detail;
      } else if (data?.detail && typeof data.detail === "object") {
        if (data.detail.code) code = data.detail.code;
        if (data.detail.message) message = data.detail.message;
      }
    } catch {
      // intentionally ignore — keep generic fallback (no server-trace leak).
    }
    throw new AuthApiError(code, message, resp.status, endpoint);
  }

  return (await resp.json()) as TOut;
}

/**
 * AC-F1: POST /api/auth/mfa/enroll via the typed API client.
 *
 * Returns the {@link MfaEnrollResponse} (`qr_code_url`, `backup_codes`).
 * Throws {@link AuthApiError} on non-2xx so the caller can surface a toast.
 */
export function mfaEnroll(
  body: MfaEnrollRequest,
  opts: AuthRequestOptions = {},
): Promise<MfaEnrollResponse> {
  return postJson<MfaEnrollRequest, MfaEnrollResponse>(
    AUTH_MFA_ENROLL_ENDPOINT,
    body,
    opts,
  );
}

/**
 * AC-F2 + AC-F4: POST /api/auth/mfa/verify via the typed API client.
 *
 * Backend issues `access_token` + `refresh_token` only when MFA is enabled
 * for the user and the supplied TOTP code is valid.
 */
export function mfaVerify(
  body: MfaVerifyRequest,
  opts: AuthRequestOptions = {},
): Promise<MfaVerifyResponse> {
  return postJson<MfaVerifyRequest, MfaVerifyResponse>(
    AUTH_MFA_VERIFY_ENDPOINT,
    body,
    opts,
  );
// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------

interface ClientOptions {
  apiBase?: string;
  signal?: AbortSignal;
}

function resolveApiBase(opts: ClientOptions): string {
  if (opts.apiBase) return opts.apiBase;
  if (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  return "";
}

async function parseError(
  response: Response,
  endpoint: string,
): Promise<AuthApiError> {
  let code = "UNKNOWN";
  let message = response.statusText || "request failed";
  try {
    const payload = (await response.json()) as {
      detail?: { code?: string; message?: string } | string;
    };
    if (payload && typeof payload.detail === "object" && payload.detail) {
      if (typeof payload.detail.code === "string") code = payload.detail.code;
      if (typeof payload.detail.message === "string")
        message = payload.detail.message;
    } else if (typeof payload?.detail === "string") {
      message = payload.detail;
    }
  } catch {
    // Non-JSON body — keep the synthesised message. We deliberately do not
    // include the raw body to avoid leaking server stack traces.
  }
  return new AuthApiError(code, message, response.status, endpoint);
}

// --------------------------------------------------------------------------
// API functions
// --------------------------------------------------------------------------

/**
 * AC-F1 (S-002): POST /api/auth/signup via the typed client.
 */
export async function signup(
  body: SignupRequest,
  opts: ClientOptions = {},
): Promise<SignupResponse> {
  const url = `${resolveApiBase(opts)}${SIGNUP_ENDPOINT}`;
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: opts.signal,
  });
  if (!response.ok) {
    throw await parseError(response, SIGNUP_ENDPOINT);
  }
  return (await response.json()) as SignupResponse;
}

/**
 * AC-F2 (S-002): GET /api/invitations/{token} via the typed client.
 * Returns null on 404 so the UI can render the standard banner-less form.
 */
export async function getInvitation(
  token: string,
  opts: ClientOptions = {},
): Promise<InvitationInfo | null> {
  const endpoint = `${INVITATION_ENDPOINT_PREFIX}/${encodeURIComponent(token)}`;
  const url = `${resolveApiBase(opts)}${endpoint}`;
  const response = await fetch(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    signal: opts.signal,
  });
  if (response.status === 404) return null;
  if (!response.ok) {
    throw await parseError(response, endpoint);
  }
  return (await response.json()) as InvitationInfo;
}

/**
 * AC-F5 / AC-F6 (S-002 spec): POST /api/auth/login via the typed client.
 * Used immediately after successful signup so the user lands signed-in on
 * the account_dashboard (or invite accept page).
 *
 * AC-F6 (UNWANTED): invalid credentials → 401 with generic message — the
 * backend already collapses 404/401 into a single 401 response (no user
 * enumeration), this client preserves that contract by surfacing the
 * AuthApiError's generic toUserMessage().
 */
export async function login(
  body: LoginRequest,
  opts: ClientOptions = {},
): Promise<LoginResponse> {
  const url = `${resolveApiBase(opts)}${LOGIN_ENDPOINT}`;
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: opts.signal,
  });
  if (!response.ok) {
    throw await parseError(response, LOGIN_ENDPOINT);
  }
  return (await response.json()) as LoginResponse;
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
