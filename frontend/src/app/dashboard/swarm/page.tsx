"use client";

/**
 * T-010d-02: /dashboard/swarm — Swarm Grid page.
 *
 * 並列 swarm session を SwarmGrid component で表示.
 * cell click で /sessions/[id] へ遷移.
 *
 * URL search params: ?size=4|9|16|64 (default 16).
 */

import * as React from "react";
import { useRouter } from "next/navigation";

import { SwarmGrid, type SwarmCell, type SwarmGridSize } from "@/components/swarm/SwarmGrid";

const VALID_SIZES: SwarmGridSize[] = ["4", "9", "16", "64"];

function readSize(): SwarmGridSize {
  if (typeof window === "undefined") return "16";
  const url = new URL(window.location.href);
  const s = url.searchParams.get("size") || "";
  return (VALID_SIZES as readonly string[]).includes(s)
    ? (s as SwarmGridSize)
    : "16";
}

export default function SwarmGridPage() {
  const router = useRouter();
  const [ready, setReady] = React.useState(false);
  const [size, setSize] = React.useState<SwarmGridSize>("16");
  const [cells, setCells] = React.useState<SwarmCell[]>([]);

  React.useEffect(() => {
    setSize(readSize());
    // Phase 1: empty state. 実 fetch は別 Sprint で wiring.
    setCells([]);
    setReady(true);
  }, []);

  const handleCellClick = React.useCallback(
    (cell: SwarmCell) => {
      router.push(`/sessions/${cell.session_id}`);
    },
    [router],
  );

  const handleSizeChange = React.useCallback((s: SwarmGridSize) => {
    setSize(s);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("size", s);
      window.history.replaceState({}, "", url.toString());
    }
  }, []);

  if (!ready) {
    return (
      <main className="mx-auto max-w-6xl p-6">
        <p className="text-sm text-slate-500">Loading…</p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-6xl p-6">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-800">
          Swarm Grid
        </h1>
        <div
          className="flex items-center gap-1"
          data-testid="swarm-size-selector"
        >
          {VALID_SIZES.map((s) => (
            <button
              key={s}
              type="button"
              data-active={s === size}
              className={
                s === size
                  ? "rounded border border-eb-500 bg-eb-50 px-2 py-1 text-xs font-semibold text-eb-700"
                  : "rounded border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
              }
              onClick={() => handleSizeChange(s)}
            >
              {s}
            </button>
          ))}
        </div>
      </div>
      <SwarmGrid
        cells={cells}
        size={size}
        onCellClick={handleCellClick}
      />
    </main>
  );
}
