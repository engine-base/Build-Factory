/**
 * T-V3-C-22 / C-23 — Typed client for the Export / Delivery endpoints (F-031).
 *
 * Consolidated module backing the S-061 (仕様書 PDF) and S-062 (納品レポート)
 * screens.
 *
 * (Phase 1.0-fix Wave 0 D: reconciles two concurrent vertical-slice merges
 * that previously left the file with stacked duplicate declarations and a
 * missing comment opener that broke `next build` type-check.)
 *
 * Backend contracts:
 *   POST /api/workspaces/{id}/exports       — queue spec_pdf / delivery_report job
 *   GET  /api/exports/{id}                  — poll status, fetch download_url
 *   GET  /api/workspaces/{id}/delivery               — delivery package
 *   POST /api/workspaces/{id}/delivery/approve       — approve delivery
 *   POST /api/workspaces/{id}/delivery/send-client   — send to client
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml (F-031 group)
 *
 * Errors follow the project-wide {detail: {code, message}} contract.
 * `ExportsApiError` (and back-compat alias `ExportApiError`) surface a
 * non-technical, endpoint-tagged message via `.toUserMessage()` and never
 * leak server stack traces (AC-F1 / AC-F4).
 *
 * @screen-id S-061,S-062
 * @feature-id F-031
 * @task-ids T-V3-C-22,T-V3-C-23
 * @entities E-014
 * @phase Phase 1B
 */

// ---------------------------------------------------------------------------
// Endpoint constants + helpers.
// ---------------------------------------------------------------------------

export const EXPORTS_BY_WORKSPACE_ENDPOINT_TEMPLATE =
  "/api/workspaces/{id}/exports";
export const EXPORT_BY_ID_ENDPOINT_TEMPLATE = "/api/exports/{id}";

export const WORKSPACE_DELIVERY_ENDPOINT_PATTERN =
  "/api/workspaces/{id}/delivery";
export const WORKSPACE_EXPORTS_ENDPOINT_PATTERN =
  "/api/workspaces/{id}/exports";
export const EXPORT_BY_ID_ENDPOINT_PATTERN = "/api/exports/{id}";

export function buildExportsByWorkspaceEndpoint(workspaceId: string): string {
  return EXPORTS_BY_WORKSPACE_ENDPOINT_TEMPLATE.replace(
    "{id}",
    encodeURIComponent(workspaceId),
  );
}

export function buildExportByIdEndpoint(exportId: string): string {
  return EXPORT_BY_ID_ENDPOINT_TEMPLATE.replace(
    "{id}",
    encodeURIComponent(exportId),
  );
}

export function workspaceDeliveryEndpoint(workspaceId: string): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/delivery`;
}

export function workspaceDeliveryApproveEndpoint(workspaceId: string): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/delivery/approve`;
}

