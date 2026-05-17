"use client";

/**
 * S-025 画面遷移マップ — T-V3-C-51 / F-005b.
 *
 * @screen-id S-025
 * @feature-id F-005b
 * @task-ids T-V3-C-51,T-V3-SCR-10,T-V3-DB-02
 * @entities E-022,E-024
 * @phase Phase 1
 *
 * Implements the v3 screen documented at:
 *   docs/mocks/2026-05-15_v3/spec/S-025-screen-flow-map.html
 *
 * 3-tier AC mapping (逐語 — see docs/audit/2026-05-16_v3/T-V3-C-51.md):
 *   structural.AC-S1 (h1 == "画面遷移マップ" / mock h1 逐語)        — page heading.
 *   structural.AC-S2 (Lucide icons exclusively / no emoji glyphs)   — see Lucide imports.
 *   functional.AC-F1 (EVENT-DRIVEN GET /api/workspaces/{id}/screen-flow on mount;
 *     2xx renders into the page / 4xx → inline error toast + empty state) —
 *     useScreenFlowMap hook on mount.
 *   functional.AC-F2 (UNWANTED: unauthenticated → redirect /login (S-001) /
 *     never render workspace-scoped data) — useRouter().replace("/login") on 401.
 *   functional.AC-F3 (EVENT-DRIVEN GET /api/workspaces/{id}/mocks/{screen_id}/html
 *     returns the latest mock html version) — handleNodeClick → fetchMockHtml.
 *
 * Backend contract: T-V3-B-09 implemented backend/routers/screen_flow.py.
 *
 * Workspace scoping: the page reads ?workspace_id from the search params; in
 * production the (app) layout will supply it from the active workspace. Until
 * that wiring lands we default to "active" (T-V3-B-09 already accepts the
 * sentinel via x-bf-implementation-path).
 */

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  Box,
  BookOpen,
  Download,
  Layout,
  LayoutDashboard,
  Map,
  Maximize,
  Minus,
  Plus,
  X,
} from "lucide-react";

import {
  ScreenFlowApiError,
  type ScreenFlowEdge,
  type ScreenFlowNode,
} from "@/api/screen-flow";
import { useScreenFlowMap } from "@/hooks/use-screen-flow-map";

// --------------------------------------------------------------------------
// Mock-derived literals — 逐語 from docs/mocks/2026-05-15_v3/spec/S-025-*.html
// --------------------------------------------------------------------------

const S025_H1_TEXT = "画面遷移マップ";
const S025_SUBTITLE = "SVG flow map / クライアントに画面の繋がりを共有可";

// --------------------------------------------------------------------------
// Layout helper — distribute nodes deterministically into a grid so we never
// require a runtime layout engine for the smoke test. Real production
// implementations can swap this for @xyflow/react in T-V3-C-XX (Wave 2).
// --------------------------------------------------------------------------

interface PositionedNode extends ScreenFlowNode {
  x: number;
  y: number;
}

function layoutNodes(nodes: ScreenFlowNode[]): PositionedNode[] {
  const NODE_W = 140;
  const NODE_H = 64;
  const GAP_X = 60;
  const GAP_Y = 40;
  const COLS = 6;
  return nodes.map((n, idx) => {
    const col = idx % COLS;
    const row = Math.floor(idx / COLS);
    return {
      ...n,
      x: 60 + col * (NODE_W + GAP_X),
      y: 70 + row * (NODE_H + GAP_Y),
    };
  });
}

// --------------------------------------------------------------------------
// Page component
// --------------------------------------------------------------------------

