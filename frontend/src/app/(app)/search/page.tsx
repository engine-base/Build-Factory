"use client";

/**
 * T-V3-C-11 / S-011: Global Search (Cmd+K) page.
 *
 * Implements the screen documented at:
 *   docs/mocks/2026-05-15_v3/account/S-011-global-search.html
 *
 * Mock-impl meta (lint-mock-impl-diff Gate #8):
 * @screen-id S-011
 * @feature-id F-024
 * @task-ids T-V3-C-11
 * @entities E-001,E-008,E-009,E-018,E-022,E-029
 * @phase Phase 1B
 *
 * 3-tier AC mapping:
 *   structural.AC-S1 (data-screen-id="S-011") — root element.
 *   functional.AC-F1 (GET /api/search?q=&category= via typed client) — searchGlobal().
 *   functional.AC-F2 (4xx/5xx -> non-technical toast referencing failing endpoint) — onError handler.
 *   functional.AC-F3 (FTS+vector ranked hits) — preserved order from backend `hits`.
 *   functional.AC-F4 (RLS visibility) — enforced server-side; UI surfaces backend output as-is.
 */

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Activity,
  Briefcase,
  CheckCircle2,
  FileText,
  Search as SearchIcon,
  User,
} from "lucide-react";

import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import {
  SEARCH_CATEGORIES,
  type SearchCategory,
  type SearchHit,
  searchGlobal,
  SearchApiError,
} from "@/api/search";

const CATEGORY_LABEL: Record<SearchCategory | "all", string> = {
  all: "全て",
  tasks: "Tasks",
  artifacts: "Artifacts",
  knowledge: "Specs",
  audit: "Audit Logs",
};

const KIND_LABEL: Record<string, string> = {
  workspace: "Workspaces",
  task: "Tasks",
  spec: "Specs / 仕様書",
  mock: "Mocks",
  ai_employee: "AI 社員",
  skill: "Skills",
  audit_log: "Audit Logs",
};

const KIND_ORDER: string[] = [
  "task",
  "workspace",
  "spec",
  "mock",
  "ai_employee",
  "skill",
  "audit_log",
];

function KindIcon({ kind }: { kind: string }) {
  switch (kind) {
    case "task":
      return <CheckCircle2 className="h-3.5 w-3.5 text-eb-500" aria-hidden />;
    case "workspace":
      return <Briefcase className="h-3.5 w-3.5 text-eb-500" aria-hidden />;
    case "audit_log":
      return <Activity className="h-3.5 w-3.5 text-gray-500" aria-hidden />;
    case "ai_employee":
      return <User className="h-3.5 w-3.5 text-eb-500" aria-hidden />;
    default:
      return <FileText className="h-3.5 w-3.5 text-gray-500" aria-hidden />;
  }
}

function groupHits(hits: SearchHit[]): Record<string, SearchHit[]> {
  const grouped: Record<string, SearchHit[]> = {};
  for (const hit of hits) {
    const key = typeof hit.kind === "string" ? hit.kind : "other";
    grouped[key] ??= [];
    grouped[key].push(hit);
  }
  return grouped;
}

// Debounce timer (ms). Avoids hammering the rate-limited backend on every keystroke.
const QUERY_DEBOUNCE_MS = 200;
// Minimum length before triggering a server call (AC-F1 requires non-empty q).
const MIN_QUERY_LEN = 1;

