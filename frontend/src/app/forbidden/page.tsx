"use client";

/**
 * T-V3-C-55 / S-046 — 403 Forbidden (forbidden_403) system page.
 *
 * Mock-impl source of truth:
 *   docs/mocks/2026-05-15_v3/system/S-046-forbidden-403.html
 * Spec source of truth:
 *   docs/functional-breakdown/2026-05-16_v3/screens.json#S-046
 *
 * 3-tier AC mapping (T-V3-C-55):
 *   - Tier 1 / AC-S1: h1 === "アクセス権限がありません" (mock h1 逐語コピー)
 *   - Tier 1 / AC-S2: Lucide icons only, no emojis (design-tokens.md §8)
 *   - Tier 2 / AC-F1: 401 → router.replace("/login") (no workspace data render)
 *   - Tier 2 / AC-F2: skeleton role="status" aria-live="polite" while loading
 *
 * Design system: ENGINE BASE green (#1a6648 = eb-500), Noto Sans JP, shadcn/ui.
 *
 * Route: /forbidden (App Router). The Next.js middleware (frontend/middleware.ts)
 * forwards backend-403 responses here via x-bf-forbidden-redirect.
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Factory, Home, Lock, Mail } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ForbiddenApiError } from "@/lib/api/forbidden-403";
import { useForbidden403 } from "@/hooks/use-forbidden-403";

// ---------------------------------------------------------------------------
// Mock-derived screen literals — 逐語コピー (h1_text from screens.json[S-046]).
// AC-S1: h1 === "アクセス権限がありません"
// ---------------------------------------------------------------------------
const S046_H1_TEXT = "アクセス権限がありません";
const S046_SUBTITLE =
  "このページを表示する権限がアカウントに付与されていません。";

const CURRENT_ROLE_LABEL = "現在のロール";
const REQUIRED_ROLE_LABEL = "必要なロール";
const READONLY_NOTE = "(読み取り専用)";

const REQUEST_ACCESS_LABEL = "管理者にロール変更依頼";
const REQUEST_ACCESS_DONE_LABEL = "依頼を送信しました";
const DASHBOARD_LABEL = "ダッシュボードへ";

const DASHBOARD_PATH = "/dashboard";

// ---------------------------------------------------------------------------
// Skeleton loader — AC-F2: role="status" aria-live="polite" while loading.
// ---------------------------------------------------------------------------
function ForbiddenSkeleton() {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="読み込み中"
      data-testid="forbidden-skeleton"
      className="max-w-md w-full"
    >
      <div className="flex flex-col items-center gap-3 text-center">
        <div className="w-20 h-20 rounded-full bg-slate-200 animate-pulse" />
        <div className="h-20 w-32 bg-slate-200 rounded animate-pulse" />
        <div className="h-7 w-3/4 bg-slate-200 rounded animate-pulse" />
        <div className="h-4 w-full bg-slate-200 rounded animate-pulse" />
      </div>
      <div className="mt-6 h-32 bg-white border border-slate-200 rounded-md p-4 animate-pulse" />
      <div className="mt-6 flex items-center justify-center gap-3">
        <div className="h-10 w-44 bg-slate-200 rounded-md animate-pulse" />
        <div className="h-10 w-44 bg-slate-200 rounded-md animate-pulse" />
      </div>
      <span className="sr-only">読み込み中…</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// S-046 — Forbidden (403) page.
// ---------------------------------------------------------------------------
export default function Forbidden403Page() {
  const router = useRouter();
  const {
    data,
    isLoading,
    isError,
    error,
    unauthenticated,
    requestAccess,
    isRequestingAccess,
    isAccessRequested,
  } = useForbidden403();

  // AC-F1: UNWANTED — unauthenticated visitor → redirect to /login (S-001).
  // We do this in an effect so the redirect runs after render commit and
  // server components don't see partially-rendered workspace data.
  React.useEffect(() => {
    if (unauthenticated) {
      router.replace("/login");
    }
  }, [unauthenticated, router]);

  // If we already know we're unauthorised, render nothing so no workspace-
  // scoped UI ever appears — AC-F1 second-half guarantee.
  if (unauthenticated) {
    return (
      <div
        data-screen-id="S-046"
        data-screen-name="forbidden_403"
        className="min-h-screen bg-slate-50"
        aria-hidden
      />
    );
  }

  const handleDashboard = () => {
    router.push(DASHBOARD_PATH);
  };

  const handleRequestAccess = async () => {
    try {
      await requestAccess();
    } catch (err) {
      // Non-401 errors do not redirect; the page surfaces the message
      // inline via the typed error envelope rather than throwing further.
      if (err instanceof ForbiddenApiError && err.status === 401) {
        router.replace("/login");
      }
    }
  };

  // Non-401 fetch errors keep the page renderable (defaults below ensure
  // the role chips degrade gracefully — we do NOT swallow the role data,
  // we just fall back to a neutral label).
  const currentRole =
    !isError && data?.role ? data.role : ("guest" as const);
  const requiredRole = "workspace_admin" as const;

  return (
    <div
      data-screen-id="S-046"
      data-screen-name="forbidden_403"
      data-screen-category="system"
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

      <main
        className="flex-1 flex items-center justify-center px-6 py-8"
        role="main"
      >
        {isLoading ? (
          <ForbiddenSkeleton />
        ) : (
          <div
            className="text-center max-w-md w-full"
            data-testid="forbidden-content"
          >
            <div className="inline-flex w-20 h-20 rounded-full bg-amber-50 items-center justify-center mb-4">
              <Lock className="w-10 h-10 text-amber-600" aria-hidden />
            </div>
            <div className="text-[100px] font-bold tabular-nums text-amber-600 leading-none">
              403
            </div>
            <h1 className="text-2xl font-bold mt-4">{S046_H1_TEXT}</h1>
            <p className="text-sm text-slate-600 mt-2">{S046_SUBTITLE}</p>

            {/* Role mismatch explanation — current vs required (from mock). */}
            <div
              className="mt-6 bg-white border border-slate-200 rounded-md p-4 text-left"
              data-testid="forbidden-role-card"
            >
              <div className="text-xs text-slate-500 mb-2 font-semibold">
                {CURRENT_ROLE_LABEL}
              </div>
              <div className="flex items-center gap-2">
                <span
                  className="text-[11px] bg-slate-100 text-slate-700 border border-slate-200 px-2 py-0.5 rounded-full font-mono"
                  data-testid="forbidden-current-role"
                >
                  {currentRole}
                </span>
                <span className="text-xs text-slate-500">{READONLY_NOTE}</span>
              </div>
              <div className="text-xs text-slate-500 mt-3 font-semibold">
                {REQUIRED_ROLE_LABEL}
              </div>
              <div className="mt-2">
                <span
                  className="text-[11px] bg-eb-50 text-eb-700 border border-eb-500/30 px-2 py-0.5 rounded-full font-mono"
                  data-testid="forbidden-required-role"
                >
                  {requiredRole}
                </span>
              </div>
            </div>

            <div className="mt-6 flex items-center justify-center gap-3 flex-wrap">
              <Button
                type="button"
                onClick={handleRequestAccess}
                disabled={isRequestingAccess || isAccessRequested}
                data-testid="forbidden-request-access-button"
                variant="outline"
                className="border border-slate-200 hover:bg-slate-50 text-sm h-10 px-5 rounded-md flex items-center gap-2 disabled:opacity-60"
              >
                <Mail className="w-4 h-4" aria-hidden />
                <span>
                  {isAccessRequested
                    ? REQUEST_ACCESS_DONE_LABEL
                    : REQUEST_ACCESS_LABEL}
                </span>
              </Button>
              <Button
                type="button"
                onClick={handleDashboard}
                data-testid="forbidden-dashboard-button"
                className="bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-10 px-5 rounded-md flex items-center gap-2"
              >
                <Home className="w-4 h-4" aria-hidden />
                <span>{DASHBOARD_LABEL}</span>
              </Button>
            </div>

            {/* Inline error surface for non-401 failures (non-technical). */}
            {isError &&
            error instanceof ForbiddenApiError &&
            error.status !== 401 ? (
              <p
                className="mt-4 text-xs text-amber-700"
                role="alert"
                data-testid="forbidden-inline-error"
              >
                <ArrowLeft className="inline w-3 h-3 mr-1" aria-hidden />
                {error.message}
              </p>
            ) : null}
          </div>
        )}
      </main>
    </div>
  );
}
