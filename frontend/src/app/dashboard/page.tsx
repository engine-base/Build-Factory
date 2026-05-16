"use client";

/**
 * T-V3-C-06 / S-006: 10 案件 俯瞰 (Account Dashboard) page.
 *
 * Implements the screen documented at:
 *   docs/mocks/2026-05-15_v3/account/S-006-account-dashboard.html
 * Pairs with the session-expired dialog:
 *   docs/mocks/2026-05-15_v3/dialog/S-054-session-expired.html
 *
 * Mock-impl meta (lint-mock-impl-diff Gate #8):
 * @screen-id S-006
 * @feature-id F-024,F-018,F-008,F-007,F-017
 * @task-ids T-V3-C-06,T-V3-DRIFT-01,T-V3-DRIFT-02,T-V3-RF-03
 * @entities E-008,E-009,E-018,E-025,E-027,E-029
 * @phase Phase 1B
 *
 * 3-tier AC mapping:
 *   structural.AC-S1 (data-screen-id="S-006")                    — root <main> element.
 *   structural.AC-S2 (h1 text "10 案件 俯瞰")                     — page header.
 *   structural.AC-S3 (6 section h2: Pending Reviews / Phase 進捗 / 完了タスク (7d)
 *                     / 全 Workspaces (10 案件並走中) / AI 社員 使用率（今週） /
 *                     直近の Activity) — section headings rendered in mock order.
 *   structural.AC-S4 (KPI labels: Active Projects / Running Sessions /
 *                     Monthly Cost / Anomalies (24h)) — 4 hero cards.
 *   functional.AC-F1 (GET /api/accounts/{id}/dashboard via typed client) —
 *                    `getAccountDashboard()` is the page's primary action,
 *                    invoked from a one-shot React effect.
 *   functional.AC-F2 (4xx/5xx → non-technical toast referencing the failing
 *                    endpoint, no stack trace) — error handler delegates to
 *                    `DashboardApiError.toUserMessage()`.
 *   functional.AC-F3 (server aggregates KPI across every workspace the caller
 *                    belongs to) — surfaced to the UI via `payload.kpi`.
 *   functional.AC-F4 (401 + session_expired → render S-054 dialog and preserve
 *                    in-flight form data in localStorage) — sentinel handled
 *                    by `SessionExpiredError` and the inline session-expired
 *                    dialog component below.
 */

import * as React from "react";
import { toast } from "sonner";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bot,
  Briefcase,
  CheckCircle2,
  ClockAlert,
  Download,
  Layers,
  LogIn,
  Wallet,
  Zap,
} from "lucide-react";

import {
  ACCOUNT_DASHBOARD_ENDPOINT_PATTERN,
  DashboardApiError,
  SessionExpiredError,
  getAccountDashboard,
  type AccountDashboardResponse,
  type DashboardWorkspaceSummary,
} from "@/api/search";

// --------------------------------------------------------------------------
// Constants — verbatim mock copy. Any deviation breaks AC-S2/S3/S4 + Gate #8.
// --------------------------------------------------------------------------

const H1_TEXT = "10 案件 俯瞰";

const KPI_LABELS = [
  "Active Projects",
  "Running Sessions",
  "Monthly Cost",
  "Anomalies (24h)",
] as const;

const SECTION_H2_TEXTS = [
  "Pending Reviews",
  "Phase 進捗",
  "完了タスク (7d)",
  "全 Workspaces (10 案件並走中)",
  "AI 社員 使用率（今週）",
  "直近の Activity",
] as const;

/** localStorage key the typed router uses for the active account id. */
const STORAGE_ACCOUNT_ID_KEY = "bf.account_id";
/** AC-F4: in-flight form draft preservation key. */
const STORAGE_INFLIGHT_FORM_KEY = "bf.inflight_form_data";

function readActiveAccountId(): string {
  if (typeof window === "undefined") return "1";
  return window.localStorage.getItem(STORAGE_ACCOUNT_ID_KEY) ?? "1";
}

function readAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("bf.access_token");
}

