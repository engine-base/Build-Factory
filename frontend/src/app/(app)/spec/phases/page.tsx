"use client";

/**
 * S-016 フェーズ管理 — T-V3-C-37 / F-008.
 *
 * @screen-id S-016
 * @feature-id F-008
 * @task-ids T-V3-C-37,T-V3-RF-06,T-V3-DB-01,T-V3-FIX-01
 * @entities E-013,E-014
 * @phase Phase 1
 *
 * Implements the v3 screen documented at:
 *   docs/mocks/2026-05-15_v3/moat/S-016-phase-management.html
 *
 * 3-tier AC mapping (逐語 — see docs/audit/2026-05-16_v3/T-V3-C-37.md):
 *   structural.AC-S1: h1 == "フェーズ管理"
 *     — page heading inside the data-screen-id="S-016" root element.
 *   structural.AC-S2: section h2 set == { "Phase Timeline" }
 *     — single section heading on the timeline card.
 *   structural.AC-S3: Lucide icons only (no emoji glyphs).
 *
 *   functional.AC-F1: On mount for an authenticated workspace member, the
 *     system shall call GET /api/workspaces/{id}/phases and render the
 *     2xx body; on 4xx the system shall render an inline error toast and
 *     an empty state. — see useEffect + PhasesApiError → error banner.
 *   functional.AC-F2: Unauthenticated visitor → redirect /login (S-001) and
 *     never render workspace-scoped data. — see the early redirect branch.
 *   functional.AC-F3: When POST /api/workspaces/{id}/phases/{phase_id}/gate
 *     is called and all gate_conditions evaluate true, the system shall
 *     unlock the next phase. — see triggerGate handler + 201 response surfacing
 *     unlocked_phase_id and refetching the phase list.
 *
 * Mock fixtures the UI mirrors (逐語 from S-016-phase-management.html):
 *   h1                : "フェーズ管理"
 *   subtitle          : "案件を時系列で区切り / Gate 条件を満たして次へ進める"
 *   timeline h2       : "Phase Timeline"
 *   "フェーズ追加" CTA  : top-right primary button
 *   "Gate 通過" CTA    : per-phase secondary button
 */

import * as React from "react";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Circle,
  GitCommit,
  Layers,
  Lock,
  Plus,
  RefreshCw,
  Unlock,
  X,
} from "lucide-react";

import {
  PhasesApiError,
  createPhase,
  getPhases,
  triggerPhaseGate,
  workspacePhaseGateEndpoint,
  workspacePhasesEndpoint,
  type Phase,
  type PhaseGateCondition,
} from "@/api/phases";

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
 *   3. `null` → caller handles missing state (renders empty inline error).
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

function statusTone(status: string): { chip: string; ring: string } {
  switch (status) {
    case "completed":
      return {
        chip: "bg-emerald-50 text-emerald-700 border-emerald-200",
        ring: "ring-emerald-100",
      };
    case "running":
      return {
        chip: "bg-emerald-50 text-emerald-700 border-emerald-200",
        ring: "ring-eb-100",
      };
    case "locked":
      return {
        chip: "bg-slate-100 text-slate-600 border-slate-200",
        ring: "ring-slate-100",
      };
    case "blocked":
      return {
        chip: "bg-rose-50 text-rose-700 border-rose-200",
        ring: "ring-rose-100",
      };
    default:
      return {
        chip: "bg-slate-100 text-slate-600 border-slate-200",
        ring: "ring-slate-100",
      };
  }
}

function formatDateRange(
  start: string | null | undefined,
  end: string | null | undefined,
): string {
  const fmt = (iso: string | null | undefined): string => {
    if (!iso) return "—";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return `${d.getUTCMonth() + 1}/${d.getUTCDate()}`;
  };
  return `${fmt(start)} - ${fmt(end)}`;
}

function pendingCount(conditions: PhaseGateCondition[] | null | undefined): number {
  if (!conditions || conditions.length === 0) return 0;
  return conditions.filter((c) => c.satisfied !== true).length;
}

// --------------------------------------------------------------------------
// Page component
// --------------------------------------------------------------------------

