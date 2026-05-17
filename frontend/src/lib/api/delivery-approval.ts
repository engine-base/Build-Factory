/**
 * T-V3-C-45 / F-013 / S-035: Typed client for the delivery-approval endpoints.
 *
 * Backend contracts (T-V3-B-21 implemented):
 *   GET  /api/workspaces/{id}/delivery               — fetch delivery package
 *   POST /api/workspaces/{id}/delivery/approve       — approve (workspace_admin)
 *   POST /api/workspaces/{id}/delivery/send-client   — send to client (workspace_admin)
 *
 * OpenAPI:
 *   docs/api-design/2026-05-16_v3/openapi.yaml
 *     #/paths/~1api~1workspaces~1{id}~1delivery
 *     #/paths/~1api~1workspaces~1{id}~1delivery~1approve
 *     #/paths/~1api~1workspaces~1{id}~1delivery~1send-client
 *
 * Auth model: bearerAuth
 *   - GET    member (workspace member)
 *   - POST   workspace_admin
 *
 * The thrown {@link DeliveryApprovalApiError} surfaces a non-technical user
 * message tagged with the failing endpoint (AC-F1 of S-035). Server stack
 * traces are never leaked to the toast / page.
 *
 * @screen-id S-035
 * @feature-id F-013,F-015
 * @task-ids T-V3-C-45
 * @entities E-018
 * @phase Phase 1
 */

// --------------------------------------------------------------------------
// Endpoint helpers — exposed for both UI and test assertions.
// --------------------------------------------------------------------------

export const WORKSPACE_DELIVERY_ENDPOINT_PATTERN =
  "/api/workspaces/{id}/delivery";
export const WORKSPACE_DELIVERY_APPROVE_ENDPOINT_PATTERN =
  "/api/workspaces/{id}/delivery/approve";
export const WORKSPACE_DELIVERY_SEND_CLIENT_ENDPOINT_PATTERN =
  "/api/workspaces/{id}/delivery/send-client";

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

// --------------------------------------------------------------------------
// Domain types (mirror openapi.yaml Delivery schema).
// --------------------------------------------------------------------------

export type DeliveryStatus =
  | "draft"
  | "approved"
  | "sent"
  | "accepted"
  | (string & {});

export interface DeliveryChecklistItem {
  id: string;
  label: string;
  status: "ok" | "warning" | "pending" | (string & {});
  detail?: string | null;
  actionable?: boolean;
}

export interface DeliveryTestSummary {
  unit_pass?: number | null;
  unit_total?: number | null;
  unit_skipped?: number | null;
  integration_pass?: number | null;
  integration_total?: number | null;
  e2e_pass?: number | null;
  e2e_total?: number | null;
  coverage_pct?: number | null;
}

export interface ClientAcceptance {
  /** Identifier (email or display label) of the reviewer. */
  reviewer_label?: string | null;
  /** "approved" | "pending" | "n_a" | "rejected". */
  state?: "approved" | "pending" | "n_a" | "rejected" | (string & {});
  note?: string | null;
}

export interface Delivery {
  id: string;
  workspace_id: string;
  status: DeliveryStatus;
  approved_at?: string | null;
  sent_at?: string | null;
  artifact_urls?: string[];
  /** "Phase 1 dogfood セットアップ完成" 等のラベル. */
  phase_label?: string | null;
  /** 0-100 inclusive. */
  readiness_pct?: number | null;
  /** Done / total tasks (mock: "23 / 36 task done"). */
  tasks_done?: number | null;
  tasks_total?: number | null;
  /** Due date (YYYY-MM-DD). */
  due_date?: string | null;
  /** Project / engagement name. */
  project_label?: string | null;
  /** Optional HTML preview rendered inside the approval panel. */
  html_preview?: string | null;
  /** Static report bullet list (mirrors mock fallback). */
  report_items?: string[];
  checklist?: DeliveryChecklistItem[];
  test_summary?: DeliveryTestSummary | null;
  client_acceptance?: ClientAcceptance | null;
}

export interface WorkspaceDeliveryResponse {
  delivery: Delivery;
}

export interface ApproveDeliveryResponse {
  approved_at: string;
}

export interface SendClientDeliveryRequest {
  client_email?: string;
}

export interface SendClientDeliveryResponse {
  sent_at: string;
  delivery_token?: string;
}

// --------------------------------------------------------------------------
// Error envelope (FastAPI {detail: {code, message}} contract).
// --------------------------------------------------------------------------

interface BackendErrorEnvelope {
  detail?:
    | string
    | {
        code?: string;
        message?: string;
      };
}

