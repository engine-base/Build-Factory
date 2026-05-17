/**
 * T-V3-C-17 / F-028: Typed client for the email-templates router endpoint
 * backing the S-056 (サインアップ確認メール) email-template preview screen and
 * adjacent S-057 / S-058 / S-059 / S-060 preview screens.
 *
 * Backend contract (REUSE — implemented by T-V3-B-30 / T-V3-B-EMAIL-01):
 *   GET /api/email/templates  — backend/routers/email.py::list_email_templates
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml#/paths/~1api~1email~1templates
 *
 * The typed client emits the failing endpoint inside `EmailApiError` so the UI
 * toast can satisfy AC-F1 (UNWANTED 4xx/5xx → endpoint-referenced message,
 * no server stack-trace leak).
 *
 * @screen-id S-056
 * @feature-id F-028
 * @task-ids T-V3-C-17
 * @entities E-043
 * @phase Phase 1B
 */

export const EMAIL_TEMPLATES_ENDPOINT = "/api/email/templates";

// --------------------------------------------------------------------------
// Types — mirror OpenAPI components/schemas/EmailTemplate + GET response.
// --------------------------------------------------------------------------

/** One row from GET /api/email/templates. */
export interface EmailTemplate {
  id: string;
  name: string;
  subject?: string;
  body_html?: string;
  body_text?: string;
  body_md?: string;
  locale?: string;
  variables?: string[];
  /** Server may include extra metadata (active flag, updated_at, …). */
  [extra: string]: unknown;
}

/** Envelope returned by GET /api/email/templates. */
export interface EmailTemplatesResponse {
  templates: EmailTemplate[];
  workspace_id?: number | null;
  count?: number;
}

// --------------------------------------------------------------------------
// Error class
// --------------------------------------------------------------------------

const USER_MESSAGES: Record<number | "default", string> = {
  400: "リクエストが不正です",
  401: "サインインが必要です",
  403: "この操作を実行する権限がありません",
  404: "メールテンプレートが見つかりませんでした",
  422: "入力内容を確認してください",
  429: "リクエストが多すぎます。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "通信に失敗しました",
};

