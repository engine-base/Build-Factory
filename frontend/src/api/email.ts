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
}
