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
        Cost Dashboard
      </h1>
      <CostDashboard
        defaultDimension={dim}
        defaultFrom={from}
        defaultTo={to}
      />
    </main>
  );
}
