/**
 * T-V3-C-08 / F-004: Typed client for account members + invitations endpoints
 * backing the S-008 メンバー管理 screen.
 *
 * Backend contracts (T-V3-B-05 / T-V3-B-06 implemented):
 *   GET    /api/accounts/{id}/members              — backend/routers/accounts.py::get_accounts_by_id_members
 *   POST   /api/accounts/{id}/invitations          — backend/routers/accounts.py::post_accounts_by_id_invitations
 *   DELETE /api/accounts/{id}/members/{user_id}    — backend/routers/accounts.py::delete_accounts_by_id_members_by_user_id
 *
 * OpenAPI:
 *   docs/api-design/2026-05-16_v3/openapi.yaml#/paths/~1api~1accounts~1{id}~1members
 *   docs/api-design/2026-05-16_v3/openapi.yaml#/paths/~1api~1accounts~1{id}~1invitations
 *   docs/api-design/2026-05-16_v3/openapi.yaml#/paths/~1api~1accounts~1{id}~1members~1{user_id}
 *
 * The thrown {@link AccountsApiError} surfaces a non-technical, endpoint-tagged
 * message for the S-008 toast surface without ever leaking server stack traces
 * (AC-F4). 429 rate-limit handling (AC-F5: max 20 invitations / hour / account)
 * is preserved verbatim from the backend `Retry-After` payload.
 */

export const ACCOUNT_MEMBERS_ENDPOINT_PATTERN =
  "/api/accounts/{id}/members";
export const ACCOUNT_INVITATIONS_ENDPOINT_PATTERN =
  "/api/accounts/{id}/invitations";
export const ACCOUNT_MEMBER_DETAIL_ENDPOINT_PATTERN =
  "/api/accounts/{id}/members/{user_id}";

/** Build the canonical members list endpoint for the given account id. */
export function accountMembersEndpoint(accountId: string): string {
  return `/api/accounts/${encodeURIComponent(accountId)}/members`;
}

/** Build the canonical invitations endpoint for the given account id. */
export function accountInvitationsEndpoint(accountId: string): string {
  return `/api/accounts/${encodeURIComponent(accountId)}/invitations`;
}

/** Build the canonical member detail endpoint for delete operations. */
export function accountMemberDetailEndpoint(
  accountId: string,
  userId: string,
): string {
  return `/api/accounts/${encodeURIComponent(accountId)}/members/${encodeURIComponent(userId)}`;
}

// --------------------------------------------------------------------------
// Types — mirror openapi.yaml AccountMember + endpoint envelopes
// --------------------------------------------------------------------------

export type AccountMemberRole =
  | "owner"
  | "admin"
  | "member"
  | "viewer"
  | "guest"
  | "account_owner"
  | "workspace_admin"
  | "monitor";

export interface AccountMember {
  account_id: string;
  user_id: string;
  role: string;
  /** Optional display fields backend may include for the S-008 table. */
  email?: string;
  display_name?: string;
  status?: "active" | "pending" | "invited" | string;
  last_login_at?: string | null;
  workspace_names?: string[];
}

export interface ListAccountMembersResponse {
  members: AccountMember[];
  total: number;
}

export interface InviteAccountMemberRequest {
  email: string;
  role: "owner" | "admin" | "member" | "viewer" | "guest";
}

export interface InviteAccountMemberResponse {
  invitation_token: string;
  expires_at: string;
}

export interface RemoveAccountMemberResponse {
  removed_at: string;
}

// --------------------------------------------------------------------------
// Error class — AC-F4 (non-technical, endpoint-tagged, no stack)
// --------------------------------------------------------------------------

interface BackendErrorEnvelope {
  detail?:
    | string
    | {
        code?: string;
        message?: string;
        retry_after?: number;
      };
}

/** Thrown for any non-2xx response from the account members / invitations APIs. */
export class AccountsApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly endpoint: string;
  readonly retryAfterSeconds?: number;

  constructor(
    code: string,
    message: string,
    status: number,
    endpoint: string,
    retryAfterSeconds?: number,
  ) {
    super(message);
    this.name = "AccountsApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
    this.retryAfterSeconds = retryAfterSeconds;
  }

  /**
   * AC-F4 (UNWANTED): produce a non-technical, end-user friendly message that
   * references the failing endpoint without leaking server stack traces.
   *
   * AC-F5 surfaces 429 with a dedicated message so the UI can display the
   * rate-limit copy verbatim.
   */
  toUserMessage(): string {
    const friendly =
      ACCOUNTS_USER_MESSAGES[this.status] ?? ACCOUNTS_USER_MESSAGES.default;
    return `${friendly} (${this.endpoint})`;
  }
}

const ACCOUNTS_USER_MESSAGES: Record<number | "default", string> = {
  400: "リクエストが不正です",
  401: "サインインが必要です",
  403: "この操作を実行する権限がありません",
  404: "対象が見つかりません",
  409: "このメンバーはすでに参加しています",
  422: "入力内容を確認してください",
  429: "招待回数の上限に達しました。1 時間後に再試行してください",
  500: "サーバーエラーが発生しました。時間をおいて再試行してください",
  default: "通信に失敗しました",
};

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------

