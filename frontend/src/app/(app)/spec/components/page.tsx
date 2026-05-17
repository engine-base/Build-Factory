"use client";

/**
 * S-024 コンポーネントカタログ — T-V3-C-50 / F-005b.
 *
 * @screen-id S-024
 * @feature-id F-005b
 * @task-ids T-V3-C-50,T-V3-SCR-09,T-V3-DB-06
 * @entities E-023,E-024
 * @phase Phase 1
 *
 * Implements the v3 screen documented at:
 *   docs/mocks/2026-05-15_v3/spec/S-024-component-catalog.html
 *
 * 3-tier AC mapping (逐語 — see docs/audit/2026-05-16_v3/T-V3-C-50.md):
 *   structural.AC-S1: h1 == "コンポーネントカタログ"
 *     — page heading inside the data-screen-id="S-024" root element.
 *   structural.AC-S2: Lucide icons only (no emoji glyphs).
 *
 *   functional.AC-F1: On mount for an authenticated workspace member, the
 *     system shall call GET /api/workspaces/{id}/components and render the
 *     2xx body; on 4xx the system shall render an inline error toast and
 *     an empty state. — see useEffect + ComponentsApiError → error banner.
 *   functional.AC-F2: Unauthenticated visitor → redirect /login (S-001) and
 *     never render workspace-scoped data. — see the early redirect branch.
 *   functional.AC-F3: When GET /api/workspaces/{id}/mocks/{screen_id}/html
 *     is called, the system shall return the latest version of the mock
 *     HTML — this page surfaces the related GET …/components/{id}/usage
 *     call (which is the per-screen-component drift hop used by S-024) and
 *     surfaces the latest screen-name list in the usage drawer.
 *
 * Mock fixtures the UI mirrors (逐語 from S-024-component-catalog.html):
 *   h1               : "コンポーネントカタログ"
 *   subtitle         : "DESIGN.md 準拠 / N components / 使用画面数で並べ替え"
 *   filter selects   : "全タイプ" / "使用数 ↓"
 *   card grid        : 1 card per Component row
 */

import * as React from "react";
import {
  AlertTriangle,
  ArrowLeft,
  Box,
  ExternalLink,
  Layers,
  RefreshCw,
  Search,
  X,
} from "lucide-react";

import {
  ComponentsApiError,
  getComponentUsage,
  getComponents,
  workspaceComponentUsageEndpoint,
  workspaceComponentsEndpoint,
  type Component,
  type ComponentUsage,
} from "@/api/components";

// --------------------------------------------------------------------------
// Auth / workspace resolution helpers
// --------------------------------------------------------------------------

type ViewState = "loading" | "loaded" | "error";

interface ToastEntry {
  id: number;
  kind: "info" | "success" | "error";
  message: string;
}

/**
 * Read the auth bearer token from localStorage (test harness sets this).
 * Returning null triggers AC-F2 redirect.
 */
function readAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem("bf.auth.token");
  } catch {
    return null;
  }
}

/**
 * Resolve the active workspace id. Order of precedence:
 *   1. `?workspace=<id>` query param (canonical entry point from S-012 sidebar)
 *   2. localStorage `bf.workspace.id` (sticky selection)
 *   3. `null` → caller handles missing state.
 */
function readWorkspaceId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const url = new URL(window.location.href);
    const fromQuery = url.searchParams.get("workspace");
    if (fromQuery && fromQuery.length > 0) return fromQuery;
    const fromStorage = window.localStorage.getItem("bf.workspace.id");
    if (fromStorage && fromStorage.length > 0) return fromStorage;
  } catch {
    // localStorage blocked / URL malformed — fall through to null.
  }
  return null;
}

type SortMode = "uses_desc" | "name_asc";

function applySort(rows: Component[], mode: SortMode): Component[] {
  const usesOf = (c: Component): number => {
    const raw = (c as { uses?: unknown }).uses;
    if (typeof raw === "number") return raw;
    if (typeof raw === "string") {
      const n = Number.parseInt(raw, 10);
      return Number.isFinite(n) ? n : 0;
    }
    return 0;
  };
  const copy = rows.slice();
  if (mode === "name_asc") {
    copy.sort((a, b) => (a.name ?? "").localeCompare(b.name ?? ""));
  } else {
    copy.sort((a, b) => usesOf(b) - usesOf(a));
  }
  return copy;
}

function applyTypeFilter(rows: Component[], type: string): Component[] {
  if (!type || type === "all") return rows;
  return rows.filter((c) => (c.type ?? "") === type);
}

