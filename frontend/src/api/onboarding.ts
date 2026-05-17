/**
 * T-V3-C-41 / F-027 / S-050: Typed client for the onboarding flow endpoints
 * backing the S-048 / S-049 / S-050 onboarding screens.
 *
 * Backend contracts (T-V3-B-29 / drift fix queue):
 *   GET    /api/me/onboarding              — backend/routers/me.py::get_me_onboarding
 *   POST   /api/me/onboarding/advance      — backend/routers/me.py::post_me_onboarding_advance
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml#/paths/~1api~1me~1onboarding
 *
 * EARS AC mapping (S-050 / T-V3-C-41):
 *   functional.AC-F1: UNWANTED unauthenticated visitor -> 401 surfaces here so
 *     the page can redirect to /login (S-001) without leaking workspace data.
 *   functional.AC-F2: STATE-DRIVEN data fetching surface — the typed client is
 *     the boundary between fetch state and the page's skeleton/loaded swap.
 *
 * Error envelope follows the project-wide FastAPI contract:
 *   { detail: { code: string; message: string } }
 */

import { env } from "@/env";

// --------------------------------------------------------------------------
// Endpoint constants
// --------------------------------------------------------------------------

export const ONBOARDING_GET_ENDPOINT = "/api/me/onboarding";
export const ONBOARDING_ADVANCE_ENDPOINT = "/api/me/onboarding/advance";

// --------------------------------------------------------------------------
// Domain types — kept narrow so S-050 surfaces only the AI-intro slice.
// --------------------------------------------------------------------------

/** OpenAPI response shape for GET /api/me/onboarding (F-027). */
export interface OnboardingStateResponse {
  /** Opaque server state descriptor (raw v3 OpenAPI descriptor). */
  state?: string | null;
  /** Discrete step id — for S-050 the value is "ai_employee_intro". */
  current_step?: string | null;
  completed?: boolean | null;
}

/** OpenAPI response shape for POST /api/me/onboarding/advance (F-027). */
export interface OnboardingAdvanceResponse {
  next_step?: string | null;
  completed?: boolean | null;
}

/**
 * Persona card surfaced on S-050. The route exposes a static catalog matching
 * the mock (`docs/mocks/2026-05-15_v3/onboarding/S-050-ai-employee-intro.html`)
 * for the canonical BMAD 10 personas. A separate F-003 fetch is *not* required
 * by S-050 because the screen is informational only; if/when the org chart
 * becomes data-driven the catalog can be merged with /api/ai-employees/org-chart.
 */
export interface AiEmployeePersonaCard {
  id: string;
  name: string;
  initials: string;
  role: string;
  /** Tailwind color class for the avatar bg (must remain inside the design-system). */
  colorClass: string;
}

// --------------------------------------------------------------------------
// Error envelope + class (AC-F1 — non-technical, no stack-trace leak)
// --------------------------------------------------------------------------

interface BackendErrorEnvelope {
  detail?: { code?: string; message?: string } | string;
}

const USER_MESSAGES: Record<number | "default", string> = {
  400: "リクエストが不正です",
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

/** Thrown for any non-2xx response from the /api/me/onboarding endpoints. */
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

  /** AC-F1 (S-050 UNWANTED 401): user-facing summary, no stack-trace leak. */
  toUserMessage(): string {
    return `${friendlyMessageForStatus(this.status)} (${this.endpoint})`;
  }
}

// --------------------------------------------------------------------------
// Internal HTTP helper
// --------------------------------------------------------------------------

export interface OnboardingRequestOptions {
  apiBase?: string;
  signal?: AbortSignal;
  /** Bearer token (Authorization: Bearer ...) for the authenticated role. */
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
  try {
    return (await response.json()) as TOut;
  } catch {
    return {} as TOut;
  }
}

// --------------------------------------------------------------------------
// Public API
// --------------------------------------------------------------------------

/**
 * AC-F1/AC-F2 surface: GET /api/me/onboarding — returns the user's onboarding
 * progress. The S-050 page uses this only to verify the session is still alive
 * (401 -> redirect /login); it intentionally does not block render on the
 * response because the persona catalog is static.
 */
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
 * POST /api/me/onboarding/advance — moves the user from S-050 to S-012
 * (workspace dashboard). The S-050 page wires this to the primary CTA.
 */
export function advanceOnboarding(
  opts: OnboardingRequestOptions = {},
): Promise<OnboardingAdvanceResponse> {
  return request<OnboardingAdvanceResponse>(
    ONBOARDING_ADVANCE_ENDPOINT,
    { method: "POST", body: JSON.stringify({}) },
    opts,
  );
}

// --------------------------------------------------------------------------
// Persona catalog (mock-aligned — never fetched from network on S-050).
// --------------------------------------------------------------------------

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
