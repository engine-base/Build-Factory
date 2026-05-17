/**
 * T-V3-C-17 / C-18 / C-19 / C-20 / C-21 — Typed client for the email router
 * endpoints backing the S-056 .. S-060 email-template preview screens (F-028).
 *
 * (Phase 1.0-fix Wave 0 D: reconciles multiple concurrent vertical-slice
 * merges that previously left the file with stacked duplicate declarations
 * and a missing comment opener that broke `next build` type-check.)
 *
 * Backend contracts:
 *   GET  /api/email/templates       — list active EmailTemplate rows.
 *   POST /api/email/test-send       — enqueue a test send (429 rate-limited).
 *
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml
 *          #/paths/~1api~1email~1templates
 *          #/paths/~1api~1email~1test-send
 *
 * Errors follow the project-wide {detail: {code, message}} contract.
 * `EmailApiError.toUserMessage()` produces a non-technical sentence tagged
 * with the failing endpoint and never leaks server stack traces (AC-F1).
 *
 * @screen-id S-056,S-057,S-058,S-059,S-060
 * @feature-id F-028
 * @task-ids T-V3-C-17,T-V3-C-18,T-V3-C-19,T-V3-C-20,T-V3-C-21
 * @entities E-043
 * @phase Phase 1B
 */

// ---------------------------------------------------------------------------
// Endpoint constants.
// ---------------------------------------------------------------------------

export const EMAIL_TEMPLATES_ENDPOINT = "/api/email/templates";
export const EMAIL_TEMPLATE_BY_ID_ENDPOINT_PREFIX = "/api/email/templates";
export const EMAIL_TEST_SEND_ENDPOINT = "/api/email/test-send";

/** Stable id used by S-058 to look up the invitation template. */
export const EMAIL_TEMPLATE_KEY_INVITATION = "email_invitation";

// ---------------------------------------------------------------------------
// Domain types — match the OpenAPI EmailTemplate schema.
// ---------------------------------------------------------------------------

export interface EmailTemplate {
  /** UUID string. */
  id: string;
  /** Logical template key (e.g. "email_invitation", "email_signup_verify"). */
  name: string;
  /** Subject line shown in the recipient inbox preview. */
  subject?: string;
  /** Rendered HTML body (server-side template). */
  body_html?: string;
  /** Plain-text fallback for clients that don't render HTML. */
  body_text?: string;
  /** Markdown source (when the backend stores Markdown). */
  body_md?: string;
  /** Locale tag (e.g. "ja", "en"). */
  locale?: string;
  /** Placeholder names referenced by the template. */
  variables?: string[];
  /** Server may include extra metadata (active flag, updated_at, …). */
  [extra: string]: unknown;
}

export interface EmailTemplateListResponse {
  templates: EmailTemplate[];
  /** Echoed back when the caller scoped the call via x-workspace-id. */
  workspace_id?: number | string | null;
  count?: number;
}

/** Back-compat alias. */
export type EmailTemplatesResponse = EmailTemplateListResponse;

export interface EmailTestSendRequest {
  template_id: string;
  /** Recipient email address (preferred field). */
  recipient?: string;
  /** Back-compat: some callers pass `to` instead of `recipient`. */
  to?: string;
  /** Optional template variable bag. */
  detail?: Record<string, unknown>;
  /** Back-compat name. */
  variables?: Record<string, string>;
}

export interface EmailTestSendResponse {
  /** UUID assigned to the queued delivery row. */
  delivery_id?: string;
  /** Provider message id (Resend / SES). */
  message_id?: string;
  /** ISO-8601 timestamp when the send was enqueued. */
  queued_at?: string;
  template_id?: string;
  recipient?: string;
  status: string;
}

// ---------------------------------------------------------------------------
// Error envelope + class.
// ---------------------------------------------------------------------------

interface BackendErrorEnvelope {
  detail?: { code?: string; message?: string; errors?: unknown } | string;
}