export default function ScreenFlowMapPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const workspaceId = searchParams?.get("workspace_id") ?? "active";

  const { data, loading, error, reload, fetchMockHtml } =
    useScreenFlowMap(workspaceId);

  const [drawerScreenId, setDrawerScreenId] = React.useState<string | null>(
    null,
  );
  const [drawerHtml, setDrawerHtml] = React.useState<string | null>(null);
  const [drawerBusy, setDrawerBusy] = React.useState(false);
  const [drawerError, setDrawerError] = React.useState<string | null>(null);

  // --------------------------------------------------------------------
  // AC-F2: 401 from GET screen-flow → router.replace("/login"), never
  // render workspace-scoped UI. Page early-returns an aria-hidden shell.
  // --------------------------------------------------------------------
  React.useEffect(() => {
    if (error && error.status === 401) {
      router.replace("/login");
    }
  }, [error, router]);

  if (error && error.status === 401) {
    return (
      <div
        data-screen-id="S-025"
        data-feature-id="F-005b"
        data-screen-name="screen_flow_map"
        className="min-h-screen bg-slate-50"
        aria-hidden
      />
    );
  }

  const errorMessage =
    error && error.status !== 401 ? error.toUserMessage() : null;

  const nodes: ScreenFlowNode[] = data?.nodes ?? [];
  const edges: ScreenFlowEdge[] = data?.edges ?? [];
  const positioned = layoutNodes(nodes);
  const nodeIndex = new Map(positioned.map((p) => [p.screen_id, p]));

  // AC-F3: GET /mocks/{screen_id}/html on node click — surfaces 4xx as a
  // drawer-local inline error message without leaking server stack traces.
  const handleNodeClick = async (screenId: string) => {
    setDrawerScreenId(screenId);
    setDrawerHtml(null);
    setDrawerError(null);
    setDrawerBusy(true);
    try {
      const payload = await fetchMockHtml(screenId);
      setDrawerHtml(payload.html ?? "");
    } catch (err) {
      if (err instanceof ScreenFlowApiError) {
        if (err.status === 401) {
          router.replace("/login");
          return;
        }
        setDrawerError(err.toUserMessage());
      } else {
        setDrawerError("通信に失敗しました");
      }
    } finally {
      setDrawerBusy(false);
    }
  };

  const closeDrawer = () => {
    setDrawerScreenId(null);
    setDrawerHtml(null);
    setDrawerError(null);
  };

  return (
    <div
      data-screen-id="S-025"
      data-feature-id="F-005b"
      data-task-ids="T-V3-C-51,T-V3-SCR-10,T-V3-DB-02"
      data-entities="E-022,E-024"
      data-phase="Phase 1"
      data-screen-name="screen_flow_map"
      className="min-h-screen bg-slate-50 text-slate-900 flex"
    >
      {/* Sidebar (matches mock S-025 left nav) */}
      <aside className="w-[240px] bg-eb-700 text-white flex flex-col shrink-0">
        <div className="px-5 py-4 border-b border-eb-600">
          <div className="text-[11px] tracking-widest text-eb-100 font-bold">
            BUILD-FACTORY
          </div>
          <div className="text-sm font-bold mt-1">Build-Factory dogfood</div>
        </div>
        <nav className="flex-1 px-2 py-3 text-sm space-y-0.5 overflow-y-auto">
          <a
            href="/dashboard"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100"
          >
            <LayoutDashboard className="w-4 h-4" aria-hidden />
            ダッシュボード
          </a>
          <div className="text-[10px] uppercase tracking-wider text-eb-200 px-3 pt-3 pb-1 font-bold">
            Spec
          </div>
          <a
            href="/spec/viewer"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100"
          >
            <BookOpen className="w-4 h-4" aria-hidden />
            仕様書
          </a>
          <a
            href="/spec/screen-mock"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100"
          >
            <Layout className="w-4 h-4" aria-hidden />
            画面 Mock
          </a>
          <a
            href="/spec/components"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100"
          >
            <Box className="w-4 h-4" aria-hidden />
            Components
          </a>
          <span
            aria-current="page"
            className="px-3 py-1.5 rounded-md flex items-center gap-2 bg-eb-600 font-semibold"
          >
            <Map className="w-4 h-4" aria-hidden />
            Flow Map
          </span>
        </nav>
        <div className="px-4 py-3 border-t border-eb-600">
          <a
            href="/dashboard"
            className="text-[11px] text-eb-100 inline-flex items-center gap-1 hover:text-white"
          >
            <ArrowLeft className="w-3 h-3" aria-hidden />
            ダッシュボードへ戻る
          </a>
        </div>
      </aside>

      <main className="flex-1 flex flex-col overflow-hidden">
        <div className="px-6 py-3 border-b border-slate-200 bg-white flex items-center justify-between flex-shrink-0">
          <div>
            <h1 className="text-lg font-bold flex items-center gap-2">
              <Map className="w-5 h-5 text-eb-500" aria-hidden />
              {S025_H1_TEXT}
            </h1>
            <p className="text-xs text-slate-500 mt-0.5">{S025_SUBTITLE}</p>
          </div>
          <div className="flex items-center gap-2">
            <select
              data-testid="category-filter"
              aria-label="カテゴリフィルタ"
              className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md"
              defaultValue="all"
            >
              <option value="all">全カテゴリ</option>
              <option value="auth">Auth</option>
              <option value="account">Account</option>
              <option value="workspace">Workspace</option>
            </select>
            <button
              type="button"
              data-testid="svg-export"
              onClick={() => void reload()}
              className="border border-slate-200 hover:bg-slate-50 text-sm h-9 px-3 rounded-md flex items-center gap-2"
            >
              <Download className="w-4 h-4" aria-hidden />
              SVG export
            </button>
          </div>
        </div>

        {/* AC-F1 inline error toast (4xx surface, non-technical) */}
        {errorMessage && (
          <div
            role="alert"
            data-testid="screen-flow-error"
            className="mx-6 mt-4 p-3 rounded-md bg-amber-50 border border-amber-300 text-amber-800 text-sm flex items-start gap-2"
          >
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden />
            <span>{errorMessage}</span>
          </div>
        )}

        {/* Canvas */}
        <div
          className="flex-1 relative bg-slate-100 overflow-auto"
          style={{
            backgroundImage:
              "radial-gradient(circle, #cbd5e1 1px, transparent 1px)",
            backgroundSize: "16px 16px",
          }}
          data-testid="flow-canvas"
        >
          {loading && (
            <div
              className="absolute inset-0 flex items-center justify-center text-sm text-slate-500"
              role="status"
              aria-live="polite"
              data-testid="flow-loading"
            >
              読み込み中…
            </div>
          )}

          {!loading && (errorMessage || nodes.length === 0) && (
            <div
              className="absolute inset-0 flex items-center justify-center text-sm text-slate-500"
              data-testid="flow-empty"
            >
              {errorMessage
                ? "画面遷移マップを読み込めませんでした。"
                : "まだ画面遷移マップが登録されていません。"}
            </div>
          )}

          {!loading && !errorMessage && nodes.length > 0 && (
            <svg
              data-testid="flow-svg"
              role="img"
              aria-label="画面遷移マップ"
              width={Math.max(1200, 60 + 6 * (140 + 60))}
              height={Math.max(
                700,
                90 + Math.ceil(positioned.length / 6) * (64 + 40),
              )}
              className="absolute"
            >
              <defs>
                <marker
                  id="arrow-s025"
                  viewBox="0 0 10 10"
                  refX="9"
                  refY="5"
                  markerWidth="6"
                  markerHeight="6"
                  orient="auto"
                >
                  <path d="M0,0 L10,5 L0,10 z" fill="#475569" />
                </marker>
              </defs>
              {edges.map((edge, idx) => {
                const from = nodeIndex.get(edge.from_screen_id);
                const to = nodeIndex.get(edge.to_screen_id);
                if (!from || !to) return null;
                return (
                  <line
                    key={`${edge.from_screen_id}->${edge.to_screen_id}-${idx}`}
                    data-testid={`flow-edge-${edge.from_screen_id}-${edge.to_screen_id}`}
                    x1={from.x + 140}
                    y1={from.y + 32}
                    x2={to.x}
                    y2={to.y + 32}
                    stroke="#475569"
                    strokeWidth={1.5}
                    markerEnd="url(#arrow-s025)"
                  />
                );
              })}
            </svg>
          )}

          {!loading && !errorMessage && nodes.length > 0 && (
            <ul
              data-testid="flow-node-list"
              className="absolute inset-0 list-none"
            >
              {positioned.map((node) => (
                <li
                  key={node.screen_id}
                  className="absolute"
                  style={{
                    left: `${node.x}px`,
                    top: `${node.y}px`,
                    width: "140px",
                  }}
                >
                  <button
                    type="button"
                    data-testid={`flow-node-${node.screen_id}`}
                    onClick={() => void handleNodeClick(node.screen_id)}
                    className="block w-full text-left bg-white border border-slate-300 hover:border-eb-500 rounded-lg p-3 shadow-sm"
                  >
                    <div className="text-[10px] mono text-eb-500 font-bold">
                      {node.screen_id}
                    </div>
                    <div className="text-xs font-semibold truncate">
                      {node.name ?? node.screen_id}
                    </div>
                    {node.kind ? (
                      <div className="text-[10px] text-slate-500 mt-1">
                        {String(node.kind)}
                      </div>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          )}

          {/* Zoom controls (Lucide icons, mock parity) */}
          <div className="absolute top-4 right-4 bg-white border border-slate-200 rounded-md flex flex-col">
            <button
              type="button"
              aria-label="Zoom in"
              className="w-9 h-9 hover:bg-slate-50 border-b border-slate-200 flex items-center justify-center"
            >
              <Plus className="w-4 h-4" aria-hidden />
            </button>
            <button
              type="button"
              aria-label="Zoom out"
              className="w-9 h-9 hover:bg-slate-50 border-b border-slate-200 flex items-center justify-center"
            >
              <Minus className="w-4 h-4" aria-hidden />
            </button>
            <button
              type="button"
              aria-label="Fit view"
              className="w-9 h-9 hover:bg-slate-50 flex items-center justify-center"
            >
              <Maximize className="w-4 h-4" aria-hidden />
            </button>
          </div>
        </div>
      </main>

      {/* AC-F3 drawer: mock html preview */}
      {drawerScreenId && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="flow-drawer-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40"
          onClick={() => !drawerBusy && closeDrawer()}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="bg-white rounded-lg shadow-xl w-[640px] max-h-[80vh] flex flex-col"
            data-testid="flow-drawer"
          >
            <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200">
              <h2 id="flow-drawer-title" className="text-base font-bold">
                {drawerScreenId} mock html
              </h2>
              <button
                type="button"
                onClick={closeDrawer}
                disabled={drawerBusy}
                aria-label="閉じる"
                className="text-slate-500 hover:text-slate-900"
              >
                <X className="w-4 h-4" aria-hidden />
              </button>
            </div>
            <div className="p-5 overflow-auto flex-1">
              {drawerBusy && (
                <div
                  role="status"
                  aria-live="polite"
                  data-testid="flow-drawer-loading"
                  className="text-sm text-slate-500"
                >
                  読み込み中…
                </div>
              )}
              {drawerError && (
                <div
                  role="alert"
                  data-testid="flow-drawer-error"
                  className="text-sm text-amber-800 bg-amber-50 border border-amber-300 rounded-md p-3"
                >
                  {drawerError}
                </div>
              )}
              {!drawerBusy && !drawerError && drawerHtml !== null && (
                <pre
                  data-testid="flow-drawer-html"
                  className="text-xs mono whitespace-pre-wrap break-all bg-slate-50 border border-slate-200 rounded-md p-3"
                >
                  {drawerHtml}
                </pre>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
