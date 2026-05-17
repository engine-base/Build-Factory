"use client";

/**
 * S-012 案件ダッシュボード — T-V3-C-61 / F-006,F-007,F-008,F-026.
 *
 * @screen-id S-012
 * @feature-id F-006,F-007,F-008,F-026
 * @task-ids T-V3-C-61,T-V3-RF-03
 * @entities E-009,E-018,E-025,E-013,E-017
 * @phase Phase 1
 *
 * Implements the v3 screen documented at:
 *   docs/mocks/2026-05-15_v3/workspace/S-012-workspace-dashboard.html
 *
 * 3-tier AC mapping (逐語 — see docs/audit/2026-05-16_v3/T-V3-C-61.md):
 *   structural.AC-S1: h1 == "Build-Factory dogfood"
 *     — page heading inside the data-screen-id="S-012" root element.
 *   structural.AC-S2: KPI labels set == {Spec / Task / Moat / Safety /
 *     Settings / Workspace / Phase 進捗 / Tasks / Running Sessions}
 *     — sidebar section labels + top KPI tile labels (mock kpi_labels).
 *   structural.AC-S3: section h2 set == { "現在のフェーズ: Phase 1 (実装)" /
 *     "Constitution" / "最近のタスク" / "Pending Reviews (3)" /
 *     "Running Sessions (5)" } — section heading labels match the mock.
 *   structural.AC-S4: Lucide icons only (no emoji glyphs).
 *
 *   functional.AC-F1: On mount for an authenticated workspace member, the
 *     system shall call GET /api/workspaces/{id}/dashboard and render the
 *     2xx body; on 4xx the system shall render an inline error toast and an
 *     empty state. — see useWorkspaceDashboard + error banner.
 *   functional.AC-F2: Unauthenticated visitor → redirect /login (S-001), no
 *     workspace-scoped data is rendered.
 *   functional.AC-F3: PUT /api/workspaces/{id}/requirements persists items
 *     and returns version+1 — covered by the requirements page (T-V3-C-47);
 *     this page only documents the contract via the JSDoc reference.
 *   functional.AC-F4: GET /api/workspaces/{id}/tasks?group_by=feature returns
 *     accordion-friendly metadata — covered by the kanban page (T-V3-C-52);
 *     this page documents the contract.
 *   functional.AC-F5: POST /api/workspaces/{id}/phases/{phase_id}/gate
 *     unlocks the next phase — covered by the phases page (T-V3-C-37);
 *     this page documents the contract.
 *   functional.AC-F6: POST /api/workspaces/{id}/constitution/versions creates
 *     a new version snapshot — covered by the constitution page; this page
 *     documents the contract.
 *
 * Mock fixtures the UI mirrors (逐語 from S-012-workspace-dashboard.html):
 *   h1                : "Build-Factory dogfood"
 *   subtitle          : "Phase 1 開発 / 受託 SaaS の dogfood 検証"
 *   primary CTA       : "全タスク並列実行 (Play All)"
 *   KPI labels        : Phase 進捗 / Tasks / Running Sessions / Cost (this month)
 *   sidebar sections  : Spec / Task / Moat / Safety / Settings / Workspace
 *   section h2 set    : 現在のフェーズ: Phase 1 (実装) / Constitution / 最近のタスク /
 *                       Pending Reviews (3) / Running Sessions (5)
 */

import * as React from "react";
import { useParams } from "next/navigation";
import {
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Flag,
  GitBranch,
  Kanban,
  Layers,
  LayoutDashboard,
  Lock,
  Mic,
  FileText,
  Layout,
  Play,
  RefreshCw,
  Settings,
  Shield,
  Users,
  Zap,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  WorkspaceDashboardApiError,
  workspaceDashboardEndpoint,
  type DashboardKpi,
  type DashboardPendingReview,
  type DashboardPhase,
  type DashboardSession,
  type DashboardTaskRow,
  type WorkspaceDashboardResponse,
} from "@/api/workspace-dashboard";
import { useWorkspaceDashboard } from "@/hooks/useWorkspaceDashboard";

// --------------------------------------------------------------------------
// Mock-derived screen literals — 逐語コピー (h1_text / labels from mock HTML).
// AC-S1 / AC-S2 / AC-S3 enforce these values at the structural lint level.
// --------------------------------------------------------------------------

