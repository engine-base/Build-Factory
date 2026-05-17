/**
 * T-V3-C-42 / F-017 / S-040: Typed client for the observability cost summary
 * endpoint backing the コスト ダッシュボード screen.
 *
 * Backend contract (T-V3-B-23, REUSE/REFACTOR):
 *   GET /api/observability/cost-summary
 *     ?workspace_id=<uuid>&from=<YYYY-MM-DD>&to=<YYYY-MM-DD>
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml
 *          #/paths/~1api~1observability~1cost-summary
 *
 * Auth model: bearerAuth (workspace_admin role enforced server-side by
 * `cost_log:workspace_admin_rw` access policy).
 *
 * The thrown {@link CostDashboardApiError} surfaces a non-technical, end-user
 * friendly message tagged with the failing endpoint (AC-F1) without leaking
 * server stack traces or internal SQL fragments.
 *
 * 3-tier AC mapping (docs/audit/2026-05-16_v3/T-V3-C-42.md):
 *   functional.AC-F1 → `getCostSummary()` GETs cost summary. 2xx body is
 *                      returned; 4xx/5xx → CostDashboardApiError carrying
 *                      endpoint + status for the page's toast.
 *   functional.AC-F2 → on 401 the page surfaces a "sign-in required" toast
 *                      tagged with the endpoint and renders an empty state.
 *   functional.AC-F3 → response shape preserves `total_usd`, `by_provider`,
 *                      and `by_user` breakdowns (mirrors openapi.yaml).
 *
 * @screen-id S-040
 * @feature-id F-017
 * @task-ids T-V3-C-42
 * @entities E-027,E-028
 * @phase Phase 1
 */

// --------------------------------------------------------------------------
// Endpoint helpers (exposed so callers / tests can assert canonical paths).
// --------------------------------------------------------------------------

export const COST_SUMMARY_ENDPOINT = "/api/observability/cost-summary";

export interface CostSummaryQuery {
  workspace_id?: string;
  /** YYYY-MM-DD inclusive lower bound. */
  from?: string;
  /** YYYY-MM-DD inclusive upper bound. */
  to?: string;
}

/** Render `GET /api/observability/cost-summary?...` with the query inlined. */
export function buildCostSummaryEndpoint(query: CostSummaryQuery = {}): string {
  const params = new URLSearchParams();
  if (query.workspace_id) params.set("workspace_id", query.workspace_id);
  if (query.from) params.set("from", query.from);
  if (query.to) params.set("to", query.to);
  const qs = params.toString();
  return qs ? `${COST_SUMMARY_ENDPOINT}?${qs}` : COST_SUMMARY_ENDPOINT;
}

// --------------------------------------------------------------------------
// Schema (mirrors openapi.yaml#GET /api/observability/cost-summary 200 body)
// --------------------------------------------------------------------------

/** Per-provider USD breakdown (e.g. {anthropic: 8.42, openai: 1.20}). */
export type CostByProvider = Record<string, number>;

/** Per-user / per-AI-employee USD breakdown. */
export type CostByUser = Record<string, number>;

/** Per-day USD breakdown keyed by ISO date string (YYYY-MM-DD). */
export type CostByDay = Record<string, number>;

/**
 * GET /api/observability/cost-summary 200 body shape.
 *
 * The openapi.yaml descriptor types `by_provider` / `by_user` as a free-form
 * "object" descriptor; we widen to typed records here so the page can iterate
 * safely. Unknown extra keys are tolerated for forward-compat.
 */
export interface CostSummaryResponse {
  total_usd: number;
  by_provider: CostByProvider;
  by_user: CostByUser;
  /** Optional daily-trend bucket (used by the 日別コスト推移 (15 日) section). */
  by_day?: CostByDay;
  /** Tolerate unknown server-side fields without breaking the typed client. */
  [extra: string]: unknown;
}

// --------------------------------------------------------------------------
// Error envelope (FastAPI {detail: {code, message}} contract).
// --------------------------------------------------------------------------

const USER_MESSAGES: Record<number | "default", string> = {
  400: "リクエストが不正です",
  401: "サインインが必要です",
  403: "この操作を実行する権限がありません",
  404: "対象が見つかりませんでした",
  409: "競合する状態のため操作を完了できませんでした",
  422: "入力内容を確認してください",
  429: "リクエストが多すぎます。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "コスト情報の取得に失敗しました",
};

