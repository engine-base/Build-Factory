"use client";

/**
 * S-049 案件セットアップ — Workspace Setup Wizard (Step 2 / 3) — T-V3-C-40 / F-027.
 *
 * @screen-id S-049
 * @feature-id F-027
 * @task-ids T-V3-C-40,T-V3-B-29
 * @entities E-041
 * @phase Phase 1
 *
 * Mock 逐語準拠:
 *   docs/mocks/2026-05-15_v3/onboarding/S-049-workspace-setup-wizard.html
 *     - h1                : "最初の案件を作成"   (screens.json[S-049].h1_text)
 *     - stepper           : 2/3 (welcome / project_setup / ai_intro)
 *     - 主要アクション    : POST /api/me/onboarding/advance (T-V3-B-29 実装済)
 *     - 状態              : loading / loaded / error    (screens.json[S-049].states)
 *
 * 3-tier AC mapping (逐語 — docs/audit/2026-05-16_v3/T-V3-C-40.md):
 *   structural.AC-S1  → <h1>最初の案件を作成</h1> rendered when view === "loaded".
 *   structural.AC-S2  → All icon glyphs use lucide-react (no emoji).
 *   functional.AC-F1  → Unauthenticated visitor: router.replace("/login") + no
 *                       workspace-scoped data rendered.
 *   functional.AC-F2  → While view === "loading": <SkeletonLoader role="status"
 *                       aria-live="polite"> → atomically replaced once loaded.
 *
 * Backend contracts (OpenAPI 2026-05-16_v3):
 *   GET  /api/me/onboarding        — get_me_onboarding
 *   POST /api/me/onboarding/advance — post_me_onboarding_advance
 *
 * Mock layout reference (docs/mocks/2026-05-15_v3/onboarding/S-049-*.html):
 *   - card: max-w-[640px] center, white card border slate-200 rounded-lg.
 *   - radio cards for AI 社員 (mary / preston / secretary, mary = default).
 *   - <details> 高度な設定 with 月間トークン上限 / 並列セッション上限.
 *   - footer: 戻る (S-048) ←→ 次へ (POST advance → S-050).
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  AlertCircle,
  Loader2,
  RotateCcw,
  Sliders,
} from "lucide-react";

import {
  LOGIN_REDIRECT_PATH,
  OnboardingApiError,
  type WorkspaceSetupWizardPayload,
} from "@/api/onboarding";
import { useWorkspaceSetupWizard } from "@/hooks/use-workspace-setup-wizard";

// ---------------------------------------------------------------------------
// Mock-derived literals (逐語コピー — keep in sync with screens.json[S-049]).
// ---------------------------------------------------------------------------
const S049_H1_TEXT = "最初の案件を作成";
const S049_STEP_LABEL = "Step 2 / 3";
const S049_SUBTITLE = "案件の基本情報を入力してください";

const PROJECT_KIND_OPTIONS: WorkspaceSetupWizardPayload["project_kind"][] = [
  "受託",
  "内製",
  "OSS",
];

const DURATION_OPTIONS: string[] = ["1 ヶ月", "3 ヶ月", "6 ヶ月", "未定"];

interface AiEmployeeOption {
  id: WorkspaceSetupWizardPayload["ai_employee"];
  initials: string;
  name: string;
  role: string;
  swatch: string; // tailwind background class
}

const AI_EMPLOYEE_OPTIONS: AiEmployeeOption[] = [
  {
    id: "mary",
    initials: "MR",
    name: "mary",
    role: "BA / 推奨",
    swatch: "bg-emerald-500",
  },
  {
    id: "preston",
    initials: "PS",
    name: "preston",
    role: "PM",
    swatch: "bg-amber-500",
  },
  {
    id: "secretary",
    initials: "SC",
    name: "secretary",
    role: "PM 代理",
    swatch: "bg-purple-500",
  },
];

const DEFAULT_TOKEN_CAP = 10_000_000;
const DEFAULT_PARALLEL_CAP = 5;

// ---------------------------------------------------------------------------
// Helpers — non-technical, endpoint-tagged user messages (AC-F1 family).
// ---------------------------------------------------------------------------

function userMessageFromError(err: OnboardingApiError | null): string | null {
  if (!err) return null;
  return err.toUserMessage();
}

// ---------------------------------------------------------------------------
// Skeleton loader (AC-F2 — STATE-DRIVEN: loading).
// ---------------------------------------------------------------------------

function SkeletonLoader() {
  return (
    <div
      data-testid="workspace-setup-skeleton"
      role="status"
      aria-live="polite"
      aria-busy="true"
      aria-label="読み込み中"
      className="max-w-[640px] w-full animate-pulse space-y-6"
    >
      <div className="flex items-center gap-2 mb-8 max-w-xs mx-auto">
        <div className="flex-1 h-1.5 bg-slate-200 rounded-full" />
        <div className="flex-1 h-1.5 bg-slate-200 rounded-full" />
        <div className="flex-1 h-1.5 bg-slate-200 rounded-full" />
      </div>
      <div className="text-center space-y-2">
        <div className="h-3 w-20 bg-slate-200 rounded mx-auto" />
        <div className="h-7 w-56 bg-slate-200 rounded mx-auto" />
        <div className="h-4 w-72 bg-slate-200 rounded mx-auto" />
      </div>
      <div className="bg-white border border-slate-200 rounded-lg p-6 space-y-4">
        <div className="h-10 bg-slate-100 rounded" />
        <div className="grid grid-cols-2 gap-3">
          <div className="h-10 bg-slate-100 rounded" />
          <div className="h-10 bg-slate-100 rounded" />
        </div>
        <div className="grid grid-cols-3 gap-2">
          <div className="h-20 bg-slate-100 rounded" />
          <div className="h-20 bg-slate-100 rounded" />
          <div className="h-20 bg-slate-100 rounded" />
        </div>
      </div>
      <span className="sr-only">案件セットアップを読み込んでいます。</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stepper.
// ---------------------------------------------------------------------------

function Stepper({ current }: { current: number }) {
  return (
    <div className="flex items-center gap-2 mb-8 max-w-xs mx-auto">
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          aria-hidden="true"
          className={
            "flex-1 h-1.5 rounded-full " +
            (i <= current ? "bg-eb-500" : "bg-slate-200")
          }
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page.
// ---------------------------------------------------------------------------

export default function WorkspaceSetupWizardPage() {
  const router = useRouter();
  const {
    view,
    error,
    requiresAuth,
    isAdvancing,
    advanceError,
    submit,
    refetch,
  } = useWorkspaceSetupWizard();

  // AC-F1 — redirect unauthenticated visitors to /login.
  React.useEffect(() => {
    if (requiresAuth) {
      router.replace(LOGIN_REDIRECT_PATH);
    }
  }, [requiresAuth, router]);

  // -------------------------------------------------------------------------
  // Form state.
  // -------------------------------------------------------------------------
  const [workspaceName, setWorkspaceName] = React.useState<string>("");
  const [projectKind, setProjectKind] =
    React.useState<WorkspaceSetupWizardPayload["project_kind"]>("受託");
  const [duration, setDuration] = React.useState<string>("3 ヶ月");
  const [aiEmployee, setAiEmployee] =
    React.useState<WorkspaceSetupWizardPayload["ai_employee"]>("mary");
  const [tokenCap, setTokenCap] = React.useState<number>(DEFAULT_TOKEN_CAP);
  const [parallelCap, setParallelCap] =
    React.useState<number>(DEFAULT_PARALLEL_CAP);

  const [formError, setFormError] = React.useState<string | null>(null);

  const onSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setFormError(null);
    const trimmed = workspaceName.trim();
    if (!trimmed) {
      setFormError("案件名を入力してください");
      return;
    }
    const payload: WorkspaceSetupWizardPayload = {
      workspace_name: trimmed,
      project_kind: projectKind,
      duration,
      ai_employee: aiEmployee,
      monthly_token_cap: tokenCap,
      parallel_session_cap: parallelCap,
    };
    try {
      await submit(payload);
      router.push("/onboarding/ai-intro"); // S-050 next.
    } catch {
      // advanceError already set by the hook; UI updates inline.
    }
  };

  // -------------------------------------------------------------------------
  // AC-F1 (UNWANTED) — while we know auth is required, render nothing
  // workspace-scoped. Skeleton remains visible so the redirect cannot flash
  // any sensitive content.
  // -------------------------------------------------------------------------
  if (requiresAuth) {
    return (
      <main
        data-screen-id="S-049"
        data-feature-id="F-027"
        data-screen-name="workspace_setup_wizard"
        className="min-h-screen flex items-center justify-center px-6 py-8 bg-slate-50"
      >
        <SkeletonLoader />
      </main>
    );
  }

  // -------------------------------------------------------------------------
  // AC-F2 (STATE-DRIVEN: loading) — render skeleton until data arrives.
  // -------------------------------------------------------------------------
  if (view === "loading") {
    return (
      <main
        data-screen-id="S-049"
        data-feature-id="F-027"
        data-screen-name="workspace_setup_wizard"
        className="min-h-screen flex items-center justify-center px-6 py-8 bg-slate-50"
      >
        <SkeletonLoader />
      </main>
    );
  }

  // -------------------------------------------------------------------------
  // Error pane.
  // -------------------------------------------------------------------------
  if (view === "error") {
    const msg = userMessageFromError(error) ?? "読み込みに失敗しました";
    return (
      <main
        data-screen-id="S-049"
        data-feature-id="F-027"
        data-screen-name="workspace_setup_wizard"
        className="min-h-screen flex items-center justify-center px-6 py-8 bg-slate-50"
      >
        <div className="max-w-[640px] w-full">
          <Stepper current={1} />
          <div className="text-center mb-6">
            <div className="text-[11px] uppercase tracking-wider text-slate-500 font-bold">
              {S049_STEP_LABEL}
            </div>
            <h1 className="text-2xl font-bold mt-1">{S049_H1_TEXT}</h1>
          </div>
          <div
            role="alert"
            data-testid="workspace-setup-error"
            className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-md px-4 py-3 flex items-start gap-2"
          >
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" aria-hidden />
            <div className="flex-1">{msg}</div>
            <button
              type="button"
              onClick={refetch}
              data-testid="workspace-setup-retry"
              className="inline-flex items-center gap-1 text-xs font-semibold text-red-700 hover:text-red-900"
            >
              <RotateCcw className="w-3.5 h-3.5" aria-hidden />
              再試行
            </button>
          </div>
        </div>
      </main>
    );
  }

  // -------------------------------------------------------------------------
  // Loaded — main wizard form.
  // -------------------------------------------------------------------------
  const advanceMsg = userMessageFromError(advanceError);

  return (
    <main
      data-screen-id="S-049"
      data-feature-id="F-027"
      data-screen-name="workspace_setup_wizard"
      className="min-h-screen flex items-center justify-center px-6 py-8 bg-slate-50"
    >
      <div className="max-w-[640px] w-full">
        <Stepper current={1} />
        <div className="text-center mb-6">
          <div className="text-[11px] uppercase tracking-wider text-slate-500 font-bold">
            {S049_STEP_LABEL}
          </div>
          <h1 className="text-2xl font-bold mt-1">{S049_H1_TEXT}</h1>
          <p className="text-sm text-slate-600 mt-2">{S049_SUBTITLE}</p>
        </div>

        <form
          onSubmit={onSubmit}
          aria-label="workspace-setup-wizard"
          className="bg-white border border-slate-200 rounded-lg p-6 space-y-4"
        >
          {/* 案件名 */}
          <div className="space-y-1.5">
            <label
              htmlFor="workspace-name"
              className="text-sm font-medium block"
            >
              案件名 <span className="text-red-600">*</span>
            </label>
            <input
              id="workspace-name"
              data-testid="workspace-name-input"
              type="text"
              placeholder="例: 受託 EC 構築 #4"
              value={workspaceName}
              onChange={(e) => setWorkspaceName(e.target.value)}
              required
              maxLength={128}
              disabled={isAdvancing}
              className="border border-slate-200 bg-white text-sm h-10 px-3 rounded-md w-full"
            />
          </div>

          {/* 案件種別 / 想定期間 */}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label
                htmlFor="project-kind"
                className="text-sm font-medium block"
              >
                案件種別
              </label>
              <select
                id="project-kind"
                data-testid="project-kind-select"
                value={projectKind}
                onChange={(e) =>
                  setProjectKind(
                    e.target
                      .value as WorkspaceSetupWizardPayload["project_kind"],
                  )
                }
                disabled={isAdvancing}
                className="border border-slate-200 bg-white text-sm h-10 px-3 rounded-md w-full"
              >
                {PROJECT_KIND_OPTIONS.map((kind) => (
                  <option key={kind} value={kind}>
                    {kind}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1.5">
              <label htmlFor="duration" className="text-sm font-medium block">
                想定期間
              </label>
              <select
                id="duration"
                data-testid="duration-select"
                value={duration}
                onChange={(e) => setDuration(e.target.value)}
                disabled={isAdvancing}
                className="border border-slate-200 bg-white text-sm h-10 px-3 rounded-md w-full"
              >
                {DURATION_OPTIONS.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* AI 社員 selector */}
          <div className="space-y-1.5">
            <span className="text-sm font-medium block">
              ヒアリング 開始時の AI 社員
            </span>
            <div
              role="radiogroup"
              aria-label="ヒアリング 開始時の AI 社員"
              data-testid="ai-employee-radiogroup"
              className="grid grid-cols-3 gap-2"
            >
              {AI_EMPLOYEE_OPTIONS.map((opt) => {
                const selected = aiEmployee === opt.id;
                return (
                  <label
                    key={opt.id}
                    data-testid={`ai-employee-${opt.id}`}
                    className={
                      "rounded-md p-3 text-center cursor-pointer transition-colors " +
                      (selected
                        ? "border border-eb-500 bg-eb-50 ring-2 ring-eb-100"
                        : "border border-slate-200 hover:border-eb-300")
                    }
                  >
                    <input
                      type="radio"
                      name="ai-employee"
                      value={opt.id}
                      checked={selected}
                      onChange={() => setAiEmployee(opt.id)}
                      disabled={isAdvancing}
                      className="sr-only"
                    />
                    <div
                      className={
                        "w-8 h-8 rounded-full text-white text-xs font-bold flex items-center justify-center mx-auto mb-1 mono " +
                        opt.swatch
                      }
                    >
                      {opt.initials}
                    </div>
                    <div className="text-xs font-bold">{opt.name}</div>
                    <div className="text-[10px] text-slate-500">{opt.role}</div>
                  </label>
                );
              })}
            </div>
          </div>

          {/* 高度な設定 (任意) */}
          <details className="border border-slate-200 rounded-md">
            <summary
              data-testid="advanced-toggle"
              className="cursor-pointer px-3 py-2 text-sm font-medium flex items-center gap-2"
            >
              <Sliders className="w-4 h-4 text-slate-500" aria-hidden />
              高度な設定 (任意)
            </summary>
            <div className="p-4 border-t border-slate-200 space-y-3">
              <div className="space-y-1.5">
                <label
                  htmlFor="token-cap"
                  className="text-sm font-medium block"
                >
                  月間トークン上限
                </label>
                <input
                  id="token-cap"
                  data-testid="token-cap-input"
                  type="number"
                  min={0}
                  value={tokenCap}
                  onChange={(e) =>
                    setTokenCap(Number.parseInt(e.target.value, 10) || 0)
                  }
                  disabled={isAdvancing}
                  className="border border-slate-200 text-sm h-9 px-3 rounded-md w-full mono"
                />
              </div>
              <div className="space-y-1.5">
                <label
                  htmlFor="parallel-cap"
                  className="text-sm font-medium block"
                >
                  並列セッション上限
                </label>
                <input
                  id="parallel-cap"
                  data-testid="parallel-cap-input"
                  type="number"
                  min={1}
                  max={20}
                  value={parallelCap}
                  onChange={(e) =>
                    setParallelCap(Number.parseInt(e.target.value, 10) || 1)
                  }
                  disabled={isAdvancing}
                  className="border border-slate-200 text-sm h-9 px-3 rounded-md w-32 mono"
                />
              </div>
            </div>
          </details>

          {/* Form-level error (client-side) */}
          {formError ? (
            <div
              role="alert"
              data-testid="workspace-setup-form-error"
              className="bg-amber-50 border border-amber-200 text-amber-800 text-xs px-3 py-2 rounded-md flex items-center gap-2"
            >
              <AlertCircle className="w-3.5 h-3.5 shrink-0" aria-hidden />
              <span>{formError}</span>
            </div>
          ) : null}

          {/* Advance API error (server) */}
          {advanceMsg ? (
            <div
              role="alert"
              data-testid="workspace-setup-advance-error"
              className="bg-red-50 border border-red-200 text-red-700 text-xs px-3 py-2 rounded-md flex items-center gap-2"
            >
              <AlertCircle className="w-3.5 h-3.5 shrink-0" aria-hidden />
              <span>{advanceMsg}</span>
            </div>
          ) : null}

          {/* Footer */}
          <div className="pt-2 flex items-center justify-between">
            <button
              type="button"
              data-testid="workspace-setup-back"
              onClick={() => router.push("/onboarding/welcome")}
              disabled={isAdvancing}
              className="text-sm text-slate-500 hover:text-slate-900 h-10 px-5 flex items-center gap-1"
            >
              <ArrowLeft className="w-4 h-4" aria-hidden />
              戻る
            </button>
            <button
              type="submit"
              data-testid="workspace-setup-next"
              disabled={isAdvancing}
              className="bg-eb-500 hover:bg-eb-600 text-white text-sm font-semibold h-10 px-6 rounded-md flex items-center gap-2 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {isAdvancing ? (
                <Loader2 className="w-4 h-4 animate-spin" aria-hidden />
              ) : null}
              <span>次へ</span>
              {!isAdvancing ? (
                <ArrowRight className="w-4 h-4" aria-hidden />
              ) : null}
            </button>
          </div>
        </form>
      </div>
    </main>
  );
}