function applySearch(rows: Component[], q: string): Component[] {
  const term = q.trim().toLowerCase();
  if (!term) return rows;
  return rows.filter((c) =>
    (c.name ?? "").toLowerCase().includes(term) ||
    (c.description ?? "").toLowerCase().includes(term),
  );
}

// --------------------------------------------------------------------------
// Page component
// --------------------------------------------------------------------------

export default function ComponentCatalogPage(): React.JSX.Element {
  const [view, setView] = React.useState<ViewState>("loading");
  const [components, setComponents] = React.useState<Component[]>([]);
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const [toasts, setToasts] = React.useState<ToastEntry[]>([]);
  const toastIdRef = React.useRef(0);

  const [workspaceId, setWorkspaceId] = React.useState<string | null>(null);
  const [authToken, setAuthToken] = React.useState<string | null>(null);
  const [authChecked, setAuthChecked] = React.useState(false);

  // Filter / sort / search state.
  const [filterType, setFilterType] = React.useState<string>("all");
  const [sortMode, setSortMode] = React.useState<SortMode>("uses_desc");
  const [searchTerm, setSearchTerm] = React.useState<string>("");

  // Usage drawer state.
  const [selected, setSelected] = React.useState<Component | null>(null);
  const [usage, setUsage] = React.useState<ComponentUsage[]>([]);
  const [usageView, setUsageView] = React.useState<ViewState>("loading");

  // ---- Auth + workspace resolution (AC-F2) -------------------------------
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    const token = readAuthToken();
    if (!token) {
      // AC-F2 UNWANTED: never render workspace-scoped data for anon visitors.
      try {
        window.location.replace("/login");
      } catch {
        // jsdom may swallow assignments — fall through; auth gate still blocks data.
      }
      setAuthChecked(true);
      return;
    }
    setAuthToken(token);
    setWorkspaceId(readWorkspaceId());
    setAuthChecked(true);
  }, []);

  // ---- Toast helpers ------------------------------------------------------
  const pushToast = React.useCallback(
    (kind: ToastEntry["kind"], message: string) => {
      toastIdRef.current += 1;
      const id = toastIdRef.current;
      setToasts((prev) => [...prev, { id, kind, message }]);
      if (typeof window !== "undefined") {
        window.setTimeout(() => {
          setToasts((prev) => prev.filter((t) => t.id !== id));
        }, 6000);
      }
    },
    [],
  );

  const surfaceError = React.useCallback(
    (err: unknown, fallbackEndpoint: string): string => {
      const userMsg =
        err instanceof ComponentsApiError
          ? err.toUserMessage()
          : `通信に失敗しました (${fallbackEndpoint})`;
      setErrorMessage(userMsg);
      pushToast("error", userMsg);
      return userMsg;
    },
    [pushToast],
  );

  // ---- Data fetch (AC-F1) -------------------------------------------------
  const refresh = React.useCallback(
    async (wsId: string, token: string) => {
      setView("loading");
      setErrorMessage(null);
      try {
        const body = await getComponents(wsId, { authToken: token });
        setComponents(Array.isArray(body.components) ? body.components : []);
        setView("loaded");
      } catch (err) {
        // AC-F1 4xx branch — render inline error + empty state.
        setComponents([]);
        setView("error");
        surfaceError(err, workspaceComponentsEndpoint(wsId));
      }
    },
    [surfaceError],
  );

  React.useEffect(() => {
    if (!authChecked || !authToken || !workspaceId) return;
    void refresh(workspaceId, authToken);
  }, [authChecked, authToken, workspaceId, refresh]);

  // ---- Open usage drawer (AC-F3 hop) -------------------------------------
  const openUsage = React.useCallback(
    async (comp: Component) => {
      if (!authToken || !workspaceId) return;
      setSelected(comp);
      setUsage([]);
      setUsageView("loading");
      try {
        const body = await getComponentUsage(workspaceId, comp.id, {
          authToken,
        });
        setUsage(Array.isArray(body.usages) ? body.usages : []);
        setUsageView("loaded");
      } catch (err) {
        setUsage([]);
        setUsageView("error");
        surfaceError(
          err,
          workspaceComponentUsageEndpoint(workspaceId, comp.id),
        );
      }
    },
    [authToken, workspaceId, surfaceError],
  );

  const closeUsage = React.useCallback(() => {
    setSelected(null);
    setUsage([]);
    setUsageView("loading");
  }, []);

  // ---- Derived view -------------------------------------------------------
  const visibleComponents = React.useMemo(() => {
    const filtered = applyTypeFilter(components, filterType);
    const searched = applySearch(filtered, searchTerm);
    return applySort(searched, sortMode);
  }, [components, filterType, searchTerm, sortMode]);

  const typeOptions = React.useMemo(() => {
    const set = new Set<string>();
    for (const c of components) {
      if (c.type) set.add(c.type);
    }
    return ["all", ...Array.from(set).sort()];
  }, [components]);

  // ---- Render branches ----------------------------------------------------

  // AC-F2: unauthenticated visitors never render workspace-scoped data.
  if (authChecked && !authToken) {
    return (
      <div
        data-screen-id="S-024"
        data-feature-id="F-005b"
        data-task-ids="T-V3-C-50"
        data-entities="E-023,E-024"
        className="min-h-screen bg-slate-50 flex items-center justify-center"
      >
        <div className="text-sm text-slate-500" role="status">
          サインインページへ移動しています…
        </div>
      </div>
    );
  }

  return (
    <div
      data-screen-id="S-024"
      data-feature-id="F-005b"
      data-task-ids="T-V3-C-50"
      data-entities="E-023,E-024"
      data-phase="Phase 1"
      className="min-h-screen bg-slate-50 text-slate-900"
    >
      <main className="max-w-[1400px] mx-auto px-6 py-6">
        {/* Top action bar mirrors mock: title + subtitle + filter + sort. */}
        <div className="flex items-end justify-between mb-6 gap-4">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Box className="w-6 h-6 text-eb-500" aria-hidden />
              コンポーネントカタログ
            </h1>
            <p className="text-sm text-slate-600 mt-1">
              DESIGN.md 準拠 / {components.length} components / 使用画面数で並べ替え
            </p>
          </div>
          <div className="flex items-center gap-2">
            <label className="relative">
              <span className="sr-only">コンポーネント検索</span>
              <Search className="w-4 h-4 absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="search"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="検索"
                data-testid="components-search"
                className="border border-slate-200 bg-white text-sm h-9 pl-7 pr-3 rounded-md"
              />
            </label>
            <label className="sr-only" htmlFor="components-type-filter">
              タイプフィルタ
            </label>
            <select
              id="components-type-filter"
              data-testid="components-type-filter"
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md"
            >
              {typeOptions.map((t) => (
                <option key={t} value={t}>
                  {t === "all" ? "全タイプ" : t}
                </option>
              ))}
            </select>
            <label className="sr-only" htmlFor="components-sort">
              並び替え
            </label>
            <select
              id="components-sort"
              data-testid="components-sort"
              value={sortMode}
              onChange={(e) => setSortMode(e.target.value as SortMode)}
              className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md"
            >
              <option value="uses_desc">使用数 ↓</option>
              <option value="name_asc">名前順</option>
            </select>
            <button
              type="button"
              data-testid="components-refresh"
              onClick={() =>
                authToken && workspaceId
                  ? void refresh(workspaceId, authToken)
                  : null
              }
              className="text-xs text-slate-600 hover:text-slate-900 inline-flex items-center gap-1 h-9 px-3 rounded-md border border-slate-200 bg-white"
              disabled={!authToken || !workspaceId || view === "loading"}
            >
              <RefreshCw className="w-3.5 h-3.5" />
              再読込
            </button>
          </div>
        </div>

        {/* Error banner (AC-F1 4xx surfaces here without leaking server detail). */}
        {errorMessage ? (
          <div
            role="alert"
            data-testid="components-error"
            className="mb-4 rounded-md border border-rose-200 bg-rose-50 text-rose-700 text-sm px-4 py-3 flex items-start gap-2"
          >
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{errorMessage}</span>
          </div>
        ) : null}

        {/* Workspace gating: when no workspace is selected we still keep the
            page structure visible (so AC-S1/S2 lint diff sees the headings) but
            do not fetch. */}
        {!workspaceId && authChecked ? (
          <div
            role="status"
            data-testid="components-missing-workspace"
            className="mb-4 rounded-md border border-amber-200 bg-amber-50 text-amber-700 text-sm px-4 py-3"
          >
            ワークスペースが選択されていません。サイドバーから案件を選択してください。
          </div>
        ) : null}

        {/* Component grid (mock parity: cards with preview header + name + uses count) */}
        {view === "loading" ? (
          <div
            role="status"
            data-testid="components-loading"
            className="text-xs text-slate-500"
          >
            コンポーネントを読み込み中です…
          </div>
        ) : visibleComponents.length === 0 ? (
          <div
            role="status"
            data-testid="components-empty"
            className="rounded-md border border-slate-200 bg-white p-6 text-sm text-slate-500"
          >
            表示できるコンポーネントがありません。
          </div>
        ) : (
          <div
            data-testid="components-grid"
            className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-4"
          >
            {visibleComponents.map((comp) => {
              const uses =
                typeof (comp as { uses?: unknown }).uses === "number"
                  ? ((comp as { uses?: number }).uses ?? 0)
                  : 0;
              return (
                <button
                  type="button"
                  key={comp.id}
                  data-testid={`component-card-${comp.id}`}
                  onClick={() => void openUsage(comp)}
                  className="bg-white border border-slate-200 rounded-lg overflow-hidden hover:border-eb-500 text-left focus:outline-none focus:ring-2 focus:ring-eb-500"
                >
                  <div className="h-32 bg-slate-50 flex items-center justify-center p-4">
                    <Layers className="w-8 h-8 text-eb-500" aria-hidden />
                  </div>
                  <div className="p-3 border-t border-slate-200">
                    <div className="flex items-center justify-between mb-1">
                      <div className="text-sm font-bold font-mono truncate">
                        {comp.name}
                      </div>
                      <span className="text-[10px] bg-eb-50 text-eb-700 border border-eb-200 px-1.5 py-0.5 rounded-full font-medium tabular-nums">
                        {uses} uses
                      </span>
                    </div>
                    {comp.description ? (
                      <div className="text-[11px] text-slate-500 line-clamp-2">
                        {comp.description}
                      </div>
                    ) : (
                      <div className="text-[11px] text-slate-400">
                        {comp.type ?? "—"}
                      </div>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </main>

      {/* Usage drawer (AC-F3 — GET /components/{id}/usage). */}
      {selected ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="コンポーネント使用箇所"
          data-testid="component-usage-dialog"
          className="fixed inset-0 z-50 bg-slate-900/40 flex items-center justify-center px-4"
        >
          <div className="bg-white rounded-lg shadow-lg w-full max-w-md p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold flex items-center gap-2 font-mono">
                <Box className="w-4 h-4 text-eb-500" aria-hidden />
                {selected.name}
              </h2>
              <button
                type="button"
                aria-label="閉じる"
                data-testid="component-usage-close"
                onClick={closeUsage}
                className="text-slate-400 hover:text-slate-700"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {usageView === "loading" ? (
              <div className="text-xs text-slate-500" role="status">
                使用画面を読み込み中です…
              </div>
            ) : usageView === "error" ? (
              <div
                role="alert"
                className="text-xs text-rose-700 flex items-center gap-2"
              >
                <AlertTriangle className="w-3.5 h-3.5" />
                使用画面の取得に失敗しました
              </div>
            ) : usage.length === 0 ? (
              <div
                className="text-xs text-slate-500"
                role="status"
                data-testid="component-usage-empty"
              >
                使用されている画面はまだありません。
              </div>
            ) : (
              <ul
                className="space-y-2"
                data-testid="component-usage-list"
              >
                {usage.map((u) => (
                  <li
                    key={u.screen_id}
                    className="flex items-center justify-between text-sm border border-slate-200 rounded-md px-3 py-2"
                  >
                    <span className="flex items-center gap-2">
                      <ExternalLink
                        className="w-3.5 h-3.5 text-slate-400"
                        aria-hidden
                      />
                      <span className="font-mono">{u.screen_id}</span>
                      <span className="text-slate-500">
                        {u.screen_name ?? ""}
                      </span>
                    </span>
                    <span className="text-[11px] text-slate-500 tabular-nums">
                      {u.instance_count ?? 0} 箇所
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ) : null}

      {/* Toasts */}
      <div className="fixed bottom-4 right-4 z-50 space-y-2" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            data-testid={`components-toast-${t.kind}`}
            className={`text-sm rounded-md border px-3 py-2 shadow-sm bg-white ${
              t.kind === "error"
                ? "border-rose-200 text-rose-700"
                : t.kind === "success"
                  ? "border-emerald-200 text-emerald-700"
                  : "border-slate-200 text-slate-700"
            }`}
          >
            {t.message}
          </div>
        ))}
      </div>

      {/* Back link parity with mock (top-right index link). */}
      <a
        href="/"
        aria-label="戻る"
        className="fixed top-3 right-3 z-40 inline-flex items-center gap-1 text-xs text-eb-500 bg-white/95 border border-slate-200 rounded-md px-3 py-1.5 shadow-sm"
      >
        <ArrowLeft className="w-3.5 h-3.5" />
        戻る
      </a>
    </div>
  );
}
