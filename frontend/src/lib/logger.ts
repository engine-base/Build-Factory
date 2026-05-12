/**
 * T-S0-11: pino 中央集約 logger (Frontend).
 *
 * 目的:
 *   Build-Factory 全 frontend で構造化ログを統一する.
 *   production では JSON 出力 (Sentry breadcrumbs / クラウド log 取込み),
 *   development では pino-pretty で人間可読 colored 出力.
 *
 * ADR-010 / audit_logs との関係 (backend logging_config.py と同じ精神):
 *   - pino (本 module): 人間 / 監視ツール / Sentry 向け. ephemeral / 非永続. 全ログ.
 *   - audit_logs (DB): 監査 trail. 重要イベントのみ. backend 経由のみ書込.
 *
 *   pino 出力に audit_logs を二重書きしない.
 *
 * 使い方:
 *   import { logger, withContext } from "@/lib/logger";
 *   logger.info({ event: "page.view", path: "/dashboard" });
 *   const reqLogger = withContext({ request_id: uuid, actor_user_id: "alice" });
 *   reqLogger.warn({ event: "rate_limit.near" }, "API approaching limit");
 *
 * AC マッピング (1:1 backend と対):
 *   AC-1 UBIQUITOUS    : pino で全 frontend ログ統一 (JSON/pretty).
 *   AC-2 EVENT-DRIVEN  : withContext() で per-component / per-request context 追加.
 *   AC-3 STATE-DRIVEN  : pino-pretty は dev のみ (transport: pino-pretty), prod は JSON.
 *   AC-4 UNWANTED      : log 出力で secret / 認証情報を含めない (caller 責任).
 */
import pino, { type Logger } from "pino";

/**
 * 環境判定.
 * - production: NEXT_PUBLIC_NODE_ENV === "production" or process.env.NODE_ENV === "production"
 * - development: それ以外
 */
const isProduction =
  typeof process !== "undefined" &&
  (process.env.NEXT_PUBLIC_NODE_ENV === "production" ||
    process.env.NODE_ENV === "production");

/**
 * 既定 log level. LOG_LEVEL env var で上書き可能.
 * - dev default: "debug"
 * - prod default: "info"
 */
const defaultLevel =
  typeof process !== "undefined" && process.env.LOG_LEVEL
    ? process.env.LOG_LEVEL
    : isProduction
      ? "info"
      : "debug";

/**
 * pino logger インスタンス (singleton, 全 frontend で共有).
 *
 * dev では pino-pretty に流し込んで色付き表示. prod ではそのまま JSON 出力.
 * Next.js の SSR / RSC でも import-safe (browser/node 両対応).
 */
export const logger: Logger = pino({
  level: defaultLevel,
  ...(isProduction
    ? {}
    : {
        // dev のみ pino-pretty を使う (prod は dependency に含めない)
        transport: {
          target: "pino-pretty",
          options: {
            colorize: true,
            translateTime: "SYS:HH:MM:ss.l",
            ignore: "pid,hostname",
          },
        },
      }),
});

/**
 * Per-request / per-component context bindings.
 *
 * 推奨 keys:
 *   - request_id: per-request UUID
 *   - session_id: claude-agent-sdk session (when available)
 *   - actor_user_id: 認証 user id
 *   - component: React component name (debugging)
 *
 * Example:
 *   const reqLogger = withContext({ request_id, actor_user_id });
 *   reqLogger.info({ event: "form.submit" });
 *
 * @param ctx Context key-value pairs to bind.
 * @returns child logger with context bound.
 */
export function withContext(ctx: Record<string, unknown>): Logger {
  return logger.child(ctx);
}

/**
 * 環境情報 (test 用に export).
 */
export const __loggerEnv = {
  isProduction,
  defaultLevel,
};