/**
 * Structured error for the /api/observability/cost-summary endpoint.
 * `toUserMessage()` produces a non-technical sentence referencing the failing
 * endpoint without leaking server stack traces (AC-F1).
 */
export class CostDashboardApiError extends Error {
  public readonly code: string;
  public readonly status: number;
  public readonly endpoint: string;

  constructor(code: string, message: string, status: number, endpoint: string) {
    super(message);
    this.name = "CostDashboardApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * AC-F1: non-technical, end-user friendly message tagged with the failing
   * endpoint. Never embeds stack traces, SQL fragments, or raw exception
   * class names from the server.
   */
  toUserMessage(): string {
    const friendly = USER_MESSAGES[this.status] ?? USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

interface BackendErrorEnvelope {
  detail?:
    | string
    | {
        code?: string;
        message?: string;
        errors?: unknown;
      };
}

async function parseErrorEnvelope(
  response: Response,
  endpoint: string,
): Promise<CostDashboardApiError> {
  let code = "UNKNOWN_ERROR";
  let message = response.statusText || "request failed";
  try {
    const envelope = (await response.json()) as BackendErrorEnvelope;
    if (envelope && typeof envelope.detail === "object" && envelope.detail) {
      if (typeof envelope.detail.code === "string") code = envelope.detail.code;
      if (typeof envelope.detail.message === "string") {
        message = envelope.detail.message;
      }
    } else if (typeof envelope?.detail === "string") {
      message = envelope.detail;
    }
  } catch {
    // Non-JSON body — keep the synthesised message. We deliberately do not
    // embed the raw body to avoid leaking server stack traces (AC-F1).
  }
  return new CostDashboardApiError(code, message, response.status, endpoint);
}

// --------------------------------------------------------------------------
// Internal helpers
// --------------------------------------------------------------------------

export interface CostDashboardRequestOptions {
  apiBase?: string;
  signal?: AbortSignal;
  /** Bearer token forwarded as `Authorization: Bearer <token>`. */
  authToken?: string | null;
  /** Test seam — defaults to the global `fetch`. */
  fetchImpl?: typeof fetch;
}

function resolveApiBase(apiBase?: string): string {
  if (apiBase) return apiBase;
  if (typeof process !== "undefined") {
    const env = process.env ?? {};
    if (env.NEXT_PUBLIC_API_URL) return env.NEXT_PUBLIC_API_URL;
    if (env.NEXT_PUBLIC_API_BASE) return env.NEXT_PUBLIC_API_BASE;
  }
  return "http://localhost:8001";
}

function buildAuthHeader(
  opts: CostDashboardRequestOptions,
): Record<string, string> {
  if (!opts.authToken) return {};
  return { Authorization: `Bearer ${opts.authToken}` };
}

// --------------------------------------------------------------------------
// API functions
// --------------------------------------------------------------------------

/**
 * AC-F1 / AC-F3: GET /api/observability/cost-summary via the typed client.
 *
 * EVENT-DRIVEN: When the S-040 page mounts (or its date range changes), the
 * system shall call this client. The 2xx body is returned verbatim; any
 * non-2xx is converted to a {@link CostDashboardApiError} carrying the failing
 * endpoint so the UI can render a non-technical, endpoint-tagged toast.
 *
 * @throws CostDashboardApiError on 4xx / 5xx / network failure.
 */
export async function getCostSummary(
  query: CostSummaryQuery = {},
  opts: CostDashboardRequestOptions = {},
): Promise<CostSummaryResponse> {
  const endpoint = buildCostSummaryEndpoint(query);
  const baseUrl = resolveApiBase(opts.apiBase).replace(/\/$/, "");
  const url = `${baseUrl}${endpoint}`;
  const fetchImpl = opts.fetchImpl ?? fetch;

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "GET",
      headers: {
        Accept: "application/json",
        ...buildAuthHeader(opts),
      },
      signal: opts.signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") throw err;
    throw new CostDashboardApiError(
      "network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    data = {};
  }
  const obj = (data ?? {}) as Partial<CostSummaryResponse>;
  return {
    total_usd: typeof obj.total_usd === "number" ? obj.total_usd : 0,
    by_provider:
      obj.by_provider && typeof obj.by_provider === "object"
        ? (obj.by_provider as CostByProvider)
        : {},
    by_user:
      obj.by_user && typeof obj.by_user === "object"
        ? (obj.by_user as CostByUser)
        : {},
    by_day:
      obj.by_day && typeof obj.by_day === "object"
        ? (obj.by_day as CostByDay)
        : undefined,
  };
}
