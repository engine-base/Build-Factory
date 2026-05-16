/**
 * T-V3-C-10 / F-018: Typed clients for the notifications router (S-010 通知 Inbox).
 *
 * Backend contract:
 *   backend/routers/notifications.py
 *     - GET  /api/notifications              (list + unread_count)
 *     - POST /api/notifications/{id}/read    (mark single read)
 *     - POST /api/notifications/read-all     (mark all unread read)
 *   backend/schemas/notifications.py
 *     - Notification / NotificationListResponse / NotificationReadResponse
 *       / NotificationReadAllRequest / NotificationReadAllResponse
 *   OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml#/paths/~1api~1notifications
 *
 * Errors follow the project-wide {detail: {code, message}} contract used by
 * the FastAPI backend. The thrown {@link NotificationsApiError} surfaces a
 * non-technical message that references the failing endpoint without leaking
 * server stack traces (AC-F4 on S-010).
 */

export const NOTIFICATIONS_LIST_ENDPOINT = "/api/notifications";
export const NOTIFICATION_READ_ENDPOINT_PATTERN = "/api/notifications/{id}/read";
export const NOTIFICATIONS_READ_ALL_ENDPOINT = "/api/notifications/read-all";

// --------------------------------------------------------------------------
// Types — kept structurally aligned with backend Pydantic schemas.
// --------------------------------------------------------------------------

export interface Notification {
  id: number;
  workspace_id?: number | null;
  recipient_user_id: string;
  event_type: string;
  title: string;
  body?: string | null;
  link_url?: string | null;
  is_read: boolean;
  priority: string;
  detail: Record<string, unknown>;
  created_at?: string | null;
  read_at?: string | null;
}

export interface NotificationListResponse {
  items: Notification[];
  /** AC-F5 (STATE-DRIVEN): unread items contribute to this counter. */
  unread_count: number;
}

export interface NotificationReadResponse {
  /** ISO-8601 timestamp when the notification was marked as read. */
  read_at: string;
}

export interface NotificationReadAllRequest {
  /** Optional event_type prefix filter. `null`/`undefined` ≡ all categories. */
  category?: string | null;
}

export interface NotificationReadAllResponse {
  marked_count: number;
}

export interface NotificationListQuery {
  unread_only?: boolean;
  category?: string;
}

// --------------------------------------------------------------------------
// Error type
// --------------------------------------------------------------------------

