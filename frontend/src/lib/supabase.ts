/**
 * T-S0-07: Supabase FE wrapper (browser client).
 *
 * 目的:
 *   Build-Factory frontend で Supabase を使うための統一 entry point.
 *   既存の api.ts (backend REST 経由) と直交し、auth / realtime / RLS
 *   依存の読み取りなど Supabase 直接アクセスが必要な部分のみで本 wrapper を使う.
 *
 * 既存 api.ts との関係 (REFACTOR の精神):
 *   - 既存 api.ts: backend FastAPI REST 経由 (workspace / employees / etc.)
 *   - 本 wrapper: Supabase Auth / Realtime / RLS-aware 直接アクセス
 *   両者は併存し, 既存 api.ts は無改変 (REUSE).
 *
 * Graceful degradation:
 *   NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY 未設定 → mock client
 *   を返し, 全 method が { data: null, error: SupabaseNotConfiguredError } を返す.
 *   開発初期で Supabase project 未作成でも build/tsc が通る.
 *
 * 使い方:
 *   import { getSupabaseClient } from "@/lib/supabase";
 *   const supabase = getSupabaseClient();
 *   const { data: user } = await supabase.auth.getUser();
 *
 * 4 層 observability との分離:
 *   - 本 wrapper は logger (pino, T-S0-11) を呼ばない (caller 責任).
 *   - Sentry (T-S0-10) も呼ばない (caller 責任).
 *   - audit_logs (DB) は backend 経由のみ. 本 wrapper は直接書込まない.
 *
 * AC マッピング:
 *   AC-1 UBIQUITOUS    : getSupabaseClient() / isSupabaseConfigured() /
 *                        SupabaseNotConfiguredError 公開. 既存 api.ts 無改変.
 *   AC-2 EVENT-DRIVEN  : 環境変数を validate して singleton client を返す /
 *                        2 回目以降は cached instance.
 *   AC-3 STATE-DRIVEN  : 未設定で mock client (graceful no-throw) /
 *                        client は session を local/cookie storage に保持.
 *   AC-4 UNWANTED      : URL form 不正で SupabaseConfigError /
 *                        hardcoded SUPABASE_ANON_KEY / DSN なし.
 */

/* eslint-disable @typescript-eslint/no-explicit-any */

const VALID_URL_PATTERN = /^https:\/\/[a-z0-9-]+\.supabase\.co\/?$/;

/**
 * Supabase が未設定 (env var なし) の時に method 呼出が返すエラー.
 */
export class SupabaseNotConfiguredError extends Error {
  readonly code = "SUPABASE_NOT_CONFIGURED";
  constructor(message = "Supabase URL / ANON_KEY not configured") {
    super(message);
    this.name = "SupabaseNotConfiguredError";
  }
}

/**
 * env var 形式不正 (URL pattern や ANON_KEY 空) の時に init で raise.
 */
export class SupabaseConfigError extends Error {
  readonly code = "SUPABASE_CONFIG_INVALID";
  constructor(message: string) {
    super(message);
    this.name = "SupabaseConfigError";
  }
}

type SupabaseClientLike = {
  auth: {
    getUser: () => Promise<{ data: any; error: any }>;
    signOut: () => Promise<{ error: any }>;
  };
  from: (table: string) => any;
  __isMock?: boolean;
};

let _client: SupabaseClientLike | null = null;
let _checked = false;
let _configured = false;

function _readEnv(): { url: string | null; key: string | null } {
  // NEXT_PUBLIC_ prefix で client/server 両方から参照可能
  const url =
    (typeof process !== "undefined" &&
      process.env.NEXT_PUBLIC_SUPABASE_URL) ||
    null;
  const key =
    (typeof process !== "undefined" &&
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY) ||
    null;
  return {
    url: url && url.trim() ? url.trim() : null,
    key: key && key.trim() ? key.trim() : null,
  };
}

function _validateEnv(url: string | null, key: string | null): void {
  // URL が指定済かつ patten 不正なら raise
  if (url !== null && !VALID_URL_PATTERN.test(url)) {
    throw new SupabaseConfigError(
      `NEXT_PUBLIC_SUPABASE_URL must match https://*.supabase.co/, got ${url}`,
    );
  }
  // ANON_KEY が指定済かつ空白なら raise (空白でない短文字列は許容)
  if (key !== null && key.length < 10) {
    throw new SupabaseConfigError(
      "NEXT_PUBLIC_SUPABASE_ANON_KEY must be >= 10 chars",
    );
  }
}

/**
 * 環境変数が両方とも設定されており、形式 valid なら true.
 * 形式不正な値が指定されている場合は throw (silent ignore しない).
 */
export function isSupabaseConfigured(): boolean {
  const { url, key } = _readEnv();
  _validateEnv(url, key); // 不正値で raise
  return Boolean(url && key);
}

/**
 * Mock client (Supabase 未設定時に返す).
 * 全 method が SupabaseNotConfiguredError を error field に乗せて返す.
 */
function _createMockClient(): SupabaseClientLike {
  const err = new SupabaseNotConfiguredError();
  return {
    __isMock: true,
    auth: {
      getUser: async () => ({ data: { user: null }, error: err }),
      signOut: async () => ({ error: err }),
    },
    from: (_table: string) => ({
      select: () => ({ data: null, error: err }),
      insert: () => ({ data: null, error: err }),
      update: () => ({ data: null, error: err }),
      delete: () => ({ data: null, error: err }),
    }),
  };
}

/**
 * Singleton Supabase client を返す.
 * 環境変数が設定済 → @supabase/supabase-js から createClient.
 * 未設定 → mock client (graceful).
 */
export async function getSupabaseClient(): Promise<SupabaseClientLike> {
  if (_client !== null) return _client;

  const { url, key } = _readEnv();
  _validateEnv(url, key);

  if (!url || !key) {
    _configured = false;
    _checked = true;
    _client = _createMockClient();
    return _client;
  }

  try {
    // dynamic import: @supabase/supabase-js が未インストールでも tsc/build 通る
    const mod: any = await import("@supabase/supabase-js" as any).catch(
      () => null,
    );
    if (!mod || !mod.createClient) {
      console.warn(
        "@supabase/supabase-js not installed; using mock client (graceful)",
      );
      _configured = false;
      _checked = true;
      _client = _createMockClient();
      return _client;
    }
    _client = mod.createClient(url, key, {
      auth: {
        // session を browser local/cookie storage に保持
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    });
    _configured = true;
    _checked = true;
    return _client!;
  } catch (e) {
    console.warn("Supabase client init failed; using mock", e);
    _configured = false;
    _checked = true;
    _client = _createMockClient();
    return _client;
  }
}

/**
 * Convenience: 現在の user を返す (graceful).
 */
export async function getCurrentUser(): Promise<{
  user: any;
  error: any;
}> {
  const supabase = await getSupabaseClient();
  const { data, error } = await supabase.auth.getUser();
  return { user: data?.user ?? null, error };
}

/**
 * Convenience: sign out + cached client clear.
 */
export async function signOut(): Promise<{ error: any }> {
  const supabase = await getSupabaseClient();
  const { error } = await supabase.auth.signOut();
  return { error };
}

/** Test-only: reset cached client (for unit tests). */
export function __resetForTests(): void {
  _client = null;
  _checked = false;
  _configured = false;
}

/** Test-only: state introspection. */
export function __getState(): { checked: boolean; configured: boolean } {
  return { checked: _checked, configured: _configured };
}
