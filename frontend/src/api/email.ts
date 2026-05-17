/**
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