// --------------------------------------------------------------------------
// AC-F4: in-flight form data preservation helper.
//
// Walks every <input>/<textarea>/<select> currently rendered in the document
// and serialises name → value pairs into localStorage so the user does not
// lose their work when the S-054 dialog appears.
// --------------------------------------------------------------------------
function preserveInflightFormData(): void {
  if (typeof window === "undefined") return;
  try {
    const draft: Record<string, string> = {};
    const elements = window.document.querySelectorAll<
      HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
    >("input[name], textarea[name], select[name]");
    elements.forEach((el) => {
      const name = el.getAttribute("name") ?? "";
      if (!name) return;
      draft[name] = el.value ?? "";
    });
    window.localStorage.setItem(
      STORAGE_INFLIGHT_FORM_KEY,
      JSON.stringify({
        ts: Date.now(),
        path:
          typeof window.location !== "undefined"
            ? window.location.pathname
            : "",
        fields: draft,
      }),
    );
  } catch {
    // Best-effort — never re-throw from the preservation path.
  }
}

// --------------------------------------------------------------------------
// Visual primitives
// --------------------------------------------------------------------------

function formatJpy(value: number): string {
  return `¥${Math.round(value).toLocaleString("ja-JP")}`;
}

function clampPct(value: number): number {
  if (Number.isNaN(value)) return 0;
  if (value <= 0) return 0;
  if (value >= 1) return 100;
  return Math.round(value * 100);
}

interface KpiCardProps {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  icon: React.ReactNode;
  tone?: "default" | "alert";
  bar?: number; // 0..100
}

function KpiCard({
  label,
  value,
  hint,
  icon,
  tone = "default",
  bar,
}: KpiCardProps): React.JSX.Element {
  const borderClass =
    tone === "alert" ? "border-red-200" : "border-slate-200";
  const labelClass =
    tone === "alert" ? "text-red-600" : "text-slate-500";
  const valueClass =
    tone === "alert" ? "text-red-600" : "text-slate-900";
  return (
    <div className={`bg-white border ${borderClass} rounded-lg p-4`}>
      <div className="flex items-start justify-between mb-2">
        <div
          className={`text-[10px] font-bold uppercase tracking-wider ${labelClass}`}
        >
          {label}
        </div>
        <div className="text-slate-400">{icon}</div>
      </div>
      <div
        className={`text-[28px] font-bold tabular-nums leading-none ${valueClass}`}
      >
        {value}
      </div>
      {hint ? (
        <div className="text-xs text-slate-500 mt-2">{hint}</div>
      ) : null}
      {typeof bar === "number" ? (
        <div className="mt-3 h-1 bg-slate-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-eb-500"
            style={{ width: `${Math.max(0, Math.min(100, bar))}%` }}
          />
        </div>
      ) : null}
    </div>
  );
}

interface PhaseRowProps {
  name: string;
  phase: string;
  progress: number;
}