const USER_MESSAGES: Record<number | "default", string> = {
  400: "リクエストが不正です",
  401: "サインインが必要です",
  403: "この操作を実行する権限がありません",
  404: "メールテンプレートが見つかりませんでした",
  409: "メールテンプレートは既に処理済みです",
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

  constructor(
    code: string,
    message: string,
    status: number,
    endpoint: string,
  ) {
    super(message);
    this.name = "EmailApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * AC-F1 (UNWANTED): non-technical user-facing message tagged with the
   * failing endpoint. Never embeds raw stack traces or backend exception
   * class names.
   */
  toUserMessage(): string {
    const friendly = USER_MESSAGES[this.status] ?? USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

// ---------------------------------------------------------------------------
// Internal helpers.
// ---------------------------------------------------------------------------

export interface EmailRequestOptions {
  apiBase?: string;
  /** Back-compat: callers also use `baseUrl`. */
  baseUrl?: string;
  signal?: AbortSignal;
  /** Bearer access token (workspace_admin scope is enforced server-side). */
  authToken?: string | null;
  /** Back-compat: callers also use `token`. */
  token?: string | null;
  /** x-workspace-id header (integer). Backend filters per workspace. */
  workspaceId?: number | string | null;
  /** Test seam — defaults to global fetch. */
  fetchImpl?: typeof fetch;
}

/** Back-compat alias used by S-057 callers. */
export type ClientOptions = EmailRequestOptions;

function resolveBaseUrl(opts: EmailRequestOptions): string {
  if (opts.baseUrl) return opts.baseUrl.replace(/\/$/, "");
  if (opts.apiBase) return opts.apiBase.replace(/\/$/, "");
  if (typeof process !== "undefined") {
    const e = process.env ?? {};
    if (e.NEXT_PUBLIC_API_URL) return e.NEXT_PUBLIC_API_URL.replace(/\/$/, "");
    if (e.NEXT_PUBLIC_API_BASE) return e.NEXT_PUBLIC_API_BASE.replace(/\/$/, "");
  }
  return "http://localhost:8001";
}

function buildHeaders(
  opts: EmailRequestOptions,
  withContentType = false,
): Record<string, string> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (withContentType) headers["Content-Type"] = "application/json";
  const token = opts.authToken ?? opts.token;
  if (token) headers.Authorization = `Bearer ${token}`;
  if (opts.workspaceId !== undefined && opts.workspaceId !== null) {
    headers["x-workspace-id"] = String(opts.workspaceId);
  }
  return headers;
}

async function parseError(
  response: Response,
  endpoint: string,
): Promise<EmailApiError> {
  let code = "email.unknown";
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
  return new EmailApiError(code, message, response.status, endpoint);
}

// ---------------------------------------------------------------------------
// Public API.
// ---------------------------------------------------------------------------

/**
 * GET /api/email/templates via the typed client.
 *
 * @throws EmailApiError on 4xx / 5xx / network failure.
 */
export async function listEmailTemplates(
  opts: EmailRequestOptions = {},
): Promise<EmailTemplateListResponse> {
  const base = resolveBaseUrl(opts);
  const url = `${base}${EMAIL_TEMPLATES_ENDPOINT}`;
  const fetchImpl = opts.fetchImpl ?? fetch;

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "GET",
      headers: buildHeaders(opts),
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

  if (!response.ok) {
    throw await parseError(response, EMAIL_TEMPLATES_ENDPOINT);
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    data = { templates: [] };
  }
  if (
    data &&
    typeof data === "object" &&
    "templates" in data &&
    Array.isArray((data as { templates: unknown }).templates)
  ) {
    const payload = data as EmailTemplateListResponse;
    return {
      templates: payload.templates,
      workspace_id: payload.workspace_id ?? null,
      count: payload.count,
    };
  }
  return { templates: [], workspace_id: null };
}

/**
 * POST /api/email/test-send via the typed client.
 *
 * @throws EmailApiError on 4xx / 5xx / network failure.
 */
export async function sendTestEmail(
  body: EmailTestSendRequest,
  opts: EmailRequestOptions = {},
): Promise<EmailTestSendResponse> {
  const base = resolveBaseUrl(opts);
  const url = `${base}${EMAIL_TEST_SEND_ENDPOINT}`;
  const fetchImpl = opts.fetchImpl ?? fetch;

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "POST",
      headers: buildHeaders(opts, true),
      body: JSON.stringify(body),
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as { name?: string }).name === "AbortError") throw err;
    throw new EmailApiError(
      "email.network_error",
      "network error",
      0,
      EMAIL_TEST_SEND_ENDPOINT,
    );
  }

  if (!response.ok) {
    throw await parseError(response, EMAIL_TEST_SEND_ENDPOINT);
  }

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    data = { status: "queued" };
  }
  if (data && typeof data === "object") {
    const d = data as Record<string, unknown>;
    return {
      delivery_id: typeof d.delivery_id === "string" ? d.delivery_id : undefined,
      message_id: typeof d.message_id === "string" ? d.message_id : undefined,
      queued_at: typeof d.queued_at === "string" ? d.queued_at : undefined,
      template_id: typeof d.template_id === "string" ? d.template_id : undefined,
      recipient: typeof d.recipient === "string" ? d.recipient : undefined,
      status: typeof d.status === "string" ? d.status : "queued",
    };
  }
  return { status: "queued" };
}

// ---------------------------------------------------------------------------
// Template-selector helpers used by the preview screens.
// ---------------------------------------------------------------------------

function findByKeyOrSubstring(
  templates: EmailTemplate[] | undefined,
  exactKeys: readonly string[],
  substring: string,
): EmailTemplate | null {
  if (!templates || templates.length === 0) return null;
  const normalised = templates.map((t) => ({
    t,
    name: String(t.name ?? "").toLowerCase(),
  }));
  for (const key of exactKeys) {
    const exact = normalised.find((row) => row.name === key);
    if (exact) return exact.t;
  }
  const fuzzy = normalised.find((row) => row.name.includes(substring));
  return fuzzy?.t ?? null;
}

/** Locate the invitation template (S-058). */
export function findInvitationTemplate(
  templates: EmailTemplate[] | undefined,
): EmailTemplate | null {
  return findByKeyOrSubstring(
    templates,
    [EMAIL_TEMPLATE_KEY_INVITATION, "invitation", "email-invitation"],
    "invitation",
  );
}

/** Locate the signup-verify template (S-056). */
export function findSignupVerifyTemplate(
  templates: EmailTemplate[] | undefined,
): EmailTemplate | null {
  return findByKeyOrSubstring(
    templates,
    ["signup_verify", "signup-confirm", "email_signup_verify"],
    "signup",
  );
}

/** Locate the weekly-summary template (S-060). */
export function findWeeklySummaryTemplate(
  templates: EmailTemplate[] | undefined,
): EmailTemplate | null {
  return findByKeyOrSubstring(
    templates,
    ["weekly_summary", "weekly-summary", "email_weekly_summary"],
    "weekly",
  );
}
