"use client";

/**
 * T-V3-C-53 / S-044 — 404 Not Found page.
 *
 * This file is the canonical Next.js 15 `not-found.tsx` route handler — it
 * renders for any path that doesn't match a defined route, *and* for any
 * `notFound()` call from nested route segments. The mock at
 * `docs/mocks/2026-05-15_v3/system/S-044-not-found-404.html` is the
 * source-of-truth for layout and copy.
 *
 * Mock-impl meta (lint-mock-impl-diff Gate #8):
 *   @screen-id S-044
 *   @screen-name not_found_404
 *   @feature-id F-system
 *   @task-ids T-V3-SYS-01,T-V3-C-53
 *   @entities
 *   @phase Phase 1
 *
 * 3-tier AC mapping (逐語):
 *   structural.AC-S1: STATE-DRIVEN — h1 with exact text "ページが見つかりません".
 *   structural.AC-S2: UBIQUITOUS — Lucide icons only, no emoji.
 *   functional.AC-F1: EVENT-DRIVEN — static page, no API call. Skeleton +
 *     loaded body, on 4xx (N/A here) would render inline error toast.
 *   functional.AC-F2: UNWANTED — visitors are NOT redirected to /login from
 *     this page because S-044 is a public system page; workspace-scoped
 *     paths still pass through `(app)/layout.tsx` auth guards, so an
 *     unauthenticated visitor never reaches this component with workspace
 *     data in scope.
 *   functional.AC-F3: STATE-DRIVEN — render skeleton with role="status"
 *     aria-live="polite" while the `useNotFound404` hook hydrates the
 *     `requestedPath` from `window.location.pathname` on mount, then
 *     atomically replace it with the content block.
 */

import * as React from "react";
import Link from "next/link";
import {
  ArrowLeft,
  Factory,
  FolderKanban,
  Home,
  HelpCircle,
  LayoutDashboard,
  LifeBuoy,
  Search as SearchIcon,
} from "lucide-react";

import { useNotFound404 } from "@/lib/hooks/use-not-found-404";
import type { KnownRoute } from "@/lib/api/not-found-404";

/** Static map from `KnownRoute.icon` string → Lucide icon component. */
const ICONS: Record<KnownRoute["icon"], React.ComponentType<{ className?: string }>> = {
  Home,
  LayoutDashboard,
  FolderKanban,
  Search: SearchIcon,
  HelpCircle,
};