/** Thrown for any non-2xx response from the notifications endpoints. */
export class NotificationsApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly endpoint: string;

  constructor(code: string, message: string, status: number, endpoint: string) {
    super(message);
    this.name = "NotificationsApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * AC-F4 (UNWANTED): build a non-technical user-facing message that
   * references the failing endpoint without embedding raw stack traces or
   * backend exception class names.
   */
  toUserMessage(): string {
    const friendly =
      NOTIFICATION_USER_MESSAGES[this.status] ??
      NOTIFICATION_USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

const NOTIFICATION_USER_MESSAGES: Record<number | "default", string> = {
  400: "リクエストが正しくありません",
  401: "サインインが必要です",
  403: "この通知を操作する権限がありません",
  404: "通知が見つかりませんでした",
  409: "この通知は既に処理済みです",
  422: "入力フォーマットが正しくありません",
  429: "リクエストが多すぎます。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "通知の取得に失敗しました",
};

// --------------------------------------------------------------------------
// Internal helpers
// --------------------------------------------------------------------------

interface ClientOptions {
  apiBase?: string;
  signal?: AbortSignal;
  authToken?: string | null;
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

function authHeaders(opts: ClientOptions): Record<string, string> {
  const h: Record<string, string> = { Accept: "application/json" };
  if (opts.authToken) h.Authorization = `Bearer ${opts.authToken}`;
  return h;
}

async function parseError(
  response: Response,
  endpoint: string,
): Promise<NotificationsApiError> {
  let code = "notifications.unknown";
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
  return new NotificationsApiError(code, message, response.status, endpoint);
}

// --------------------------------------------------------------------------
// Public API
// --------------------------------------------------------------------------

/**
 * AC-F1 (EVENT-DRIVEN): GET /api/notifications via the typed client.
 *
 * Returns the full {@link NotificationListResponse} including
 * `items` and `unread_count` (AC-F5).
 *
 * @throws {@link NotificationsApiError} for any non-2xx response.
 */
export async function listNotifications(
  query: NotificationListQuery = {},
  opts: ClientOptions = {},
): Promise<NotificationListResponse> {
  const fetchImpl = opts.fetchImpl ?? fetch;
  const base = resolveApiBase(opts);
  const url = new URL(`${base}${NOTIFICATIONS_LIST_ENDPOINT}`);
  if (typeof query.unread_only === "boolean") {
    url.searchParams.set("unread_only", String(query.unread_only));
  }
  if (query.category) {
    url.searchParams.set("category", query.category);
  }

  let response: Response;
  try {
    response = await fetchImpl(url.toString(), {
      method: "GET",
      headers: authHeaders(opts),
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as { name?: string })?.name === "AbortError") throw err;
    throw new NotificationsApiError(
      "notifications.network_error",
      "network error",
      0,
      NOTIFICATIONS_LIST_ENDPOINT,
    );
  }

  if (!response.ok) {
    throw await parseError(response, NOTIFICATIONS_LIST_ENDPOINT);
  }
  return (await response.json()) as NotificationListResponse;
}

/** Canonical endpoint path for a single-notification read action. */
export function notificationReadEndpoint(id: number | string): string {
  return `/api/notifications/${encodeURIComponent(String(id))}/read`;
}

/**
 * AC-F2 (EVENT-DRIVEN): POST /api/notifications/{id}/read via the typed client.
 *
 * @throws {@link NotificationsApiError} for any non-2xx response.
 */
export async function markNotificationRead(
  id: number | string,
  opts: ClientOptions = {},
): Promise<NotificationReadResponse> {
  const fetchImpl = opts.fetchImpl ?? fetch;
  const base = resolveApiBase(opts);
  const endpoint = notificationReadEndpoint(id);
  const url = `${base}${endpoint}`;

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "POST",
      headers: { ...authHeaders(opts), "Content-Type": "application/json" },
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as { name?: string })?.name === "AbortError") throw err;
    throw new NotificationsApiError(
      "notifications.network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) {
    throw await parseError(response, endpoint);
  }
  return (await response.json()) as NotificationReadResponse;
}

/**
 * AC-F3 / AC-F6 (EVENT-DRIVEN): POST /api/notifications/read-all via the
 * typed client. Passing no `category` marks ALL of the caller's unread
 * notifications as read (AC-F6).
 *
 * @throws {@link NotificationsApiError} for any non-2xx response.
 */
export async function markAllNotificationsRead(
  body: NotificationReadAllRequest = {},
  opts: ClientOptions = {},
): Promise<NotificationReadAllResponse> {
  const fetchImpl = opts.fetchImpl ?? fetch;
  const base = resolveApiBase(opts);
  const url = `${base}${NOTIFICATIONS_READ_ALL_ENDPOINT}`;

  // omit `category` from payload when null/undefined/empty to honour the
  // backend's "no filter ≡ all unread" contract (AC-F6).
  const payload: NotificationReadAllRequest = {};
  if (typeof body.category === "string" && body.category !== "") {
    payload.category = body.category;
  }

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "POST",
      headers: { ...authHeaders(opts), "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as { name?: string })?.name === "AbortError") throw err;
    throw new NotificationsApiError(
      "notifications.network_error",
      "network error",
      0,
      NOTIFICATIONS_READ_ALL_ENDPOINT,
    );
  }

  if (!response.ok) {
    throw await parseError(response, NOTIFICATIONS_READ_ALL_ENDPOINT);
  }
  return (await response.json()) as NotificationReadAllResponse;
}
