// @ts-nocheck
/**
 * T-V3-D-11 / Wave 6 batch 3 — Screen h1 / KPI / section drift fix.
 *
 * AC mapping (docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-d-drift.json):
 *   structural.AC-S1 — each of the 9 pages renders an <h1> whose text matches
 *                       the canonical mock h1 verbatim.
 *   structural.AC-S2 — KPI labels match the mock's `[data-kpi-label]` set as
 *                       a multiset (case-sensitive). Only S-040 has a non-empty
 *                       canonical KPI set; the other 8 screens have empty KPI
 *                       sets (per docs/functional-breakdown/2026-05-16_v3/screens.json).
 *   structural.AC-S3 — section <h2> headings include all canonical mock section
 *                       texts (per screens.json `section_h2_texts`).
 *
 * Runner: `cd frontend && pnpm test __tests__/screen-drift-fix.test.tsx`.
 *
 * NOTE: This file uses `// @ts-nocheck` because vitest +
 *       @testing-library/react are *runtime-only* devDeps for the new screen
 *       test harness; they are wired by the Wave 2 frontend test setup ticket
 *       (matches the convention used by the merged T-V3-C-* PRs, e.g.
 *       `frontend/tests/screens/S-007-account_settings.spec.tsx`).
 *
 * Source of canonical h1 / KPI / section text:
 *   docs/functional-breakdown/2026-05-16_v3/screens.json (items[*].{h1_text,
 *   kpi_labels, section_h2_texts}).
 */

import * as React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

// --- mocks (avoid real network in unit tests) -----------------------------
//
// Each page below may call `fetch` on mount via @tanstack/react-query.
// We stub `globalThis.fetch` with a permissive mock so render() does not
// crash. The drift assertions only inspect h1 / h2 / KPI labels, which
// render synchronously from JSX literals.

const fetchMock = vi.fn();
const originalFetch = globalThis.fetch;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  fetchMock.mockReset();
  // default: 200 + empty object so any GET succeeds
  fetchMock.mockImplementation(() =>
    Promise.resolve(jsonResponse(200, {})),
  );
  globalThis.fetch = fetchMock as unknown as typeof fetch;
});

afterEach(() => {
  cleanup();
  globalThis.fetch = originalFetch;
});

// --- canonical expectations (verbatim from screens.json) ------------------

const CANONICAL = {
  "S-007": {
    impl_path: "frontend/src/app/settings/account/page.tsx",
    h1: "アカウント設定",
    kpis: [] as string[],
    sections: ["基本情報", "プラン / 課金", "所有者 (Account Owner)", "Danger Zone"],
  },
  "S-009": {
    impl_path: "frontend/src/app/settings/profile/page.tsx",
    h1: "プロフィール設定",
    kpis: [] as string[],
    sections: [
      "プロフィール",
      "通知設定",
      "LLM プロバイダ (BYOK)",
      "OAuth 連携",
      "ユーザークローン (高本さんの判断基準を学習)",
      "Danger Zone",
    ],
  },
  "S-028": {
    impl_path: "frontend/src/app/tasks/page.tsx",
    h1: "タスクリスト",
    kpis: [] as string[],
    sections: [] as string[],
  },
  "S-031": {
    impl_path: "frontend/src/app/dashboard/swarm/page.tsx",
    h1: "Swarm 並列実行",
    kpis: [] as string[],
    sections: [] as string[],
  },
  "S-036": {
    impl_path: "frontend/src/app/ai-employees/page.tsx",
    h1: "AI 社員 組織図",
    kpis: [] as string[],
    sections: [] as string[],
  },
  "S-038": {
    impl_path: "frontend/src/app/skills/page.tsx",
    h1: "スキルマネージャ",
    kpis: [] as string[],
    sections: [] as string[],
  },
  "S-039": {
    impl_path: "frontend/src/app/knowledge/page.tsx",
    h1: "ナレッジベース",
    kpis: [] as string[],
    sections: [] as string[],
  },
  "S-040": {
    impl_path: "frontend/src/app/dashboard/costs/page.tsx",
    h1: "コスト ダッシュボード",
    kpis: ["Ops", "今月コスト", "トークン (今月)", "セッション平均"],
    sections: ["案件別コスト", "AI 社員別コスト", "日別コスト推移 (15 日)"],
  },
  "S-041": {
    impl_path: "frontend/src/app/audit-logs/page.tsx",
    h1: "監査ログ",
    kpis: [] as string[],
    sections: [] as string[],
  },
} as const;

// --- helpers --------------------------------------------------------------

function getH1Text(container: HTMLElement): string {
  // grab the FIRST <h1> we see; pages may have nested icons inside, so we
  // normalize whitespace.
  const h1 = container.querySelector("h1");
  return (h1?.textContent ?? "").replace(/\s+/g, " ").trim();
}

function getH2Texts(container: HTMLElement): string[] {
  const els = Array.from(container.querySelectorAll("h2"));
  return els.map((el) => (el.textContent ?? "").replace(/\s+/g, " ").trim());
}

function getKpiLabels(container: HTMLElement): string[] {
  const els = Array.from(container.querySelectorAll("[data-kpi-label]"));
  return els.map((el) => el.getAttribute("data-kpi-label") ?? "");
}

// --- dynamic imports (lazy) ----------------------------------------------
//
// We dynamic-import each page module inside its test so a transient import
// failure for one screen does not skip the rest.

async function renderScreen(impl_path: string) {
  // map repo-relative impl_path → module import (drop "frontend/src/" and
  // ".tsx" so we can rely on the project tsconfig "paths" alias `@/...`).
  const modPath =
    "@/" + impl_path.replace(/^frontend\/src\//, "").replace(/\.tsx$/, "");
  const mod = await import(/* @vite-ignore */ modPath);
  const Page = mod.default;
  return render(<Page />);
}

// --- structural AC tests (per screen) -------------------------------------

describe("T-V3-D-11 / screen drift fix — h1 / KPI / section parity", () => {
  for (const [screenId, spec] of Object.entries(CANONICAL)) {
    describe(`${screenId} — ${spec.impl_path}`, () => {
      // AC-S1: h1 text equals canonical mock h1 verbatim
      it(`AC-S1: <h1> reads ${JSON.stringify(spec.h1)}`, async () => {
        const { container } = await renderScreen(spec.impl_path);
        expect(getH1Text(container)).toBe(spec.h1);
      });

      // AC-S2: KPI multiset
      it("AC-S2: [data-kpi-label] multiset matches mock", async () => {
        const { container } = await renderScreen(spec.impl_path);
        const actual = getKpiLabels(container).slice().sort();
        const expected = spec.kpis.slice().sort();
        expect(actual).toEqual(expected);
      });

      // AC-S3: section h2 text set ⊇ canonical mock section set
      // (extra h2's are allowed; the mock's canonical set must be present.)
      it("AC-S3: section <h2> set includes all canonical mock h2 texts", async () => {
        const { container } = await renderScreen(spec.impl_path);
        const actual = getH2Texts(container);
        for (const wanted of spec.sections) {
          expect(actual).toContain(wanted);
        }
      });
    });
  }
});