export default function GlobalSearchPage() {
  const [rawQuery, setRawQuery] = React.useState("");
  const [debouncedQuery, setDebouncedQuery] = React.useState("");
  const [category, setCategory] = React.useState<SearchCategory | "all">("all");
  const [latencyMs, setLatencyMs] = React.useState<number | null>(null);

  // Debounce user input.
  React.useEffect(() => {
    const handle = window.setTimeout(() => {
      setDebouncedQuery(rawQuery.trim());
    }, QUERY_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [rawQuery]);

  // Cmd+K / Ctrl+K → focus input. The page is the result view; keystroke wiring
  // is provided so the same component can power an in-app modal trigger.
  // Esc on focused input → clear query (mock parity).
  const inputRef = React.useRef<HTMLInputElement | null>(null);
  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
      } else if (
        e.key === "Escape" &&
        document.activeElement === inputRef.current
      ) {
        setRawQuery("");
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const queryEnabled = debouncedQuery.length >= MIN_QUERY_LEN;
  const apiCategory = category === "all" ? undefined : category;

  // AC-F1: typed API client GET /api/search?q=&category=.
  const result = useQuery({
    queryKey: ["global-search", debouncedQuery, apiCategory] as const,
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

  // AC-F2: surface non-technical error toast referencing failing endpoint,
  // without leaking server stack traces.
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
        : `検索に失敗しました (${"/api/search"})`;
    if (lastToastedRef.current !== userMsg) {
      toast.error(userMsg);
      lastToastedRef.current = userMsg;
    }
  }, [result.isError, result.error]);

  const hits = React.useMemo(
    () => (result.data?.hits ?? []).slice(),
    [result.data],
  );
  const total = result.data?.total ?? hits.length;
  const grouped = React.useMemo(() => groupHits(hits), [hits]);

  // Stable ordering: KIND_ORDER first, then any unknown kinds (preserves
  // backend ranking within a group — AC-F3).
  const orderedKinds = React.useMemo(() => {
    const present = new Set(Object.keys(grouped));
    const ordered = KIND_ORDER.filter((k) => present.has(k));
    const extras = Array.from(present).filter((k) => !KIND_ORDER.includes(k));
    return [...ordered, ...extras];
  }, [grouped]);

  return (
    <div
      data-screen-id="S-011"
      data-feature-id="F-024"
      data-task-ids="T-V3-C-11"
      data-entities="E-001,E-008,E-009,E-018,E-022,E-029"
      data-phase="Phase 1B"
      className="min-h-full bg-gray-50 px-4 py-8 sm:px-6"
    >
      <div className="mx-auto w-full max-w-[640px]">
        <header className="mb-3 flex items-center gap-2 text-gray-700">
          <SearchIcon className="h-4 w-4" aria-hidden />
          <h1 className="text-sm font-semibold tracking-wide uppercase">
            グローバル検索 (Cmd+K)
          </h1>
        </header>

        <Command
          shouldFilter={false}
          className="border border-gray-200 shadow-xl"
        >
          <CommandInput
            ref={inputRef}
            placeholder="案件 / タスク / メンバー / 仕様書 を検索..."
            value={rawQuery}
            onValueChange={setRawQuery}
            aria-label="グローバル検索"
            data-testid="global-search-input"
          />

          {/* Category chips */}
          <div
            className="flex items-center gap-1 overflow-x-auto border-b border-gray-200 px-3 py-2"
            role="tablist"
            aria-label="検索カテゴリ"
          >
            {(["all", ...SEARCH_CATEGORIES] as const).map((cat) => {
              const isActive = category === cat;
              return (
                <button
                  key={cat}
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  data-testid={`category-chip-${cat}`}
                  onClick={() => setCategory(cat)}
                  className={
                    "whitespace-nowrap rounded-full px-2 py-1 text-[11px] font-medium transition-colors " +
                    (isActive
                      ? "border border-eb-200 bg-eb-50 text-eb-700"
                      : "text-gray-600 hover:bg-gray-100")
                  }
                >
                  {CATEGORY_LABEL[cat]}
                </button>
              );
            })}
          </div>

          <CommandList data-testid="search-results-list">
            {result.isLoading && queryEnabled ? (
              <div
                className="px-3 py-6 text-center text-sm text-gray-500"
                role="status"
              >
                検索中…
              </div>
            ) : null}

            {!queryEnabled && !result.isLoading ? (
              <div className="px-3 py-10 text-center text-sm text-gray-400">
                クエリを入力すると検索結果が表示されます
              </div>
            ) : null}

            {queryEnabled &&
            !result.isLoading &&
            hits.length === 0 &&
            !result.isError ? (
              <CommandEmpty>該当する結果はありません</CommandEmpty>
            ) : null}

            {result.isError ? (
              <div
                className="px-3 py-6 text-center text-sm text-red-600"
                role="alert"
                data-testid="search-error"
              >
                {result.error instanceof SearchApiError
                  ? result.error.toUserMessage()
                  : "検索に失敗しました (/api/search)"}
              </div>
            ) : null}

            {orderedKinds.map((kind, idx) => {
              const kindHits = grouped[kind] ?? [];
              if (kindHits.length === 0) return null;
              return (
                <React.Fragment key={kind}>
                  {idx > 0 ? <CommandSeparator /> : null}
                  <CommandGroup heading={KIND_LABEL[kind] ?? kind}>
                    {kindHits.map((hit) => {
                      const itemKey = `${kind}:${hit.id}`;
                      return (
                        <CommandItem
                          key={itemKey}
                          value={itemKey}
                          data-testid={`search-hit-${kind}-${hit.id}`}
                          onSelect={() => {
                            if (hit.url && typeof window !== "undefined") {
                              window.location.assign(hit.url);
                            }
                          }}
                        >
                          <span className="mr-2 flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-gray-200 bg-white">
                            <KindIcon kind={kind} />
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-sm font-medium">
                              {hit.title}
                            </span>
                            {hit.snippet ? (
                              <span className="block truncate text-[11px] text-gray-500 font-mono">
                                {hit.snippet}
                              </span>
                            ) : null}
                          </span>
                          {typeof hit.score === "number" ? (
                            <span
                              className="ml-2 shrink-0 font-mono text-[10px] text-gray-400"
                              aria-label="ranking score"
                            >
                              {hit.score.toFixed(2)}
                            </span>
                          ) : null}
                        </CommandItem>
                      );
                    })}
                  </CommandGroup>
                </React.Fragment>
              );
            })}
          </CommandList>

          <div className="flex items-center gap-3 border-t border-gray-200 px-4 py-2 text-[11px] text-gray-500">
            <span>↑↓ 選択</span>
            <span>↵ 開く</span>
            <span>esc 閉じる</span>
            <span
              className="ml-auto font-mono"
              data-testid="search-footer-stats"
            >
              {queryEnabled
                ? `${total} 件${latencyMs !== null ? ` (${latencyMs}ms)` : ""}`
                : "—"}
            </span>
          </div>
        </Command>
      </div>
    </div>
  );
}
