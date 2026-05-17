"use client";

/**
 * T-017-03: /dashboard/costs — 8-tab cost dashboard page.
 *
 * URL search params (deep link 対応):
 *   ?dim=DIM&from=ISO&to=ISO
 */

import * as React from "react";

import { CostDashboard } from "@/components/dashboard/CostDashboard";
import {
  VALID_COST_DIMENSIONS,
  type CostDimension,
} from "@/lib/api/cost-dashboard";

function readDim(): CostDimension {
  if (typeof window === "undefined") return "overview";
  const url = new URL(window.location.href);
  const dim = url.searchParams.get("dim") || "";
  return (VALID_COST_DIMENSIONS as readonly string[]).includes(dim)
    ? (dim as CostDimension)
    : "overview";
}

function readDate(key: string): string {
  if (typeof window === "undefined") return "";
  const url = new URL(window.location.href);
  return url.searchParams.get(key) || "";
}

export default function CostDashboardPage() {
  const [ready, setReady] = React.useState(false);
  const [dim, setDim] = React.useState<CostDimension>("overview");
  const [from, setFrom] = React.useState<string>("");
  const [to, setTo] = React.useState<string>("");

  React.useEffect(() => {
    setDim(readDim());
    setFrom(readDate("from"));
    setTo(readDate("to"));
    setReady(true);
  }, []);

  if (!ready) {
    return (
      <main className="mx-auto max-w-5xl p-6">
        <p className="text-sm text-slate-500">Loading…</p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-5xl p-6">
      <h1 className="mb-4 text-lg font-semibold text-slate-800">
        コスト ダッシュボード
      </h1>

      {/* T-V3-D-11 / S-040 mock parity:
          mock の KPI band (4 labels) と 3 section h2 を canonical text として配置する.
          実数値は CostDashboard の dimension 切替で表示する (Phase 1 後続で wiring). */}
      <section
        aria-label="KPI summary"
        className="mb-4 grid grid-cols-4 gap-2 text-xs"
        data-testid="s040-kpi-band"
      >
        <div
          data-kpi-label="Ops"
          className="rounded border border-slate-200 bg-white px-3 py-2"
        >
          <div className="font-bold uppercase tracking-wider text-[10px] text-slate-500">
            Ops
          </div>
          <div className="text-sm font-semibold text-slate-800 mt-1">—</div>
        </div>
        <div
          data-kpi-label="今月コスト"
          className="rounded border border-slate-200 bg-white px-3 py-2"
        >
          <div className="font-bold uppercase tracking-wider text-[10px] text-slate-500">
            今月コスト
          </div>
          <div className="text-sm font-semibold text-slate-800 mt-1">—</div>
        </div>
        <div
          data-kpi-label="トークン (今月)"
          className="rounded border border-slate-200 bg-white px-3 py-2"
        >
          <div className="font-bold uppercase tracking-wider text-[10px] text-slate-500">
            トークン (今月)
          </div>
          <div className="text-sm font-semibold text-slate-800 mt-1">—</div>
        </div>
        <div
          data-kpi-label="セッション平均"
          className="rounded border border-slate-200 bg-white px-3 py-2"
        >
          <div className="font-bold uppercase tracking-wider text-[10px] text-slate-500">
            セッション平均
          </div>
          <div className="text-sm font-semibold text-slate-800 mt-1">—</div>
        </div>
      </section>

      {/* T-V3-D-11 / S-040 mock parity: 3 section h2 headings. */}
      <section className="mb-3" data-testid="s040-section-by-workspace">
        <h2 className="text-sm font-bold text-slate-700">案件別コスト</h2>
      </section>
      <section className="mb-3" data-testid="s040-section-by-employee">
        <h2 className="text-sm font-bold text-slate-700">AI 社員別コスト</h2>
      </section>
      <section className="mb-3" data-testid="s040-section-daily-trend">
        <h2 className="text-sm font-bold text-slate-700">日別コスト推移 (15 日)</h2>
      </section>

      <CostDashboard
        defaultDimension={dim}
        defaultFrom={from}
        defaultTo={to}
      />
    </main>
  );
}