const USER_MESSAGES: Record<number | "default", string> = {
  400: "リクエストに問題があります",
  401: "サインインが必要です",
  403: "この操作を実行する権限がありません",
  404: "納品データが見つかりませんでした",
  409: "現在この操作は実行できません",
  422: "入力内容を確認してください",
  429: "リクエストの上限に達しました。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "通信に失敗しました",
};

export class DeliveryApprovalApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly endpoint: string;

  constructor(code: string, message: string, status: number, endpoint: string) {
    super(message);
    this.name = "DeliveryApprovalApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * AC-F1 (UNWANTED 4xx/5xx → endpoint-tagged toast, no stack trace).
   */
  toUserMessage(): string {
    const friendly = USER_MESSAGES[this.status] ?? USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

// --------------------------------------------------------------------------
// Internal helpers.
// --------------------------------------------------------------------------

export interface DeliveryApprovalRequestOptions {
  apiBase?: string;
  signal?: AbortSignal;
  authToken?: string | null;
  /** Test seam — defaults to the global fetch. */
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
  opts: DeliveryApprovalRequestOptions,
): Record<string, string> {
  if (!opts.authToken) return {};
  return { Authorization: `Bearer ${opts.authToken}` };
}

async function parseErrorEnvelope(
  response: Response,
  endpoint: string,
): Promise<DeliveryApprovalApiError> {
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
    // Non-JSON body — keep the synthesised message. The raw body is
    // deliberately NOT embedded to avoid leaking server stack traces (AC-F1).
  }
  return new DeliveryApprovalApiError(
    code,
    message,
    response.status,
    endpoint,
  );
}

// --------------------------------------------------------------------------
// API functions
// --------------------------------------------------------------------------

/**
 * AC-F1: GET /api/workspaces/{id}/delivery — returns the full delivery package.
 *
 * @throws DeliveryApprovalApiError on non-2xx — carries the failing endpoint
 *         so the UI can surface a non-technical toast referencing it.
 */
export async function getWorkspaceDelivery(
  workspaceId: string,
  opts: DeliveryApprovalRequestOptions = {},
): Promise<WorkspaceDeliveryResponse> {
  const endpoint = workspaceDeliveryEndpoint(workspaceId);
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
    throw new DeliveryApprovalApiError(
      "network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseErrorEnvelope(response, endpoint);
  }
  return (await response.json()) as WorkspaceDeliveryResponse;
}

/**
 * POST /api/workspaces/{id}/delivery/approve — marks the delivery as approved
 * (workspace_admin role). Returns the server-recorded approved_at timestamp.
 *
 * @throws DeliveryApprovalApiError on non-2xx.
 */
export async function approveWorkspaceDelivery(
  workspaceId: string,
  opts: DeliveryApprovalRequestOptions = {},
): Promise<ApproveDeliveryResponse> {
  const endpoint = workspaceDeliveryApproveEndpoint(workspaceId);
  const baseUrl = resolveApiBase(opts.apiBase).replace(/\/$/, "");
  const url = `${baseUrl}${endpoint}`;
  const fetchImpl = opts.fetchImpl ?? fetch;

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...buildAuthHeader(opts),
      },
      body: "{}",
      signal: opts.signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") throw err;
    throw new DeliveryApprovalApiError(
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
  const obj = (data ?? {}) as { approved_at?: unknown };
  return {
    approved_at:
      typeof obj.approved_at === "string"
        ? obj.approved_at
        : new Date().toISOString(),
  };
}

/**
 * POST /api/workspaces/{id}/delivery/send-client — email the delivery to the
 * client (workspace_admin role). Returns sent_at + an opaque delivery_token
 * that the client portal uses to access the report.
 *
 * @throws DeliveryApprovalApiError on non-2xx.
 */
export async function sendDeliveryToClient(
  workspaceId: string,
  body: SendClientDeliveryRequest = {},
  opts: DeliveryApprovalRequestOptions = {},
): Promise<SendClientDeliveryResponse> {
  const endpoint = workspaceDeliverySendClientEndpoint(workspaceId);
  const baseUrl = resolveApiBase(opts.apiBase).replace(/\/$/, "");
  const url = `${baseUrl}${endpoint}`;
  const fetchImpl = opts.fetchImpl ?? fetch;

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...buildAuthHeader(opts),
      },
      body: JSON.stringify(body),
      signal: opts.signal,
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") throw err;
    throw new DeliveryApprovalApiError(
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
  const obj = (data ?? {}) as {
    sent_at?: unknown;
    delivery_token?: unknown;
  };
  return {
    sent_at:
      typeof obj.sent_at === "string"
        ? obj.sent_at
        : new Date().toISOString(),
    delivery_token:
      typeof obj.delivery_token === "string" ? obj.delivery_token : undefined,
  };
}