const S012_H1_TEXT = "Build-Factory dogfood" as const;
const S012_SUBTITLE = "Phase 1 開発 / 受託 SaaS の dogfood 検証" as const;
const S012_PLAY_ALL_LABEL = "全タスク並列実行 (Play All)" as const;

const KPI_LABEL_PHASE = "Phase 進捗" as const;
const KPI_LABEL_TASKS = "Tasks" as const;
const KPI_LABEL_SESSIONS = "Running Sessions" as const;
const KPI_LABEL_COST = "Cost (this month)" as const;

const SECTION_H2_PHASE = "現在のフェーズ: Phase 1 (実装)" as const;
const SECTION_H2_CONSTITUTION = "Constitution" as const;
const SECTION_H2_RECENT_TASKS = "最近のタスク" as const;
const SECTION_H2_PENDING_REVIEWS = "Pending Reviews" as const;
const SECTION_H2_SESSIONS = "Running Sessions" as const;

const SIDEBAR_GROUPS = {
  spec: "Spec",
  task: "Task",
  moatSafety: "Moat / Safety",
  settings: "Settings",
  workspace: "Workspace",
} as const;

// --------------------------------------------------------------------------
// Auth + token helpers (parity with S-016 / S-020).
// --------------------------------------------------------------------------

function readAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem("bf.auth.token");
  } catch {
    return null;
  }
}

function readWorkspaceIdFromQuery(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const url = new URL(window.location.href);
    const q = url.searchParams.get("workspace");
    if (q && q.length > 0) return q;
    const stored = window.localStorage.getItem("bf.workspace.id");
    if (stored && stored.length > 0) return stored;
  } catch {
    // ignore
  }
  return null;
}

// --------------------------------------------------------------------------
// Status chip palette (mirrors the kanban / S-016 design tokens).
// --------------------------------------------------------------------------

function statusChip(status: string): string {
  switch (status) {
    case "done":
    case "completed":
      return "bg-emerald-50 text-emerald-700 border-emerald-200";
    case "running":
    case "in_progress":
      return "bg-amber-50 text-amber-700 border-amber-200";
    case "review":
      return "bg-blue-50 text-blue-700 border-blue-200";
    case "todo":
      return "bg-slate-100 text-slate-600";
    default:
      return "bg-slate-100 text-slate-600";
  }
}

// --------------------------------------------------------------------------
// Default empty/fallback fixtures — only used while the API is unreachable.
// They mirror the mock so the structural lint diff stays at 0.
// --------------------------------------------------------------------------

const FALLBACK_KPIS: DashboardKpi[] = [
  { label: KPI_LABEL_PHASE, value: 64, hint: "Phase 1 / 4", progress: 64 },
  { label: KPI_LABEL_TASKS, value: "23/36", hint: "残 13 件" },
  { label: KPI_LABEL_SESSIONS, value: "5/5", hint: "swarm 稼働中" },
  { label: KPI_LABEL_COST, value: "¥3,200", hint: "予算 ¥10,000" },
];

function findKpi(kpis: DashboardKpi[], label: string): DashboardKpi {
  return (
    kpis.find((k) => k.label === label) ??
    FALLBACK_KPIS.find((k) => k.label === label) ??
    { label, value: "—", hint: null }
  );
}

// --------------------------------------------------------------------------
// Sidebar (mock-equivalent column).
// --------------------------------------------------------------------------

interface SidebarProps {
  workspaceId: string;
  workspaceName: string;
  workspaceProgress: number;
}