export function workspaceDeliverySendClientEndpoint(
  workspaceId: string,
): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/delivery/send-client`;
}

export function workspaceExportsEndpoint(workspaceId: string): string {
  return `/api/workspaces/${encodeURIComponent(workspaceId)}/exports`;
}

export function exportByIdEndpoint(exportId: string): string {
  return `/api/exports/${encodeURIComponent(exportId)}`;
}

// ---------------------------------------------------------------------------
// Domain types.
// ---------------------------------------------------------------------------

export type ExportType = "spec_pdf" | "delivery_report" | "delivery_report_pdf" | string;

export type ExportStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled"
  | string;

export interface ExportRecord {
  id: string;
  type?: ExportType;
  status?: ExportStatus;
  workspace_id?: string | number | null;
  /**
   * Null while status is 'queued' or 'running' (AC-F3). The UI keeps the
   * download button disabled until a non-null URL appears.
   */
  download_url?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  /** Tolerate unknown server-side metadata. */
  [extra: string]: unknown;
}

/** POST /api/workspaces/{id}/exports request body (AC-F2). */
export interface QueueExportRequest {
  type: ExportType;
  /** Optional renderer options (page size, watermark, …). */
  options?: Record<string, unknown> | string;
}

/** POST /api/workspaces/{id}/exports response. */
export interface ExportQueueResponse {
  export_id: string;
  status?: string;
}

/** Shorter alias used by S-062 callers. */
export type QueueExportResponse = ExportQueueResponse;

/** GET /api/exports/{id} response (AC-F3) — S-061 shape. */
export interface ExportStatusResponse {
  export: ExportRecord | null;
  /** Null while status is queued / running. */
  download_url: string | null;
}

export interface VerificationRow {
  label: string;
  result: string;
  note?: string | null;
}

/** Optional embedded summary block (KPI tiles + bullet lists). */
export interface DeliverySummary {
  title?: string | null;
  subtitle?: string | null;
  delivery_id_label?: string | null;
  delivery_date?: string | null;
  client_email?: string | null;
  assignee_email?: string | null;
  kpi?: {
    completed_tasks?: number | null;
    tests_passed?: number | null;
    coverage_pct?: number | null;
    redline_breaches?: number | null;
  } | null;
  implementation_items?: string[];
  verification_rows?: VerificationRow[];
}

/** Delivery — mirrors the openapi.yaml `Delivery` component schema. */
export interface Delivery {
  id: string;
  workspace_id: string;
  /** Lifecycle status — draft / approved / sent / accepted. */
  status: "draft" | "approved" | "sent" | "accepted" | string;
  approved_at?: string | null;
  sent_at?: string | null;
  artifact_urls?: string[];
  summary?: DeliverySummary | null;
}

export interface WorkspaceDeliveryResponse {
  delivery: Delivery;
}

// ---------------------------------------------------------------------------
// Error envelope + class.
// ---------------------------------------------------------------------------

interface BackendErrorEnvelope {
  detail?:
    | string
    | {
        code?: string;
        message?: string;
        errors?: unknown;
      };
}

const USER_MESSAGES: Record<number | "default", string> = {
  400: "リクエストが不正です",
  401: "サインインが必要です",
  403: "この操作を実行する権限がありません",
  404: "対象が見つかりませんでした",
  409: "競合する状態のため操作を完了できませんでした",
  422: "入力内容を確認してください",
  429: "リクエストが多すぎます。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "通信に失敗しました",
};

/**
 * Structured error for /api/exports/* + /api/workspaces/{id}/exports +
 * /api/workspaces/{id}/delivery endpoints. `toUserMessage()` produces a
 * non-technical sentence referencing the failing endpoint without leaking
 * server stack traces (AC-F1 / AC-F4).
 */
export class ExportsApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly endpoint: string;

  constructor(code: string, message: string, status: number, endpoint: string) {
    super(message);
    this.name = "ExportsApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  toUserMessage(): string {
    const friendly = USER_MESSAGES[this.status] ?? USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

/** Back-compat alias for S-061 callers that imported the singular class name. */
export const ExportApiError = ExportsApiError;
export type ExportApiError = ExportsApiError;

// ---------------------------------------------------------------------------
// Internal helpers.
// ---------------------------------------------------------------------------

export interface ExportsRequestOptions {
  apiBase?: string;
  signal?: AbortSignal;
  /** Bearer token forwarded as `Authorization: Bearer <token>`. */
  authToken?: string | null;
  /** Back-compat name used by S-061 callers. */
  token?: string | null;
  /** Test seam — defaults to the global `fetch`. */
  fetchImpl?: typeof fetch;
  /** Back-compat name used by S-061 callers. */
  baseUrl?: string;
}

function resolveBaseUrl(opts: ExportsRequestOptions): string {
  if (opts.baseUrl) return opts.baseUrl.replace(/\/$/, "");
  if (opts.apiBase) return opts.apiBase.replace(/\/$/, "");
  if (typeof process !== "undefined") {
    const e = process.env ?? {};
    if (e.NEXT_PUBLIC_API_URL) return e.NEXT_PUBLIC_API_URL.replace(/\/$/, "");
    if (e.NEXT_PUBLIC_API_BASE) return e.NEXT_PUBLIC_API_BASE.replace(/\/$/, "");
  }
  return "http://localhost:8001";
}

function buildAuthHeader(
  opts: ExportsRequestOptions,
): Record<string, string> {
  const token = opts.authToken ?? opts.token;
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

async function parseErrorEnvelope(
  response: Response,
  endpoint: string,
): Promise<ExportsApiError> {
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
    // Non-JSON body — keep the synthesised message. AC-F1: never embed raw body.
  }
  return new ExportsApiError(code, message, response.status, endpoint);
}

async function doFetch(
  url: string,
  init: RequestInit,
  opts: ExportsRequestOptions,
  endpoint: string,
): Promise<Response> {
  const fetchImpl = opts.fetchImpl ?? fetch;
  try {
    return await fetchImpl(url, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init.headers as Record<string, string> | undefined),
        ...buildAuthHeader(opts),
      },
      signal: opts.signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") throw err;
    throw new ExportsApiError(
      "network_error",
      "network error",
      0,
      endpoint,
    );
  }
}

// ---------------------------------------------------------------------------
// Delivery endpoints (S-062).
// ---------------------------------------------------------------------------

/** AC-F1 (S-062): GET /api/workspaces/{id}/delivery via the typed client. */
export async function getWorkspaceDelivery(
  workspaceId: string,
  opts: ExportsRequestOptions = {},
): Promise<WorkspaceDeliveryResponse> {
  const endpoint = workspaceDeliveryEndpoint(workspaceId);
  const base = resolveBaseUrl(opts);
  const url = `${base}${endpoint}`;
  const response = await doFetch(url, { method: "GET" }, opts, endpoint);
  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  return (await response.json()) as WorkspaceDeliveryResponse;
}

// ---------------------------------------------------------------------------
// Export queue endpoints (S-061 / S-062).
// ---------------------------------------------------------------------------

/**
 * AC-F2: POST /api/workspaces/{id}/exports — queue a spec_pdf / delivery_report
 * job and return the new export_id.
 */
export async function queueExport(
  workspaceId: string,
  body: QueueExportRequest,
  opts: ExportsRequestOptions = {},
): Promise<ExportQueueResponse> {
  const endpoint = workspaceExportsEndpoint(workspaceId);
  const base = resolveBaseUrl(opts);
  const url = `${base}${endpoint}`;
  const response = await doFetch(
    url,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
    opts,
    endpoint,
  );
  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  let data: unknown;
  try {
    data = await response.json();
  } catch {
    data = {};
  }
  const obj = (data ?? {}) as { export_id?: unknown; status?: unknown };
  return {
    export_id: typeof obj.export_id === "string" ? obj.export_id : "",
    status: typeof obj.status === "string" ? obj.status : "queued",
  };
}

/** Convenience: queue the spec_pdf job for S-062. */
export function requestSpecPdfExport(
  workspaceId: string,
  opts: ExportsRequestOptions = {},
): Promise<ExportQueueResponse> {
  return queueExport(workspaceId, { type: "spec_pdf" }, opts);
}

/**
 * AC-F3 (S-062): GET /api/exports/{id} via the typed client. The backend
 * returns download_url=null while status is 'queued' or 'running'.
 */
export async function getExport(
  exportId: string,
  opts: ExportsRequestOptions = {},
): Promise<ExportRecord> {
  const endpoint = exportByIdEndpoint(exportId);
  const base = resolveBaseUrl(opts);
  const url = `${base}${endpoint}`;
  const response = await doFetch(url, { method: "GET" }, opts, endpoint);
  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  return (await response.json()) as ExportRecord;
}

/**
 * AC-F3 (S-061): GET /api/exports/{id} via the typed client — returns the
 * S-061-shaped envelope ({export, download_url}) so the page can drive the
 * download CTA off a single object.
 */
export async function getExportById(
  exportId: string,
  opts: ExportsRequestOptions = {},
): Promise<ExportStatusResponse> {
  const endpoint = buildExportByIdEndpoint(exportId);
  const base = resolveBaseUrl(opts);
  const url = `${base}${endpoint}`;
  const response = await doFetch(url, { method: "GET" }, opts, endpoint);
  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  let data: unknown;
  try {
    data = await response.json();
  } catch {
    data = {};
  }
  const obj = (data ?? {}) as {
    export?: ExportRecord | null;
    download_url?: unknown;
  };
  const downloadUrl =
    typeof obj.download_url === "string" && obj.download_url.length > 0
      ? obj.download_url
      : null;
  return {
    export: obj.export ?? null,
    download_url: downloadUrl,
  };
}

/**
 * Convenience: tell whether the given status string is in a "terminal,
 * downloadable" state. Used by S-061 to enable / disable the download CTA.
 */
export function isExportDownloadable(
  status: string | undefined | null,
): boolean {
  return status === "succeeded";
}
