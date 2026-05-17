"use client";

/**
 * S-023 画面モックビューア — T-V3-C-49 / F-005b.
 *
 * @screen-id S-023
 * @feature-id F-005b
 * @task-ids T-V3-C-49
 * @entities E-022,E-023
 * @phase Phase 1
 *
 * Implements the v3 screen documented at:
 *   docs/mocks/2026-05-15_v3/spec/S-023-screen-mock-viewer.html
 *
 * 3-tier AC mapping (逐語 — see docs/audit/2026-05-16_v3/T-V3-C-49.md):
 *   structural.AC-S1: h1 == "画面モックビューア" inside data-screen-id="S-023" root.
 *   structural.AC-S2: Lucide icons only (no emoji glyphs).
 *
 *   functional.AC-F1: On mount for an authenticated workspace member, the
 *     system shall call GET /api/workspaces/{id}/mocks and render the 2xx
 *     body; on 4xx the system shall render an inline error toast and an
 *     empty state. — handled by useScreenMockViewer + error banner +
 *     mocks-empty state.
 *   functional.AC-F2: Unauthenticated visitor -> redirect /login (S-001) and
 *     never render workspace-scoped data. — early-return + window.location
 *     .replace("/login").
 *   functional.AC-F3: When GET /api/workspaces/{id}/mocks/{screen_id}/html is
 *     called, the system shall return the latest version of the mock HTML.
 *     — selected screen triggers an HTML fetch which is wired into the
 *     iframe `srcdoc` attribute.
 */

import * as React from "react";
import { useParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  ExternalLink,
  Layout,
  Monitor,
  RefreshCw,
  Search,
  Smartphone,
  Tablet,
} from "lucide-react";

import {
  readAuthToken,
  readWorkspaceId,
  useScreenMockViewer,
} from "@/hooks/useScreenMockViewer";

type DeviceMode = "desktop" | "tablet" | "mobile";

const DEVICE_WIDTHS: Record<DeviceMode, number> = {
  desktop: 1280,
  tablet: 768,
  mobile: 375,
};

/**
 * S-023 page — dynamic-segment route mounted at
 * `/spec/mocks/[id]` where `[id]` is the workspace id.
 *
 * Route param `id` is the primary workspace selector (overrides the
 * `?workspace=` query / localStorage fallback used by other spec pages).
 */