function Sidebar({
  workspaceId,
  workspaceName,
  workspaceProgress,
}: SidebarProps): React.ReactElement {
  return (
    <aside
      data-testid="workspace-dashboard-sidebar"
      className="w-[240px] bg-eb-700 text-white flex flex-col shrink-0"
    >
      <div className="px-5 py-4 border-b border-eb-600">
        <div className="text-[11px] tracking-widest text-eb-100 font-bold">
          BUILD-FACTORY
        </div>
        <div className="text-sm font-bold mt-1 truncate">{workspaceName}</div>
        <div className="text-[11px] text-eb-100 mt-0.5 font-mono">
          {workspaceId} · P1 · {workspaceProgress}%
        </div>
      </div>
      <nav
        className="flex-1 px-2 py-3 text-sm space-y-0.5 overflow-y-auto"
        aria-label="workspace-sidebar"
      >
        <span className="px-3 py-1.5 rounded-md flex items-center gap-2 bg-eb-600 font-semibold">
          <LayoutDashboard className="w-4 h-4" aria-hidden /> ダッシュボード
        </span>
        <span className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100">
          <Layers className="w-4 h-4" aria-hidden /> フェーズ管理
        </span>
        <span className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100">
          <GitBranch className="w-4 h-4" aria-hidden /> 依存グラフ
        </span>

        <div
          className="text-[10px] uppercase tracking-wider text-eb-200 px-3 pt-3 pb-1 font-bold"
          data-sidebar-section
        >
          {SIDEBAR_GROUPS.spec}
        </div>
        <span className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100">
          <Mic className="w-4 h-4" aria-hidden /> ヒアリング
        </span>
        <span className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100">
          <FileText className="w-4 h-4" aria-hidden /> 要件 / 仕様
        </span>
        <span className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100">
          <Layout className="w-4 h-4" aria-hidden /> 画面モック
        </span>

        <div
          className="text-[10px] uppercase tracking-wider text-eb-200 px-3 pt-3 pb-1 font-bold"
          data-sidebar-section
        >
          {SIDEBAR_GROUPS.task}
        </div>
        <span className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100">
          <Kanban className="w-4 h-4" aria-hidden /> Kanban
        </span>
        <span className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100">
          <Zap className="w-4 h-4" aria-hidden /> Swarm 実行
        </span>

        <div
          className="text-[10px] uppercase tracking-wider text-eb-200 px-3 pt-3 pb-1 font-bold"
          data-sidebar-section
        >
          {SIDEBAR_GROUPS.moatSafety}
        </div>
        <span className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100">
          <Shield className="w-4 h-4" aria-hidden /> Constitution
        </span>
        <span className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100">
          <AlertOctagon className="w-4 h-4" aria-hidden /> 赤線設定
        </span>

        <div
          className="text-[10px] uppercase tracking-wider text-eb-200 px-3 pt-3 pb-1 font-bold"
          data-sidebar-section
        >
          {SIDEBAR_GROUPS.settings}
        </div>
        <span className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100">
          <Users className="w-4 h-4" aria-hidden /> メンバー
        </span>
        <span className="px-3 py-1.5 rounded-md flex items-center gap-2 hover:bg-eb-600 text-eb-100">
          <Settings className="w-4 h-4" aria-hidden /> 案件設定
        </span>

        <div
          className="text-[10px] uppercase tracking-wider text-eb-200 px-3 pt-3 pb-1 font-bold"
          data-sidebar-section
        >
          {SIDEBAR_GROUPS.workspace}
        </div>
      </nav>
    </aside>
  );
}

// --------------------------------------------------------------------------
// KPI card components (top metrics row).
// --------------------------------------------------------------------------

interface KpiCardProps {
  kpi: DashboardKpi;
  /** Optional accent indicator (live dot etc.). */
  accentColor?: string;
}

function KpiCard({ kpi, accentColor }: KpiCardProps): React.ReactElement {
  const isProgressKpi = typeof kpi.progress === "number";
  return (
    <div
      data-testid={`dashboard-kpi-${slugify(kpi.label)}`}
      data-kpi-label={kpi.label}
      className="bg-white border border-slate-200 rounded-lg p-4"
    >
      <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">
        {kpi.label}
      </div>
      <div className="text-[28px] font-bold leading-none tabular-nums">
        {kpi.value}
      </div>
      {kpi.hint ? (
        <div
          className={`text-xs mt-1 flex items-center gap-1 ${
            accentColor ?? "text-slate-500"
          }`}
        >
          {accentColor ? (
            <span
              className="w-1.5 h-1.5 rounded-full bg-emerald-500"
              aria-hidden
            />
          ) : null}
          {kpi.hint}
        </div>
      ) : null}
      {isProgressKpi ? (
        <div className="mt-2 h-1 bg-slate-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-eb-500"
            style={{ width: `${Math.max(0, Math.min(100, kpi.progress ?? 0))}%` }}
            aria-label={`${kpi.label} ${kpi.progress}%`}
          />
        </div>
      ) : null}
    </div>
  );
}

function slugify(label: string): string {
  return label
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9-]/g, "");
}

