/**
 * T-V3-C-01 / F-001: Typed client for POST /api/auth/login + POST /api/auth/mfa/verify.
 *
 * Backend contracts:
 *   - backend/routers/auth.py::post_auth_login   (T-V3-AUTH-01 / T-V3-B-01)
 *   - backend/routers/auth.py::post_auth_mfa_verify (T-V3-AUTH-04 / T-V3-B-02)
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml#/api/auth/login + /api/auth/mfa/verify
 *
 * Errors follow the project-wide {detail: {code, message}} contract used by the
 * FastAPI backend. The thrown AuthApiError surfaces a non-technical message
 * for the UI toast while preserving the failing endpoint reference, never
 * leaking server stack traces (AC-F3).
 */

export const LOGIN_ENDPOINT = "/api/auth/login";
export const MFA_VERIFY_ENDPOINT = "/api/auth/mfa/verify";

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
  /** When true the caller must follow up with POST /api/auth/mfa/verify before treating the session as established. */
  mfa_required?: boolean;
}

export interface MfaVerifyRequest {
  user_id: string;
  totp_code: string;
}

export interface MfaVerifyResponse {
  access_token: string;
  refresh_token: string;
}

/** Thrown for any non-2xx response from POST /api/auth/login or /api/auth/mfa/verify. */
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
   * AC-F3: produce a non-technical user-facing message that references the
   * failing endpoint without leaking server stack traces or implementation
   * detail (no `traceback`, no raw `code`).
   *
   * AC-F6: generic 401 message (no user enumeration).
   */
  toUserMessage(): string {
    const friendly = AUTH_USER_MESSAGES[this.status] ?? AUTH_USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

const AUTH_USER_MESSAGES: Record<number | "default", string> = {
  400: "入力内容を確認してください",
  // AC-F6: generic — must not reveal whether email or password was wrong.
  401: "メールアドレスまたはパスワードが正しくありません",
  403: "アカウントがロックされています。しばらくしてから再試行してください",
  404: "アカウントが見つかりません",
  422: "入力内容を確認してください",
  429: "試行回数の上限に達しました。しばらく待って再試行してください",
  500: "サインインに失敗しました。時間をおいて再試行してください",
  default: "サインインに失敗しました",
};

function resolveApiBase(opts: { apiBase?: string }): string {
  if (opts.apiBase) return opts.apiBase;
  if (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_BASE) {
    return process.env.NEXT_PUBLIC_API_BASE;
  }
  return "http://localhost:8001";
}

async function readErrorBody(resp: Response): Promise<{ code: string; message: string }> {
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
  return { code, message };
}

export interface LoginOptions {
  apiBase?: string;
  signal?: AbortSignal;
}

/**
 * AC-F1 / AC-F5: POST /api/auth/login via the typed API client.
 *
 * Returns the raw LoginResponse on 2xx. Throws AuthApiError otherwise so the
 * caller can surface AC-F3 / AC-F6 toasts.
 */
export async function loginWithPassword(
  body: LoginRequest,
  opts: LoginOptions = {},
): Promise<LoginResponse> {
  const base = resolveApiBase(opts);
  const url = `${base}${LOGIN_ENDPOINT}`;

  let resp: Response;
  try {
    resp = await fetch(url, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      signal: opts.signal,
      credentials: "include",
    });
  } catch (e) {
    if ((e as { name?: string }).name === "AbortError") {
      throw e;
    }
    throw new AuthApiError("auth.network_error", "network error", 0, LOGIN_ENDPOINT);
  }

  if (!resp.ok) {
    const { code, message } = await readErrorBody(resp);
    throw new AuthApiError(code, message, resp.status, LOGIN_ENDPOINT);
  }

  return (await resp.json()) as LoginResponse;
}

/**
 * AC-F2 / AC-F7 / AC-F8: POST /api/auth/mfa/verify via the typed API client.
 *
 * Called after loginWithPassword() returns mfa_required=true. The UI surfaces
 * the S-053 mfa_challenge dialog to collect the TOTP code, then invokes this
 * helper to swap the pending session for a real access_token.
 */
export async function verifyMfaCode(
  body: MfaVerifyRequest,
  opts: LoginOptions = {},
): Promise<MfaVerifyResponse> {
  const base = resolveApiBase(opts);
  const url = `${base}${MFA_VERIFY_ENDPOINT}`;

  let resp: Response;
  try {
    resp = await fetch(url, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      signal: opts.signal,
      credentials: "include",
    });
  } catch (e) {
    if ((e as { name?: string }).name === "AbortError") {
      throw e;
    }
    throw new AuthApiError(
      "auth.network_error",
      "network error",
      0,
      MFA_VERIFY_ENDPOINT,
    );
  }

  if (!resp.ok) {
    const { code, message } = await readErrorBody(resp);
    throw new AuthApiError(code, message, resp.status, MFA_VERIFY_ENDPOINT);
  }

  return (await resp.json()) as MfaVerifyResponse;
}

/**
 * AC-F4: resolve the next-route target after a successful login.
 *
 * Spec (screens.json[S-001].transitions): "account_dashboard or
 * workspace_dashboard (last visited)". We honour last_visited if present
 * (typed string in localStorage under bf:last_visited), otherwise fall back
 * to /workspaces (workspace dashboard) which is the public landing target.
 */
export const LAST_VISITED_STORAGE_KEY = "bf:last_visited";
export const POST_LOGIN_FALLBACK_PATH = "/workspaces";

export function resolvePostLoginPath(
  lastVisited?: string | null,
): string {
  if (lastVisited && typeof lastVisited === "string" && lastVisited.startsWith("/")) {
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
