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
}