/** Thrown for any non-2xx response from the email endpoints. */
export class EmailApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly endpoint: string;

  constructor(code: string, message: string, status: number, endpoint: string) {
    super(message);
    this.name = "EmailApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * AC-F1 (S-056 UNWANTED): produce a non-technical, user-facing message that
   * references the failing endpoint without leaking server stack traces.
   */
  toUserMessage(): string {
    const friendly = USER_MESSAGES[this.status] ?? USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------

interface ClientOptions {
  apiBase?: string;
  signal?: AbortSignal;
  /** Bearer access token (workspace_admin role required by backend). */
  authToken?: string | null;
  /** Optional x-workspace-id (integer). Backend filters per workspace. */
  workspaceId?: number | string | null;
}

function resolveApiBase(opts: ClientOptions): string {
  if (opts.apiBase) return opts.apiBase;
  if (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  return "http://localhost:8001";
}

interface BackendErrorEnvelope {
  detail?: { code?: string; message?: string } | string;
}

async function parseError(
  response: Response,
  endpoint: string,
): Promise<EmailApiError> {
  let code = "UNKNOWN";
  let message = response.statusText || "request failed";
  try {
    const payload = (await response.json()) as BackendErrorEnvelope;
    if (payload && typeof payload.detail === "object" && payload.detail) {
      if (typeof payload.detail.code === "string") code = payload.detail.code;
      if (typeof payload.detail.message === "string")
        message = payload.detail.message;
    } else if (typeof payload?.detail === "string") {
      message = payload.detail;
    }
  } catch {
    // Non-JSON body — keep the synthesised message. We deliberately do not
    // embed the raw body to avoid leaking server stack traces (AC-F1).
  }
  return new EmailApiError(code, message, response.status, endpoint);
}

// --------------------------------------------------------------------------
// Typed API surface
// --------------------------------------------------------------------------

/**
 * GET /api/email/templates via the typed client (T-V3-B-30 backend).
 *
 * Used by the S-056 サインアップ確認メール preview page to load the
 * `signup_verify` template (and adjacent templates) from the workspace.
 */
export async function listEmailTemplates(
  opts: ClientOptions = {},
): Promise<EmailTemplatesResponse> {
  const base = resolveApiBase(opts);
  const url = `${base}${EMAIL_TEMPLATES_ENDPOINT}`;

  const headers: Record<string, string> = { Accept: "application/json" };
  if (opts.authToken) headers.Authorization = `Bearer ${opts.authToken}`;
  if (opts.workspaceId !== undefined && opts.workspaceId !== null) {
    headers["x-workspace-id"] = String(opts.workspaceId);
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method: "GET",
      headers,
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as { name?: string }).name === "AbortError") throw err;
    throw new EmailApiError(
      "email.network_error",
      "network error",
      0,
      EMAIL_TEMPLATES_ENDPOINT,
    );
  }

  if (!response.ok) throw await parseError(response, EMAIL_TEMPLATES_ENDPOINT);

  try {
    const payload = (await response.json()) as EmailTemplatesResponse;
    return {
      templates: Array.isArray(payload?.templates) ? payload.templates : [],
      workspace_id: payload?.workspace_id ?? null,
      count: payload?.count,
    };
  } catch {
    return { templates: [], workspace_id: null };
  }
}

/**
 * Locate the signup-verify template among the listed templates.
 *
 * Picks by canonical name (`signup_verify` / `signup-confirm` / contains
 * `signup`). Returns `null` when no matching row exists so the UI can render
 * an empty-state placeholder instead of crashing.
 */
export function findSignupVerifyTemplate(
  templates: EmailTemplate[] | undefined,
): EmailTemplate | null {
  if (!templates || templates.length === 0) return null;
  const normalised = templates.map((t) => ({
    t,
    name: String(t.name ?? "").toLowerCase(),
  }));
  return (
    normalised.find((row) => row.name === "signup_verify")?.t ??
    normalised.find((row) => row.name === "signup-confirm")?.t ??
    normalised.find((row) => row.name.includes("signup"))?.t ??
    null
  );
 * T-V3-C-18 / F-028: Typed client for the Email Template router
 * (signup verify / password reset / invitation / task notif / weekly summary).
 *
 * Backend contracts:
 *   GET  /api/email/templates           — backend/routers/email.py::get_email_templates
 *   PUT  /api/email/templates/{id}      — backend/routers/email.py::put_email_templates_by_id
 *   POST /api/email/test-send           — backend/routers/email.py::post_email_test_send
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml#/paths/~1api~1email~1templates
 *
 * The thrown {@link EmailApiError} surfaces a non-technical message for the UI
 * toast while preserving the failing endpoint reference, never leaking server
 * stack traces (AC-F1 on S-057).
 *
 * NOTE: This file is *additive*. The minimal surface area documented here is
 * what S-057 (password-reset email preview) needs in Wave 4 / Group C; sibling
 * screens (S-056, S-058..060) will extend the same module without breaking
 * call sites (Open/Closed).
 */

export const EMAIL_TEMPLATES_ENDPOINT = "/api/email/templates";
export const EMAIL_TEMPLATE_BY_ID_ENDPOINT_PREFIX = "/api/email/templates";
export const EMAIL_TEST_SEND_ENDPOINT = "/api/email/test-send";

// ---------------------------------------------------------------------------
// Schema (mirrors openapi.yaml#/components/schemas/EmailTemplate)
// ---------------------------------------------------------------------------

export interface EmailTemplate {
  /** UUID v4. */
  id: string;
  /** Logical name (e.g. "password_reset", "signup_verify"). */
  name: string;
  /** Subject line shown in the recipient inbox preview. */
  subject?: string;
  /** Rendered HTML body (server-side template). */
  body_html?: string;
  /** Plain-text fallback for clients that don't render HTML. */
  body_text?: string;
  /** Template variable names (e.g. ["reset_url", "expires_in"]). */
  variables?: string[];
}

export interface EmailTemplateListResponse {
  templates: EmailTemplate[];
}

export interface EmailTestSendRequest {
  /** Template id to send. */
  template_id: string;
  /** Recipient email (testing only — Resend/SES sandbox). */
  to: string;
  /** Template variable substitutions. */
  variables?: Record<string, string>;
}

export interface EmailTestSendResponse {
  /** Provider message id (Resend / SES). */
  message_id: string;
  status: string;
}

// ---------------------------------------------------------------------------
// Error type (parity with auth.ApiError shape)
// ---------------------------------------------------------------------------

/**
 * Structured API error for the /api/email/* router. The message is
 * intentionally normalized to a short, non-technical sentence so server
 * stack traces / SQL / internal paths never reach the UI layer (AC-F1).
 */
export class EmailApiError extends Error {
  public readonly endpoint: string;
  public readonly status: number;

  constructor(endpoint: string, status: number, message?: string) {
    super(message ?? `${endpoint} failed (${status})`);
    this.name = "EmailApiError";
    this.endpoint = endpoint;
    this.status = status;
  }
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

const DEFAULT_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

interface ClientInit {
  fetchImpl?: typeof fetch;
  baseUrl?: string;
  /** Bearer access token (workspace_admin scope required by backend). */
  token?: string;
}

function buildHeaders(init?: ClientInit): HeadersInit {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (init?.token) {
    headers["Authorization"] = `Bearer ${init.token}`;
  }
  return headers;
}

function normalizeError(endpoint: string, status: number): string {
  if (status === 401) {
    return `${endpoint}: 認証が切れました。再ログインしてください`;
  }
  if (status === 403) {
    return `${endpoint}: この操作には権限が必要です (workspace_admin)`;
  }
  if (status === 404) {
    return `${endpoint}: テンプレートが見つかりませんでした`;
  }
  if (status === 422) {
    return `${endpoint}: 入力内容を確認してください`;
  }
  if (status === 429) {
    return `${endpoint}: リクエストが多すぎます。しばらく待って再試行してください`;
  }
  if (status >= 500) {
    return `${endpoint}: サーバーで一時的なエラーが発生しました`;
  }
  return `${endpoint}: 不明なエラー (${status})`;
}

// ---------------------------------------------------------------------------
// GET /api/email/templates
// ---------------------------------------------------------------------------

/**
 * Fetch every EmailTemplate visible to the caller (workspace_admin scope).
 * Used by S-056..S-060 preview screens.
 *
 * EVENT-DRIVEN: When the S-057 page mounts, the system shall call
 * GET /api/email/templates via this typed client.
 *
 * @throws EmailApiError on 4xx / 5xx / network failure.
 */
export async function listEmailTemplates(
  init?: ClientInit,
): Promise<EmailTemplateListResponse> {
  const endpoint = `GET ${EMAIL_TEMPLATES_ENDPOINT}`;
  const fetchImpl = init?.fetchImpl ?? fetch;
  const baseUrl = init?.baseUrl ?? DEFAULT_BASE;

  let res: Response;
  try {
    res = await fetchImpl(`${baseUrl}${EMAIL_TEMPLATES_ENDPOINT}`, {
      method: "GET",
      headers: buildHeaders(init),
    });
  } catch {
    throw new EmailApiError(
      endpoint,
      0,
      `${endpoint}: ネットワークに接続できませんでした`,
    );
  }

  if (!res.ok) {
    throw new EmailApiError(endpoint, res.status, normalizeError(endpoint, res.status));
  }

  let data: unknown;
  try {
    data = await res.json();
  } catch {
    data = { templates: [] };
  }
  if (
    data &&
    typeof data === "object" &&
    "templates" in data &&
    Array.isArray((data as { templates: unknown }).templates)
  ) {
    return { templates: (data as { templates: EmailTemplate[] }).templates };
  }
  return { templates: [] };
}

// ---------------------------------------------------------------------------
// POST /api/email/test-send
// ---------------------------------------------------------------------------

/**
 * Send a test email through the same backend pipeline used in production
 * (Resend / SES). Useful for S-057 preview "send to me" CTA.
 *
 * UNWANTED: If an email bounces, the backend shall retry up to 3 times with
 * exponential backoff before alerting admins. The UI surfaces only the
 * final success / failure (AC-F3).
 *
 * @throws EmailApiError on 4xx / 5xx / network failure.
 */
export async function sendTestEmail(
  payload: EmailTestSendRequest,
  init?: ClientInit,
): Promise<EmailTestSendResponse> {
  const endpoint = `POST ${EMAIL_TEST_SEND_ENDPOINT}`;
  const fetchImpl = init?.fetchImpl ?? fetch;
  const baseUrl = init?.baseUrl ?? DEFAULT_BASE;

  let res: Response;
  try {
    res = await fetchImpl(`${baseUrl}${EMAIL_TEST_SEND_ENDPOINT}`, {
      method: "POST",
      headers: buildHeaders(init),
      body: JSON.stringify(payload),
    });
  } catch {
    throw new EmailApiError(
      endpoint,
      0,
      `${endpoint}: ネットワークに接続できませんでした`,
    );
  }

  if (!res.ok) {
    throw new EmailApiError(endpoint, res.status, normalizeError(endpoint, res.status));
  }

  let data: unknown;
  try {
    data = await res.json();
  } catch {
    data = { message_id: "", status: "queued" };
  }
  if (data && typeof data === "object") {
    const d = data as { message_id?: unknown; status?: unknown };
    return {
      message_id: typeof d.message_id === "string" ? d.message_id : "",
      status: typeof d.status === "string" ? d.status : "queued",
    };
  }
  return { message_id: "", status: "queued" };
}

// ---------------------------------------------------------------------------
// T-V3-C-21 / S-060 — weekly-summary template selector (additive, Open/Closed).
//
// Locates the `weekly_summary` template among the GET /api/email/templates
// response. Picks by canonical name (`weekly_summary` / `weekly-summary` /
// contains `weekly`). Returns `null` when no matching row exists so the UI
// can render the mock-default copy (S-060 mock parity) instead of crashing.
// ---------------------------------------------------------------------------

/**
 * Locate the weekly-summary template among the listed templates.
 *
 * @screen-id S-060
 * @feature-id F-028
 * @task-ids T-V3-C-21
 */
export function findWeeklySummaryTemplate(
  templates: EmailTemplate[] | undefined,
): EmailTemplate | null {
  if (!templates || templates.length === 0) return null;
  const normalised = templates.map((t) => ({
    t,
    name: String(t.name ?? "").toLowerCase(),
  }));
  return (
    normalised.find((row) => row.name === "weekly_summary")?.t ??
    normalised.find((row) => row.name === "weekly-summary")?.t ??
    normalised.find((row) => row.name.includes("weekly"))?.t ??
    null
  );
}
