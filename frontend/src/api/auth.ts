/**
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
   * AC-F3 (S-002): produce a non-technical user-facing message that references
   * the failing endpoint without leaking server stack traces.
   */
  toUserMessage(): string {
    const friendly =
      AUTH_USER_MESSAGES[this.status] ?? AUTH_USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

const AUTH_USER_MESSAGES: Record<number | "default", string> = {
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
}