export default function ScreenMockViewerPage(): React.JSX.Element {
  const params = useParams<{ id?: string | string[] }>();
  const routeWorkspaceId = React.useMemo<string | null>(() => {
    const raw = params?.id;
    if (!raw) return null;
    if (Array.isArray(raw)) return raw[0] ?? null;
    return raw;
  }, [params]);

  const [authChecked, setAuthChecked] = React.useState(false);
  const [authToken, setAuthToken] = React.useState<string | null>(null);
  const [workspaceId, setWorkspaceId] = React.useState<string | null>(null);
  const [filter, setFilter] = React.useState<string>("");
  const [device, setDevice] = React.useState<DeviceMode>("desktop");

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
    setWorkspaceId(routeWorkspaceId ?? readWorkspaceId());
    setAuthChecked(true);
  }, [routeWorkspaceId]);

  const viewer = useScreenMockViewer({ workspaceId, authToken });

  // ---- AC-F2 early-return: unauthenticated visitors render nothing ------
  if (authChecked && !authToken) {
    return (
      <div
        data-screen-id="S-023"
        data-feature-id="F-005b"
        data-task-ids="T-V3-C-49"
        data-entities="E-022,E-023"
        className="min-h-screen bg-slate-50 flex items-center justify-center"
      >
        <div className="text-sm text-slate-500" role="status">
          サインインページへ移動しています…
        </div>
      </div>
    );
  }

  const filteredMocks = React.useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return viewer.mocks;
    return viewer.mocks.filter((m) => {
      const sid = (m.screen_id ?? "").toLowerCase();
      const name = (m.name ?? "").toLowerCase();
      const cat = (m.category ?? "").toLowerCase();
      return sid.includes(q) || name.includes(q) || cat.includes(q);
    });
  }, [filter, viewer.mocks]);

  const grouped = React.useMemo(() => {
    const map = new Map<string, typeof filteredMocks>();
    for (const m of filteredMocks) {
      const cat = (m.category as string | null | undefined) ?? "その他";
      const existing = map.get(cat) ?? [];
      existing.push(m);
      map.set(cat, existing);
    }
    return Array.from(map.entries()).map(([category, items]) => ({
      category,
      items,
    }));
  }, [filteredMocks]);

  const selectedMock = React.useMemo(() => {
    if (!viewer.selectedScreenId) return null;
    return (
      viewer.mocks.find((m) => m.screen_id === viewer.selectedScreenId) ?? null
    );
  }, [viewer.mocks, viewer.selectedScreenId]);

  const iframeWidth = DEVICE_WIDTHS[device];

  return (
    <div
      data-screen-id="S-023"
      data-feature-id="F-005b"
      data-task-ids="T-V3-C-49"
      data-entities="E-022,E-023"
      data-phase="Phase 1"
      className="min-h-screen bg-slate-50 text-slate-900 flex flex-col"
    >
      {/* Top action bar — mirrors mock h1 + subtitle + sticky CTA. */}
      <header className="px-6 py-3 border-b border-slate-200 bg-white flex items-center justify-between flex-shrink-0">
        <div>
          <h1 className="text-lg font-bold flex items-center gap-2">
            <Layout className="w-5 h-5 text-eb-500" aria-hidden />
            画面モックビューア
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            仕様画面の HTML mock を iframe でプレビュー / レスポンシブ確認
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            data-testid="mocks-refresh"
            onClick={() => void viewer.refresh()}
            disabled={
              !authToken || !workspaceId || viewer.state === "loading"
            }
            className="text-xs text-slate-600 hover:text-slate-900 inline-flex items-center gap-1 h-9 px-3 rounded-md border border-slate-200 bg-white disabled:opacity-60"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            再読込
          </button>
        </div>
      </header>

      {/* Error banner (AC-F1 4xx / AC-F3 fetch failures). */}
      {viewer.errorMessage ? (
        <div
          role="alert"
          data-testid="mocks-error"
          className="mx-6 mt-4 rounded-md border border-rose-200 bg-rose-50 text-rose-700 text-sm px-4 py-3 flex items-start gap-2"
        >
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden />
          <span>{viewer.errorMessage}</span>
        </div>
      ) : null}

      {/* Missing-workspace inline state (does not block AC-S1/S2 lint). */}
      {!workspaceId && authChecked ? (
        <div
          role="status"
          data-testid="mocks-missing-workspace"
          className="mx-6 mt-4 rounded-md border border-amber-200 bg-amber-50 text-amber-700 text-sm px-4 py-3"
        >
          ワークスペースが選択されていません。URL パス
          <code className="font-mono">/spec/mocks/&lt;workspace-id&gt;</code>
          で開いてください。
        </div>
      ) : null}

      {/* Body grid: screen list + preview + side panel. */}
      <div className="flex-1 grid grid-cols-[220px_1fr_280px] overflow-hidden">
        {/* Screen list */}
        <aside className="border-r border-slate-200 bg-white overflow-y-auto">
          <div className="px-3 py-2 border-b border-slate-200 sticky top-0 bg-white">
            <label className="relative block">
              <Search
                className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400"
                aria-hidden
              />
              <input
                type="search"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="検索..."
                aria-label="モック検索"
                className="w-full border border-slate-200 text-xs h-8 pl-7 pr-2 rounded-md focus-visible:outline-none focus-visible:border-eb-500"
                data-testid="mocks-filter"
              />
            </label>
          </div>

          <div className="p-2 space-y-0.5 text-sm" data-testid="mocks-list">
            {viewer.state === "loading" ? (
              <div
                role="status"
                data-testid="mocks-loading"
                className="text-xs text-slate-500 px-2 py-3"
              >
                モックを読み込み中です…
              </div>
            ) : viewer.mocks.length === 0 && viewer.state === "loaded" ? (
              <div
                role="status"
                data-testid="mocks-empty"
                className="text-xs text-slate-500 px-2 py-3"
              >
                モックはまだ生成されていません。
              </div>
            ) : viewer.state === "error" && filteredMocks.length === 0 ? (
              <div
                role="status"
                data-testid="mocks-empty"
                className="text-xs text-slate-500 px-2 py-3"
              >
                モックを取得できませんでした。
              </div>
            ) : (
              grouped.map(({ category, items }) => (
                <React.Fragment key={category}>
                  <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold px-2 pt-2 pb-1">
                    {category} ({items.length})
                  </div>
                  {items.map((m) => {
                    const isActive = m.screen_id === viewer.selectedScreenId;
                    return (
                      <button
                        type="button"
                        key={m.screen_id}
                        data-testid={`mocks-row-${m.screen_id}`}
                        onClick={() => viewer.selectScreen(m.screen_id)}
                        className={`block w-full text-left px-2 py-1.5 rounded-md font-mono text-xs ${
                          isActive
                            ? "bg-eb-50 text-eb-700 font-semibold"
                            : "hover:bg-slate-50 text-slate-700"
                        }`}
                      >
                        {m.screen_id}
                        {m.name ? (
                          <span className="ml-2 font-sans text-[11px] text-slate-500">
                            {m.name}
                          </span>
                        ) : null}
                      </button>
                    );
                  })}
                </React.Fragment>
              ))
            )}
          </div>
        </aside>

        {/* Preview iframe */}
        <section className="flex flex-col overflow-hidden">
          {/* Device toolbar */}
          <div className="px-4 py-2 border-b border-slate-200 bg-slate-50 flex items-center gap-2">
            <button
              type="button"
              data-testid="device-desktop"
              onClick={() => setDevice("desktop")}
              className={`px-3 py-1 rounded-md text-xs font-semibold flex items-center gap-1 border ${
                device === "desktop"
                  ? "bg-white border-eb-500 text-eb-500"
                  : "border-transparent hover:bg-white text-slate-600"
              }`}
            >
              <Monitor className="w-3 h-3" aria-hidden />
              Desktop (1280px)
            </button>
            <button
              type="button"
              data-testid="device-tablet"
              onClick={() => setDevice("tablet")}
              className={`px-3 py-1 rounded-md text-xs flex items-center gap-1 border ${
                device === "tablet"
                  ? "bg-white border-eb-500 text-eb-500 font-semibold"
                  : "border-transparent hover:bg-white text-slate-600"
              }`}
            >
              <Tablet className="w-3 h-3" aria-hidden />
              Tablet
            </button>
            <button
              type="button"
              data-testid="device-mobile"
              onClick={() => setDevice("mobile")}
              className={`px-3 py-1 rounded-md text-xs flex items-center gap-1 border ${
                device === "mobile"
                  ? "bg-white border-eb-500 text-eb-500 font-semibold"
                  : "border-transparent hover:bg-white text-slate-600"
              }`}
            >
              <Smartphone className="w-3 h-3" aria-hidden />
              Mobile
            </button>
            <div className="ml-auto flex items-center gap-2 text-xs text-slate-500">
              <button
                type="button"
                data-testid="preview-refresh"
                onClick={() =>
                  viewer.selectedScreenId &&
                  viewer.selectScreen(viewer.selectedScreenId)
                }
                aria-label="プレビューを再読込"
                className="px-2 py-1 rounded hover:bg-white"
              >
                <RefreshCw className="w-3.5 h-3.5" aria-hidden />
              </button>
              <button
                type="button"
                data-testid="preview-external"
                aria-label="新規タブで開く"
                disabled={!viewer.selectedHtml}
                onClick={() => {
                  if (typeof window === "undefined") return;
                  if (!viewer.selectedHtml) return;
                  const blob = new Blob([viewer.selectedHtml], {
                    type: "text/html",
                  });
                  const url = URL.createObjectURL(blob);
                  window.open(url, "_blank", "noopener");
                }}
                className="px-2 py-1 rounded hover:bg-white disabled:opacity-50"
              >
                <ExternalLink className="w-3.5 h-3.5" aria-hidden />
              </button>
            </div>
          </div>

          {/* iframe surface */}
          <div className="flex-1 bg-slate-100 p-6 overflow-auto flex items-start justify-center">
            <div
              className="bg-white shadow-lg rounded border border-slate-200 overflow-hidden"
              style={{
                width: `${iframeWidth}px`,
                maxWidth: "100%",
                aspectRatio: "16 / 10",
              }}
            >
              {viewer.htmlLoading ? (
                <div
                  role="status"
                  data-testid="preview-loading"
                  className="w-full h-full flex items-center justify-center text-xs text-slate-500"
                >
                  プレビューを読み込み中…
                </div>
              ) : viewer.selectedHtml ? (
                <iframe
                  data-testid="mocks-preview-iframe"
                  title={`mock preview ${viewer.selectedScreenId ?? ""}`}
                  srcDoc={viewer.selectedHtml}
                  sandbox="allow-same-origin"
                  className="w-full h-full"
                />
              ) : (
                <div
                  role="status"
                  data-testid="preview-placeholder"
                  className="w-full h-full flex items-center justify-center text-xs text-slate-500"
                >
                  左のリストから画面を選択してください。
                </div>
              )}
            </div>
          </div>
        </section>

        {/* Right: linked spec / responsive / meta. */}
        <aside className="border-l border-slate-200 bg-white overflow-y-auto">
          <div className="px-4 py-3 border-b border-slate-200 flex items-center gap-2">
            <Layout className="w-4 h-4 text-eb-500" aria-hidden />
            <span className="text-sm font-bold">
              {selectedMock?.screen_id ?? "—"} 詳細
            </span>
          </div>

          <div className="p-4 border-b border-slate-200">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-2">
              メタ
            </div>
            <dl className="text-xs space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <dt className="text-slate-500">画面名</dt>
                <dd className="font-medium text-slate-800 text-right truncate">
                  {selectedMock?.name ?? "—"}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-2">
                <dt className="text-slate-500">カテゴリ</dt>
                <dd className="font-medium text-slate-800 text-right truncate">
                  {(selectedMock?.category as string | null | undefined) ?? "—"}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-2">
                <dt className="text-slate-500">バージョン</dt>
                <dd className="font-mono text-slate-800">
                  {selectedMock && typeof selectedMock.version === "number"
                    ? `v${selectedMock.version}`
                    : "—"}
                </dd>
              </div>
            </dl>
          </div>

          <div className="p-4">
            <div className="text-[10px] uppercase tracking-wider text-slate-500 font-bold mb-2">
              レスポンシブ
            </div>
            <div className="space-y-1.5 text-xs">
              <div className="flex items-center justify-between">
                <span>Desktop (1280px+)</span>
                <span className="text-emerald-600 font-semibold">OK</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Tablet (768px)</span>
                <span className="text-slate-500">閲覧専用</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Mobile (&lt;640px)</span>
                <span className="text-slate-500">PC 推奨表示</span>
              </div>
            </div>
          </div>
        </aside>
      </div>

      {/* Back link parity with mock (top-right index link). */}
      <a
        href="/"
        aria-label="戻る"
        className="fixed top-3 right-3 z-40 inline-flex items-center gap-1 text-xs text-eb-500 bg-white/95 border border-slate-200 rounded-md px-3 py-1.5 shadow-sm"
      >
        <ArrowLeft className="w-3.5 h-3.5" aria-hidden />
        戻る
      </a>
    </div>
  );
}
