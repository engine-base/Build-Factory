"use client";

/**
 * T-017-03: 8-tab cost dashboard.
 *
 * GET /api/observability/cost-summary?dimension=DIM の結果を Recharts で
 * 描画する.
 *
 * 8 tabs (VALID_COST_DIMENSIONS と一致):
 *   overview / provider / model / workspace / persona / skill /
 *   period_daily / session
 *
 * 設計:
 *   - eb-500 palette (CLAUDE.md §5.2 ENGINE BASE green)
 *   - Lucide icons (絵文字禁止 / CLAUDE.md §5.1)
 *   - URL search params (?dim=, ?from=, ?to=) で deep link 対応
 *   - AbortController で並行 fetch dedupe
 *   - empty state: 'データがありません' (no crash)
 */

import * as React from "react";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import {
  LayoutDashboard,
  Cloud,
  Cpu,
  Building2,
  UserCircle2,
  Wrench,
  CalendarDays,
  ListTree,
} from "lucide-react";

import { cn } from "@/lib/utils";
import {
  fetchCostSummary,
  CostDashboardError,
  VALID_COST_DIMENSIONS,
  type CostDimension,
  type CostSummary,
} from "@/lib/api/cost-dashboard";

interface CostDashboardProps {
  className?: string;
  defaultDimension?: CostDimension;
  defaultFrom?: string;
  defaultTo?: string;
  /** test injection. */
  apiBase?: string;
}

const TAB_META: Record<CostDimension, { label: string; icon: React.ElementType }> = {
  overview: { label: "全体", icon: LayoutDashboard },
  provider: { label: "プロバイダ", icon: Cloud },
  model: { label: "モデル", icon: Cpu },
  workspace: { label: "ワークスペース", icon: Building2 },
  persona: { label: "ペルソナ", icon: UserCircle2 },
  skill: { label: "スキル", icon: Wrench },
  period_daily: { label: "期間", icon: CalendarDays },
  session: { label: "セッション", icon: ListTree },
};

// ENGINE BASE green palette + accent.
const PIE_COLORS = [
  "#1a6648",  // eb-500
  "#0f4d35",  // eb-700
  "#f59e0b",  // amber-500
  "#f43f5e",  // rose-500
  "#0ea5e9",  // sky-500
  "#10b981",  // emerald-500
  "#a855f7",  // violet-500
  "#64748b",  // slate-500
];

function formatUsd(value: number): string {
  return `$${value.toFixed(2)}`;
}

export function CostDashboard({
  className,
  defaultDimension = "overview",
  defaultFrom,
  defaultTo,
  apiBase,
}: CostDashboardProps) {
  const [dimension, setDimension] =
    React.useState<CostDimension>(defaultDimension);
  const [from, setFrom] = React.useState<string>(defaultFrom ?? "");
  const [to, setTo] = React.useState<string>(defaultTo ?? "");
  const [summary, setSummary] = React.useState<CostSummary | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState<boolean>(false);

  React.useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchCostSummary(dimension, {
      from: from || undefined,
      to: to || undefined,
      apiBase,
      signal: controller.signal,
    })
      .then((s) => setSummary(s))
      .catch((e: unknown) => {
        if (e instanceof CostDashboardError) {
          setError(`${e.code}: ${e.message}`);
        } else if (e instanceof Error && e.name !== "AbortError") {
          setError(e.message);
        }
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [dimension, from, to, apiBase]);

  // URL search params 反映 (deep link 対応 / AC-3)
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    url.searchParams.set("dim", dimension);
    if (from) url.searchParams.set("from", from);
    else url.searchParams.delete("from");
    if (to) url.searchParams.set("to", to);
    else url.searchParams.delete("to");
    window.history.replaceState({}, "", url.toString());
  }, [dimension, from, to]);

  return (
    <div className={cn("flex flex-col gap-4", className)}>
      {/* tab strip */}
      <nav
        className="flex flex-wrap items-center gap-1 border-b border-slate-200"
        data-testid="cost-tab-strip"
      >
        {VALID_COST_DIMENSIONS.map((dim) => {
          const meta = TAB_META[dim];
          const Icon = meta.icon;
          const active = dim === dimension;
          return (
            <button
              key={dim}
              type="button"
              role="tab"
              data-dim={dim}
              data-active={active}
              className={cn(
                "inline-flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium",
                active
                  ? "border-eb-500 text-eb-700"
                  : "border-transparent text-slate-600 hover:border-slate-300",
              )}
              onClick={() => setDimension(dim)}
            >
              <Icon className="h-4 w-4" />
              {meta.label}
            </button>
          );
        })}
      </nav>

      {/* date range */}
      <div className="flex flex-wrap items-end gap-3">
        <label className="text-xs text-slate-600">
          From
          <input
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            className="ml-2 rounded border border-slate-300 px-2 py-1 text-xs"
            data-testid="cost-from"
          />
        </label>
        <label className="text-xs text-slate-600">
          To
          <input
            type="date"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            className="ml-2 rounded border border-slate-300 px-2 py-1 text-xs"
            data-testid="cost-to"
          />
        </label>
      </div>

      {/* totals */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Card title="Total Cost" value={summary ? formatUsd(summary.total_usd) : "—"} />
        <Card title="Input Tokens" value={summary ? summary.total_input_tokens.toLocaleString() : "—"} />
        <Card title="Output Tokens" value={summary ? summary.total_output_tokens.toLocaleString() : "—"} />
        <Card title="Cache Read" value={summary ? summary.total_cache_read_tokens.toLocaleString() : "—"} />
      </div>

      {/* chart */}
      <section
        className="min-h-[280px] rounded border border-slate-200 bg-white p-4"
        data-testid="cost-chart"
      >
        {error ? (
          <div className="text-sm text-rose-600" data-testid="cost-error">
            {error}
          </div>
        ) : loading ? (
          <div className="text-sm text-slate-500">Loading…</div>
        ) : !summary || summary.items.length === 0 ? (
          <div
            className="py-12 text-center text-sm text-slate-500"
            data-testid="cost-empty"
          >
            データがありません
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            {dimension === "period_daily" ? (
              <LineChart data={summary.items}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="label" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="cost_usd"
                  stroke="#1a6648"
                  name="Cost (USD)"
                />
              </LineChart>
            ) : dimension === "provider" || dimension === "persona" ? (
              <PieChart>
                <Tooltip />
                <Legend />
                <Pie
                  data={summary.items}
                  dataKey="cost_usd"
                  nameKey="label"
                  outerRadius={100}
                >
                  {summary.items.map((_, idx) => (
                    <Cell
                      key={`pie-${idx}`}
                      fill={PIE_COLORS[idx % PIE_COLORS.length]}
                    />
                  ))}
                </Pie>
              </PieChart>
            ) : (
              <BarChart data={summary.items}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="label" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Bar dataKey="cost_usd" fill="#1a6648" name="Cost (USD)" />
              </BarChart>
            )}
          </ResponsiveContainer>
        )}
      </section>
    </div>
  );
}

function Card({ title, value }: { title: string; value: string }) {
  return (
    <div className="rounded border border-slate-200 bg-white p-3">
      <div className="text-xs text-slate-500">{title}</div>
      <div className="mt-1 text-lg font-semibold text-slate-800">{value}</div>
    </div>
  );
}

export default CostDashboard;
