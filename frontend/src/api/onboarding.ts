/**
 * T-V3-C-40 / F-027: Typed client for onboarding (welcome / setup / AI intro).
 *
 * Backend contracts (T-V3-B-29 / merged via PR #342):
 *   - GET  /api/me/onboarding        — backend/routers/me.py::get_me_onboarding
 *   - POST /api/me/onboarding/advance — backend/routers/me.py::post_me_onboarding_advance
 *   - POST /api/me/onboarding/skip    — backend/routers/me.py::post_me_onboarding_skip
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml#/api/me/onboarding{,/advance,/skip}
 *
 * Errors follow the project-wide {detail: {code, message}} contract. The
 * thrown OnboardingApiError surfaces a non-technical, endpoint-tagged message
 * for UI toasts and never leaks server stack traces (AC-F1 on S-049 family).
 */

export const ONBOARDING_GET_ENDPOINT = "/api/me/onboarding";
export const ONBOARDING_ADVANCE_ENDPOINT = "/api/me/onboarding/advance";
export const ONBOARDING_SKIP_ENDPOINT = "/api/me/onboarding/skip";

// ---------------------------------------------------------------------------
// Wire types — match openapi.yaml verbatim.
// ---------------------------------------------------------------------------

export type OnboardingStep = "welcome" | "project_setup" | "ai_intro" | string;

export interface OnboardingState {
  /** Current high-level state descriptor (object per openapi v3 schema). */
  state: string;
  /** Active step key (e.g. "project_setup"). */
  current_step: OnboardingStep;
  completed: boolean;
}

export interface OnboardingAdvanceRequest {
  /** Step key the client just completed. */
  step: OnboardingStep;
  /**
   * Step-specific payload (workspace_setup_wizard form values etc.).
   * Free-form by openapi schema; the backend validates per-step.
   */
  payload: Record<string, unknown>;
}

export interface OnboardingAdvanceResponse {
  next_step: OnboardingStep | "complete";
  completed: boolean;
}

export interface OnboardingSkipRequest {
  reason?: string | null;
}

export interface OnboardingSkipResponse {
  skipped_at: string;
}

/** Workspace setup wizard form payload (Step 2 / 3 — S-049). */
export interface WorkspaceSetupWizardPayload {
  /** 案件名 — required, 1..128 chars. */
  workspace_name: string;
  /** 案件種別: 受託 / 内製 / OSS. */
  project_kind: "受託" | "内製" | "OSS";
  /** 想定期間 (フリーテキスト. 1ヶ月 / 3ヶ月 / 6ヶ月 / 未定). */
  duration: string;
  /** ヒアリング開始時の AI 社員 (mary / preston / secretary). */
  ai_employee: "mary" | "preston" | "secretary";
  /** 月間トークン上限 (任意). */
  monthly_token_cap?: number;
  /** 並列セッション上限 (任意). */
  parallel_session_cap?: number;
}

// ---------------------------------------------------------------------------
// Error envelope.
// ---------------------------------------------------------------------------

/** Thrown for any non-2xx response from the onboarding endpoints. */
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

  /**
   * Build a non-technical, endpoint-tagged user-facing message.
   * Never leaks server stack traces (AC-F1). The endpoint stays visible so
   * QA / support can correlate without exposing internals.
   */
  toUserMessage(): string {
    if (this.status === 401) {
      return `サインインが必要です (${this.endpoint})`;
    }
    if (this.status === 403) {
      return `権限がありません (${this.endpoint})`;
    }
    if (this.status === 409) {
      return `この操作は現在の状態では実行できません (${this.endpoint})`;
    }
    if (this.status === 422) {
      return `入力内容を確認してください (${this.endpoint})`;
    }
    if (this.status >= 500) {
      return `処理に失敗しました。時間を置いて再試行してください (${this.endpoint})`;
    }
    return `処理に失敗しました (${this.endpoint})`;
  }
}

// ---------------------------------------------------------------------------
// Internal helpers.
// ---------------------------------------------------------------------------

interface ServerErrorEnvelope {
  detail?: {
    code?: string;
    message?: string;
  };
}

async function parseError(
  resp: Response,
  endpoint: string,
): Promise<OnboardingApiError> {
  let code = `HTTP_${resp.status}`;
  let message = `request failed: ${resp.status}`;
  try {
    const body = (await resp.json()) as ServerErrorEnvelope;
    if (body?.detail?.code) code = body.detail.code;
    if (body?.detail?.message) message = body.detail.message;
  } catch {
    // Fall through with default code/message.
  }
  return new OnboardingApiError(code, message, resp.status, endpoint);
}

// ---------------------------------------------------------------------------
// Public API.
// ---------------------------------------------------------------------------

/**
 * GET /api/me/onboarding — fetch the current onboarding state for the
 * authenticated user. Used by S-049 to verify the wizard is on the correct
 * step (project_setup) and to prefill any previously saved values.
 */
export async function getOnboardingState(): Promise<OnboardingState> {
  const resp = await fetch(ONBOARDING_GET_ENDPOINT, {
    method: "GET",
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  });
  if (!resp.ok) {
    throw await parseError(resp, ONBOARDING_GET_ENDPOINT);
  }
  return (await resp.json()) as OnboardingState;
}

/**
 * POST /api/me/onboarding/advance — submit the current step's payload and
 * advance to the next step. Returns the next_step the client should render.
 */
export async function advanceOnboarding(
  body: OnboardingAdvanceRequest,
): Promise<OnboardingAdvanceResponse> {
  const resp = await fetch(ONBOARDING_ADVANCE_ENDPOINT, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    throw await parseError(resp, ONBOARDING_ADVANCE_ENDPOINT);
  }
  return (await resp.json()) as OnboardingAdvanceResponse;
}

/**
 * POST /api/me/onboarding/skip — skip an optional step. Required steps
 * (project_setup) return 409 from the backend; the UI must NOT call skip
 * on a required step.
 */
export async function skipOnboarding(
  body: OnboardingSkipRequest = {},
): Promise<OnboardingSkipResponse> {
  const resp = await fetch(ONBOARDING_SKIP_ENDPOINT, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    throw await parseError(resp, ONBOARDING_SKIP_ENDPOINT);
  }
  return (await resp.json()) as OnboardingSkipResponse;
}

// ---------------------------------------------------------------------------
// Auth/session helpers — UNWANTED redirect target for unauthenticated visitors
// (AC-F1 on S-049: redirect to /login if not authenticated).
// ---------------------------------------------------------------------------

export const LOGIN_REDIRECT_PATH = "/login";

/** localStorage key used by the auth layer to remember the last-visited path. */
export const LAST_VISITED_STORAGE_KEY = "buildfactory.last_visited";

/** Token storage key matching the rest of the frontend auth flow. */
export const ACCESS_TOKEN_STORAGE_KEY = "buildfactory.access_token";

/**
 * Lightweight authentication probe used by the S-049 page to decide whether
 * to render the wizard or redirect to /login (AC-F1 — UNWANTED).
 * Server-side rendering returns `false` so the initial render shows the
 * skeleton loader; the client effect then makes the redirect decision.
 */
export function hasAccessToken(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return Boolean(window.localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY));
  } catch {
    return false;
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
