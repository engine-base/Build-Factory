/**
 * T-V3-C-01 .. C-05 — Typed client for the auth router endpoints (F-001).
 *
 * Consolidated module backing the S-001 (login), S-002 (signup),
 * S-003 (password-reset), S-004 (mfa-setup), S-005 (mfa-challenge),
 * and S-006 (oauth-callback) screens.
 *
 * (Phase 1.0-fix Wave 0 D: reconciles five concurrent vertical-slice merges
 * that previously left the file with stacked duplicate declarations and a
 * missing comment opener that broke `next build` type-check.)
 *
 * Backend contracts (backend/routers/auth.py + routers/invitations.py):
 *   POST /api/auth/signup
 *   POST /api/auth/login
 *   POST /api/auth/password-reset
 *   POST /api/auth/mfa/enroll
 *   POST /api/auth/mfa/verify
 *   GET  /api/auth/oauth/{provider}/callback
 *   GET  /api/invitations/{token}
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml (F-001 + F-004 groups)
 *
 * Errors follow the project-wide {detail: {code, message}} contract used by
 * the FastAPI backend. All thrown error classes surface a non-technical,
 * endpoint-tagged message via `.toUserMessage()` and never leak server
 * stack traces (AC-F2 / AC-F3 / AC-F6 across the screens).
 */

import { env } from "@/env";

// ---------------------------------------------------------------------------
// Endpoint constants.
// ---------------------------------------------------------------------------

export const SIGNUP_ENDPOINT = "/api/auth/signup";
export const LOGIN_ENDPOINT = "/api/auth/login";
export const PASSWORD_RESET_ENDPOINT = "/api/auth/password-reset";
export const AUTH_MFA_ENROLL_ENDPOINT = "/api/auth/mfa/enroll";
export const AUTH_MFA_VERIFY_ENDPOINT = "/api/auth/mfa/verify";
/** Back-compat alias for callers using the shorter name. */
export const MFA_VERIFY_ENDPOINT = AUTH_MFA_VERIFY_ENDPOINT;
export const INVITATION_ENDPOINT_PREFIX = "/api/invitations";

/** OAuth providers accepted by the backend (auth.py oauth_supported_providers). */
export const OAUTH_PROVIDERS = [
  "anthropic",
  "github",
  "slack",
  "google",
] as const;
export type OAuthProvider = (typeof OAUTH_PROVIDERS)[number];

export const OAUTH_CALLBACK_ENDPOINT_PATTERN =
  "/api/auth/oauth/{provider}/callback";

/** Storage key for the "last-visited" path used by AC-F4 (S-001). */
export const LAST_VISITED_STORAGE_KEY = "bf:last_visited";
/** Fallback path when no last-visited path is stored. */
export const POST_LOGIN_FALLBACK_PATH = "/workspaces";

// ---------------------------------------------------------------------------
// Domain types.
// ---------------------------------------------------------------------------

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

export interface LoginRequest {
  email: string;
  password: string;
  /** Optional inline MFA code (when user already had TOTP in hand). */
  mfa_code?: string | null;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  user_id: string;
  /**
   * When true the caller must follow up with POST /api/auth/mfa/verify before
   * treating the session as established.
   */
  mfa_required?: boolean;
}

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

export type PasswordResetRequest = {
  email: string;
};

export type PasswordResetResponse = {
  status: string;
};

