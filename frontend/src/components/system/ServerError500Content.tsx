"use client";

/**
 * T-V3-C-54 / S-045 — Shared body for the 500 server-error screen.
 *
 * Rendered from three callers:
 *   - frontend/src/app/global-error.tsx  (Next.js 15 root error boundary)
 *   - frontend/src/app/error.tsx         (Next.js 15 route error boundary)
 *   - frontend/src/app/(system)/server-error-500/page.tsx (regular route)
 *
 * Mock-impl source of truth:
 *   docs/mocks/2026-05-15_v3/system/S-045-server-error-500.html
 * Spec:
 *   docs/functional-breakdown/2026-05-16_v3/screens.json#S-045
 *
 * 3-tier AC mapping (T-V3-C-54):
 *   - Tier 1 / AC-S1: h1 === "サーバーエラー" (mock h1 逐語コピー)
 *   - Tier 1 / AC-S2: Lucide icons only — react-icons / emoji 禁止
 *   - Tier 2 / AC-F1: UNWANTED 401 → router.replace("/login") + no workspace data
 *   - Tier 2 / AC-F2: STATE-DRIVEN skeleton role="status" aria-live="polite"
 *
 * Design system: ENGINE BASE green (#1a6648 = eb-500), Noto Sans JP.
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  AlertOctagon,
  Factory,
  Home,
  LifeBuoy,
  RotateCw,
} from "lucide-react";

import { useServerError500 } from "@/hooks/useServerError500";
import { ServerError500ApiError } from "@/api/server-error-500";
import { captureException } from "@/lib/sentry";

// ---------------------------------------------------------------------------
// Mock-derived literals — 逐語コピー from screens.json[S-045].
// AC-S1: h1_text === "サーバーエラー"
// ---------------------------------------------------------------------------
const S045_H1_TEXT = "サーバーエラー";
const S045_LEAD =
  "一時的な問題が発生しています。少し時間をおいて再度お試しください。";
const S045_DASHBOARD_PATH = "/dashboard"; // S-006 account dashboard
const SUPPORT_MAILTO = "mailto:support@engine-base.com";

export interface ServerError500ContentProps {
  /** Error captured by an upstream React boundary (global-error / error.tsx). */
  error?: (Error & { digest?: string }) | null;
  /** Reset callback provided by the React error boundary, if any. */
  reset?: () => void;
}

