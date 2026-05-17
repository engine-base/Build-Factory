"use client";

/**
 * T-V3-C-56 / S-047 — メンテナンス中 (Maintenance) page.
 *
 * Mock source of truth:
 *   docs/mocks/2026-05-15_v3/system/S-047-maintenance.html
 * Spec source of truth:
 *   docs/functional-breakdown/2026-05-16_v3/screens.json#S-047
 *
 * Mock-impl meta (lint-mock-impl-diff Gate #8):
 * @screen-id S-047
 * @feature-id
 * @task-ids T-V3-C-56
 * @entities
 * @phase Phase 1
 *
 * 3-tier AC mapping (逐語 from docs/audit/2026-05-16_v3/T-V3-C-56.md):
 *   structural.AC-S1 (h1 "メンテナンス中")                           — H1 below.
 *   structural.AC-S2 (Lucide icons exclusively, no emoji)             — lucide-react imports.
 *   functional.AC-F1 (401 → /login, no workspace data)                — useEffect router.replace.
 *   functional.AC-F2 (skeleton role="status" aria-live="polite" then  — MaintenanceSkeleton
 *                     atomic swap)                                       conditional render.
 *
 * Design tokens: ENGINE BASE green (eb-500 = #1a6648), Noto Sans JP.
 * Companion: `frontend/middleware.ts` 503-forwards every request to this page
 * when the MAINTENANCE_MODE env flag is set.
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ExternalLink, Wrench } from "lucide-react";

import {
  MaintenanceApiError,
  type MaintenanceStatus,
} from "@/lib/api/maintenance";
import { useMaintenance } from "@/lib/hooks/use-maintenance";

// ---------------------------------------------------------------------------
// Mock-derived literals — 逐語コピー (h1_text from screens.json[S-047]).
// AC-S1: h1_text === "メンテナンス中"
// ---------------------------------------------------------------------------
const S047_H1_TEXT = "メンテナンス中";
const S047_SUBTITLE_LEAD = "サービス品質向上のためメンテナンスを実施しています。";
const S047_SUBTITLE_TAIL = "もうしばらくお待ちください。";
const S047_DETAILS_HEADING = "メンテナンス内容";
const S047_STATUS_LABEL = "ステータス: 進行中 ·";
const S047_STATUS_LINK_TEXT = "status.engine-base.com で詳細を見る";

// ETA countdown — JST display matching the mock.
const JST_TZ = "Asia/Tokyo";

function formatJst(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const fmt = new Intl.DateTimeFormat("ja-JP", {
    timeZone: JST_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const parts = fmt.formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return (
    `${get("year")}-${get("month")}-${get("day")} ` +
    `${get("hour")}:${get("minute")} JST`
  );
}

interface CountdownDisplay {
  elapsedMinutes: number;
  totalMinutes: number;
  progressPercent: number;
  isOverdue: boolean;
}

export function computeCountdown(
  status: Pick<MaintenanceStatus, "started_at" | "eta_at">,
  now: Date = new Date(),
): CountdownDisplay {
  const start = new Date(status.started_at).getTime();
  const end = new Date(status.eta_at).getTime();
  const nowMs = now.getTime();
  if (Number.isNaN(start) || Number.isNaN(end) || end <= start) {
    return {
      elapsedMinutes: 0,
      totalMinutes: 0,
      progressPercent: 0,
      isOverdue: false,
    };
  }
  const totalMinutes = Math.max(1, Math.round((end - start) / 60_000));
  const rawElapsed = Math.round((nowMs - start) / 60_000);
  const elapsedMinutes = Math.max(0, rawElapsed);
  const progressPercent = Math.min(
    100,
    Math.max(0, Math.round((elapsedMinutes / totalMinutes) * 100)),
  );
  const isOverdue = nowMs > end;
  return { elapsedMinutes, totalMinutes, progressPercent, isOverdue };
}

// ---------------------------------------------------------------------------
// Skeleton loader — AC-F2: role="status" aria-live="polite" while loading.
// ---------------------------------------------------------------------------
function MaintenanceSkeleton() {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="読み込み中"
      data-testid="maintenance-skeleton"
      className="text-center max-w-md w-full"
    >
      <div className="inline-flex w-20 h-20 rounded-full bg-slate-200 mb-4 animate-pulse" />
      <div className="h-7 w-2/3 mx-auto bg-slate-200 rounded animate-pulse" />
      <div className="h-4 w-3/4 mx-auto bg-slate-200 rounded mt-3 animate-pulse" />
      <div className="mt-6 bg-white border border-slate-200 rounded-md p-4">
        <div className="h-4 w-full bg-slate-100 rounded animate-pulse" />
        <div className="h-4 w-5/6 bg-slate-100 rounded animate-pulse mt-2" />
        <div className="h-4 w-2/3 bg-slate-100 rounded animate-pulse mt-2" />
        <div className="mt-3 h-2 bg-slate-100 rounded-full animate-pulse" />
      </div>
      <div className="mt-6 bg-white border border-slate-200 rounded-md p-4">
        <div className="h-3 w-1/3 bg-slate-100 rounded animate-pulse" />
        <div className="h-4 w-full bg-slate-100 rounded animate-pulse mt-3" />
        <div className="h-4 w-3/4 bg-slate-100 rounded animate-pulse mt-2" />
      </div>
      <span className="sr-only">読み込み中…</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// S-047 — Maintenance page.
// ---------------------------------------------------------------------------
export default function MaintenancePage() {
  const router = useRouter();
  const { data, isLoading, isError, error } = useMaintenance();

  // AC-F1: UNWANTED — unauthenticated visitor → redirect to /login (S-001).
  React.useEffect(() => {
    if (!isError) return;
    if (error instanceof MaintenanceApiError && error.status === 401) {
      router.replace("/login");
    }
  }, [isError, error, router]);

  // AC-F1 second half: never render any workspace-scoped data while we know
  // the request was unauthenticated. Render an aria-hidden placeholder so the
  // page tree still mounts (avoids React reconciliation churn during redirect).
  if (isError && error instanceof MaintenanceApiError && error.status === 401) {
    return (
      <div
        data-screen-id="S-047"
        data-feature-id=""
        data-task-ids="T-V3-C-56"
        data-screen-name="maintenance"
        data-phase="Phase 1"
        className="min-h-screen bg-slate-50"
        aria-hidden
      />
    );
  }

  // Defensive fallback for any non-401 error / "no active window" 404 — the
  // page still renders the h1 because the mock is the source of truth (the
  // user is told "メンテナンス中" regardless of whether ETA fetch succeeds).
  const countdown = data
    ? computeCountdown({ started_at: data.started_at, eta_at: data.eta_at })
    : null;

  return (
    <div
      data-screen-id="S-047"
      data-feature-id=""
      data-task-ids="T-V3-C-56"
      data-screen-name="maintenance"
      data-phase="Phase 1"
      className="bg-slate-50 min-h-screen flex flex-col font-sans"
    >
      <a
        href="/"
        data-testid="maintenance-back-link"
        className="fixed top-3 right-3 z-50 inline-flex items-center gap-1.5 px-3 py-1.5 bg-white/95 border border-slate-200 rounded-md text-xs font-semibold text-eb-500 shadow-sm hover:bg-white"
      >
        <ArrowLeft className="w-3.5 h-3.5" aria-hidden />
        <span>Index に戻る</span>
      </a>

      <main className="flex-1 flex items-center justify-center px-6 py-8">
        {isLoading ? (
          <MaintenanceSkeleton />
        ) : (
          <div className="text-center max-w-md w-full" data-testid="maintenance-content">
            <div className="inline-flex w-20 h-20 rounded-full bg-eb-50 items-center justify-center mb-4 relative">
              <Wrench className="w-10 h-10 text-eb-500" aria-hidden />
              <span
                className="absolute top-2 right-2 w-2 h-2 rounded-full bg-eb-500"
                aria-hidden
              />
            </div>
            <h1 className="text-2xl font-bold">{S047_H1_TEXT}</h1>
            <p className="text-sm text-slate-600 mt-2 leading-relaxed">
              {S047_SUBTITLE_LEAD}
              <br />
              {S047_SUBTITLE_TAIL}
            </p>

            {data && countdown ? (
              <div
                className="mt-6 bg-white border border-slate-200 rounded-md p-4 text-left"
                data-testid="maintenance-eta"
              >
                <div className="flex justify-between text-sm mb-2">
                  <span className="text-slate-500">開始</span>
                  <span className="font-bold font-mono" data-testid="maintenance-started-at">
                    {formatJst(data.started_at)}
                  </span>
                </div>
                <div className="flex justify-between text-sm mb-2">
                  <span className="text-slate-500">予定終了</span>
                  <span className="font-bold font-mono" data-testid="maintenance-eta-at">
                    {formatJst(data.eta_at)}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-slate-500">経過</span>
                  <span
                    className="font-bold font-mono text-eb-500"
                    data-testid="maintenance-elapsed"
                  >
                    {countdown.elapsedMinutes} 分 / {countdown.totalMinutes} 分
                  </span>
                </div>
                <div
                  className="mt-3 h-2 bg-slate-100 rounded-full overflow-hidden"
                  role="progressbar"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={countdown.progressPercent}
                  aria-label="メンテナンス進行率"
                  data-testid="maintenance-progress"
                >
                  <div
                    className="h-full bg-eb-500"
                    style={{ width: `${countdown.progressPercent}%` }}
                  />
                </div>
              </div>
            ) : null}

            {data && data.items.length > 0 ? (
              <div
                className="mt-6 bg-white border border-slate-200 rounded-md p-4 text-left"
                data-testid="maintenance-items"
              >
                <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-2">
                  {S047_DETAILS_HEADING}
                </div>
                <ul className="text-sm space-y-1 list-disc pl-5 text-slate-700">
                  {data.items.map((item) => (
                    <li key={item.label}>{item.label}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            <div className="mt-6 flex items-center justify-center gap-2 text-xs text-slate-500">
              <span
                className="w-1.5 h-1.5 rounded-full bg-eb-500"
                aria-hidden
              />
              <span>{S047_STATUS_LABEL}</span>
              {data?.status_page_url ? (
                <a
                  href={data.status_page_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-eb-500 hover:underline inline-flex items-center gap-1"
                  data-testid="maintenance-status-link"
                >
                  <span>{S047_STATUS_LINK_TEXT}</span>
                  <ExternalLink className="w-3 h-3" aria-hidden />
                </a>
              ) : (
                <span data-testid="maintenance-status-link-missing">
                  {S047_STATUS_LINK_TEXT}
                </span>
              )}
            </div>

            {isError &&
            (!(error instanceof MaintenanceApiError) ||
              error.status !== 401) ? (
              <p
                className="mt-4 text-xs text-slate-400"
                data-testid="maintenance-fallback-note"
              >
                最新のメンテナンス情報を取得できませんでした。
              </p>
            ) : null}
          </div>
        )}
      </main>
    </div>
  );
}
