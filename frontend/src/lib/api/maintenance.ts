/**
 * T-V3-C-56 / S-047: Typed client for the maintenance status endpoint.
 *
 * Mock-impl source of truth:
 *   docs/mocks/2026-05-15_v3/system/S-047-maintenance.html
 * Spec source of truth:
 *   docs/functional-breakdown/2026-05-16_v3/screens.json#S-047
 *
 * Backend contract (canonical, owned by ops team — read-only):
 *   GET /api/system/maintenance — returns {status, started_at, eta_at,
 *                                          items, status_page_url}
 *
 * Error envelope follows the FastAPI project-wide contract:
 *   { detail: { code, message } }
 *
 * Auth behaviour:
 *   - 200 OK         : maintenance status payload (any authenticated user).
 *   - 401 Unauthorized : page redirects to /login (S-001) per AC-F1
 *                       (work_package_boundary AC `If an unauthenticated visitor`).
 *   - 404 Not Found  : no active maintenance window — page renders empty state.
 *
 * `MAINTENANCE` env flag forwarding is handled at the middleware layer
 * (`frontend/middleware.ts`), which 307-forwards every request to /maintenance
 * with HTTP 503 when MAINTENANCE_MODE=1 (T-V3-C-56 middleware addition).
 */

export const MAINTENANCE_STATUS_ENDPOINT = "/api/system/maintenance";

export interface MaintenanceItem {
  /** Free-text bullet rendered in the "メンテナンス内容" list. */
  label: string;
}

export interface MaintenanceStatus {
  /** "scheduled" | "in_progress" | "completed". Page only renders when in_progress. */
  status: "scheduled" | "in_progress" | "completed";
  /** ISO-8601 maintenance window start time (server clock). */
  started_at: string;
  /** ISO-8601 expected end time (server clock). */
  eta_at: string;
  /** Bulleted maintenance items (DB migration, RLS補完, etc.). */
  items: MaintenanceItem[];
  /** External status page link (e.g. status.engine-base.com). */
  status_page_url: string;
}

/** Thrown for any non-2xx response from /api/system/maintenance. */
export class MaintenanceApiError extends Error {
  code: string;
  status: number;
  endpoint: string;

  constructor(code: string, message: string, status: number, endpoint: string) {
    super(message);
    this.name = "MaintenanceApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }
}

export interface MaintenanceRequestOptions {
  apiBase?: string;
  signal?: AbortSignal;
}

function resolveApiBase(opts: MaintenanceRequestOptions): string {
  if (opts.apiBase) return opts.apiBase;
  if (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_BASE) {
    return process.env.NEXT_PUBLIC_API_BASE;
  }
  return "http://localhost:8001";
}

async function readErrorDetail(
  resp: Response,
): Promise<{ code: string; message: string }> {
  let code = "maintenance.unknown";
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
    // Keep generic fallback — never leak server traces.
  }
  return { code, message };
}

/**
 * AC-F1 / AC-F2: GET /api/system/maintenance.
 *
 * Returns the {@link MaintenanceStatus} body on 2xx. Throws
 * {@link MaintenanceApiError} otherwise so the page can:
 *   - On 401 → redirect to /login (S-001) per AC-F1.
 *   - On other non-2xx → render a friendly fallback while the skeleton
 *     dismisses atomically per AC-F2.
 */
export async function getMaintenanceStatus(
  opts: MaintenanceRequestOptions = {},
): Promise<MaintenanceStatus> {
  const base = resolveApiBase(opts);
  const url = `${base}${MAINTENANCE_STATUS_ENDPOINT}`;

  let resp: Response;
  try {
    resp = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: opts.signal,
      credentials: "include",
    });
  } catch (e) {
    if ((e as { name?: string }).name === "AbortError") {
      throw e;
    }
    throw new MaintenanceApiError(
      "maintenance.network_error",
      "network error",
      0,
      MAINTENANCE_STATUS_ENDPOINT,
    );
  }

  if (!resp.ok) {
    const { code, message } = await readErrorDetail(resp);
    throw new MaintenanceApiError(
      code,
      message,
      resp.status,
      MAINTENANCE_STATUS_ENDPOINT,
    );
  }

  return (await resp.json()) as MaintenanceStatus;
}
