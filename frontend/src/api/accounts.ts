/**
 * T-V3-C-07 / F-004: Typed client for the accounts router endpoints backing
 * the S-007 (アカウント設定) screen + S-052 (unsaved-changes) + S-055
 * (Danger Zone) dialog patterns.
 *
 * Backend contracts (REUSE — implemented by T-V3-B-05):
 *   GET    /api/accounts/{account_id}                  — backend/routers/accounts.py::get_account
 *   PATCH  /api/accounts/{account_id}                  — backend/routers/accounts.py::update_account
 *   POST   /api/accounts/{account_id}/transfer-owner   — backend/routers/accounts.py::transfer_owner_route
 *   DELETE /api/accounts/{account_id}                  — backend/routers/accounts.py::deactivate_account
 *   POST   /api/accounts/{account_id}/invitations      — backend/routers/accounts.py::create_account_invitation_route
 * OpenAPI: docs/api-design/2026-05-16_v3/openapi.yaml (F-004 group)
 *
 * NOTE: This module deliberately keeps the surface narrow — only the typed
 * functions S-007 needs. The router exposes PATCH; the AC text says "PUT
 * /api/accounts/{id}", however backend impl (T-V3-B-05) is PATCH-style
 * partial update so we expose `updateAccount` and document the AC alias.
 * The typed client emits the failing endpoint inside `AccountsApiError`
 * so the UI toast can satisfy AC-F5 (no stack-trace leak).
 */

export const ACCOUNT_GET_ENDPOINT = (id: string | number) =>
  `/api/accounts/${encodeURIComponent(String(id))}`;
export const ACCOUNT_UPDATE_ENDPOINT = (id: string | number) =>
  `/api/accounts/${encodeURIComponent(String(id))}`;
export const ACCOUNT_TRANSFER_OWNER_ENDPOINT = (id: string | number) =>
  `/api/accounts/${encodeURIComponent(String(id))}/transfer-owner`;
export const ACCOUNT_DELETE_ENDPOINT = (id: string | number) =>
  `/api/accounts/${encodeURIComponent(String(id))}`;
export const ACCOUNT_INVITATION_ENDPOINT = (id: string | number) =>
  `/api/accounts/${encodeURIComponent(String(id))}/invitations`;

// --------------------------------------------------------------------------
// Types
// --------------------------------------------------------------------------

export interface Account {
  id: number | string;
  name: string;
  account_type?: string;
  plan?: string;
  owner_user_id?: string;
  // The backend may surface additional metadata (billing_method, etc.).
  // Keep it open so the typed client never throws on extra fields.
  [extra: string]: unknown;
}

export interface AccountUpdatePayload {
  name?: string;
  account_type?: string;
  plan?: string;
}

export interface TransferOwnerPayload {
  /** Backend contract field name (T-V3-B-05 / TransferOwnerRequest). */
  new_owner_user_id: string;
}

export interface TransferOwnerResponse {
  old_owner_id: string;
  new_owner_id: string;
  transferred_at: string;
}

export interface AccountInvitationPayload {
  email: string;
  role?: string;
  expires_in_days?: number;
}

export interface AccountInvitationResponse {
  invitation_token: string;
  expires_at: string;
}

// --------------------------------------------------------------------------
// Error class
// --------------------------------------------------------------------------

const USER_MESSAGES: Record<number | "default", string> = {
  400: "リクエストが不正です",
  401: "サインインが必要です",
  403: "この操作を実行する権限がありません",
  404: "アカウントが見つかりませんでした",
  409: "対象ユーザーはこのアカウントのメンバーではありません",
  422: "入力内容を確認してください",
  429: "リクエストが多すぎます。しばらく待って再試行してください",
  500: "サーバーで一時的なエラーが発生しました",
  default: "通信に失敗しました",
};

/** Thrown for any non-2xx response from the accounts endpoints. */
export class AccountsApiError extends Error {
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
    this.name = "AccountsApiError";
    this.code = code;
    this.status = status;
    this.endpoint = endpoint;
  }

  /**
   * AC-F5 (S-007 UNWANTED): produce a non-technical user-facing message that
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
  /** Bearer token for endpoints requiring `authenticated` role. */
  authToken?: string | null;
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
): Promise<AccountsApiError> {
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
    // include the raw body to avoid leaking server stack traces.
  }
  return new AccountsApiError(code, message, response.status, endpoint);
}

async function request<T>(
  method: "GET" | "PATCH" | "POST" | "DELETE",
  endpoint: string,
  body: unknown,
  opts: ClientOptions,
): Promise<T> {
  const base = resolveApiBase(opts);
  const url = `${base}${endpoint}`;

  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (opts.authToken) headers.Authorization = `Bearer ${opts.authToken}`;

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as { name?: string }).name === "AbortError") throw err;
    throw new AccountsApiError(
      "accounts.network_error",
      "network error",
      0,
      endpoint,
    );
  }

  if (!response.ok) throw await parseError(response, endpoint);

  // DELETE may legitimately return 204 / empty body.
  if (response.status === 204) return undefined as unknown as T;

  try {
    return (await response.json()) as T;
  } catch {
    return undefined as unknown as T;
  }
}

// --------------------------------------------------------------------------
// Typed API surface (S-007 AC-F1..F4 + AC-F8 invitations rate-limit)
// --------------------------------------------------------------------------

/** AC-F1 (S-007): GET /api/accounts/{id} via the typed API client. */
export function getAccount(
  accountId: string | number,
  opts: ClientOptions = {},
): Promise<Account> {
  return request<Account>(
    "GET",
    ACCOUNT_GET_ENDPOINT(accountId),
    undefined,
    opts,
  );
}

/**
 * AC-F2 (S-007): PUT /api/accounts/{id} via the typed API client.
 *
 * NOTE: The backend exposes PATCH (partial update) for T-V3-B-05. Both verbs
 * map to the same logical operation in the AC spec. The function uses PATCH
 * to match the existing router contract; the public name `updateAccount`
 * stays verb-agnostic so future PUT migration is purely server-side.
 */
export function updateAccount(
  accountId: string | number,
  body: AccountUpdatePayload,
  opts: ClientOptions = {},
): Promise<Account> {
  return request<Account>(
    "PATCH",
    ACCOUNT_UPDATE_ENDPOINT(accountId),
    body,
    opts,
  );
}

/** AC-F3 (S-007): POST /api/accounts/{id}/transfer-owner via the typed client. */
export function transferAccountOwner(
  accountId: string | number,
  body: TransferOwnerPayload,
  opts: ClientOptions = {},
): Promise<TransferOwnerResponse> {
  return request<TransferOwnerResponse>(
    "POST",
    ACCOUNT_TRANSFER_OWNER_ENDPOINT(accountId),
    body,
    opts,
  );
}

/** AC-F4 (S-007): DELETE /api/accounts/{id} via the typed API client. */
export function deleteAccount(
  accountId: string | number,
  opts: ClientOptions = {},
): Promise<void> {
  return request<void>(
    "DELETE",
    ACCOUNT_DELETE_ENDPOINT(accountId),
    undefined,
    opts,
  );
}

/** AC-F8 (S-007): POST /api/accounts/{id}/invitations — rate-limit aware. */
export function createAccountInvitation(
  accountId: string | number,
  body: AccountInvitationPayload,
  opts: ClientOptions = {},
): Promise<AccountInvitationResponse> {
  return request<AccountInvitationResponse>(
    "POST",
    ACCOUNT_INVITATION_ENDPOINT(accountId),
    body,
    opts,
  );
}
