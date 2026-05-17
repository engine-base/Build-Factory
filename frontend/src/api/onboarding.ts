/**
 * T-V3-C-39 / S-048 — Typed client for /api/me/onboarding (Feature F-027).
 *
 * Backend contracts (T-V3-B-29 ONBOARDING 実装済 — backend/routers/onboarding.py):
 *   GET   /api/me/onboarding          — get_me_onboarding
 *   POST  /api/me/onboarding/advance  — post_me_onboarding_advance
 *   POST  /api/me/onboarding/skip     — post_me_onboarding_skip
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml#/paths/~1api~1me~1onboarding
 *
 * EARS AC mapping (T-V3-C-39):
 *   AC-F1: 401 → page redirect to /login (S-001) handled by the page via
 *          {@link OnboardingApiError.status} === 401
 *   AC-F2: GET state during skeleton phase → {@link getOnboardingState}
 *
 * Non-technical error toast envelope follows the project-wide FastAPI contract:
 *   { detail: { code: string; message: string } }
 */

import { env } from "@/env";

export const ONBOARDING_ENDPOINT = "/api/me/onboarding";
export const ONBOARDING_ADVANCE_ENDPOINT = "/api/me/onboarding/advance";
export const ONBOARDING_SKIP_ENDPOINT = "/api/me/onboarding/skip";

// --------------------------------------------------------------------------
// Types (mirror backend Pydantic models — backend/routers/onboarding.py)
// --------------------------------------------------------------------------

/** GET /api/me/onboarding response shape. */
export interface OnboardingStateResponse {
  /** Opaque state descriptor (welcome|setup|ai_intro|done). */
  state: string;
  /** Current onboarding step id (e.g. "welcome"). */
  current_step: string;
  /** True once all required steps have been advanced or skipped. */
  completed: boolean;
}

/** POST /api/me/onboarding/advance request shape. */
export interface AdvanceRequest {
  /** Step id being completed (e.g. "welcome"). */
  step: string;
  /** Step-scoped payload (free-form per backend service contract). */
  payload?: Record<string, unknown>;
}

/** POST /api/me/onboarding/advance response shape. */
export interface AdvanceResponse {
  /** Next step id (null when flow completes). */
  next_step: string | null;
  /** True iff the advance call completed the full flow. */
  completed: boolean;
  /** Echo of the step now active after the advance (welcome→setup, etc.). */
  current_step?: string;
}

/** POST /api/me/onboarding/skip request shape. */
export interface SkipRequest {
  /** Optional step id to skip (defaults to current_step server-side). */
  step?: string;
}

/** POST /api/me/onboarding/skip response shape. */
export interface SkipResponse {
  /** ISO 8601 timestamp at which the skip was recorded. */
  skipped_at: string;
  /** Next step id, or null when the flow short-circuits to done. */
  next_step?: string | null;
  /** Whether the entire flow is now considered complete. */
  completed?: boolean;
}

// --------------------------------------------------------------------------
// Error class (AC-F1: 401 surfaces non-leaky message + lets caller redirect)
// --------------------------------------------------------------------------

interface BackendErrorEnvelope {
  detail?: { code?: string; message?: string } | string;
}

/**
 * Thrown for any non-2xx response from the /api/me/onboarding endpoints.
 *
 * `.toUserMessage()` returns a non-technical, end-user friendly message that
 * references the failing endpoint and never includes raw server stack traces,
 * backend exception class names, or SQL details.
 */
export class OnboardingApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly endpoint: string;

  constructor(code: string, message: string, status: number, endpoint: string) {
    super(message);
    this.name = "OnboardingApiError";
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
  404: "オンボーディング状態が見つかりませんでした",
  409: "ステップの順序が一致しません",
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

export interface OnboardingRequestOptions {
  apiBase?: string;
  signal?: AbortSignal;
  /** Bearer token (Authorization: Bearer ...) — authenticated role required. */
  authToken?: string | null;
  /** Test seam — defaults to global fetch. */
  fetchImpl?: typeof fetch;
}

function resolveApiBase(opts: OnboardingRequestOptions): string {
  if (opts.apiBase) return opts.apiBase;
  const fromEnv = env.NEXT_PUBLIC_API_URL;
  return (fromEnv ?? "http://localhost:8001").replace(/\/$/, "");
}

async function parseError(
  response: Response,
  endpoint: string,
): Promise<OnboardingApiError> {
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
    // Non-JSON body — keep the synthesised message. Never leak raw body.
  }
  return new OnboardingApiError(code, message, response.status, endpoint);
}

async function request<TOut>(
  endpoint: string,
  init: RequestInit,
  opts: OnboardingRequestOptions,
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
    throw new OnboardingApiError(
      "NETWORK_ERROR",
      "network error",
      0,
      endpoint,
    );
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

/** GET /api/me/onboarding — current onboarding flow state. */
export function getOnboardingState(
  opts: OnboardingRequestOptions = {},
): Promise<OnboardingStateResponse> {
  return request<OnboardingStateResponse>(
    ONBOARDING_ENDPOINT,
    { method: "GET" },
    opts,
  );
}

/** POST /api/me/onboarding/advance — mark a step as completed and pull the next. */
export function advanceOnboarding(
  body: AdvanceRequest,
  opts: OnboardingRequestOptions = {},
): Promise<AdvanceResponse> {
  return request<AdvanceResponse>(
    ONBOARDING_ADVANCE_ENDPOINT,
    { method: "POST", body: JSON.stringify({ payload: {}, ...body }) },
    opts,
  );
}

/** POST /api/me/onboarding/skip — skip the current (or named) step. */
export function skipOnboarding(
  body: SkipRequest = {},
  opts: OnboardingRequestOptions = {},
): Promise<SkipResponse> {
  return request<SkipResponse>(
    ONBOARDING_SKIP_ENDPOINT,
    { method: "POST", body: JSON.stringify(body) },
    opts,
  );
}
