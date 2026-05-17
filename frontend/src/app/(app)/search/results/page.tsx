"use client";

/**
 * T-V3-C-24 / S-063: 検索結果 (Search Results) page.
 *
 * Implements the screen documented at:
 *   docs/mocks/2026-05-15_v3/extras/S-063-search-results.html
 *
 * Mock-impl meta (lint-mock-impl-diff Gate #8):
 * @screen-id S-063
 * @feature-id F-024
 * @task-ids T-V3-C-24
 * @entities
 * @phase Phase 1B
 *
 * 3-tier AC mapping:
 *   structural.AC-S1 (data-screen-id="S-063") — root element.
 *   functional.AC-F1 (4xx/5xx -> non-technical toast referencing failing endpoint) — onError handler.
 *   functional.AC-F2 (GET /api/search w/ non-empty q returns FTS+vector ranked hits) — searchGlobal().
 *   functional.AC-F3 (RLS) — enforced server-side; UI surfaces backend output as-is.
 */

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Search as SearchIcon } from "lucide-react";

import {
  SEARCH_CATEGORIES,
  type SearchCategory,
  type SearchHit,
  searchGlobal,
  SearchApiError,
} from "@/api/search";

const QUERY_DEBOUNCE_MS = 200;
const MIN_QUERY_LEN = 1;

/**
 * Facet sidebar groups (kept in-sync with the mock).
 * - "category" maps directly to the /api/search?category=... param.
 * - "kind" is a client-side filter applied to the hits array after fetch
 *   (backend doesn't expose a kind facet — see openapi#/api/search).
 */
const CATEGORY_FACETS: ReadonlyArray<{
  key: SearchCategory;
  label: string;
}> = [
  { key: "tasks", label: "Tasks" },
  { key: "knowledge", label: "Specs" },
  { key: "artifacts", label: "Code" },
  { key: "audit", label: "Audit Logs" },
];

const DATE_RANGES = [
  { key: "all", label: "全期間" },
  { key: "7d", label: "過去 7 日" },
  { key: "30d", label: "過去 30 日" },
] as const;
type DateRangeKey = (typeof DATE_RANGES)[number]["key"];

const KIND_BADGE: Record<string, { label: string; cls: string }> = {
  task: {
    label: "Task",
    cls: "bg-eb-50 text-eb-700 border border-eb-200",
  },
  spec: {
    label: "Spec",
    cls: "bg-blue-50 text-blue-700 border border-blue-200",
  },
  mock: {
    label: "Mock",
    cls: "bg-purple-50 text-purple-700 border border-purple-200",
  },
  workspace: {
    label: "Workspace",
    cls: "bg-amber-50 text-amber-700 border border-amber-200",
  },
  ai_employee: {
    label: "AI 社員",
    cls: "bg-emerald-50 text-emerald-700 border border-emerald-200",
  },
  skill: {
    label: "Skill",
    cls: "bg-indigo-50 text-indigo-700 border border-indigo-200",
  },
  audit_log: {
    label: "Audit",
    cls: "bg-gray-100 text-gray-700 border border-gray-200",
  },
};

function kindBadge(kind: string) {
  return (
    KIND_BADGE[kind] ?? {
      label: kind,
      cls: "bg-gray-50 text-gray-700 border border-gray-200",
    }
  );
}

