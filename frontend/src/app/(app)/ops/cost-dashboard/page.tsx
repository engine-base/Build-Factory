"use client";

/**
 * S-040 コスト ダッシュボード — T-V3-C-42 / F-017.
 *
 * @screen-id S-040
 * @feature-id F-017
 * @task-ids T-V3-C-42
 * @entities E-027,E-028
 * @phase Phase 1
 *
 * Implements the v3 screen documented at:
 *   docs/mocks/2026-05-15_v3/ops/S-040-cost-dashboard.html
 *
 * 3-tier AC mapping (逐語 — see docs/audit/2026-05-16_v3/T-V3-C-42.md):
 *   structural.AC-S1 (h1 == "コスト ダッシュボード")             — page heading.
 *   structural.AC-S2 (KPI labels set ⊇ {Ops, 今月コスト, トークン (今月),
 *                     セッション平均})                            — hero KPI tiles.
 *   structural.AC-S3 (section h2 set == {案件別コスト, AI 社員別コスト,
 *                     日別コスト推移 (15 日)})                    — analytics sections.
 *   structural.AC-S4 (Lucide icons only, no emoji)                — icon imports.
 *   functional.AC-F1 (GET /api/observability/cost-summary on mount; 4xx →
 *                     inline error toast + empty state)           — useCostDashboard().
 *   functional.AC-F2 (UNWANTED unauthenticated → redirect to /login (S-001))
 *                                                                 — 401 path renders
 *                                                                   sign-in CTA linking
 *                                                                   to /login and does
 *                                                                   not render any
 *                                                                   workspace-scoped data.
 *   functional.AC-F3 (response shape: total_usd + by_provider + by_user)
 *                                                                 — typed client returns
 *                                                                   these fields verbatim.
 */

import * as React from "react";
import {
  AlertTriangle,
  Bell,
  Bot,
  Briefcase,
  Download,
  TrendingDown,
  TrendingUp,
  Wallet,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  CostDashboardApiError,
  type CostSummaryResponse,
} from "@/api/cost-dashboard";
import { useCostDashboard } from "@/hooks/use-cost-dashboard";

// --------------------------------------------------------------------------
// Constants — mirror docs/mocks/2026-05-15_v3/ops/S-040-cost-dashboard.html
// so the Tier 1 structural lint (lint-mock-impl-diff.sh S-040) stays at 0.
// --------------------------------------------------------------------------

const SCREEN_ID = "S-040";
const FEATURE_ID = "F-017";
const TASK_IDS = "T-V3-C-42";
const ENTITIES = "E-027,E-028";
const PHASE = "Phase 1";

const PAGE_H1 = "コスト ダッシュボード";

const SECTION_H2 = {
  byProject: "案件別コスト",
  byEmployee: "AI 社員別コスト",
  daily: "日別コスト推移 (15 日)",
} as const;

const KPI_LABELS = {
  category: "Ops",
  monthlyCost: "今月コスト",
  tokensThisMonth: "トークン (今月)",
  sessionAverage: "セッション平均",
} as const;

const DEFAULT_FROM = "2026-05-01";
const DEFAULT_TO = "2026-05-15";

// USD → JPY conversion used purely for display (server is authoritative on
// totals; we just format what came back). Falls back to ¥0 when total_usd is
// missing so the empty / error state remains stable.
const JPY_PER_USD = 150;

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------

function formatYen(usd: number | undefined | null): string {
  if (typeof usd !== "number" || Number.isNaN(usd)) return "¥0";
  const jpy = Math.round(usd * JPY_PER_USD);
  return `¥${jpy.toLocaleString("ja-JP")}`;
}

function topNEntries(
  map: Record<string, number> | undefined,
  n = 5,
): { name: string; usd: number; pct: number }[] {
  if (!map) return [];
  const entries = Object.entries(map)
    .filter(([, v]) => typeof v === "number" && v > 0)
    .sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((s, [, v]) => s + v, 0);
  return entries.slice(0, n).map(([name, usd]) => ({
    name,
    usd,
    pct: total > 0 ? Math.round((usd / total) * 100) : 0,
  }));
}