interface ClientOptions {
  apiBase?: string;
  signal?: AbortSignal;
  /** Bearer token for authenticated / account_owner endpoints. */
  authToken?: string | null;
  /** Test-only fetch override (the S-008 spec injects a vi.fn() mock). */
  fetchImpl?: typeof fetch;
}

function resolveApiBase(opts: ClientOptions): string {
  if (opts.apiBase) return opts.apiBase;
  if (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  return "http://localhost:8001";
}

function buildAuthHeaders(opts: ClientOptions): Record<string, string> {
  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  if (opts.authToken) headers.Authorization = `Bearer ${opts.authToken}`;
  return headers;
}

async function parseError(
  response: Response,
  endpoint: string,
): Promise<AccountsApiError> {
  let code = "UNKNOWN";
  let message = response.statusText || "request failed";
  let retryAfter: number | undefined;
  try {
    const payload = (await response.json()) as BackendErrorEnvelope;
    if (payload && typeof payload.detail === "object" && payload.detail) {
      if (typeof payload.detail.code === "string") code = payload.detail.code;
      if (typeof payload.detail.message === "string") {
        message = payload.detail.message;
      }
      if (typeof payload.detail.retry_after === "number") {
        retryAfter = payload.detail.retry_after;
      }
    } else if (typeof payload?.detail === "string") {
      message = payload.detail;
    }
  } catch {
    // Non-JSON body — keep the synthesised message. We deliberately do not
    // include the raw body to avoid leaking server stack traces (AC-F4).
  }
  // Header-based Retry-After fallback (FastAPI sets this on 429).
  if (!retryAfter) {
    const header = response.headers.get("Retry-After");
    if (header) {
      const parsed = Number(header);
      if (Number.isFinite(parsed)) retryAfter = parsed;
    }
  }
  return new AccountsApiError(code, message, response.status, endpoint, retryAfter);
}

// --------------------------------------------------------------------------
// API functions
// --------------------------------------------------------------------------

/**
 * AC-F1 (S-008): GET /api/accounts/{id}/members via the typed client.
 */
export async function listAccountMembers(
  accountId: string,
  opts: ClientOptions = {},
): Promise<ListAccountMembersResponse> {
  const endpoint = accountMembersEndpoint(accountId);
  const fetchImpl = opts.fetchImpl ?? fetch;
  const url = `${resolveApiBase(opts)}${endpoint}`;
  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "GET",
      headers: buildAuthHeaders(opts),
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as { name?: string }).name === "AbortError") throw err;
    throw new AccountsApiError(
      "NETWORK_ERROR",
      "network error",
      0,
      endpoint,
    );
  }
  if (!response.ok) {
    throw await parseError(response, endpoint);
  }
  const data = (await response.json()) as Partial<ListAccountMembersResponse>;
  return {
    members: Array.isArray(data.members) ? data.members : [],
    total: typeof data.total === "number" ? data.total : (data.members?.length ?? 0),
  };
}

/**
 * AC-F2 (S-008): POST /api/accounts/{id}/invitations via the typed client.
 *
 * AC-F5 (EVENT-DRIVEN): when the backend returns 429 (rate limit, see
 * `x-bf-rate-limit: 20/hour/account` in openapi.yaml), the thrown
 * AccountsApiError surfaces `.status === 429` so the UI can render the
 * dedicated copy and respect `retryAfterSeconds`.
 */
export async function inviteAccountMember(
  accountId: string,
  body: InviteAccountMemberRequest,
  opts: ClientOptions = {},
): Promise<InviteAccountMemberResponse> {
  const endpoint = accountInvitationsEndpoint(accountId);
  const fetchImpl = opts.fetchImpl ?? fetch;
  const url = `${resolveApiBase(opts)}${endpoint}`;
  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "POST",
      headers: {
        ...buildAuthHeaders(opts),
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as { name?: string }).name === "AbortError") throw err;
    throw new AccountsApiError(
      "NETWORK_ERROR",
      "network error",
      0,
      endpoint,
    );
  }
  if (!response.ok) {
    throw await parseError(response, endpoint);
  }
  return (await response.json()) as InviteAccountMemberResponse;
}

/**
 * AC-F3 (S-008): DELETE /api/accounts/{id}/members/{user_id} via the typed
 * client. The UI must show the S-051 confirm-delete dialog (typed-name
 * confirmation) before calling this — see members/page.tsx ConfirmDeleteDialog.
 */
export async function removeAccountMember(
  accountId: string,
  userId: string,
  opts: ClientOptions = {},
): Promise<RemoveAccountMemberResponse> {
  const endpoint = accountMemberDetailEndpoint(accountId, userId);
  const fetchImpl = opts.fetchImpl ?? fetch;
  const url = `${resolveApiBase(opts)}${endpoint}`;
  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "DELETE",
      headers: buildAuthHeaders(opts),
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as { name?: string }).name === "AbortError") throw err;
    throw new AccountsApiError(
      "NETWORK_ERROR",
      "network error",
      0,
      endpoint,
    );
  }
  if (!response.ok) {
    throw await parseError(response, endpoint);
  }
  return (await response.json()) as RemoveAccountMemberResponse;
}
