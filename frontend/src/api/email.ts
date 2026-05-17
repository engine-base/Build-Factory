/**
 * T-V3-C-19 / F-028: Typed clients for the email router (S-058 招待メール).
 *
 * Backend contract:
 *   backend/routers/email.py (T-V3-B-30, F-028)
 *     - GET  /api/email/templates           (list active EmailTemplate rows)
 *     - POST /api/email/test-send           (enqueue a test send, 429 rate-limited)
 *   OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml
 *            #/paths/~1api~1email~1templates
 *
 * Errors follow the project-wide `{detail: {code, message}}` contract used by
 * the FastAPI backend. The thrown {@link EmailApiError} surfaces a non-technical
 * message that references the failing endpoint without leaking server stack
 * traces (AC-F1 on S-058 — same convention as notifications.ts on S-010).
 */

export const EMAIL_TEMPLATES_ENDPOINT = "/api/email/templates";
export const EMAIL_TEST_SEND_ENDPOINT = "/api/email/test-send";

/** Stable id used by S-058 to look up the invitation template. */
export const EMAIL_TEMPLATE_KEY_INVITATION = "email_invitation";

// --------------------------------------------------------------------------
// Types — structurally aligned with the backend Pydantic schemas
// (schemas/EmailTemplate in openapi.yaml).
// --------------------------------------------------------------------------

export interface EmailTemplate {
  /** UUID string (openapi.yaml#components.schemas.EmailTemplate.id). */
  id: string;
  /**
   * Logical template key (e.g. "email_invitation", "email_signup_verify").
   * Used by S-058 to identify the invitation template (`name === "email_invitation"`).
   */
  name: string;
  subject?: string;
  body_html?: string;
  body_text?: string;
  /** Placeholder names referenced by the template (e.g. ["inviter", "workspace"]). */
  variables?: string[];
}

export interface EmailTemplateListResponse {
  templates: EmailTemplate[];
  /** Echoed back when the caller scoped the call via x-workspace-id. */
  workspace_id?: number | null;
  count?: number;
}

export interface EmailTestSendRequest {
  /** EmailTemplate UUID (openapi.yaml#components.schemas.TestSendRequest.template_id). */
  template_id: string;
  /** Recipient email address. */
  recipient: string;
  /** Optional template variable bag (e.g. {inviter: "masato"}). */
  detail?: Record<string, unknown>;
}

export interface EmailTestSendResponse {
  /** UUID assigned to the queued delivery row. */
  delivery_id: string;
  /** ISO-8601 timestamp when the send was enqueued. */
  queued_at: string;
  template_id: string;
  recipient: string;
  status: string;
}