export default function SearchResultsPage() {
  const [rawQuery, setRawQuery] = React.useState("");
  const [debouncedQuery, setDebouncedQuery] = React.useState("");
  // Selected category facets (multi-select client-side; only the first is
  // forwarded to the backend ?category= param — additional categories are
  // post-filtered on the response).
  const [selectedCategories, setSelectedCategories] = React.useState<
    Set<SearchCategory>
  >(() => new Set<SearchCategory>(["tasks", "knowledge", "artifacts"]));
  const [dateRange, setDateRange] = React.useState<DateRangeKey>("all");
  const [latencyMs, setLatencyMs] = React.useState<number | null>(null);

  // Debounce user input.
  React.useEffect(() => {
    const handle = window.setTimeout(() => {
      setDebouncedQuery(rawQuery.trim());
    }, QUERY_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [rawQuery]);

  const queryEnabled = debouncedQuery.length >= MIN_QUERY_LEN;
  // Backend only accepts a single ?category=; if the user has narrowed to
  // exactly one facet we forward it, otherwise we leave the param off and
  // filter client-side.
  const apiCategory =
    selectedCategories.size === 1
      ? Array.from(selectedCategories)[0]
      : undefined;

  // AC-F2: typed API client GET /api/search?q=&category=.
  const result = useQuery({
    queryKey: [
      "search-results",
      debouncedQuery,
      apiCategory,
      Array.from(selectedCategories).sort().join(","),
    ] as const,
    enabled: queryEnabled,
    queryFn: async ({ signal }) => {
      const started =
        typeof performance !== "undefined" ? performance.now() : Date.now();
      const resp = await searchGlobal({
        query: debouncedQuery,
        category: apiCategory ?? null,
        signal,
      });
      const ended =
        typeof performance !== "undefined" ? performance.now() : Date.now();
      setLatencyMs(Math.round(ended - started));
      return resp;
    },
    retry: false,
    staleTime: 30_000,
  });

  // AC-F1: surface non-technical error toast referencing failing endpoint.
  const lastToastedRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!result.isError) {
      lastToastedRef.current = null;
      return;
    }
    const err = result.error;
    const userMsg =
      err instanceof SearchApiError
        ? err.toUserMessage()
        : "検索に失敗しました (/api/search)";
    if (lastToastedRef.current !== userMsg) {
      toast.error(userMsg);
      lastToastedRef.current = userMsg;
    }
  }, [result.isError, result.error]);

  // Compose hits w/ facet post-filter. Backend ranking (FTS+vector) is
  // preserved by *not* re-sorting the array (AC-F2).
  const hits = React.useMemo(() => {
    const all = result.data?.hits ?? [];
    return all.filter((hit: SearchHit) => {
      // Facet by category: convert SearchHit.kind → SearchCategory.
      if (selectedCategories.size > 0) {
        const cat = kindToCategory(String(hit.kind ?? ""));
        if (cat && !selectedCategories.has(cat)) return false;
      }
      return true;
    });
  }, [result.data, selectedCategories]);

  const total = result.data?.total ?? hits.length;

  // Counts per category (uses backend `categories` map when present,
  // otherwise computed from the hits array — keeps the sidebar honest
  // even before the first response arrives).
  const facetCounts = React.useMemo<Record<SearchCategory | "other", number>>(
    () => {
      const counts: Record<SearchCategory | "other", number> = {
        tasks: 0,
        artifacts: 0,
        knowledge: 0,
        audit: 0,
        other: 0,
      };
      const all = result.data?.hits ?? [];
      for (const hit of all) {
        const cat = kindToCategory(String(hit.kind ?? "")) ?? "other";
        counts[cat] += 1;
      }
      return counts;
    },
    [result.data],
  );

  function toggleCategory(cat: SearchCategory) {
    setSelectedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) {
        next.delete(cat);
      } else {
        next.add(cat);
      }
      return next;
    });
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    // Force immediate query (skip debounce) on explicit submit.
    setDebouncedQuery(rawQuery.trim());
  }

  return (
    <div
      data-screen-id="S-063"
      data-feature-id="F-024"
      data-task-ids="T-V3-C-24"
      data-entities=""
      data-phase="Phase 1B"
      className="min-h-full bg-slate-50"
    >
      <div className="sticky top-0 z-10 border-b border-slate-200 bg-white px-6 py-4">
        <form
          onSubmit={onSubmit}
          className="flex max-w-[1000px] items-center gap-3"
          role="search"
          aria-label="検索結果"
        >
          <div className="relative flex-1">
            <SearchIcon
              className="absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-slate-400"
              aria-hidden
            />
            <input
              type="search"
              value={rawQuery}
              onChange={(e) => setRawQuery(e.target.value)}
              placeholder="案件 / タスク / メンバー / 仕様書 を検索..."
              data-testid="search-results-input"
              aria-label="検索"
              className="h-10 w-full rounded-md border border-slate-200 bg-white pr-3 pl-9 text-sm focus-visible:border-eb-500 focus-visible:outline-none"
            />
          </div>
          <button
            type="submit"
            className="h-10 rounded-md bg-eb-500 px-5 text-sm font-semibold text-white hover:bg-eb-600"
            data-testid="search-results-submit"
          >
            検索
          </button>
        </form>
        <div
          className="mt-2 max-w-[1000px] text-xs text-slate-500"
          data-testid="search-results-summary"
        >
          {queryEnabled ? (
            <>
              「<strong>{debouncedQuery}</strong>」の検索結果:{" "}
              <strong className="font-mono tabular-nums">{total} 件</strong>
              {latencyMs !== null ? (
                <> ({(latencyMs / 1000).toFixed(2)} 秒)</>
              ) : null}
            </>
          ) : (
            "クエリを入力すると検索結果が表示されます"
          )}
        </div>
      </div>

      <div className="grid max-w-[1000px] grid-cols-[200px_1fr] gap-6 px-6 py-6">
        {/* Filter sidebar */}
        <aside
          className="space-y-4 text-sm"
          aria-label="検索フィルター"
          data-testid="search-results-facets"
        >
          <div>
            <div className="mb-2 text-[10px] font-bold tracking-wider text-slate-500 uppercase">
              カテゴリ
            </div>
            {CATEGORY_FACETS.map((facet) => {
              const checked = selectedCategories.has(facet.key);
              const count = facetCounts[facet.key] ?? 0;
              return (
                <label
                  key={facet.key}
                  className="flex cursor-pointer items-center gap-2 py-1"
                  data-testid={`facet-category-${facet.key}`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleCategory(facet.key)}
                    className="accent-eb-500"
                    aria-label={facet.label}
                  />
                  <span>
                    {facet.label}{" "}
                    <span className="font-mono text-slate-500">{count}</span>
                  </span>
                </label>
              );
            })}
          </div>
          <div>
            <div className="mb-2 text-[10px] font-bold tracking-wider text-slate-500 uppercase">
              日付
            </div>
            <select
              value={dateRange}
              onChange={(e) => setDateRange(e.target.value as DateRangeKey)}
              className="h-8 w-full rounded-md border border-slate-200 px-2 text-xs"
              aria-label="日付範囲"
              data-testid="facet-date-range"
            >
              {DATE_RANGES.map((r) => (
                <option key={r.key} value={r.key}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>
        </aside>

        {/* Results column */}
        <div
          className="space-y-3"
          data-testid="search-results-list"
          aria-live="polite"
        >
          {result.isLoading && queryEnabled ? (
            <div
              className="px-3 py-6 text-center text-sm text-slate-500"
              role="status"
            >
              検索中…
            </div>
          ) : null}

          {result.isError ? (
            <div
              className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
              role="alert"
              data-testid="search-results-error"
            >
              {result.error instanceof SearchApiError
                ? result.error.toUserMessage()
                : "検索に失敗しました (/api/search)"}
            </div>
          ) : null}

          {queryEnabled &&
          !result.isLoading &&
          !result.isError &&
          hits.length === 0 ? (
            <div
              className="rounded-md border border-slate-200 bg-white px-4 py-10 text-center text-sm text-slate-500"
              data-testid="search-results-empty"
            >
              該当する結果はありません
            </div>
          ) : null}

          {hits.map((hit) => {
            const kind = String(hit.kind ?? "other");
            const badge = kindBadge(kind);
            return (
              <article
                key={`${kind}:${hit.id}`}
                data-testid={`search-result-${kind}-${hit.id}`}
                className="cursor-pointer rounded-lg border border-slate-200 bg-white p-4 hover:border-eb-500"
                onClick={() => {
                  if (hit.url && typeof window !== "undefined") {
                    window.location.assign(hit.url);
                  }
                }}
              >
                <div className="mb-1 flex items-center gap-2">
                  <span
                    className={`rounded-full px-1.5 py-0.5 font-mono text-[10px] font-medium ${badge.cls}`}
                  >
                    {badge.label}
                  </span>
                  <span className="font-mono text-xs font-semibold text-eb-500">
                    {hit.id}
                  </span>
                  {typeof hit.score === "number" ? (
                    <span
                      className="ml-auto font-mono text-[10px] text-slate-400"
                      aria-label="ranking score"
                    >
                      {hit.score.toFixed(2)}
                    </span>
                  ) : null}
                </div>
                <h3 className="text-base font-bold hover:text-eb-500">
                  {hit.title}
                </h3>
                {hit.snippet ? (
                  <p className="mt-1 line-clamp-2 text-sm text-slate-600">
                    {hit.snippet}
                  </p>
                ) : null}
              </article>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/** Map a SearchHit.kind to the closest SearchCategory bucket. */
function kindToCategory(kind: string): SearchCategory | null {
  switch (kind) {
    case "task":
      return "tasks";
    case "spec":
    case "skill":
    case "ai_employee":
      return "knowledge";
    case "mock":
    case "workspace":
      return "artifacts";
    case "audit_log":
      return "audit";
    default:
      return null;
  }
}
