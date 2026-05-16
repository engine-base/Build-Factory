/**
 * T-V3-C-06 / F-024 / S-006: Typed client for the account dashboard endpoint.
 *
 * Backend contract:
 *   backend/routers/accounts.py::get_accounts_by_id_dashboard (T-V3-B-27)
 *   backend/services/account_dashboard.py::get_account_dashboard
 *   docs/api-design/2026-05-16_v3/openapi.yaml#/paths/~1api~1accounts~1{id}~1dashboard
 *
 * 3-tier AC mapping (T-V3-C-06):
 *   functional.AC-F1 → `getAccountDashboard()` performs GET on the canonical
 *                      endpoint, returning the typed {@link AccountDashboardResponse}.
 *   functional.AC-F2 → 4xx/5xx → throws {@link DashboardApiError} whose
 *                      `toUserMessage()` references the failing endpoint and
 *                      never embeds server stack traces.
 *   functional.AC-F3 → caller receives an aggregate that the backend computes
 *                      across every workspace the caller belongs to inside the
 *                      account (validated server-side).
 *   functional.AC-F4 → 401 + code === "session_expired" → throws
 *                      {@link SessionExpiredError} so the UI can render the
 *                      S-054 dialog and preserve any in-flight form data in
 *                      localStorage.
 *
 * Co-located with the future global search endpoints documented in F-024.
 */

export const ACCOUNT_DASHBOARD_ENDPOINT_PATTERN =
  "/api/accounts/{id}/dashboard";

/** Build the canonical endpoint path for the given account id. */
export function accountDashboardEndpoint(accountId: string | number): string {
  // We intentionally do NOT validate the id here — the backend returns 422 on
  // bad shape so the caller can render the canonical endpoint inside a toast.
  return `/api/accounts/${encodeURIComponent(String(accountId))}/dashboard`;
}

/** Per-workspace KPI row aggregated by the backend. */
export interface DashboardWorkspaceSummary {
  /** Workspace id (numeric in the local backend, UUID-shaped in production). */
  id: number | string;
  /** Display name (verbatim from the workspaces table). */
  name: string;
  /** Lifecycle status — running / review / idle / archived etc. */
  status?: string | null;
  /** Caller's role inside the workspace. */
  role?: string | null;
  /** 0..1 phase progress ratio. */
  progress: number;
  /** Completed task count in the workspace. */
  completed_tasks: number;
  /** Currently running session count. */
  running_sessions: number;
  /** Monthly cost in JPY (server pre-aggregated, no client-side currency math). */
  monthly_cost_jpy: number;
  /** Pending approval count (Pending Reviews KPI source). */
  pending_approvals: number;
}

/** Account-level KPI aggregate covering every workspace the caller belongs to. */
export interface DashboardAccountKpi {
  workspace_count: number;
  total_progress: number;
  completed_tasks: number;
  running_sessions: number;
  monthly_cost_jpy: number;
  pending_approvals: number;
}

/** Shape returned by GET /api/accounts/{id}/dashboard. */
export interface AccountDashboardResponse {
  account_id: number | string;
  workspaces: DashboardWorkspaceSummary[];
  kpi: DashboardAccountKpi;
  computed_at: number;
  duration_ms: number;
}

/** Backend FastAPI error envelope: `{detail: {code, message, errors?}}`. */
interface BackendErrorEnvelope {
  detail?:
    | string
    | {
        code?: string;
        message?: string;
        errors?: unknown;
      };
}

/** Thrown for any non-2xx response from the dashboard endpoint. */
export class DashboardApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly endpoint: string;

  constructor(code: string, message: string, status: number, endpoint: string) {
    super(message);
    this.name = "DashboardApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * AC-F2: produce a non-technical, end-user friendly message tagged with the
   * failing endpoint. Never embeds stack traces / SQL / exception class names.
   */
  toUserMessage(): string {
    const friendly = DASHBOARD_USER_MESSAGES[this.status] ?? DASHBOARD_USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

/**
 * AC-F4 sentinel — backend returned 401 with `code === "session_expired"`.
 * Allows the UI to discriminate from other 401s (auth missing, signature
 * invalid) and render the dedicated S-054 dialog.
 */
export class SessionExpiredError extends DashboardApiError {
  constructor(endpoint: string, message = "session expired") {
    super("session_expired", message, 401, endpoint);
    this.name = "SessionExpiredError";
  }
}

const DASHBOARD_USER_MESSAGES: Record<number | "default", string> = {
  400: "リクエストに問題があります",
  401: "サインインが必要です",
  403: "このアカウントを閲覧する権限がありません",
  404: "アカウントが見つかりませんでした",
  422: "入力内容を確認してください",
  429: "リクエストが多すぎます。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "ダッシュボードを読み込めませんでした",
};

function resolveApiBase(apiBase?: string): string {
  if (apiBase) return apiBase;
  if (typeof process !== "undefined") {
    const env = process.env ?? {};
    if (env.NEXT_PUBLIC_API_URL) return env.NEXT_PUBLIC_API_URL;
    if (env.NEXT_PUBLIC_API_BASE) return env.NEXT_PUBLIC_API_BASE;
  }
  return "http://localhost:8001";
}

export interface AccountDashboardRequestOptions {
  apiBase?: string;
  signal?: AbortSignal;
  /** Bearer token (required: endpoint demands `member` role). */
  authToken?: string | null;
  /** Test seam — defaults to the global `fetch`. */
  fetchImpl?: typeof fetch;
}

/**
 * AC-F1: GET /api/accounts/{id}/dashboard via the typed client.
 *
 * Throws {@link DashboardApiError} on non-2xx (or
 * {@link SessionExpiredError} for the 401 + `session_expired` case) so the
 * caller can surface a toast / S-054 dialog without leaking server traces.
 */
export async function getAccountDashboard(
  accountId: string | number,
  opts: AccountDashboardRequestOptions = {},
): Promise<AccountDashboardResponse> {
  const endpoint = accountDashboardEndpoint(accountId);
  const baseUrl = resolveApiBase(opts.apiBase).replace(/\/$/, "");
  const url = `${baseUrl}${endpoint}`;
  const fetchImpl = opts.fetchImpl ?? fetch;

  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  if (opts.authToken) headers.Authorization = `Bearer ${opts.authToken}`;

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "GET",
      headers,
      signal: opts.signal,
      credentials: "include",
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") throw err;
    // network-level failure (no response) — don't leak the cause to the UI.
    throw new DashboardApiError(
      "network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
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
      // intentionally ignore parse failure — keep generic fallback so we never
      // forward raw HTML / stack-traced JSON to the UI (AC-F2).
    }

    // AC-F4: 401 + code "session_expired" is a special sentinel for the UI to
    // render the S-054 dialog instead of a generic toast.
    if (response.status === 401 && code === "session_expired") {
      throw new SessionExpiredError(endpoint, message);
    }
    throw new DashboardApiError(code, message, response.status, endpoint);
  }

  return (await response.json()) as AccountDashboardResponse;
}