export default function NotFoundPage(): React.JSX.Element {
  const { query, setQuery, matches, requestedPath } = useNotFound404();

  // While `requestedPath` is null (SSR / first render before useEffect runs)
  // we render the skeleton; once the hook resolves the path we swap to the
  // content block atomically. This satisfies AC-F3 even though the hook is
  // purely client-side (no fetch).
  const isLoading = requestedPath === null;

  return (
    <div
      data-screen-id="S-044"
      data-screen-name="not_found_404"
      data-feature-id="F-system"
      data-task-ids="T-V3-SYS-01,T-V3-C-53"
      data-entities=""
      data-phase="Phase 1"
      className="bg-slate-50 min-h-screen flex flex-col"
    >
      {/* Page header (mirrors mock S-044 line 16). */}
      <header className="px-6 py-4 border-b border-slate-200 bg-white">
        <div className="flex items-center gap-2">
          <div
            className="w-7 h-7 rounded-md bg-eb-500 flex items-center justify-center"
            aria-hidden
          >
            <Factory className="w-4 h-4 text-white" />
          </div>
          <div className="text-sm font-bold">Build-Factory</div>
        </div>
      </header>

      <main className="flex-1 flex items-center justify-center px-6 py-10">
        {isLoading ? (
          <div
            role="status"
            aria-live="polite"
            data-testid="not-found-skeleton"
            className="w-full max-w-md text-center space-y-4 animate-pulse"
          >
            <div className="h-[120px] w-[160px] mx-auto rounded-md bg-slate-200" />
            <div className="h-7 w-2/3 mx-auto rounded bg-slate-200" />
            <div className="h-4 w-4/5 mx-auto rounded bg-slate-200" />
            <span className="sr-only">読み込み中…</span>
          </div>
        ) : (
          <div
            className="w-full max-w-2xl text-center"
            data-testid="not-found-content"
          >
            <div
              className="text-[120px] font-bold tabular-nums text-eb-500 leading-none"
              aria-hidden
            >
              404
            </div>
            <h1 className="text-2xl font-bold mt-4">ページが見つかりません</h1>
            <p className="text-sm text-slate-600 mt-2">
              URL が変更されたか、削除された可能性があります。
            </p>
            {requestedPath ? (
              <p
                className="text-xs text-slate-500 font-mono mt-2 bg-slate-100 inline-block px-3 py-1 rounded"
                data-testid="not-found-requested-path"
              >
                requested: {requestedPath}
              </p>
            ) : null}

            {/* Primary CTAs — mirror mock buttons (lines 23-26). */}
            <div className="mt-8 flex items-center justify-center gap-3 flex-wrap">
              <button
                type="button"
                onClick={() => {
                  if (typeof window !== "undefined") {
                    window.history.back();
                  }
                }}
                data-testid="not-found-back-button"
                className="border border-slate-200 hover:bg-slate-50 text-sm h-10 px-5 rounded-md flex items-center gap-2"
              >
                <ArrowLeft className="w-4 h-4" aria-hidden />
                前のページへ戻る
              </button>
              <Link
                href="/"
                data-testid="not-found-home-link"
                className="bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-10 px-5 rounded-md inline-flex items-center gap-2"
              >
                <Home className="w-4 h-4" aria-hidden />
                ダッシュボードへ
              </Link>
            </div>

            {/* Search box — visitor can filter the known-routes list. */}
            <div className="mt-10 mx-auto max-w-md">
              <label
                htmlFor="not-found-search"
                className="block text-left text-xs font-semibold text-slate-500 mb-1"
              >
                ページを検索
              </label>
              <div className="relative">
                <SearchIcon
                  className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400"
                  aria-hidden
                />
                <input
                  id="not-found-search"
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="ダッシュボード / タスク / 監査ログ..."
                  data-testid="not-found-search-input"
                  aria-label="ページを検索"
                  className="h-10 w-full rounded-md border border-slate-200 bg-white pl-9 pr-3 text-sm focus-visible:border-eb-500 focus-visible:outline-none"
                />
              </div>
            </div>

            {/* Known-routes suggestion list. */}
            <ul
              className="mt-6 mx-auto max-w-md text-left space-y-2"
              data-testid="not-found-suggestions"
              aria-label="提案ルート"
            >
              {matches.length === 0 ? (
                <li
                  className="rounded-md border border-slate-200 bg-white px-4 py-3 text-sm text-slate-500 text-center"
                  data-testid="not-found-suggestions-empty"
                >
                  該当するページはありません
                </li>
              ) : (
                matches.map((route) => {
                  const Icon = ICONS[route.icon];
                  return (
                    <li key={route.href}>
                      <Link
                        href={route.href}
                        data-testid={`not-found-suggestion-${route.href}`}
                        className="flex items-center gap-3 rounded-md border border-slate-200 bg-white px-4 py-3 hover:border-eb-500 hover:bg-eb-50"
                      >
                        <Icon className="w-4 h-4 text-eb-500" aria-hidden />
                        <span className="flex-1">
                          <span className="block text-sm font-semibold">
                            {route.label}
                          </span>
                          <span className="block text-xs text-slate-500">
                            {route.description}
                          </span>
                        </span>
                      </Link>
                    </li>
                  );
                })
              )}
            </ul>

            <div className="text-xs text-slate-500 mt-8 flex items-center justify-center gap-1">
              <LifeBuoy className="w-3.5 h-3.5" aria-hidden />
              問題が続く場合{" "}
              <a className="text-eb-500 hover:underline" href="mailto:support@engine-base.com">
                サポートに連絡
              </a>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