// ---------------------------------------------------------------------------
// Skeleton loader — AC-F2: role="status" aria-live="polite".
// ---------------------------------------------------------------------------
function ServerError500Skeleton() {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="エラー情報を読み込み中"
      data-testid="server-error-500-skeleton"
      className="text-center max-w-md w-full"
    >
      <div className="inline-flex w-20 h-20 rounded-full bg-slate-100 animate-pulse mb-4" />
      <div className="h-24 w-32 mx-auto bg-slate-100 rounded animate-pulse" />
      <div className="h-6 w-2/3 mx-auto bg-slate-100 rounded mt-4 animate-pulse" />
      <div className="h-4 w-3/4 mx-auto bg-slate-100 rounded mt-3 animate-pulse" />
      <div className="mt-6 h-28 bg-slate-100 rounded animate-pulse" />
      <span className="sr-only">読み込み中…</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main body — used by global-error / error.tsx / route page.
// ---------------------------------------------------------------------------
export default function ServerError500Content(
  props: ServerError500ContentProps = {},
) {
  const { error, reset } = props;
  const router = useRouter();

  // Surface the boundary error to Sentry as a breadcrumb-bearing event.
  // The `captureException` helper degrades gracefully when @sentry/nextjs
  // or the DSN are unavailable (see frontend/src/lib/sentry.ts).
  React.useEffect(() => {
    if (!error) return;
    void captureException(error);
  }, [error]);

  // The boundary-supplied error may carry a `digest` (Next.js 15 production
  // build) — use it as the correlation id when querying the backend.
  const errorId = error?.digest ?? null;

  const {
    data,
    isLoading,
    isError: isContextError,
    error: contextError,
  } = useServerError500({ errorId, enabled: Boolean(errorId) });

  // AC-F1: UNWANTED — unauthenticated visitor → redirect to /login (S-001).
  // We mirror the welcome page implementation: detect 401 from the error
  // context fetch and bail out of rendering any workspace-scoped data.
  React.useEffect(() => {
    if (!isContextError) return;
    if (
      contextError instanceof ServerError500ApiError &&
      contextError.status === 401
    ) {
      router.replace("/login");
    }
  }, [isContextError, contextError, router]);

  if (
    isContextError &&
    contextError instanceof ServerError500ApiError &&
    contextError.status === 401
  ) {
    return (
      <div
        data-screen-id="S-045"
        data-feature-id="F-system"
        data-screen-name="server_error_500"
        className="min-h-screen bg-slate-50"
        aria-hidden
      />
    );
  }

  const handleRetry = () => {
    if (reset) {
      reset();
      return;
    }
    if (typeof window !== "undefined") {
      window.location.reload();
    }
  };

  return (
    <div
      data-screen-id="S-045"
      data-feature-id="F-system"
      data-screen-name="server_error_500"
      className="min-h-screen flex flex-col bg-slate-50 text-slate-900 font-sans"
    >
      <header className="px-6 py-4 border-b border-slate-200 bg-white">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-md bg-eb-500 flex items-center justify-center">
            <Factory className="w-4 h-4 text-white" aria-hidden />
          </div>
          <div className="text-sm font-bold">Build-Factory</div>
        </div>
      </header>

      <main className="flex-1 flex items-center justify-center px-6 py-10">
        {isLoading ? (
          <ServerError500Skeleton />
        ) : (
          <div
            className="text-center max-w-md w-full"
            data-testid="server-error-500-content"
          >
            <div className="inline-flex w-20 h-20 rounded-full bg-red-50 items-center justify-center mb-4">
              <AlertOctagon
                className="w-10 h-10 text-red-600"
                aria-hidden
              />
            </div>
            <div
              className="text-[100px] font-bold tabular-nums text-red-600 leading-none"
              data-testid="server-error-500-status"
            >
              500
            </div>
            <h1 className="text-2xl font-bold mt-4">{S045_H1_TEXT}</h1>
            <p className="text-sm text-slate-600 mt-2">{S045_LEAD}</p>

            <div className="mt-6 bg-white border border-red-200 rounded-md p-4 text-left">
              <div className="text-[10px] uppercase tracking-wider text-red-600 font-bold mb-2">
                エラー詳細
              </div>
              <dl
                className="space-y-1.5 text-xs font-mono"
                data-testid="server-error-500-details"
              >
                <div className="flex">
                  <dt className="text-slate-500 w-24">error_id:</dt>
                  <dd data-testid="server-error-500-error-id">
                    {data?.error_id ?? errorId ?? "(unknown)"}
                  </dd>
                </div>
                <div className="flex">
                  <dt className="text-slate-500 w-24">timestamp:</dt>
                  <dd>{data?.timestamp ?? "—"}</dd>
                </div>
                <div className="flex">
                  <dt className="text-slate-500 w-24">path:</dt>
                  <dd>{data?.path ?? "—"}</dd>
                </div>
                <div className="flex">
                  <dt className="text-slate-500 w-24">status:</dt>
                  <dd className="text-red-600 font-bold">
                    {data?.status ?? 500} Internal Server Error
                  </dd>
                </div>
              </dl>
              <div className="mt-3 pt-3 border-t border-slate-100 text-[11px] text-slate-500">
                問題は自動的に開発チームに通知されました
              </div>
            </div>

            <div className="mt-6 flex items-center justify-center gap-3">
              <button
                type="button"
                onClick={handleRetry}
                data-testid="server-error-500-retry-button"
                className="border border-slate-200 hover:bg-slate-50 text-sm h-10 px-5 rounded-md flex items-center gap-2"
              >
                <RotateCw className="w-4 h-4" aria-hidden />
                <span>再試行</span>
              </button>
              <a
                href={S045_DASHBOARD_PATH}
                data-testid="server-error-500-dashboard-link"
                className="bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-10 px-5 rounded-md flex items-center gap-2"
              >
                <Home className="w-4 h-4" aria-hidden />
                <span>ダッシュボードへ</span>
              </a>
            </div>

            <div className="text-xs text-slate-500 mt-6">
              5 分以上続く場合{" "}
              <a
                href={data?.support_url ?? SUPPORT_MAILTO}
                data-testid="server-error-500-support-link"
                className="text-eb-500 hover:underline inline-flex items-center gap-1"
              >
                <LifeBuoy className="w-3.5 h-3.5" aria-hidden />
                <span>サポートに連絡 (error_id を伝えてください)</span>
              </a>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