export default function PhasesPage(): JSX.Element {
  const [view, setView] = React.useState<ViewState>("loading");
  const [phases, setPhases] = React.useState<Phase[]>([]);
  const [currentPhaseId, setCurrentPhaseId] = React.useState<string | null>(
    null,
  );
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null);
  const [toasts, setToasts] = React.useState<ToastEntry[]>([]);
  const toastIdRef = React.useRef(0);

  const [workspaceId, setWorkspaceId] = React.useState<string | null>(null);
  const [authToken, setAuthToken] = React.useState<string | null>(null);
  const [authChecked, setAuthChecked] = React.useState(false);

  // Create dialog state
  const [createOpen, setCreateOpen] = React.useState(false);
  const [draftName, setDraftName] = React.useState("");
  const [draftConditions, setDraftConditions] = React.useState<string>("");
  const [creating, setCreating] = React.useState(false);

  // Gate trigger pending state — keyed by phase id.
  const [gateInFlight, setGateInFlight] = React.useState<string | null>(null);

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
        err instanceof PhasesApiError
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
        const body = await getPhases(wsId, { authToken: token });
        setPhases(Array.isArray(body.phases) ? body.phases : []);
        setCurrentPhaseId(body.current_phase_id ?? null);
        setView("loaded");
      } catch (err) {
        // AC-F1 4xx branch — render inline error + empty state.
        setPhases([]);
        setCurrentPhaseId(null);
        setView("error");
        surfaceError(err, workspacePhasesEndpoint(wsId));
      }
    },
    [surfaceError],
  );

  React.useEffect(() => {
    if (!authChecked || !authToken || !workspaceId) return;
    void refresh(workspaceId, authToken);
  }, [authChecked, authToken, workspaceId, refresh]);

  // ---- Create phase (workspace_admin path used by mock CTA) --------------
  const handleCreate = React.useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!authToken || !workspaceId) return;
      const name = draftName.trim();
      const conditions = draftConditions
        .split("\n")
        .map((s) => s.trim())
        .filter((s) => s.length > 0);
      if (!name || conditions.length === 0) {
        pushToast("error", "フェーズ名と Gate 条件を入力してください");
        return;
      }
      setCreating(true);
      try {
        await createPhase(
          workspaceId,
          { name, gate_conditions: conditions },
          { authToken },
        );
        pushToast("success", `フェーズ「${name}」を作成しました`);
        setCreateOpen(false);
        setDraftName("");
        setDraftConditions("");
        await refresh(workspaceId, authToken);
      } catch (err) {
        surfaceError(err, workspacePhasesEndpoint(workspaceId));
      } finally {
        setCreating(false);
      }
    },
    [
      authToken,
      workspaceId,
      draftName,
      draftConditions,
      pushToast,
      refresh,
      surfaceError,
    ],
  );

  // ---- Trigger gate (AC-F3) ----------------------------------------------
  const handleTriggerGate = React.useCallback(
    async (phaseId: string) => {
      if (!authToken || !workspaceId) return;
      setGateInFlight(phaseId);
      try {
        const body = await triggerPhaseGate(
          workspaceId,
          phaseId,
          {},
          { authToken },
        );
        // AC-F3: server returns `unlocked_phase_id` when all conditions evaluated true.
        pushToast(
          "success",
          `Gate を通過しました (次フェーズ: ${body.unlocked_phase_id})`,
        );
        await refresh(workspaceId, authToken);
      } catch (err) {
        surfaceError(
          err,
          workspacePhaseGateEndpoint(workspaceId, phaseId),
        );
      } finally {
        setGateInFlight(null);
      }
    },
    [authToken, workspaceId, pushToast, refresh, surfaceError],
  );

  // ---- Render branches ----------------------------------------------------

  // AC-F2: unauthenticated visitors never render workspace-scoped data.
  if (authChecked && !authToken) {
    return (
      <div
        data-screen-id="S-016"
        data-feature-id="F-008"
        data-task-ids="T-V3-C-37"
        data-entities="E-013,E-014"
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
      data-screen-id="S-016"
      data-feature-id="F-008"
      data-task-ids="T-V3-C-37"
      data-entities="E-013,E-014"
      data-phase="Phase 1"
      className="min-h-screen bg-slate-50 text-slate-900"
    >
      <main className="max-w-[1400px] mx-auto px-6 py-6">
        {/* Top action bar mirrors mock: title + subtitle + create CTA. */}
        <div className="flex items-end justify-between mb-6 gap-4">
          <div>
            <h1 className="text-2xl font-bold">フェーズ管理</h1>
            <p className="text-sm text-slate-600 mt-1">
              案件を時系列で区切り / Gate 条件を満たして次へ進める
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              data-testid="phases-refresh"
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
            <button
              type="button"
              data-testid="create-phase-open"
              onClick={() => setCreateOpen(true)}
              className="bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-9 px-4 rounded-md flex items-center gap-2"
              disabled={!authToken || !workspaceId}
            >
              <Plus className="w-4 h-4" />
              フェーズ追加
            </button>
          </div>
        </div>

        {/* Error banner (AC-F1 4xx / AC-F3 gate failures). */}
        {errorMessage ? (
          <div
            role="alert"
            data-testid="phases-error"
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
            data-testid="phases-missing-workspace"
            className="mb-4 rounded-md border border-amber-200 bg-amber-50 text-amber-700 text-sm px-4 py-3"
          >
            ワークスペースが選択されていません。サイドバーから案件を選択してください。
          </div>
        ) : null}

        {/* Phase Timeline (mock h2). */}
        <section
          data-testid="phase-timeline"
          className="bg-white border border-slate-200 rounded-lg p-5 mb-6"
        >
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-bold text-eb-500 flex items-center gap-2">
              <GitCommit className="w-4 h-4" />
              Phase Timeline
            </h2>
            <span className="text-xs text-slate-500">
              {view === "loading" ? "読み込み中…" : `${phases.length} phases`}
            </span>
          </div>

          {view === "loading" ? (
            <div
              role="status"
              data-testid="phases-loading"
              className="text-xs text-slate-500"
            >
              フェーズを読み込み中です…
            </div>
          ) : phases.length === 0 ? (
            <div
              role="status"
              data-testid="phases-empty"
              className="text-xs text-slate-500"
            >
              フェーズはまだ登録されていません。
            </div>
          ) : (
            <ol className="space-y-3" data-testid="phases-list">
              {phases.map((phase, idx) => {
                const tone = statusTone(phase.status);
                const isCurrent = currentPhaseId === phase.id;
                const progress =
                  typeof phase.progress === "number"
                    ? Math.max(0, Math.min(100, phase.progress))
                    : null;
                return (
                  <li
                    key={phase.id}
                    data-testid={`phase-row-${phase.id}`}
                    className={`grid grid-cols-[100px_1fr_120px] gap-3 items-center text-xs ${
                      isCurrent ? "font-semibold" : "text-slate-700"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="w-5 h-5 rounded-full bg-eb-500 text-white text-[9px] font-bold flex items-center justify-center font-mono">
                        {idx}
                      </span>
                      <span className="truncate">{phase.name}</span>
                    </div>
                    <div className="relative h-6 bg-slate-50 rounded">
                      {progress !== null ? (
                        <div
                          className="absolute left-0 top-0 h-full bg-eb-500 rounded flex items-center justify-end pr-2 text-white text-[10px] font-semibold"
                          style={{ width: `${progress}%` }}
                          aria-label={`${phase.name} progress ${progress}%`}
                        >
                          {progress > 0 ? `${progress}%` : ""}
                        </div>
                      ) : null}
                    </div>
                    <span
                      className={`text-[10px] inline-flex items-center justify-center px-2 py-1 rounded-full border ${tone.chip}`}
                    >
                      {phase.status}
                    </span>
                  </li>
                );
              })}
            </ol>
          )}
        </section>

        {/* Per-phase detail cards: gate conditions + Gate 通過 button. */}
        <div className="space-y-4" data-testid="phases-cards">
          {phases.map((phase) => {
            const tone = statusTone(phase.status);
            const isCurrent = currentPhaseId === phase.id;
            const conditions = phase.gate_conditions ?? [];
            const remaining = pendingCount(conditions);
            const gateDisabled =
              phase.status === "completed" ||
              phase.status === "locked" ||
              remaining > 0;
            return (
              <article
                key={phase.id}
                data-testid={`phase-card-${phase.id}`}
                className={`bg-white border rounded-lg p-5 ${
                  isCurrent
                    ? `border-eb-200 ring-2 ${tone.ring}`
                    : "border-slate-200"
                }`}
              >
                <header className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <Layers className="w-5 h-5 text-eb-500" aria-hidden />
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="text-lg font-bold">{phase.name}</h3>
                        <span
                          className={`text-[11px] px-2 py-0.5 rounded-full font-medium border ${tone.chip}`}
                        >
                          {phase.status}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 mt-0.5 font-mono">
                        {formatDateRange(phase.start_date, phase.end_date)}
                      </p>
                    </div>
                  </div>
                  {phase.status === "locked" ? (
                    <Lock className="w-5 h-5 text-slate-400" aria-hidden />
                  ) : (
                    <Unlock className="w-5 h-5 text-eb-500" aria-hidden />
                  )}
                </header>

                {conditions.length > 0 ? (
                  <div className="border-t border-slate-200 pt-3">
                    <div className="text-[11px] uppercase tracking-wider text-slate-500 font-bold mb-2">
                      Phase Gate (次フェーズに進む条件)
                    </div>
                    <ul
                      className="space-y-2"
                      data-testid={`phase-conditions-${phase.id}`}
                    >
                      {conditions.map((cond, idx) => (
                        <li
                          key={cond.id ?? `${phase.id}-cond-${idx}`}
                          className={`flex items-center gap-2 text-sm ${
                            cond.satisfied ? "text-slate-900" : "text-slate-500"
                          }`}
                        >
                          {cond.satisfied ? (
                            <CheckCircle2
                              className="w-4 h-4 text-emerald-600"
                              aria-hidden
                            />
                          ) : (
                            <Circle className="w-4 h-4" aria-hidden />
                          )}
                          <span>{cond.label}</span>
                        </li>
                      ))}
                    </ul>
                    <div className="flex items-center justify-end gap-2 mt-4">
                      <button
                        type="button"
                        data-testid={`phase-gate-trigger-${phase.id}`}
                        onClick={() => void handleTriggerGate(phase.id)}
                        disabled={
                          gateDisabled || gateInFlight === phase.id || !authToken
                        }
                        className={`${
                          gateDisabled
                            ? "bg-slate-100 text-slate-400 cursor-not-allowed"
                            : "bg-eb-500 hover:bg-eb-600 text-white"
                        } text-sm font-semibold h-9 px-4 rounded-md flex items-center gap-2`}
                      >
                        {gateDisabled ? (
                          <>
                            <Lock className="w-4 h-4" />
                            Gate 通過 ({remaining}/{conditions.length} 残)
                          </>
                        ) : (
                          <>
                            <Unlock className="w-4 h-4" />
                            Gate 通過
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      </main>

      {/* Create phase dialog (mock CTA: "フェーズ追加"). */}
      {createOpen ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="フェーズ追加"
          className="fixed inset-0 z-50 bg-slate-900/40 flex items-center justify-center px-4"
        >
          <form
            data-testid="create-phase-form"
            onSubmit={handleCreate}
            className="bg-white rounded-lg shadow-lg w-full max-w-md p-5 space-y-4"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold">フェーズを追加</h3>
              <button
                type="button"
                aria-label="閉じる"
                onClick={() => setCreateOpen(false)}
                className="text-slate-400 hover:text-slate-700"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <label className="block text-xs font-semibold text-slate-700">
              フェーズ名
              <input
                type="text"
                value={draftName}
                onChange={(e) => setDraftName(e.target.value)}
                required
                className="mt-1 block w-full rounded-md border border-slate-200 px-3 py-2 text-sm"
              />
            </label>

            <label className="block text-xs font-semibold text-slate-700">
              Gate 条件 (1 行 = 1 条件)
              <textarea
                value={draftConditions}
                onChange={(e) => setDraftConditions(e.target.value)}
                required
                rows={4}
                placeholder={"全 main task が done\n赤線抵触 = 0"}
                className="mt-1 block w-full rounded-md border border-slate-200 px-3 py-2 text-sm font-mono"
              />
            </label>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setCreateOpen(false)}
                className="text-xs text-slate-500 hover:text-slate-900 h-9 px-3"
              >
                キャンセル
              </button>
              <button
                type="submit"
                disabled={creating}
                className="bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-9 px-4 rounded-md disabled:opacity-60"
              >
                {creating ? "作成中…" : "追加"}
              </button>
            </div>
          </form>
        </div>
      ) : null}

      {/* Toasts */}
      <div className="fixed bottom-4 right-4 z-50 space-y-2" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            data-testid={`phases-toast-${t.kind}`}
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