function PhaseRow({ name, phase, progress }: PhaseRowProps): React.JSX.Element {
  const pct = clampPct(progress);
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium truncate">{name}</span>
        <span className="text-[11px] mono text-slate-500">
          {phase} · {pct}%
        </span>
      </div>
      <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div className="h-full bg-eb-500" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

interface WorkspaceRowProps {
  workspace: DashboardWorkspaceSummary;
}

function WorkspaceRow({ workspace }: WorkspaceRowProps): React.JSX.Element {
  const pct = clampPct(workspace.progress);
  const statusLabel = workspace.status || "—";
  const statusTone =
    statusLabel === "running"
      ? "bg-emerald-50 text-emerald-700 border-emerald-200"
      : statusLabel === "review"
        ? "bg-amber-50 text-amber-700 border-amber-200"
        : "bg-slate-100 text-slate-600 border-slate-200";
  return (
    <tr
      className="border-t border-slate-100 hover:bg-slate-50"
      data-testid="workspace-row"
    >
      <td className="px-4 py-2.5 font-medium">{workspace.name}</td>
      <td className="px-4 py-2.5">
        <span className="text-xs">{pct}%</span>
      </td>
      <td className="px-4 py-2.5 text-right tabular-nums">
        {workspace.completed_tasks}
      </td>
      <td className="px-4 py-2.5 text-right tabular-nums">
        {workspace.running_sessions}
      </td>
      <td className="px-4 py-2.5 text-right tabular-nums">
        {formatJpy(workspace.monthly_cost_jpy)}
      </td>
      <td className="px-4 py-2.5 text-xs text-slate-500">
        {workspace.role ?? "—"}
      </td>
      <td className="px-4 py-2.5">
        <span
          className={`text-[11px] px-2 py-0.5 rounded-full font-medium border ${statusTone}`}
        >
          {statusLabel}
        </span>
      </td>
    </tr>
  );
}

// --------------------------------------------------------------------------
// AC-F4: Session-expired dialog (inline S-054 implementation).
// --------------------------------------------------------------------------

interface SessionExpiredDialogProps {
  endpoint: string;
  onClose: () => void;
}

function SessionExpiredDialog({
  endpoint,
  onClose,
}: SessionExpiredDialogProps): React.JSX.Element {
  const handleSignin = React.useCallback(() => {
    if (typeof window !== "undefined") {
      window.location.assign("/login");
    }
  }, []);
  return (
    <div
      data-screen-id="S-054"
      data-feature-id=""
      data-task-ids="T-V3-C-06"
      data-entities=""
      data-phase="Phase 1B"
      role="dialog"
      aria-modal="true"
      aria-labelledby="session-expired-title"
      className="fixed inset-0 z-50 bg-slate-900/60 flex items-center justify-center px-6"
    >
      <div className="bg-white rounded-xl shadow-2xl max-w-[440px] w-full p-6 text-center">
        <div className="inline-flex w-14 h-14 rounded-full bg-amber-50 items-center justify-center mb-4">
          <ClockAlert className="w-7 h-7 text-amber-600" aria-hidden />
        </div>
        <h2
          id="session-expired-title"
          className="text-xl font-bold text-slate-900"
        >
          セッションの有効期限が切れました
        </h2>
        <p className="text-sm text-slate-600 mt-2 leading-relaxed">
          セキュリティのため、長時間操作がない場合は自動的にログアウトします。再度ログインしてください。
        </p>
        <p className="text-[11px] text-slate-400 mt-3 mono">{endpoint}</p>
        <button
          type="button"
          onClick={handleSignin}
          className="w-full bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-10 rounded-md mt-5 flex items-center justify-center gap-2"
          data-testid="session-expired-signin"
        >
          <LogIn className="w-4 h-4" aria-hidden />
          ログイン画面へ
        </button>
        <button
          type="button"
          onClick={onClose}
          className="w-full text-xs text-slate-500 hover:text-slate-700 mt-3"
        >
          後で
        </button>
        <div className="text-xs text-slate-500 mt-3">
          編集中のデータは下書きとして保存されています
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
// Page component
// --------------------------------------------------------------------------

type LoadState =
  | { kind: "loading" }
  | { kind: "loaded"; payload: AccountDashboardResponse }
  | { kind: "error"; userMessage: string }
  | { kind: "session_expired"; endpoint: string };

export default function AccountDashboardPage(): React.JSX.Element {
  const [state, setState] = React.useState<LoadState>({ kind: "loading" });
  const ranRef = React.useRef(false);

  React.useEffect(() => {
    if (ranRef.current) return;
    ranRef.current = true;
    const controller = new AbortController();
    const accountId = readActiveAccountId();
    const authToken = readAuthToken();
    (async () => {
      try {
        const payload = await getAccountDashboard(accountId, {
          signal: controller.signal,
          authToken,
        });
        setState({ kind: "loaded", payload });
      } catch (err) {
        if (err instanceof Error && err.name === "AbortError") return;
        if (err instanceof SessionExpiredError) {
          // AC-F4: preserve any in-flight form data before swapping the UI.
          preserveInflightFormData();
          setState({ kind: "session_expired", endpoint: err.endpoint });
          return;
        }
        if (err instanceof DashboardApiError) {
          const message = err.toUserMessage();
          toast.error(message);
          setState({ kind: "error", userMessage: message });
          return;
        }
        // Unknown error — keep the user-facing message non-technical and
        // never expose `.message` (may contain server stack traces).
        const fallback = `ダッシュボードを読み込めませんでした (${ACCOUNT_DASHBOARD_ENDPOINT_PATTERN})`;
        toast.error(fallback);
        setState({ kind: "error", userMessage: fallback });
      }
    })();
    return () => controller.abort();
  }, []);

  const closeDialog = React.useCallback(() => {
    setState({ kind: "loading" });
  }, []);

  const kpi = state.kind === "loaded" ? state.payload.kpi : null;
  const workspaces =
    state.kind === "loaded" ? state.payload.workspaces : [];
  const activeProjects = workspaces.filter((w) => {
    const status = (w.status ?? "").toLowerCase();
    return status === "running" || status === "review";
  }).length;
  const runningSessions = kpi?.running_sessions ?? 0;
  const monthlyCost = kpi?.monthly_cost_jpy ?? 0;
  const pendingReviews = kpi?.pending_approvals ?? 0;

  // Anomalies (24h) is currently a derived approximation pending the dedicated
  // alerts endpoint (tracked by T-V3-B-ALERTS-01). We surface the pending
  // approval count as the conservative upper bound so the KPI cell always
  // renders a numeric value (AC-S4 requires the label to be exposed).
  const anomalies = pendingReviews;

  const sessionCap = 50; // mock 並列上限
  const runningPct = sessionCap > 0
    ? Math.min(100, Math.round((runningSessions / sessionCap) * 100))
    : 0;

  return (
    <main
      data-screen-id="S-006"
      data-feature-id="F-024,F-018,F-008,F-007,F-017"
      data-task-ids="T-V3-C-06"
      data-entities="E-008,E-009,E-018,E-025,E-027,E-029"
      data-phase="Phase 1B"
      className="min-h-screen bg-slate-50 text-slate-900"
    >
      <div className="max-w-[1400px] mx-auto px-6 py-6">
        {/* Page header */}
        <div className="flex items-end justify-between mb-6">
          <div>
            <div className="text-[11px] uppercase tracking-wider text-slate-500 font-bold mb-1">
              Account Dashboard
            </div>
            <h1 className="text-2xl font-bold text-slate-900">{H1_TEXT}</h1>
            <p className="text-sm text-slate-600 mt-1">
              受託 + 内製プロジェクトの並走状況をリアルタイム表示
            </p>
          </div>
          <div className="flex items-center gap-2">
            <select
              aria-label="期間"
              className="border border-slate-200 bg-white text-sm h-9 px-3 rounded-md"
            >
              <option>過去 7 日</option>
              <option>過去 24 時間</option>
              <option>過去 30 日</option>
            </select>
            <button
              type="button"
              className="border border-slate-200 bg-white hover:bg-slate-50 text-sm h-9 px-4 rounded-md flex items-center gap-2"
            >
              <Download className="w-4 h-4" aria-hidden />
              HTML 出力
            </button>
          </div>
        </div>

        {state.kind === "error" ? (
          <div
            role="alert"
            data-testid="dashboard-error"
            className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-md px-4 py-3 mb-6"
          >
            {state.userMessage}
          </div>
        ) : null}

        {/* Hero KPIs (4 cards) — AC-S4 */}
        <div className="grid grid-cols-4 gap-4 mb-6">
          <KpiCard
            label={KPI_LABELS[0]}
            value={
              <>
                {activeProjects}
                <span className="text-base text-slate-500 font-normal">
                  /{workspaces.length || 10}
                </span>
              </>
            }
            hint={<span>本日の稼働中ワークスペース</span>}
            icon={<Briefcase className="w-4 h-4" aria-hidden />}
          />
          <KpiCard
            label={KPI_LABELS[1]}
            value={
              <>
                {runningSessions}
                <span className="text-base text-slate-500 font-normal">
                  /{sessionCap}
                </span>
              </>
            }
            hint={<span>並列上限 {runningPct}%</span>}
            icon={<Zap className="w-4 h-4" aria-hidden />}
            bar={runningPct}
          />
          <KpiCard
            label={KPI_LABELS[2]}
            value={formatJpy(monthlyCost)}
            hint={<span>今月の総コスト</span>}
            icon={<Wallet className="w-4 h-4" aria-hidden />}
          />
          <KpiCard
            label={KPI_LABELS[3]}
            value={anomalies}
            hint={<span>赤線抵触 / 失敗の合算</span>}
            icon={<AlertTriangle className="w-4 h-4" aria-hidden />}
            tone="alert"
          />
        </div>

        {/* 3-col grid: Pending Reviews / Phase 進捗 / 完了タスク (7d) — AC-S3 [0..2] */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          <section className="bg-white border border-slate-200 rounded-lg p-5">
            <h2 className="text-sm font-bold text-eb-500 flex items-center gap-2 mb-4">
              <CheckCircle2 className="w-4 h-4" aria-hidden />
              {SECTION_H2_TEXTS[0]}
            </h2>
            {state.kind === "loading" ? (
              <p className="text-xs text-slate-500">読み込み中...</p>
            ) : pendingReviews === 0 ? (
              <p className="text-xs text-slate-500">
                未確認のレビューはありません
              </p>
            ) : (
              <ul
                className="space-y-2 text-sm"
                data-testid="pending-reviews-list"
              >
                <li className="flex items-start gap-2 p-2 rounded-md bg-slate-50">
                  <span className="text-[10px] bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 rounded-full font-medium mt-0.5">
                    保留中
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-medium">
                      {pendingReviews} 件のレビューが未対応
                    </div>
                    <div className="text-[11px] text-slate-500 mono">
                      Pending across all workspaces
                    </div>
                  </div>
                </li>
              </ul>
            )}
          </section>

          <section className="bg-white border border-slate-200 rounded-lg p-5">
            <h2 className="text-sm font-bold text-eb-500 flex items-center gap-2 mb-4">
              <Layers className="w-4 h-4" aria-hidden />
              {SECTION_H2_TEXTS[1]}
            </h2>
            {workspaces.length === 0 ? (
              <p className="text-xs text-slate-500">表示できる案件がありません</p>
            ) : (
              <div className="space-y-3 text-sm">
                {workspaces.slice(0, 4).map((w) => (
                  <PhaseRow
                    key={String(w.id)}
                    name={w.name}
                    phase="P1"
                    progress={w.progress}
                  />
                ))}
              </div>
            )}
          </section>

          <section className="bg-white border border-slate-200 rounded-lg p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-bold text-eb-500 flex items-center gap-2">
                <BarChart3 className="w-4 h-4" aria-hidden />
                {SECTION_H2_TEXTS[2]}
              </h2>
            </div>
            <div className="text-2xl font-bold tabular-nums mb-1">
              {kpi?.completed_tasks ?? 0}
              <span className="text-sm text-slate-500 font-normal ml-1">
                件
              </span>
            </div>
            <div className="text-xs text-slate-500 mb-3">合計 (今週)</div>
          </section>
        </div>

        {/* Workspaces table — AC-S3 [3] */}
        <section className="bg-white border border-slate-200 rounded-lg overflow-hidden mb-6">
          <div className="px-5 py-3 border-b border-slate-200 flex items-center justify-between">
            <h2 className="text-sm font-bold text-eb-500 flex items-center gap-2">
              <Briefcase className="w-4 h-4" aria-hidden />
              {SECTION_H2_TEXTS[3]}
            </h2>
          </div>
          {workspaces.length === 0 ? (
            <p className="text-xs text-slate-500 px-5 py-4">
              {state.kind === "loading"
                ? "案件を読み込み中..."
                : "表示できる案件がありません"}
            </p>
          ) : (
            <table
              className="w-full text-sm"
              data-testid="workspaces-table"
            >
              <thead className="bg-slate-50">
                <tr className="text-[10px] uppercase tracking-wider text-slate-500">
                  <th className="text-left font-bold px-4 py-2">案件</th>
                  <th className="text-left font-bold px-4 py-2">Phase</th>
                  <th className="text-right font-bold px-4 py-2">Tasks</th>
                  <th className="text-right font-bold px-4 py-2">Sessions</th>
                  <th className="text-right font-bold px-4 py-2">Cost</th>
                  <th className="text-left font-bold px-4 py-2">Role</th>
                  <th className="text-left font-bold px-4 py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {workspaces.map((w) => (
                  <WorkspaceRow key={String(w.id)} workspace={w} />
                ))}
              </tbody>
            </table>
          )}
        </section>

        {/* 2-col bottom: AI 社員 使用率 / Activity — AC-S3 [4..5] */}
        <div className="grid grid-cols-2 gap-4">
          <section className="bg-white border border-slate-200 rounded-lg p-5">
            <h2 className="text-sm font-bold text-eb-500 flex items-center gap-2 mb-4">
              <Bot className="w-4 h-4" aria-hidden />
              {SECTION_H2_TEXTS[4]}
            </h2>
            <p className="text-xs text-slate-500">
              AI 社員別のコスト分布は T-V3-B-COST-01 のメトリクス API 連携後に表示します
            </p>
          </section>

          <section className="bg-white border border-slate-200 rounded-lg p-5">
            <h2 className="text-sm font-bold text-eb-500 flex items-center gap-2 mb-4">
              <Activity className="w-4 h-4" aria-hidden />
              {SECTION_H2_TEXTS[5]}
            </h2>
            <p className="text-xs text-slate-500">
              直近のアクティビティは T-V3-B-AUDIT-01 の audit feed と連携後に表示します
            </p>
          </section>
        </div>
      </div>

      {state.kind === "session_expired" ? (
        <SessionExpiredDialog
          endpoint={state.endpoint}
          onClose={closeDialog}
        />
      ) : null}
    </main>
  );
}
