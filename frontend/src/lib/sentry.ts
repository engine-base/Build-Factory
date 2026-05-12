/**
 * T-S0-10: Sentry 設定 (Frontend / Next.js).
 *
 * 目的:
 *   Build-Factory frontend で error / performance を Sentry に送信する設定基盤.
 *   pino (T-S0-11) は ephemeral, audit_logs は監査 trail, Sentry は error reporting.
 *
 * 3 層 observability (backend と対):
 *   - pino           : 人間 / 監視 (ephemeral)
 *   - audit_logs DB  : 監査 trail (backend 経由のみ)
 *   - Sentry         : error / perf (本 module)
 *
 * Graceful degradation:
 *   @sentry/nextjs が未インストール / NEXT_PUBLIC_SENTRY_DSN 未設定 → no-op.
 *   既存 component に try-except import を書く必要なし.
 *
 * 環境変数 (NEXT_PUBLIC_ prefix で browser でも参照可):
 *   - NEXT_PUBLIC_SENTRY_DSN              : DSN (省略時 disabled)
 *   - NEXT_PUBLIC_SENTRY_ENVIRONMENT      : production / staging / development
 *   - NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE : 0-1
 *   - NEXT_PUBLIC_SENTRY_RELEASE          : git sha 等
 *
 * 使い方 (app/layout.tsx 等):
 *   import { initSentry } from "@/lib/sentry";
 *   initSentry();
 *
 *   // 個別エラー
 *   import { captureException } from "@/lib/sentry";
 *   try { ... } catch (e) { captureException(e); }
 *
 * AC マッピング (backend と対):
 *   AC-1 UBIQUITOUS    : initSentry / captureException / setUser / setTag 公開.
 *                        @sentry/nextjs 未インストール / DSN なしで graceful no-op.
 *   AC-2 EVENT-DRIVEN  : initSentry で DSN + env 設定.
 *   AC-3 STATE-DRIVEN  : 未インストール時 stub 動作 / pino logger 不変.
 *   AC-4 UNWANTED      : invalid sample_rate (range outside) で error /
 *                        PII default off (sendDefaultPii: false).
 */

/* eslint-disable @typescript-eslint/no-explicit-any */

/**
 * @sentry/nextjs が installed か (dev / minimal CI で未配備でも import が落ちないように).
 *
 * Note: 本 module は `@sentry/nextjs` を直接 import しない.
 * Sentry は production runtime でのみ require され, dev / test では undefined.
 */
let _sentry: any = null;
let _initialized = false;

async function _loadSentry(): Promise<any> {
  if (_sentry !== null) return _sentry;
  try {
    // dynamic import: @sentry/nextjs が未インストールでも tsc / build が通る
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    _sentry = await import("@sentry/nextjs" as any).catch(() => null);
    return _sentry;
  } catch {
    _sentry = null;
    return null;
  }
}

/**
 * Sentry が利用可能か (init 後に判定).
 */
export function isSentryAvailable(): boolean {
  return _sentry !== null;
}

export const VALID_ENVIRONMENTS = [
  "development",
  "staging",
  "production",
  "ci",
  "test",
] as const;
export type SentryEnvironment = (typeof VALID_ENVIRONMENTS)[number];

export interface InitSentryOptions {
  dsn?: string;
  environment?: SentryEnvironment;
  tracesSampleRate?: number;
  release?: string;
  sendDefaultPii?: boolean;
}

/**
 * Initialize Sentry SDK.
 *
 * @returns true if actually initialized, false if no-op (graceful).
 */
export async function initSentry(
  options: InitSentryOptions = {},
): Promise<boolean> {
  if (_initialized) return isSentryAvailable();

  const env =
    options.environment ??
    (process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT as SentryEnvironment) ??
    "development";

  if (!VALID_ENVIRONMENTS.includes(env)) {
    throw new Error(
      `environment must be one of ${VALID_ENVIRONMENTS.join(", ")}, got ${env}`,
    );
  }

  const rateRaw =
    options.tracesSampleRate ??
    Number(process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE ?? "0.1");

  if (typeof rateRaw !== "number" || isNaN(rateRaw) || rateRaw < 0 || rateRaw > 1) {
    throw new Error(`tracesSampleRate must be in [0.0, 1.0], got ${rateRaw}`);
  }

  const sendDefaultPii = options.sendDefaultPii ?? false;
  if (typeof sendDefaultPii !== "boolean") {
    throw new Error("sendDefaultPii must be boolean");
  }

  const dsn = options.dsn ?? process.env.NEXT_PUBLIC_SENTRY_DSN;

  const sentry = await _loadSentry();
  if (!sentry) {
    console.warn("@sentry/nextjs not installed; skip init (graceful)");
    _initialized = true;
    return false;
  }

  if (!dsn) {
    console.warn(`NEXT_PUBLIC_SENTRY_DSN not configured; Sentry disabled (env=${env})`);
    _initialized = true;
    return false;
  }

  sentry.init({
    dsn,
    environment: env,
    tracesSampleRate: rateRaw,
    release: options.release ?? process.env.NEXT_PUBLIC_SENTRY_RELEASE,
    sendDefaultPii,
    maxBreadcrumbs: 50,
  });

  _initialized = true;
  return true;
}

export async function captureException(error: unknown): Promise<string | null> {
  const sentry = await _loadSentry();
  if (!sentry) return null;
  return sentry.captureException(error);
}

export async function captureMessage(
  message: string,
  level: "debug" | "info" | "warning" | "error" | "fatal" = "info",
): Promise<string | null> {
  if (typeof message !== "string" || !message.trim()) {
    throw new Error("message must be non-empty string");
  }
  const sentry = await _loadSentry();
  if (!sentry) return null;
  return sentry.captureMessage(message, level);
}

export async function setUser(
  userId: string | null,
  extra: Record<string, unknown> = {},
): Promise<void> {
  const sentry = await _loadSentry();
  if (!sentry) return;
  if (userId === null) {
    sentry.setUser(null);
    return;
  }
  sentry.setUser({ id: userId, ...extra });
}

export async function setTag(key: string, value: string): Promise<void> {
  if (typeof key !== "string" || !key.trim()) {
    throw new Error("tag key must be non-empty string");
  }
  const sentry = await _loadSentry();
  if (!sentry) return;
  sentry.setTag(key, value);
}

/** Test-only: reset for unit tests. */
export function __resetForTests(): void {
  _initialized = false;
  _sentry = null;
}