// --------------------------------------------------------------------------
// Error type
// --------------------------------------------------------------------------

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
   * AC-F1 (UNWANTED): build a non-technical user-facing message that
   * references the failing endpoint without embedding raw stack traces or
   * backend exception class names.
   */
  toUserMessage(): string {
    const friendly =
      EMAIL_USER_MESSAGES[this.status] ?? EMAIL_USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

const EMAIL_USER_MESSAGES: Record<number | "default", string> = {
  400: "リクエストが正しくありません",
  401: "サインインが必要です",
  403: "このメールテンプレートを操作する権限がありません",
  404: "メールテンプレートが見つかりませんでした",
  409: "メールテンプレートは既に処理済みです",
  422: "入力フォーマットが正しくありません",
  429: "テスト送信の上限を超えました。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "メールテンプレートの取得に失敗しました",
};

// --------------------------------------------------------------------------
// Internal helpers
// --------------------------------------------------------------------------

interface ClientOptions {
  apiBase?: string;
  signal?: AbortSignal;
  authToken?: string | null;
  /** Workspace scope (forwarded as `x-workspace-id` header). */
  workspaceId?: number | string | null;
  fetchImpl?: typeof fetch;
}

function resolveApiBase(opts: ClientOptions): string {
  if (opts.apiBase) return opts.apiBase;
  if (typeof process !== "undefined") {
    const env = process.env;
    if (env?.NEXT_PUBLIC_API_URL) return env.NEXT_PUBLIC_API_URL;
    if (env?.NEXT_PUBLIC_API_BASE) return env.NEXT_PUBLIC_API_BASE;
  }
  return "http://localhost:8001";
}

function buildHeaders(opts: ClientOptions): Record<string, string> {
  const h: Record<string, string> = { Accept: "application/json" };
  if (opts.authToken) h.Authorization = `Bearer ${opts.authToken}`;
  if (opts.workspaceId !== undefined && opts.workspaceId !== null) {
    h["x-workspace-id"] = String(opts.workspaceId);
  }
  return h;
}

async function parseError(
  response: Response,
  endpoint: string,
): Promise<EmailApiError> {
  let code = "email.unknown";
  let message = response.statusText || "request failed";
  try {
    const payload = (await response.json()) as {
      detail?: { code?: string; message?: string } | string;
    };
    if (payload && typeof payload.detail === "object" && payload.detail) {
      if (typeof payload.detail.code === "string") code = payload.detail.code;
      if (typeof payload.detail.message === "string") {
        message = payload.detail.message;
      }
    } else if (typeof payload?.detail === "string") {
      message = payload.detail;
    }
  } catch {
    // intentional: keep the generic synthesised message — never leak a
    // potentially raw HTML / stack-trace body to the UI.
  }
  return new EmailApiError(code, message, response.status, endpoint);
}

// --------------------------------------------------------------------------
// Public API
// --------------------------------------------------------------------------

/**
 * AC-F1 / Tier 2: GET /api/email/templates via the typed client.
 *
 * @throws {@link EmailApiError} for any non-2xx response.
 */
export async function listEmailTemplates(
  opts: ClientOptions = {},
): Promise<EmailTemplateListResponse> {
  const fetchImpl = opts.fetchImpl ?? fetch;
  const base = resolveApiBase(opts);
  const url = `${base}${EMAIL_TEMPLATES_ENDPOINT}`;

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "GET",
      headers: buildHeaders(opts),
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as { name?: string })?.name === "AbortError") throw err;
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
  return (await response.json()) as EmailTemplateListResponse;
}

/**
 * AC-F2 (EVENT-DRIVEN): POST /api/email/test-send via the typed client.
 *
 * When a workspace invitation is created the backend is responsible for
 * dispatching the `email_invitation` template within 60 seconds; this method
 * is the operator-facing test-send path that S-058 exposes for QA preview.
 *
 * The backend already honours AC-F3 (retry up to 3 times with exponential
 * backoff before alerting admins) via `services.email.enqueue_test_send` and
 * the delivery worker — the UI only needs to surface success / 429 / 4xx-5xx
 * states (handled in S-058 via {@link EmailApiError.toUserMessage}).
 *
 * @throws {@link EmailApiError} for any non-2xx response.
 */
export async function sendTestEmail(
  body: EmailTestSendRequest,
  opts: ClientOptions = {},
): Promise<EmailTestSendResponse> {
  const fetchImpl = opts.fetchImpl ?? fetch;
  const base = resolveApiBase(opts);
  const url = `${base}${EMAIL_TEST_SEND_ENDPOINT}`;

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "POST",
      headers: {
        ...buildHeaders(opts),
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as { name?: string })?.name === "AbortError") throw err;
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
  return (await response.json()) as EmailTestSendResponse;
}

/**
 * Locate the invitation template within a `templates[]` list returned by
 * {@link listEmailTemplates}. Falls back to the first template whose name
 * contains "invitation" so the page is resilient to small backend renames.
 */
export function findInvitationTemplate(
  templates: EmailTemplate[],
): EmailTemplate | null {
  if (!templates.length) return null;
  const exact = templates.find((t) => t.name === EMAIL_TEMPLATE_KEY_INVITATION);
  if (exact) return exact;
  const fuzzy = templates.find((t) =>
    (t.name ?? "").toLowerCase().includes("invitation"),
  );
  return fuzzy ?? null;
}