export interface OAuthCallbackResponse {
  /** Short-lived JWT access token (Authorization: Bearer ...). */
  access_token: string;
  /** Long-lived refresh token used to mint new access tokens. */
  refresh_token: string;
  /** Authenticated user id (UUID). */
  user_id: string;
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

// ---------------------------------------------------------------------------
// Error envelope + classes.
// ---------------------------------------------------------------------------

interface BackendErrorEnvelope {
  detail?:
    | { code?: string; message?: string; errors?: unknown }
    | string;
}

const AUTH_USER_MESSAGES: Record<number | "default", string> = {
  400: "リクエストが不正です",
  // AC-F6: generic — must not reveal whether email or password was wrong.
  401: "メールアドレスまたはパスワードが正しくありません",
  403: "この操作を実行する権限がありません",
  404: "アカウントが見つかりません",
  409: "このメールアドレスは既に登録されています",
  422: "入力内容を確認してください",
  429: "試行回数の上限に達しました。しばらく待って再試行してください",
  500: "サインインに失敗しました。時間をおいて再試行してください",
  default: "通信に失敗しました",
};

/** Thrown for any non-2xx response from the auth / invitations endpoints. */
export class AuthApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly endpoint: string;

  constructor(code: string, message: string, status: number, endpoint: string) {
    super(message);
    this.name = "AuthApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * AC-F3 / AC-F6: produce a non-technical user-facing message that
   * references the failing endpoint without leaking server stack traces.
   */
  toUserMessage(): string {
    const friendly =
      AUTH_USER_MESSAGES[this.status] ?? AUTH_USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

/**
 * Lightweight error class used by S-003 (password reset) — kept distinct from
 * `AuthApiError` because callers only need {endpoint, status} and a pre-built
 * message string.
 */
export class ApiError extends Error {
  readonly endpoint: string;
  readonly status: number;

  constructor(endpoint: string, status: number, message?: string) {
    super(message ?? `${endpoint} failed (${status})`);
    this.name = "ApiError";
    this.endpoint = endpoint;
    this.status = status;
  }
}

function friendlyOAuthMessage(status: number, code: string): string {
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
    provider: string,
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
    const friendly = friendlyOAuthMessage(this.status, this.code);
    return `${friendly} (${this.endpoint})`;
  }
}

// ---------------------------------------------------------------------------
// Internal HTTP helpers.
// ---------------------------------------------------------------------------

export interface AuthRequestOptions {
  apiBase?: string;
  signal?: AbortSignal;
  /** Bearer token for endpoints requiring `authenticated` role (mfa enroll). */
  authToken?: string | null;
  /** Test seam — defaults to global fetch. */
  fetchImpl?: typeof fetch;
}

/** Back-compat alias used by S-001 callers. */
export type LoginOptions = AuthRequestOptions;

function resolveApiBase(opts: AuthRequestOptions): string {
  if (opts.apiBase) return opts.apiBase;
  const fromEnv = env.NEXT_PUBLIC_API_URL;
  if (fromEnv) return fromEnv.replace(/\/$/, "");
  if (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_BASE) {
    return process.env.NEXT_PUBLIC_API_BASE.replace(/\/$/, "");
  }
  return "http://localhost:8001";
}

async function readErrorBody(
  resp: Response,
): Promise<{ code: string; message: string }> {
  let code = "auth.unknown";
  let message = `HTTP ${resp.status}`;
  try {
    const data = (await resp.json()) as BackendErrorEnvelope;
    if (typeof data?.detail === "string") {
      message = data.detail;
    } else if (data?.detail && typeof data.detail === "object") {
      if (typeof data.detail.code === "string") code = data.detail.code;
      if (typeof data.detail.message === "string") {
        message = data.detail.message;
      }
    }
  } catch {
    // intentionally ignore — keep generic fallback (no server-trace leak).
  }
  return { code, message };
}

async function authFetch<TOut>(
  endpoint: string,
  init: RequestInit,
  opts: AuthRequestOptions,
): Promise<TOut> {
  const base = resolveApiBase(opts);
  const fetchImpl = opts.fetchImpl ?? fetch;
  const url = endpoint.startsWith("http") ? endpoint : `${base}${endpoint}`;

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

  let resp: Response;
  try {
    resp = await fetchImpl(url, {
      ...init,
      headers,
      signal: opts.signal,
      credentials: init.credentials ?? "include",
    });
  } catch (err) {
    if ((err as { name?: string }).name === "AbortError") throw err;
    throw new AuthApiError(
      "auth.network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!resp.ok) {
    const { code, message } = await readErrorBody(resp);
    throw new AuthApiError(code, message, resp.status, endpoint);
  }

  if (resp.status === 204) return undefined as unknown as TOut;
  try {
    return (await resp.json()) as TOut;
  } catch {
    return undefined as unknown as TOut;
  }
}

// ---------------------------------------------------------------------------
// Public API — signup / login (S-001 / S-002).
// ---------------------------------------------------------------------------

/** AC-F1 (S-002): POST /api/auth/signup via the typed client. */
export function signup(
  body: SignupRequest,
  opts: AuthRequestOptions = {},
): Promise<SignupResponse> {
  return authFetch<SignupResponse>(
    SIGNUP_ENDPOINT,
    { method: "POST", body: JSON.stringify(body) },
    opts,
  );
}

/** AC-F2 (S-002): GET /api/invitations/{token} via the typed client. */
export async function getInvitation(
  token: string,
  opts: AuthRequestOptions = {},
): Promise<InvitationInfo | null> {
  const endpoint = `${INVITATION_ENDPOINT_PREFIX}/${encodeURIComponent(token)}`;
  const base = resolveApiBase(opts);
  const fetchImpl = opts.fetchImpl ?? fetch;
  const url = `${base}${endpoint}`;

  let resp: Response;
  try {
    resp = await fetchImpl(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as { name?: string }).name === "AbortError") throw err;
    throw new AuthApiError(
      "auth.network_error",
      "network error",
      0,
      endpoint,
    );
  }
  if (resp.status === 404) return null;
  if (!resp.ok) {
    const { code, message } = await readErrorBody(resp);
    throw new AuthApiError(code, message, resp.status, endpoint);
  }
  return (await resp.json()) as InvitationInfo;
}

/** AC-F5 / AC-F6 (S-002): POST /api/auth/login via the typed client. */
export function login(
  body: LoginRequest,
  opts: AuthRequestOptions = {},
): Promise<LoginResponse> {
  return authFetch<LoginResponse>(
    LOGIN_ENDPOINT,
    { method: "POST", body: JSON.stringify(body) },
    opts,
  );
}

/** Alias used by S-001 page (kept distinct for clarity in call sites). */
export function loginWithPassword(
  body: LoginRequest,
  opts: AuthRequestOptions = {},
): Promise<LoginResponse> {
  return login(body, opts);
}

/** AC-F4 (S-001): resolve the next-route target after a successful login. */
export function resolvePostLoginPath(lastVisited?: string | null): string {
  if (
    lastVisited &&
    typeof lastVisited === "string" &&
    lastVisited.startsWith("/")
  ) {
    return lastVisited;
  }
  if (typeof window !== "undefined") {
    try {
      const stored = window.localStorage.getItem(LAST_VISITED_STORAGE_KEY);
      if (stored && stored.startsWith("/")) {
        return stored;
      }
    } catch {
      // ignore storage access errors (SSR / sandboxed envs).
    }
  }
  return POST_LOGIN_FALLBACK_PATH;
}

// ---------------------------------------------------------------------------
// MFA (S-004 / S-005).
// ---------------------------------------------------------------------------

/** AC-F1 (S-004): POST /api/auth/mfa/enroll via the typed client. */
export function mfaEnroll(
  body: MfaEnrollRequest,
  opts: AuthRequestOptions = {},
): Promise<MfaEnrollResponse> {
  return authFetch<MfaEnrollResponse>(
    AUTH_MFA_ENROLL_ENDPOINT,
    { method: "POST", body: JSON.stringify(body) },
    opts,
  );
}

/** AC-F2 (S-004 / S-005): POST /api/auth/mfa/verify via the typed client. */
export function mfaVerify(
  body: MfaVerifyRequest,
  opts: AuthRequestOptions = {},
): Promise<MfaVerifyResponse> {
  return authFetch<MfaVerifyResponse>(
    AUTH_MFA_VERIFY_ENDPOINT,
    { method: "POST", body: JSON.stringify(body) },
    opts,
  );
}

/** Alias used by S-001 (login → MFA challenge) call sites. */
export function verifyMfaCode(
  body: MfaVerifyRequest,
  opts: AuthRequestOptions = {},
): Promise<MfaVerifyResponse> {
  return mfaVerify(body, opts);
}

// ---------------------------------------------------------------------------
// Password reset (S-003).
// ---------------------------------------------------------------------------

/**
 * POST /api/auth/password-reset — request a password reset email.
 *
 * EVENT-DRIVEN: the backend shall always return 2xx (no account enumeration)
 * and only sends a reset email when the account exists. 4xx/5xx surface as
 * `ApiError` so the caller can show a non-technical toast.
 */
export async function requestPasswordReset(
  payload: PasswordResetRequest,
  init?: { fetchImpl?: typeof fetch; baseUrl?: string },
): Promise<PasswordResetResponse> {
  const endpoint = `POST ${PASSWORD_RESET_ENDPOINT}`;
  const fetchImpl = init?.fetchImpl ?? fetch;
  const baseUrl = init?.baseUrl ?? resolveApiBase({});

  let res: Response;
  try {
    res = await fetchImpl(`${baseUrl}${PASSWORD_RESET_ENDPOINT}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new ApiError(
      endpoint,
      0,
      `${endpoint}: ネットワークに接続できませんでした`,
    );
  }

  if (!res.ok) {
    const code = res.status;
    const msg =
      code === 429
        ? `${endpoint}: リクエストが多すぎます。しばらく待って再試行してください`
        : code >= 500
          ? `${endpoint}: サーバーで一時的なエラーが発生しました`
          : `${endpoint}: 入力内容を確認してください (${code})`;
    throw new ApiError(endpoint, code, msg);
  }

  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    data = { status: "sent" };
  }
  if (
    data &&
    typeof data === "object" &&
    "status" in data &&
    typeof (data as { status: unknown }).status === "string"
  ) {
    return { status: (data as { status: string }).status };
  }
  return { status: "sent" };
}

// ---------------------------------------------------------------------------
// OAuth callback (S-006).
// ---------------------------------------------------------------------------

/** Build the canonical OAuth callback endpoint path for the given provider. */
export function oauthCallbackEndpoint(provider: string): string {
  return `/api/auth/oauth/${encodeURIComponent(provider)}/callback`;
}

/**
 * GET /api/auth/oauth/{provider}/callback — exchange code+state for tokens.
 *
 * AC-F1: typed API client.
 * AC-F3: returns access_token + refresh_token on success.
 * AC-F2: throws OAuthCallbackApiError with `.toUserMessage()` on 4xx/5xx.
 */
export async function completeOAuthCallback(
  input: OAuthCallbackInput,
): Promise<OAuthCallbackResponse> {
  const endpoint = oauthCallbackEndpoint(input.provider);
  const baseUrl = resolveApiBase({});
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
    const msg = err instanceof Error ? err.message : "network error";
    throw new OAuthCallbackApiError(
      "NETWORK_ERROR",
      msg,
      0,
      endpoint,
      input.provider,
    );
  }

  if (!response.ok) {
    let envelope: BackendErrorEnvelope = {};
    try {
      envelope = (await response.json()) as BackendErrorEnvelope;
    } catch {
      // ignore body parse failure.
    }
    const detail =
      envelope.detail && typeof envelope.detail === "object"
        ? envelope.detail
        : undefined;
    const code = detail?.code ?? "UNKNOWN_ERROR";
    const message = detail?.message ?? "request failed";
    throw new OAuthCallbackApiError(
      code,
      message,
      response.status,
      endpoint,
      input.provider,
    );
  }

  return (await response.json()) as OAuthCallbackResponse;
}
