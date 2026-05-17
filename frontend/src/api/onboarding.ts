/**
 * T-V3-C-39 / C-40 / C-41 — Onboarding flow typed client (F-027).
 *
 * Consolidated module backing the S-048 / S-049 / S-050 onboarding screens.
 * (Phase 1.0-fix Wave 0 D: reconciles three concurrent vertical-slice merges
 * that previously left the file with stacked duplicate declarations and a
 * missing comment opener that broke `next build`.)
 *
 * Backend contracts (T-V3-B-29 ONBOARDING — backend/routers/me.py):
 *   GET   /api/me/onboarding          — get_me_onboarding
 *   POST  /api/me/onboarding/advance  — post_me_onboarding_advance
 *   POST  /api/me/onboarding/skip     — post_me_onboarding_skip
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml#/paths/~1api~1me~1onboarding
 *
 * EARS AC mapping:
 *   functional.AC-F1 (UNWANTED unauthenticated visitor): 401 surfaces here so
 *     the page can redirect to /login (S-001) without leaking workspace data.
 *   functional.AC-F2 (STATE-DRIVEN data-fetch surface): the typed client is
 *     the boundary between fetch state and the page's skeleton/loaded swap.
 *
 * Errors follow the project-wide FastAPI contract:
 *   { detail: { code: string; message: string } }
 */

import { env } from "@/env";

// ---------------------------------------------------------------------------
// Endpoint constants.
// ---------------------------------------------------------------------------

export const ONBOARDING_GET_ENDPOINT = "/api/me/onboarding";
export const ONBOARDING_ADVANCE_ENDPOINT = "/api/me/onboarding/advance";
export const ONBOARDING_SKIP_ENDPOINT = "/api/me/onboarding/skip";
/** Test-friendly alias for the GET endpoint (S-048 spec compatibility). */
export const ONBOARDING_ENDPOINT = ONBOARDING_GET_ENDPOINT;

// ---------------------------------------------------------------------------
// Wire types — match openapi.yaml verbatim.
// ---------------------------------------------------------------------------

export type OnboardingStep =
  | "welcome"
  | "project_setup"
  | "ai_intro"
  | "ai_employee_intro"
  | string;

/** GET /api/me/onboarding response shape. */
export interface OnboardingStateResponse {
  /** Opaque server state descriptor (raw v3 OpenAPI descriptor). */
  state?: string | null;
  /** Discrete step id — for S-050 the value is "ai_employee_intro". */
  current_step?: OnboardingStep | null;
  /** True once all required steps have been advanced or skipped. */
  completed?: boolean | null;
}

/** Backwards-compat alias used by S-048/S-049 client code. */
export type OnboardingState = OnboardingStateResponse;

/** POST /api/me/onboarding/advance request shape. */
export interface OnboardingAdvanceRequest {
  /** Step id being completed (e.g. "welcome", "project_setup"). */
  step: OnboardingStep;
  /**
   * Step-specific payload (workspace_setup_wizard form values etc.).
   * Free-form per backend service contract.
   */
  payload?: Record<string, unknown>;
}

/** Shorter alias used by useWelcomeFirstLogin / tests. */
export type AdvanceRequest = OnboardingAdvanceRequest;

/** POST /api/me/onboarding/advance response shape. */
export interface OnboardingAdvanceResponse {
  next_step?: OnboardingStep | "complete" | null;
  completed?: boolean | null;
  /** Echo of the step now active after the advance (welcome → setup, etc.). */
  current_step?: OnboardingStep | null;
}

export type AdvanceResponse = OnboardingAdvanceResponse;

/** POST /api/me/onboarding/skip request shape. */
export interface OnboardingSkipRequest {
  /** Optional step id to skip (defaults to current_step server-side). */
  step?: OnboardingStep;
  reason?: string | null;
}

export type SkipRequest = OnboardingSkipRequest;

/** POST /api/me/onboarding/skip response shape. */
export interface OnboardingSkipResponse {
  /** ISO 8601 timestamp at which the skip was recorded. */
  skipped_at?: string;
  /** Next step id, or null when the flow short-circuits to done. */
  next_step?: OnboardingStep | null;
  /** Whether the entire flow is now considered complete. */
  completed?: boolean | null;
}

export type SkipResponse = OnboardingSkipResponse;

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

/**
 * Persona card surfaced on S-050. The route exposes a static catalog matching
 * the mock (`docs/mocks/2026-05-15_v3/onboarding/S-050-ai-employee-intro.html`)
 * for the canonical BMAD 10 personas.
 */
export interface AiEmployeePersonaCard {
  id: string;
  name: string;
  initials: string;
  role: string;
  /** Tailwind color class for the avatar bg (must remain inside the design-system). */
  colorClass: string;
}

// ---------------------------------------------------------------------------
// Auth / session helpers.
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
}