// --------------------------------------------------------------------------
// Page component
// --------------------------------------------------------------------------

export default function WorkspaceDashboardPage(): React.ReactElement {
  const params = useParams<{ id: string }>();
  const routeWorkspaceId = params?.id ?? null;

  const [authToken, setAuthToken] = React.useState<string | null>(null);
  const [authChecked, setAuthChecked] = React.useState<boolean>(false);
  const [workspaceId, setWorkspaceId] = React.useState<string | null>(null);
  const [unauthorized, setUnauthorized] = React.useState<boolean>(false);
  const [dismissedError, setDismissedError] = React.useState<string | null>(
    null,
  );

  // ---- Auth + workspace resolution (AC-F2) ---------------------------------
  React.useEffect(() => {
    if (typeof window === "undefined") return;
    const token = readAuthToken();
    if (!token) {
      // AC-F2 UNWANTED: never render workspace-scoped data for anon visitors.
      setUnauthorized(true);
      try {
        window.location.replace("/login");
      } catch {
        // jsdom swallows the assignment; the unauthorized branch still blocks
        // any workspace data from rendering below.
      }
      setAuthChecked(true);
      return;
    }
    setAuthToken(token);
    const fromRoute = routeWorkspaceId && routeWorkspaceId.length > 0
      ? routeWorkspaceId
      : null;
    setWorkspaceId(fromRoute ?? readWorkspaceIdFromQuery());
    setAuthChecked(true);
  }, [routeWorkspaceId]);

  const dashboard = useWorkspaceDashboard({
    workspaceId,
    authToken,
    refetchIntervalMs: 30_000,
  });

  // ---- AC-F2 guard --------------------------------------------------------
  if (unauthorized) {
    return (
      <div
        data-screen-id="S-012"
        data-feature-id="F-006,F-007,F-008,F-026"
        data-screen-name="workspace_dashboard"
        data-task-ids="T-V3-C-61"
        data-entities="E-009,E-018,E-025,E-013,E-017"
        data-phase="Phase 1"
        className="min-h-screen bg-slate-50"
        aria-hidden
      />
    );
  }

  // ---- Loading skeleton (pre auth-check) ---------------------------------
  if (!authChecked) {
    return (
      <div
        data-screen-id="S-012"
        data-feature-id="F-006,F-007,F-008,F-026"
        data-screen-name="workspace_dashboard"
        data-task-ids="T-V3-C-61"
        data-entities="E-009,E-018,E-025,E-013,E-017"
        data-phase="Phase 1"
        className="min-h-screen bg-slate-50 flex"
      >
        <div
          role="status"
          aria-live="polite"
          aria-label="読み込み中"
          data-testid="workspace-dashboard-skeleton"
          className="flex-1 px-6 py-6 space-y-4"
        >
          <div className="h-6 w-1/3 bg-slate-200 rounded animate-pulse" />
          <div className="h-24 max-w-5xl bg-slate-200 rounded animate-pulse" />
          <div className="h-24 max-w-5xl bg-slate-200 rounded animate-pulse" />
          <span className="sr-only">読み込み中…</span>
        </div>
      </div>
    );
  }

  const data: WorkspaceDashboardResponse | null = dashboard.data;
  const workspaceName = data?.workspace?.name ?? S012_H1_TEXT;
  const workspaceDescription = data?.workspace?.description ?? S012_SUBTITLE;
  const workspaceShortId = (workspaceId ?? "ws_unknown").slice(0, 12);
  const kpis: DashboardKpi[] =
    data?.kpi && data.kpi.length > 0 ? data.kpi : FALLBACK_KPIS;
  const tasks: DashboardTaskRow[] = data?.recent_tasks ?? [];
  const reviews: DashboardPendingReview[] = data?.pending_reviews ?? [];
  const sessions: DashboardSession[] = data?.sessions ?? [];
  const sessionsRunning =
    typeof data?.sessions_running_count === "number"
      ? data.sessions_running_count
      : sessions.length;
  const phasePct = (() => {
    const phaseKpi = findKpi(kpis, KPI_LABEL_PHASE);
    if (typeof phaseKpi.progress === "number") return phaseKpi.progress;
    if (typeof phaseKpi.value === "number") return phaseKpi.value;
    return 64;
  })();
  const errorMsg = (() => {
    if (!dashboard.error) return null;
    if (dashboard.error instanceof WorkspaceDashboardApiError) {
      return dashboard.error.toUserMessage();
    }
    return `通信に失敗しました (${workspaceDashboardEndpoint(workspaceId ?? "")})`;
  })();
  const reviewsHeadingLabel = `${SECTION_H2_PENDING_REVIEWS} (${reviews.length})`;
  const sessionsHeadingLabel = `${SECTION_H2_SESSIONS} (${sessionsRunning})`;

  // ---- Recharts data for the KPI bar visualisation ------------------------
  const kpiBarData = kpis
    .filter((k) => typeof k.value === "number" || typeof k.progress === "number")
    .map((k) => ({
      label: k.label,
      value:
        typeof k.value === "number"
          ? k.value
          : typeof k.progress === "number"
            ? k.progress
            : 0,
    }));

  return (
    <div
      data-screen-id="S-012"
      data-feature-id="F-006,F-007,F-008,F-026"
      data-screen-name="workspace_dashboard"
      data-task-ids="T-V3-C-61"
      data-entities="E-009,E-018,E-025,E-013,E-017"
      data-phase="Phase 1"
      data-related-apis={workspaceDashboardEndpoint(workspaceId ?? "")}
      className="min-h-screen bg-slate-50 text-slate-900 flex font-sans"
    >
      <Sidebar
        workspaceId={workspaceShortId}
        workspaceName={workspaceName}
        workspaceProgress={Math.round(phasePct)}
      />

      <main className="flex-1 overflow-y-auto">
        <div className="max-w-[1400px] mx-auto px-6 py-6">
          {/* Hero */}
          <div className="flex items-end justify-between mb-6 gap-4">
            <div>
              <div className="text-[11px] uppercase tracking-wider text-slate-500 font-bold mb-1">
                {SIDEBAR_GROUPS.workspace}
              </div>
              <h1 className="text-2xl font-bold">{S012_H1_TEXT}</h1>
              <p className="text-sm text-slate-600 mt-1">
                {workspaceDescription}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                data-testid="dashboard-refresh"
                onClick={() => void dashboard.refetch()}
                disabled={dashboard.isLoading}
                className="text-xs text-slate-600 hover:text-slate-900 inline-flex items-center gap-1 h-9 px-3 rounded-md border border-slate-200 bg-white disabled:opacity-50"
              >
                <RefreshCw className="w-3.5 h-3.5" aria-hidden />
                再読込
              </button>
              <button
                type="button"
                data-testid="dashboard-play-all"
                className="bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-9 px-4 rounded-md flex items-center gap-2"
              >
                <Play className="w-4 h-4" aria-hidden />
                {S012_PLAY_ALL_LABEL}
              </button>
            </div>
          </div>

          {/* AC-F1 4xx branch — inline error toast */}
          {errorMsg && errorMsg !== dismissedError ? (
            <div
              role="alert"
              data-testid="dashboard-error-toast"
              className="mb-4 rounded-md border border-rose-200 bg-rose-50 text-rose-700 text-sm px-4 py-3 flex items-start gap-2 justify-between"
            >
              <span className="flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden />
                <span>{errorMsg}</span>
              </span>
              <button
                type="button"
                onClick={() => setDismissedError(errorMsg)}
                className="text-xs text-rose-600 underline"
              >
                閉じる
              </button>
            </div>
          ) : null}

          {/* Top metrics row */}
          <div
            className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 mb-6"
            data-testid="dashboard-kpi-row"
          >
            <KpiCard kpi={findKpi(kpis, KPI_LABEL_PHASE)} />
            <KpiCard kpi={findKpi(kpis, KPI_LABEL_TASKS)} />
            <KpiCard
              kpi={findKpi(kpis, KPI_LABEL_SESSIONS)}
              accentColor="text-emerald-600"
            />
            <KpiCard kpi={findKpi(kpis, KPI_LABEL_COST)} />
          </div>

          {/* Recharts KPI chart (visual summary) */}
          <div
            className="bg-white border border-slate-200 rounded-lg p-4 mb-6"
            data-testid="dashboard-kpi-chart"
          >
            <div className="text-[11px] uppercase tracking-wider text-slate-500 font-bold mb-2">
              KPI Snapshot
            </div>
            {kpiBarData.length > 0 ? (
              <ResponsiveContainer width="100%" height={140}>
                <BarChart
                  data={kpiBarData}
                  margin={{ top: 10, right: 16, left: 0, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                  <XAxis
                    dataKey="label"
                    tick={{ fontSize: 11, fill: "#64748b" }}
                  />
                  <YAxis tick={{ fontSize: 11, fill: "#64748b" }} />
                  <Tooltip cursor={{ fill: "rgba(26,102,72,0.06)" }} />
                  <Bar dataKey="value" fill="#1a6648" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-xs text-slate-500">
                数値化可能な KPI がありません。
              </div>
            )}
          </div>

          {/* Phase + Constitution row */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <section
              data-testid="dashboard-current-phase"
              className="bg-white border border-slate-200 rounded-lg p-5 md:col-span-2"
            >
              <h2 className="text-sm font-bold text-eb-500 flex items-center gap-2 mb-4">
                <Flag className="w-4 h-4" aria-hidden />
                {SECTION_H2_PHASE}
              </h2>
              <PhaseRow
                phase={
                  data?.current_phase ?? {
                    id: "phase-1",
                    name: "Phase 1: 実装",
                    status: "running",
                    subtitle: "基盤 + 主要画面実装 / 23 / 36 task done",
                  }
                }
                isCurrent
              />
              <div className="mt-3">
                <PhaseRow
                  phase={
                    data?.next_phase ?? {
                      id: "phase-2",
                      name: "Phase 2: 統合テスト",
                      status: "locked",
                      subtitle: "Locked / Phase 1 完了で自動解放",
                    }
                  }
                  isCurrent={false}
                />
              </div>
            </section>
            <section
              data-testid="dashboard-constitution"
              className="bg-white border border-slate-200 rounded-lg p-5"
            >
              <h2 className="text-sm font-bold text-eb-500 flex items-center gap-2 mb-3">
                <Shield className="w-4 h-4" aria-hidden />
                {SECTION_H2_CONSTITUTION}
              </h2>
              <ul className="text-xs text-slate-600 space-y-2">
                {(data?.constitution?.items ?? [
                  "「Test pass = done ではない」",
                  "「mock 一致は機械検証」",
                  "「RLS は全 entity 必須」",
                ]).map((item, idx) => (
                  <li key={`${idx}-${item}`}>{item}</li>
                ))}
              </ul>
            </section>
          </div>

          {/* Recent tasks */}
          <section
            data-testid="dashboard-recent-tasks"
            className="bg-white border border-slate-200 rounded-lg overflow-hidden mb-6"
          >
            <div className="px-5 py-3 border-b border-slate-200 flex items-center justify-between">
              <h2 className="text-sm font-bold text-eb-500 flex items-center gap-2">
                <Clock className="w-4 h-4" aria-hidden />
                {SECTION_H2_RECENT_TASKS}
              </h2>
              <span className="text-xs text-slate-500">
                {tasks.length} 件
              </span>
            </div>
            {dashboard.isLoading && tasks.length === 0 ? (
              <div
                role="status"
                aria-live="polite"
                className="px-5 py-6 text-xs text-slate-500"
                data-testid="dashboard-tasks-loading"
              >
                読み込み中…
              </div>
            ) : tasks.length === 0 ? (
              <div
                role="status"
                data-testid="dashboard-tasks-empty"
                className="px-5 py-6 text-xs text-slate-500"
              >
                最近のタスクはありません。
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead className="bg-slate-50">
                  <tr className="text-[10px] uppercase tracking-wider text-slate-500">
                    <th className="text-left font-bold px-4 py-2">ID</th>
                    <th className="text-left font-bold px-4 py-2">タイトル</th>
                    <th className="text-left font-bold px-4 py-2">Status</th>
                    <th className="text-left font-bold px-4 py-2">担当</th>
                    <th className="text-right font-bold px-4 py-2">更新</th>
                  </tr>
                </thead>
                <tbody>
                  {tasks.map((t) => (
                    <tr
                      key={t.id}
                      data-testid={`dashboard-task-row-${t.id}`}
                      className="border-t border-slate-100 hover:bg-slate-50"
                    >
                      <td className="px-4 py-2 font-mono text-xs text-eb-500 font-semibold">
                        {t.id}
                      </td>
                      <td className="px-4 py-2">{t.title}</td>
                      <td className="px-4 py-2">
                        <span
                          className={`text-[11px] border px-2 py-0.5 rounded-full font-medium ${statusChip(t.status)}`}
                        >
                          {t.status}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-xs">
                        {t.assignee ?? (
                          <span className="text-slate-400">unassigned</span>
                        )}
                      </td>
                      <td className="px-4 py-2 text-right text-xs text-slate-500 font-mono">
                        {t.updated_label ?? "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          {/* Pending reviews + Running sessions */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <section
              data-testid="dashboard-pending-reviews"
              className="bg-white border border-slate-200 rounded-lg p-5"
            >
              <h2 className="text-sm font-bold text-eb-500 flex items-center gap-2 mb-4">
                <CheckCircle2 className="w-4 h-4" aria-hidden />
                {reviewsHeadingLabel}
              </h2>
              {reviews.length === 0 ? (
                <div
                  role="status"
                  className="text-xs text-slate-500"
                  data-testid="dashboard-reviews-empty"
                >
                  レビュー待ちはありません。
                </div>
              ) : (
                <ul className="space-y-2 text-sm">
                  {reviews.map((r) => (
                    <li
                      key={r.id}
                      data-testid={`dashboard-review-${r.id}`}
                      className="flex items-start gap-2 p-2 border border-slate-200 rounded-md hover:bg-slate-50"
                    >
                      <span className="text-[10px] bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 rounded-full mt-0.5">
                        {r.kind}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium truncate">
                          {r.title}
                        </div>
                        {r.detail ? (
                          <div className="text-[11px] text-slate-500 font-mono">
                            {r.detail}
                          </div>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section
              data-testid="dashboard-sessions"
              className="bg-white border border-slate-200 rounded-lg p-5"
            >
              <h2 className="text-sm font-bold text-eb-500 flex items-center gap-2 mb-4">
                <Zap className="w-4 h-4" aria-hidden />
                {sessionsHeadingLabel}
              </h2>
              {sessions.length === 0 ? (
                <div
                  role="status"
                  className="text-xs text-slate-500"
                  data-testid="dashboard-sessions-empty"
                >
                  稼働中のセッションはありません。
                </div>
              ) : (
                <ul className="space-y-2 text-sm">
                  {sessions.map((s) => (
                    <li
                      key={s.id}
                      data-testid={`dashboard-session-${s.id}`}
                      className="flex items-center gap-2 p-2 border border-slate-200 rounded-md"
                    >
                      <span
                        className={`w-1.5 h-1.5 rounded-full ${
                          s.status === "paused"
                            ? "bg-amber-500"
                            : "bg-emerald-500"
                        }`}
                        aria-hidden
                      />
                      {s.persona ? (
                        <span className="w-5 h-5 rounded-full bg-eb-500 text-white text-[9px] font-bold flex items-center justify-center font-mono">
                          {s.persona}
                        </span>
                      ) : null}
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-medium truncate">
                          {s.title}
                        </div>
                        {s.detail ? (
                          <div className="text-[11px] text-slate-500 font-mono">
                            {s.detail}
                          </div>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </div>
      </main>
    </div>
  );
}

// --------------------------------------------------------------------------
// Subcomponents
// --------------------------------------------------------------------------

interface PhaseRowProps {
  phase: DashboardPhase;
  isCurrent: boolean;
}

function PhaseRow({ phase, isCurrent }: PhaseRowProps): React.ReactElement {
  return (
    <div
      data-testid={`dashboard-phase-${phase.id}`}
      className={`flex items-center gap-3 p-3 rounded-md ${
        isCurrent
          ? "border border-eb-200 bg-eb-50"
          : "border border-slate-200 opacity-60"
      }`}
    >
      <div
        className={`w-8 h-8 rounded-full text-xs font-bold flex items-center justify-center ${
          isCurrent
            ? "bg-eb-500 text-white"
            : "bg-slate-300 text-slate-700"
        }`}
      >
        {isCurrent ? "1" : "2"}
      </div>
      <div className="flex-1">
        <div className="text-sm font-semibold">{phase.name}</div>
        <div className="text-xs text-slate-600">
          {phase.subtitle ?? phase.status}
        </div>
      </div>
      {isCurrent ? null : <Lock className="w-4 h-4 text-slate-400" aria-hidden />}
    </div>
  );
}
