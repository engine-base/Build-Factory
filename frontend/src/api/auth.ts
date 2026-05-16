/**
 * Auth API client (typed) — T-V3-C-03 / S-003 / F-001.
 *
 * @screen-id S-003
 * @feature-id F-001
 * @task-ids T-V3-C-03,T-V3-AUTH-10,T-V3-AUTH-03
 * @entities E-001,E-039
 * @phase Phase 1B
 *
 * 関連 endpoint:
 *   POST /api/auth/password-reset
 *     - request : { email: string }
 *     - response: 2xx (status: 'sent' | string)  ← account enumeration 回避のため、
 *                 アカウント存否に依らず常に 2xx を返す (T-V3-B-01 実装済)
 *     - error   : 4xx/5xx は ApiError として上位 (Toast) に伝播
 */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

export type PasswordResetRequest = {
  email: string;
};

export type PasswordResetResponse = {
  status: string;
};

/**
 * 構造化 API エラー (server stack を露出させないため message は短文に正規化済み).
 *
 * UNWANTED AC: stack trace / SQL / internal path を含まない。
 */
export class ApiError extends Error {
  public readonly endpoint: string;
  public readonly status: number;

  constructor(endpoint: string, status: number, message?: string) {
    super(message ?? `${endpoint} failed (${status})`);
    this.name = "ApiError";
    this.endpoint = endpoint;
    this.status = status;
  }
}

/**
 * POST /api/auth/password-reset — パスワード再設定リンクを送信する.
 *
 * EVENT-DRIVEN: When called with an email, the backend shall always return 2xx
 * (no account enumeration) and send reset email only if the account exists.
 *
 * @throws ApiError 4xx / 5xx / network failure
 */
export async function requestPasswordReset(
  payload: PasswordResetRequest,
  init?: { fetchImpl?: typeof fetch; baseUrl?: string },
): Promise<PasswordResetResponse> {
  const endpoint = "POST /api/auth/password-reset";
  const fetchImpl = init?.fetchImpl ?? fetch;
  const baseUrl = init?.baseUrl ?? BASE;

  let res: Response;
  try {
    res = await fetchImpl(`${baseUrl}/api/auth/password-reset`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    // network-level failure (no response). Don't leak the cause to UI.
    throw new ApiError(endpoint, 0, `${endpoint}: ネットワークに接続できませんでした`);
  }

  if (!res.ok) {
    // 4xx / 5xx — stack trace を漏らさない短文へ正規化.
    const code = res.status;
    const msg =
      code === 429
        ? `${endpoint}: リクエストが多すぎます。しばらく待って再試行してください`
        : code >= 500
          ? `${endpoint}: サーバーで一時的なエラーが発生しました`
          : `${endpoint}: 入力内容を確認してください (${code})`;
    throw new ApiError(endpoint, code, msg);
  }

  // 2xx — backend は { status: "sent" } 等を返す.
  let data: unknown = null;
  try {
    data = await res.json();
  } catch {
    data = { status: "sent" };
  }
  if (data && typeof data === "object" && "status" in data && typeof (data as { status: unknown }).status === "string") {
    return { status: (data as { status: string }).status };
  }
  return { status: "sent" };
}