// ---------------------------------------------------------------------------
// Error envelope + class (AC-F1 — non-technical, no stack-trace leak).
// ---------------------------------------------------------------------------

interface BackendErrorEnvelope {
  detail?: { code?: string; message?: string } | string;
}

const USER_MESSAGES: Record<number | "default", string> = {
  400: "入力内容を確認してください",
  401: "サインインが必要です",
  403: "この操作を実行する権限がありません",
  404: "オンボーディング情報が見つかりませんでした",
  409: "状態が競合しています",
  422: "入力フォーマットが正しくありません",
  429: "リクエストが多すぎます。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "通信に失敗しました",
};

function friendlyMessageForStatus(status: number): string {
  return USER_MESSAGES[status] ?? USER_MESSAGES.default;
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

  /** AC-F1: user-facing summary, no stack-trace leak. */
  toUserMessage(): string {
    return `${friendlyMessageForStatus(this.status)} (${this.endpoint})`;
  }
}

// ---------------------------------------------------------------------------
// Internal HTTP helper.
// ---------------------------------------------------------------------------

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
  let code = `HTTP_${response.status}`;
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
    // Non-JSON body — keep synthesised message. AC-F1: never embed raw body.
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
  // If the endpoint is already absolute, use as-is; otherwise prefix the base.
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
  try {
    return (await response.json()) as TOut;
  } catch {
    return {} as TOut;
  }
}

// ---------------------------------------------------------------------------
// Public API.
// ---------------------------------------------------------------------------

/** GET /api/me/onboarding — current onboarding flow state. */
export function getOnboardingState(
  opts: OnboardingRequestOptions = {},
): Promise<OnboardingStateResponse> {
  return request<OnboardingStateResponse>(
    ONBOARDING_GET_ENDPOINT,
    { method: "GET" },
    opts,
  );
}

/**
 * POST /api/me/onboarding/advance — mark a step as completed and pull the next.
 * Accepts a `body` (preferred — provides step/payload) or no-arg for screens
 * that simply want to advance past a static intro (e.g. S-050).
 */
export function advanceOnboarding(
  body?: OnboardingAdvanceRequest,
  opts: OnboardingRequestOptions = {},
): Promise<OnboardingAdvanceResponse> {
  return request<OnboardingAdvanceResponse>(
    ONBOARDING_ADVANCE_ENDPOINT,
    {
      method: "POST",
      body: JSON.stringify(body ?? {}),
    },
    opts,
  );
}

/**
 * POST /api/me/onboarding/skip — skip the current (or named) step.
 * Required steps (project_setup) return 409 from the backend; the UI must NOT
 * call skip on a required step.
 */
export function skipOnboarding(
  body: OnboardingSkipRequest = {},
  opts: OnboardingRequestOptions = {},
): Promise<OnboardingSkipResponse> {
  return request<OnboardingSkipResponse>(
    ONBOARDING_SKIP_ENDPOINT,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
    opts,
  );
}

// ---------------------------------------------------------------------------
// Persona catalog (mock-aligned — never fetched from network on S-050).
// ---------------------------------------------------------------------------

/**
 * BMAD 10 ペルソナ catalog rendered on S-050. Keep in lock-step with
 * `docs/mocks/2026-05-15_v3/onboarding/S-050-ai-employee-intro.html` — Tier 1
 * structural diff (AC-R5) runs on this list.
 */
export const AI_EMPLOYEE_PERSONAS: readonly AiEmployeePersonaCard[] = [
  {
    id: "secretary",
    name: "secretary",
    initials: "SC",
    role: "PM 代理",
    colorClass: "bg-purple-500",
  },
  {
    id: "mary",
    name: "mary",
    initials: "MR",
    role: "BA",
    colorClass: "bg-emerald-500",
  },
  {
    id: "preston",
    name: "preston",
    initials: "PS",
    role: "PM",
    colorClass: "bg-amber-500",
  },
  {
    id: "winston",
    name: "winston",
    initials: "WS",
    role: "Architect",
    colorClass: "bg-blue-500",
  },
  {
    id: "sally",
    name: "sally",
    initials: "SL",
    role: "PO",
    colorClass: "bg-eb-500",
  },
  {
    id: "devon",
    name: "devon",
    initials: "DV",
    role: "Dev",
    colorClass: "bg-eb-500",
  },
  {
    id: "quinn",
    name: "quinn",
    initials: "QN",
    role: "QA",
    colorClass: "bg-amber-500",
  },
  {
    id: "reviewer",
    name: "reviewer",
    initials: "RV",
    role: "PR",
    colorClass: "bg-slate-500",
  },
  {
    id: "brand",
    name: "brand",
    initials: "BR",
    role: "Brand",
    colorClass: "bg-pink-500",
  },
  {
    id: "mockup",
    name: "mockup",
    initials: "MK",
    role: "UI",
    colorClass: "bg-cyan-500",
  },
] as const;