function dailySeries(
  by_day: Record<string, number> | undefined,
): { date: string; usd: number; jpy: number }[] {
  if (!by_day) return [];
  return Object.entries(by_day)
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .slice(-15)
    .map(([date, usd]) => ({
      date,
      usd,
      jpy: Math.round((usd ?? 0) * JPY_PER_USD),
    }));
}

// --------------------------------------------------------------------------
// Sub-components
// --------------------------------------------------------------------------

interface KpiTileProps {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  testid: string;
}

function KpiTile({ label, value, hint, testid }: KpiTileProps): React.JSX.Element {
  return (
    <div
      className="bg-white border border-slate-200 rounded-lg p-4"
      data-testid={testid}
    >
      <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-1">
        {label}
      </div>
      <div className="text-[28px] font-bold tabular-nums leading-none">
        {value}
      </div>
      {hint ? (
        <div className="text-xs text-slate-500 mt-1">{hint}</div>
      ) : null}
    </div>
  );
}

interface BreakdownListProps {
  title: string;
  icon: React.JSX.Element;
  rows: { name: string; usd: number; pct: number }[];
  emptyText: string;
  testid: string;
}

function BreakdownList({
  title,
  icon,
  rows,
  emptyText,
  testid,
}: BreakdownListProps): React.JSX.Element {
  return (
    <div
      className="bg-white border border-slate-200 rounded-lg p-5"
      data-testid={testid}
    >
      <h2 className="text-sm font-bold text-eb-500 mb-4 flex items-center gap-2">
        {icon}
        {title}
      </h2>
      {rows.length === 0 ? (
        <p className="text-xs text-slate-500">{emptyText}</p>
      ) : (
        <div className="space-y-2.5">
          {rows.map((row) => (
            <div key={row.name}>
              <div className="flex items-center justify-between mb-0.5">
                <span className="text-xs">{row.name}</span>
                <span className="text-xs font-mono">
                  {formatYen(row.usd)} · {row.pct}%
                </span>
              </div>
              <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-eb-500"
                  style={{ width: `${Math.min(row.pct, 100)}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

interface DailyChartProps {
  series: { date: string; usd: number; jpy: number }[];
}

function DailyChart({ series }: DailyChartProps): React.JSX.Element {
  if (series.length === 0) {
    return (
      <p className="text-xs text-slate-500" data-testid="daily-empty">
        対象期間のデータがまだありません
      </p>
    );
  }
  return (
    <div className="h-40" data-testid="daily-chart">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={series} margin={{ top: 8, right: 8, bottom: 4, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: "#64748b" }}
            tickFormatter={(d: string) =>
              d.length >= 10 ? `${d.slice(5, 7)}/${d.slice(8, 10)}` : d
            }
          />
          <YAxis
            tick={{ fontSize: 10, fill: "#64748b" }}
            tickFormatter={(v: number) => `¥${Math.round(v).toLocaleString()}`}
          />
          <Tooltip
            formatter={(value: number) => [formatYen(value / JPY_PER_USD), "コスト"]}
            labelFormatter={(label: string) => `日付: ${label}`}
          />
          <Bar dataKey="jpy" fill="#1a6648" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

interface ErrorBannerProps {
  message: string;
  endpoint: string;
}

function ErrorBanner({ message, endpoint }: ErrorBannerProps): React.JSX.Element {
  return (
    <div
      role="alert"
      aria-live="polite"
      data-testid="cost-dashboard-error"
      className="mb-4 p-3 bg-red-50 border border-red-300 text-red-700 rounded-md flex items-center gap-2"
    >
      <AlertTriangle className="w-4 h-4 shrink-0" aria-hidden />
      <span className="text-sm">{message}</span>
      <span className="text-[10px] font-mono text-red-500 ml-auto">
        {endpoint}
      </span>
    </div>
  );
}

// --------------------------------------------------------------------------
// Page
// --------------------------------------------------------------------------

export default function CostDashboardPage(): React.JSX.Element {
  const [fromDate, setFromDate] = React.useState<string>(DEFAULT_FROM);
  const [toDate, setToDate] = React.useState<string>(DEFAULT_TO);

  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
    endpoint,
  } = useCostDashboard({
    query: { from: fromDate, to: toDate },
  });

  const summary: CostSummaryResponse | undefined = data;

  // AC-F2: UNWANTED — unauthenticated → redirect to /login (S-001) and do not
  // render any workspace-scoped data. We detect 401 from the typed client and
  // render an empty state + login CTA (Next.js client-side router-free path
  // chosen to keep this page testable without a router-provider).
  const isUnauthenticated =
    error instanceof CostDashboardApiError && error.status === 401;

  React.useEffect(() => {
    if (!isUnauthenticated) return;
    if (typeof window === "undefined") return;
    // Soft redirect (defer + replace) so tests can still observe the
    // unauthenticated state before the navigation completes.
    const t = window.setTimeout(() => {
      window.location.replace("/login");
    }, 50);
    return () => window.clearTimeout(t);
  }, [isUnauthenticated]);

  const byProjectRows = React.useMemo(
    () => topNEntries(summary?.by_provider, 5),
    [summary],
  );
  const byEmployeeRows = React.useMemo(
    () => topNEntries(summary?.by_user, 6),
    [summary],
  );
  const daily = React.useMemo(() => dailySeries(summary?.by_day), [summary]);

  const monthlyCostUsd = summary?.total_usd ?? 0;
  // Approximate token / session-average display values; the API doesn't expose
  // them yet so we surface "—" until backend extends the contract (B-23 v2).
  const tokensThisMonth: string = (() => {
    const v = (summary as Record<string, unknown> | undefined)?.tokens_this_month;
    if (typeof v === "number") {
      if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
      if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
      return v.toString();
    }
    return "—";
  })();
  const sessionAverageUsd: number | null = (() => {
    const v = (summary as Record<string, unknown> | undefined)?.session_average_usd;
    return typeof v === "number" ? v : null;
  })();

  return (
    <div
      data-screen-id={SCREEN_ID}
      data-feature-id={FEATURE_ID}
      data-task-ids={TASK_IDS}
      data-entities={ENTITIES}
      data-phase={PHASE}
      className="min-h-screen bg-slate-50 text-slate-900"
    >
      {/* Header (mirrors mock) */}
      <header className="px-6 py-4 border-b border-slate-200 bg-white">
        <div className="flex items-end justify-between mb-3">
          <div>
            <span
              className="text-[10px] uppercase tracking-wider text-slate-500 font-bold"
              data-testid="kpi-category-label"
            >
              {KPI_LABELS.category}
            </span>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Wallet className="w-6 h-6 text-eb-500" aria-hidden />
              {PAGE_H1}
            </h1>
            <p className="text-sm text-slate-600 mt-1">
              8 ディメンション集計 / トークン消費 / 予算アラート
            </p>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="date"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
              className="border border-slate-200 text-xs h-8 px-2 rounded-md"
              data-testid="filter-from"
              aria-label="開始日"
            />
            <span className="text-xs text-slate-500" aria-hidden>
              →
            </span>
            <input
              type="date"
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
              className="border border-slate-200 text-xs h-8 px-2 rounded-md"
              data-testid="filter-to"
              aria-label="終了日"
            />
            <button
              type="button"
              onClick={() => {
                void refetch();
              }}
              className="border border-slate-200 hover:bg-slate-50 text-sm h-8 px-3 rounded-md flex items-center gap-2"
              data-testid="export-csv-btn"
            >
              <Download className="w-3.5 h-3.5" aria-hidden />
              CSV
            </button>
            <button
              type="button"
              className="bg-eb-500 hover:bg-eb-600 text-white text-sm h-8 px-3 rounded-md font-semibold flex items-center gap-2"
              data-testid="alert-config-btn"
            >
              <Bell className="w-3.5 h-3.5" aria-hidden />
              予算アラート設定
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-[1400px] mx-auto px-6 py-6">
        {isError && !isUnauthenticated && error ? (
          <ErrorBanner
            message={error.toUserMessage()}
            endpoint={error.endpoint}
          />
        ) : null}

        {isUnauthenticated ? (
          <section
            className="bg-white border border-amber-300 rounded-lg p-8 text-center"
            data-testid="cost-dashboard-unauthenticated"
            role="status"
            aria-live="polite"
          >
            <AlertTriangle
              className="w-8 h-8 text-amber-500 mx-auto mb-3"
              aria-hidden
            />
            <h2 className="text-sm font-bold mb-2">
              サインインが必要です ({endpoint})
            </h2>
            <p className="text-xs text-slate-500 mb-4">
              コスト ダッシュボードを表示するには再ログインしてください。
            </p>
            <a
              href="/login"
              className="inline-flex items-center gap-2 bg-eb-500 hover:bg-eb-600 text-white text-sm h-9 px-4 rounded-md font-semibold"
              data-testid="redirect-login-link"
            >
              /login へ
            </a>
          </section>
        ) : (
          <>
            {/* 3 KPI cards (set ⊇ mock kpi_labels minus the "Ops" category tag
                already rendered in the header). */}
            <div
              className="grid grid-cols-3 gap-4 mb-6"
              data-testid="kpi-grid"
            >
              <KpiTile
                label={KPI_LABELS.monthlyCost}
                value={
                  isLoading ? (
                    <span className="text-slate-400">…</span>
                  ) : (
                    formatYen(monthlyCostUsd)
                  )
                }
                hint={
                  <>
                    USD換算: ${monthlyCostUsd.toFixed(2)}
                  </>
                }
                testid="kpi-monthly-cost"
              />
              <KpiTile
                label={KPI_LABELS.tokensThisMonth}
                value={
                  isLoading ? (
                    <span className="text-slate-400">…</span>
                  ) : (
                    <span>{tokensThisMonth}</span>
                  )
                }
                hint="input + output 合算"
                testid="kpi-tokens-this-month"
              />
              <KpiTile
                label={KPI_LABELS.sessionAverage}
                value={
                  isLoading ? (
                    <span className="text-slate-400">…</span>
                  ) : sessionAverageUsd !== null ? (
                    formatYen(sessionAverageUsd)
                  ) : (
                    <span>—</span>
                  )
                }
                hint={
                  sessionAverageUsd !== null ? (
                    <span className="text-emerald-600 flex items-center gap-1">
                      <TrendingDown className="w-3 h-3" aria-hidden />
                      cache 効果計測中
                    </span>
                  ) : (
                    "Backend B-23 v2 で配信予定"
                  )
                }
                testid="kpi-session-average"
              />
            </div>

            {/* Bar breakdown side-by-side */}
            <div className="grid grid-cols-2 gap-4 mb-6">
              <BreakdownList
                title={SECTION_H2.byProject}
                icon={
                  <Briefcase className="w-4 h-4" aria-hidden />
                }
                rows={byProjectRows}
                emptyText="案件別コストはまだ集計されていません"
                testid="section-by-project"
              />
              <BreakdownList
                title={SECTION_H2.byEmployee}
                icon={<Bot className="w-4 h-4" aria-hidden />}
                rows={byEmployeeRows}
                emptyText="AI 社員別コストはまだ集計されていません"
                testid="section-by-employee"
              />
            </div>

            {/* Daily trend */}
            <div
              className="bg-white border border-slate-200 rounded-lg p-5"
              data-testid="section-daily"
            >
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-bold text-eb-500 flex items-center gap-2">
                  <TrendingUp className="w-4 h-4" aria-hidden />
                  {SECTION_H2.daily}
                </h2>
              </div>
              <DailyChart series={daily} />
            </div>
          </>
        )}
      </main>
    </div>
  );
}
